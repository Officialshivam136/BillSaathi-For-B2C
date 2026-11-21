import os
import sqlite3
import tempfile
import time
import unittest
from decimal import Decimal as D

import backups
import db
from test_invoices import Base, item


class TestBackups(Base):
    def setUp(self):
        super().setUp()
        self.bdir = os.path.join(self.tmp.name, "backups")
        self.extra = os.path.join(self.tmp.name, "usb")
        os.makedirs(self.extra)

    def test_check_backup(self):
        p = db.backup_now(self.conn, self.bdir)
        info = backups.check_backup(p)
        self.assertTrue(info["ok"])
        self.assertEqual(info["customers"], 2)
        junk = os.path.join(self.bdir, "billsaathi-junk.db")
        with open(junk, "wb") as f:
            f.write(b"this is not a database" * 50)
        self.assertFalse(backups.check_backup(junk)["ok"])
        other = os.path.join(self.bdir, "billsaathi-other.db")
        sqlite3.connect(other).execute("CREATE TABLE x (a)").connection.close()
        self.assertEqual(backups.check_backup(other)["message"], "This is not a BillSaathi database")
        self.assertFalse(backups.check_backup(os.path.join(self.bdir, "missing.db"))["ok"])

    def test_restore_brings_back_old_state_and_keeps_a_safety_copy(self):
        db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        snap = db.backup_now(self.conn, self.bdir)
        db.create_invoice(self.conn, self.local, "2026-11-02", [item()])
        db.add_customer(self.conn, "Added after backup")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 2)
        safety = backups.restore(self.conn, snap, self.bdir)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 1)
        self.assertEqual([c["name"] for c in db.search_customers(self.conn, "Added")], [])
        # nothing was lost: the state just before the restore is in the safety copy
        self.assertIn("before-restore", os.path.basename(safety))
        info = backups.check_backup(safety)
        self.assertEqual((info["ok"], info["invoices"]), (True, 2))
        # and the app keeps numbering correctly from the restored state
        nxt = db.get_invoice(self.conn, db.create_invoice(self.conn, self.local, "2026-11-03", [item()]))
        self.assertEqual(nxt["number"], "BS/2026-27/0002")

    def test_restore_upgrades_an_old_backup_and_rejects_bad_files(self):
        old = os.path.join(self.bdir, "billsaathi-2026-01-01.db")
        os.makedirs(self.bdir, exist_ok=True)
        raw = sqlite3.connect(old)
        raw.executescript("BEGIN;" + db.SCHEMA_V1 + "PRAGMA user_version = 1;COMMIT;")
        raw.execute("INSERT INTO customer (name, created_at) VALUES ('Old customer', 'x')")
        raw.commit()
        raw.close()
        backups.restore(self.conn, old, self.bdir)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))
        self.assertEqual([c["name"] for c in db.search_customers(self.conn)], ["Old customer"])
        junk = os.path.join(self.bdir, "billsaathi-bad.db")
        with open(junk, "wb") as f:
            f.write(b"x" * 500)
        before = len(db.search_customers(self.conn))
        with self.assertRaises(ValueError):
            backups.restore(self.conn, junk, self.bdir)
        self.assertEqual(len(db.search_customers(self.conn)), before)  # a bad file changes nothing

    def test_list_and_prune_only_touch_daily_backups(self):
        os.makedirs(self.bdir)
        for d in range(1, 8):
            open(os.path.join(self.bdir, f"billsaathi-2026-11-0{d}.db"), "wb").close()
        manual = os.path.join(self.bdir, "billsaathi-2026-11-01-101010.db")
        safety = os.path.join(self.bdir, "billsaathi-before-restore-2026-11-01-101010.db")
        for p in (manual, safety, os.path.join(self.bdir, "notes.txt")):
            open(p, "wb").close()
        rows = backups.list_backups([("here", self.bdir)])
        self.assertEqual(len(rows), 9)  # notes.txt ignored
        self.assertEqual({r["kind"] for r in rows}, {"Daily", "Manual", "Before restore"})
        gone = backups.prune(self.bdir, keep=3)
        self.assertEqual(gone, [f"billsaathi-2026-11-0{d}.db" for d in (1, 2, 3, 4)])
        left = {r["name"] for r in backups.list_backups([("here", self.bdir)])}
        self.assertTrue({os.path.basename(manual), os.path.basename(safety)} <= left)  # never deleted

    def test_second_folder_sync(self):
        self.assertIsNone(backups.sync_extra(self.conn, self.bdir))  # nothing configured
        db.backup_if_due(self.conn, self.bdir, "2026-11-20")
        db.backup_if_due(self.conn, self.bdir, "2026-11-21")
        self.assertEqual(backups.set_extra_dir(self.conn, self.extra), self.extra)
        s = backups.sync_extra(self.conn, self.bdir)
        self.assertIn("OK", s)
        self.assertIn("2 file(s) copied", s)
        self.assertEqual(sorted(os.listdir(self.extra)), ["billsaathi-2026-11-20.db", "billsaathi-2026-11-21.db"])
        self.assertIn("0 file(s) copied", backups.sync_extra(self.conn, self.bdir))  # nothing new the second time
        self.assertEqual(db.get_setting(self.conn, "extra_backup_status"), backups.sync_extra(self.conn, self.bdir))
        self.assertTrue(backups.check_backup(os.path.join(self.extra, "billsaathi-2026-11-21.db"))["ok"])

    def test_second_folder_problems_are_reported_not_hidden(self):
        db.backup_if_due(self.conn, self.bdir, "2026-11-21")
        backups.set_extra_dir(self.conn, self.extra)
        os.rmdir(self.extra)  # the USB drive was pulled out
        s = backups.sync_extra(self.conn, self.bdir)
        self.assertIn("FAILED", s)
        self.assertIn("plugged in", s)
        with self.assertRaises(ValueError):
            backups.set_extra_dir(self.conn, os.path.join(self.tmp.name, "nope"))
        self.assertEqual(backups.set_extra_dir(self.conn, ""), "")  # clearing turns it off
        self.assertIsNone(backups.sync_extra(self.conn, self.bdir))


class TestPasscodeAuditStatementEtc(Base):
    def test_change_passcode(self):
        db.set_passcode(self.conn, "1234")
        secret = db.get_secret(self.conn)
        for old, new in (("wrong", "5678"), ("1234", "1234"), ("1234", "12")):
            with self.assertRaises(ValueError):
                db.change_passcode(self.conn, old, new)
        db.change_passcode(self.conn, "1234", "5678")
        self.assertTrue(db.check_passcode(self.conn, "5678"))
        self.assertFalse(db.check_passcode(self.conn, "1234"))
        self.assertNotEqual(db.get_secret(self.conn), secret)  # old sessions stop working
        self.assertEqual(db.list_audit(self.conn)[0]["action"], "passcode.change")

    def test_audit_filter_and_limit(self):
        for i in range(5):
            db.audit(self.conn, "Owner", "invoice.edit", "invoice", i, f"detail {i}")
        db.audit(self.conn, "Sunita", "payment.add", "payment", 1, "x" * 900)
        self.assertEqual(len(db.list_audit(self.conn, entity="invoice")), 5)
        self.assertEqual(len(db.list_audit(self.conn, q="Sunita")), 1)
        self.assertEqual(len(db.list_audit(self.conn, limit=2)), 2)
        self.assertEqual(len(db.list_audit(self.conn, q="x")[0]["detail"]), 500)  # long details are cut

    def test_edit_invoice(self):
        inv = db.create_invoice(self.conn, self.local, "2026-11-01", [item()], by="Owner")
        number = db.get_invoice(self.conn, inv)["number"]
        db.update_invoice(self.conn, inv, self.far, "2026-11-03", [item(qty="4", rate="500", gst_rate="12")], by="Owner")
        v = db.get_invoice(self.conn, inv)
        self.assertEqual((v["number"], v["customer_name"], v["date"], v["due_date"]), (number, "रमेश", "2026-11-03", "2026-11-18"))
        self.assertEqual((v["taxable"], v["igst"], v["total"], len(v["items"])), (D("2000.00"), D("240.00"), D("2240.00"), 1))
        self.assertIn("1417.50 -> 2240.00", db.list_audit(self.conn)[0]["detail"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice_item").fetchone()[0], 1)  # old lines replaced, not duplicated
        nxt = db.get_invoice(self.conn, db.create_invoice(self.conn, self.local, "2026-11-04", [item()]))
        self.assertEqual(nxt["number"], "BS/2026-27/0002")  # numbering unaffected

    def test_edit_invoice_rules(self):
        inv = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        with self.assertRaises(ValueError):  # a different financial year would break the number
            db.update_invoice(self.conn, inv, self.local, "2027-04-01", [item()])
        with self.assertRaises(ValueError):
            db.update_invoice(self.conn, inv, self.local, "2026-11-01", [])
        db.add_payment(self.conn, inv, "2026-11-02", "10", "cash")
        with self.assertRaises(ValueError) as cm:
            db.update_invoice(self.conn, inv, self.local, "2026-11-01", [item()])
        self.assertIn("credit note", str(cm.exception))
        x = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.cancel_invoice(self.conn, x, "dup")
        with self.assertRaises(ValueError):
            db.update_invoice(self.conn, x, self.local, "2026-11-01", [item()])
        y = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        iid = db.get_invoice(self.conn, y)["items"][0]["id"]
        db.create_credit_note(self.conn, y, "2026-11-02", {iid: "1"}, "r")
        with self.assertRaises(ValueError):
            db.update_invoice(self.conn, y, self.local, "2026-11-01", [item()])
        self.assertEqual(db.get_invoice(self.conn, inv)["total"], D("1417.50"))  # failed edits changed nothing

    def test_last_items_for_prefill(self):
        self.assertEqual(db.last_invoice_items(self.conn, self.local), [])
        db.create_invoice(self.conn, self.local, "2026-11-01", [item(desc="Old")])
        db.create_invoice(self.conn, self.local, "2026-11-05", [item(desc="Barfi", qty="2.5", rate="450.00", gst_rate="5", hsn="1704"),
                                                              item(desc="Peda", qty="1", rate="100", gst_rate="18")])
        x = db.create_invoice(self.conn, self.local, "2026-11-09", [item(desc="Cancelled one")])
        db.cancel_invoice(self.conn, x, "oops")
        items = db.last_invoice_items(self.conn, self.local)
        self.assertEqual([(i["description"], i["qty"], i["rate"], i["gst_rate"], i["hsn"]) for i in items],
                         [("Barfi", "2.5", "450.00", "5", "1704"), ("Peda", "1", "100.00", "18", "")])

    def test_customer_statement(self):
        a = db.create_invoice(self.conn, self.local, "2026-10-10", [item()])  # 1417.50
        b = db.create_invoice(self.conn, self.local, "2026-11-02", [item(rate="100")])  # 315.00
        db.add_payment(self.conn, a, "2026-10-20", "400", "cash")
        ia = db.get_invoice(self.conn, a)["items"][0]["id"]
        db.create_credit_note(self.conn, a, "2026-11-05", {ia: "1"}, "Returned")  # 472.50
        db.add_payment(self.conn, b, "2026-11-06", "315", "upi")
        db.add_payment(self.conn, a, "2026-11-07", "545", "upi")  # a is now fully paid: 1417.50-472.50 = 945 = 400+545
        x = db.create_invoice(self.conn, self.local, "2026-11-03", [item()])
        db.cancel_invoice(self.conn, x, "dup")
        other = db.create_invoice(self.conn, self.far, "2026-11-03", [item()])  # someone else's invoice
        st = db.customer_statement(self.conn, self.local)
        self.assertEqual(st["opening"], D("0.00"))
        self.assertEqual([r["kind"] for r in st["rows"]], ["Invoice", "Payment", "Invoice", "Credit note", "Payment", "Payment"])
        self.assertEqual(st["rows"][-1]["balance"], st["closing"])
        self.assertEqual(st["closing"], D("0.00"))  # fully settled
        self.assertEqual((st["debit"], st["credit"]), (D("1732.50"), D("1732.50")))
        # opening balance when starting mid-way
        st2 = db.customer_statement(self.conn, self.local, start="2026-11-01")
        self.assertEqual(st2["opening"], D("1017.50"))  # 1417.50 invoiced - 400 paid before November
        self.assertEqual(st2["closing"], D("0.00"))
        self.assertEqual(len(st2["rows"]), 4)
        self.assertIsNone(db.customer_statement(self.conn, 9999))
        self.assertNotEqual(other, a)

    def test_refund_shows_on_statement(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.add_payment(self.conn, a, "2026-11-02", "1417.50", "upi")
        ia = db.get_invoice(self.conn, a)["items"][0]["id"]
        db.create_credit_note(self.conn, a, "2026-11-03", {ia: "3"}, "All returned")
        self.assertEqual(db.customer_statement(self.conn, self.local)["closing"], D("-1417.50"))  # we owe them
        db.add_refund(self.conn, a, "2026-11-04", "1417.50", "cash")
        st = db.customer_statement(self.conn, self.local)
        self.assertEqual((st["rows"][-1]["kind"], st["closing"]), ("Refund", D("0.00")))


class TestCompositionExportsAndRcm(Base):
    def test_composition_bill_of_supply_has_no_tax(self):
        db.save_business(self.conn, "Tiny Shop", "Uttar Pradesh", "09ABCDE1234F1Z5", scheme="composition")
        inv = db.get_invoice(self.conn, db.create_invoice(self.conn, self.local, "2026-11-01", [item(gst_rate="18")]))
        self.assertEqual((inv["taxable"], inv["cgst"], inv["sgst"], inv["igst"], inv["total"]),
                         (D("1350.00"), D("0.00"), D("0.00"), D("0.00"), D("1350.00")))
        self.assertEqual(inv["items"][0]["gst_rate"], D("0"))
        with self.assertRaises(ValueError):  # no inter-state supply, no exports
            db.create_invoice(self.conn, self.far, "2026-11-01", [item()])
        with self.assertRaises(ValueError):
            db.create_invoice(self.conn, self.local, "2026-11-01", [item()], supply_type="export_igst")
        with self.assertRaises(ValueError):  # composition needs a GSTIN
            db.save_business(self.conn, "Tiny Shop", "Uttar Pradesh", "", scheme="composition")
        with self.assertRaises(ValueError):
            db.save_business(self.conn, "Tiny Shop", "Uttar Pradesh", "09ABCDE1234F1Z5", scheme="other")

    def test_export_under_lut_is_zero_rated_and_export_with_igst_charges_igst(self):
        abroad = db.add_customer(self.conn, "Dubai Sweets", state="Outside India")
        lut = db.get_invoice(self.conn, db.create_invoice(self.conn, abroad, "2026-11-01", [item(gst_rate="5")], supply_type="export_lut"))
        self.assertEqual((lut["igst"], lut["cgst"], lut["total"], lut["is_interstate"], lut["supply_type"]),
                         (D("0.00"), D("0.00"), D("1350.00"), 1, "export_lut"))
        paid = db.get_invoice(self.conn, db.create_invoice(self.conn, abroad, "2026-11-01", [item(gst_rate="5")], supply_type="export_igst"))
        self.assertEqual((paid["igst"], paid["total"]), (D("67.50"), D("1417.50")))
        # even a customer in the same state is treated as inter-state for an export
        same = db.get_invoice(self.conn, db.create_invoice(self.conn, self.local, "2026-11-01", [item()], supply_type="export_igst"))
        self.assertEqual((same["cgst"], same["igst"]), (D("0.00"), D("67.50")))
        with self.assertRaises(ValueError):
            db.create_invoice(self.conn, abroad, "2026-11-01", [item()], supply_type="bogus")
        rows, tot = db.gst_liability(self.conn, "2026-11")
        self.assertEqual(tot["igst"], D("135.00"))  # LUT export adds nothing

    def test_reverse_charge_purchase(self):
        pid = db.add_purchase(self.conn, "Local Transporter", "", "", "GTA-1", "2026-11-05", "10000", category="Transport",
                              rcm=True, rcm_rate="5", rcm_inter=False)
        p = db.get_purchase(self.conn, pid)
        self.assertEqual((p["taxable"], p["cgst"], p["sgst"], p["igst"], p["total"], p["rcm"]),
                         (D("10000.00"), D("250.00"), D("250.00"), D("0.00"), D("10000.00"), 1))  # vendor is paid 10,000, not 10,500
        db.add_purchase(self.conn, "Out-of-state Advocate", "", "", "ADV-1", "2026-11-06", "1000", cgst="99", rcm=True, rcm_rate="18", rcm_inter=True)
        rows, tot = db.rcm_liability(self.conn, "2026-11")
        self.assertEqual([(r["rate"], r["tax"]) for r in rows], [(D("5"), D("500.00")), (D("18"), D("180.00"))])  # typed tax is ignored
        self.assertEqual((tot["cgst"], tot["sgst"], tot["igst"], tot["tax"]), (D("250.00"), D("250.00"), D("180.00"), D("680.00")))
        self.assertEqual(db.rcm_liability(self.conn, "2026-12")[1]["tax"], D("0.00"))
        db.add_purchase(self.conn, "Normal Vendor", "09ABCDE1234F1Z5", "", "N-1", "2026-11-07", "1000", "25", "25")  # not reverse charge
        self.assertEqual(db.rcm_liability(self.conn, "2026-11")[1]["tax"], D("680.00"))
        for bad in ({"rcm_rate": ""}, {"rcm_rate": "0"}, {"rcm_rate": "7"}):
            with self.assertRaises(ValueError, msg=bad):
                db.add_purchase(self.conn, "X", "", "", "B", "2026-11-05", "100", rcm=True, **bad)


class TestRendering(Base):
    def render(self, inv_id):
        import templates as t
        t._ctx.role, t._ctx.user, t._ctx.path, t._ctx.lang = "owner", "Owner", "/", "en"
        return t.invoice_view_page(db.get_invoice(self.conn, inv_id, "2026-11-21"), db.get_business(self.conn), today="2026-11-21")

    def test_document_titles_and_notes(self):
        db.save_business(self.conn, "Sweet House", "Uttar Pradesh", "09ABCDE1234F1Z5", upi_id="shop@upi")  # registered: TAX INVOICE
        regular = self.render(db.create_invoice(self.conn, self.local, "2026-11-01", [item()]))
        self.assertIn("TAX INVOICE", regular)
        self.assertIn("CGST", regular)
        self.assertIn("<!--noxl-->", regular)
        self.assertIn("Edit invoice", regular)  # nothing depends on it yet
        abroad = db.add_customer(self.conn, "Dubai Sweets", state="Outside India")
        lut = self.render(db.create_invoice(self.conn, abroad, "2026-11-01", [item()], supply_type="export_lut"))
        self.assertIn("EXPORT INVOICE", lut)
        self.assertIn("without payment of integrated tax", lut)
        paid = self.render(db.create_invoice(self.conn, abroad, "2026-11-01", [item()], supply_type="export_igst"))
        self.assertIn("on payment of integrated tax", paid)
        db.save_business(self.conn, "Tiny Shop", "Uttar Pradesh", "09ABCDE1234F1Z5", scheme="composition")
        comp = self.render(db.create_invoice(self.conn, self.local, "2026-11-02", [item(gst_rate="18")]))
        self.assertIn("BILL OF SUPPLY", comp)
        self.assertIn("not eligible to collect tax", comp)
        self.assertNotIn("CGST", comp)
        self.assertNotIn("IGST", comp)
        self.assertNotIn("TAX INVOICE", comp)

    def test_edit_button_disappears_once_money_is_recorded(self):
        inv = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.add_payment(self.conn, inv, "2026-11-02", "10", "cash")
        self.assertNotIn("Edit invoice", self.render(inv))

    def test_rcm_in_exports_and_tally_balances(self):
        import csv
        import io
        import xml.etree.ElementTree as ET
        import exports
        import tally
        db.add_purchase(self.conn, "Local Transporter", "", "", "GTA-1", "2026-11-05", "10000", category="Transport", rcm=True, rcm_rate="5")
        db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        rows = list(csv.reader(io.StringIO(exports.gst_liability(self.conn, "2026-11").decode("utf-8-sig"))))
        flat = [r[0] if r else "" for r in rows]  # the blank spacer row is an empty list
        self.assertIn("Reverse charge on purchases", flat)
        rcm_total = next(r for r in rows if r and r[0] == "RCM TOTAL")
        self.assertEqual(rcm_total[5], "500.00")
        self.assertEqual(rows[flat.index("TOTAL")][5], "67.50")  # output tax is not mixed up with it
        pr = list(csv.reader(io.StringIO(exports.purchase_register(self.conn, "2026-11").decode("utf-8-sig"))))
        self.assertEqual((pr[0][-1], pr[1][-1], pr[1][9]), ("Reverse charge", "Yes", "10000.00"))  # vendor is paid 10,000
        _, vouchers, _ = tally.export(self.conn, "2026-11", "Shop")
        root = ET.fromstring(vouchers)
        purchase = next(v for v in root.iter("VOUCHER") if v.get("VCHTYPE") == "Purchase")
        self.assertEqual(sum(D(e.findtext("AMOUNT")) for e in purchase.findall("ALLLEDGERENTRIES.LIST")), D("0"))
        names = {e.findtext("LEDGERNAME") for e in purchase.findall("ALLLEDGERENTRIES.LIST")}
        self.assertTrue({"Input CGST", "RCM CGST Payable", "Input SGST", "RCM SGST Payable"} <= names)


if __name__ == "__main__":
    unittest.main()
