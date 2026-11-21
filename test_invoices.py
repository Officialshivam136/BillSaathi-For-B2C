import csv
import io
import os
import tempfile
import unittest
import zipfile
from decimal import Decimal as D

import db
import exports


def item(desc="Barfi", qty="3", rate="450", gst_rate="5", hsn=""):
    return {"description": desc, "qty": qty, "rate": rate, "gst_rate": gst_rate, "hsn": hsn}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(os.path.join(self.tmp.name, "t.db"))
        db.save_business(self.conn, "Sweet House", "Uttar Pradesh", upi_id="shop@upi")
        self.local = db.add_customer(self.conn, "Ramesh", "9876543210", state="Uttar Pradesh")
        self.far = db.add_customer(self.conn, "रमेश", "9000000001", state="Delhi", gstin="07ABCDE1234F1Z5")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()


class TestInvoices(Base):
    def test_numbering_sequential_and_fy(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        b = db.create_invoice(self.conn, self.local, "2026-11-02", [item()])
        c = db.create_invoice(self.conn, self.local, "2027-03-31", [item()])
        d = db.create_invoice(self.conn, self.local, "2027-04-01", [item()])
        nums = [db.get_invoice(self.conn, i)["number"] for i in (a, b, c, d)]
        self.assertEqual(nums, ["BS/2026-27/0001", "BS/2026-27/0002", "BS/2026-27/0003", "BS/2027-28/0001"])

    def test_gst_split_intra_and_inter(self):
        i = db.get_invoice(self.conn, db.create_invoice(self.conn, self.local, "2026-11-01", [item()]))
        self.assertEqual((i["taxable"], i["cgst"], i["sgst"], i["igst"], i["total"]),
                         (D("1350.00"), D("33.75"), D("33.75"), D("0.00"), D("1417.50")))
        j = db.get_invoice(self.conn, db.create_invoice(self.conn, self.far, "2026-11-01", [item()]))
        self.assertEqual((j["cgst"], j["sgst"], j["igst"]), (D("0.00"), D("0.00"), D("67.50")))
        self.assertEqual(j["breakup"][D("5")]["igst"], D("67.50"))

    def test_validation(self):
        for bad in ([], [item(qty="0")], [item(rate="abc")], [item(gst_rate="7")], [item(desc="")], [item()] * 11):
            with self.assertRaises(ValueError):
                db.create_invoice(self.conn, self.local, "2026-11-01", bad)
        with self.assertRaises(ValueError):
            db.create_invoice(self.conn, self.local, "2026-13-01", [item()])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 0)

    def test_cancel_keeps_number_and_no_reuse(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.cancel_invoice(self.conn, a, "test")
        b = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        self.assertEqual(db.get_invoice(self.conn, a)["status_label"], "Cancelled")
        self.assertEqual(db.get_invoice(self.conn, b)["number"], "BS/2026-27/0002")

    def test_cancel_blocked_with_payment(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.add_payment(self.conn, a, "2026-11-02", "10", "cash")
        with self.assertRaises(ValueError):
            db.cancel_invoice(self.conn, a, "test")


class TestPayments(Base):
    def test_status_flow_and_overpayment(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])  # 1417.50
        self.assertEqual(db.get_invoice(self.conn, a)["status_label"], "Unpaid")
        db.add_payment(self.conn, a, "2026-11-02", "400", "upi")
        v = db.get_invoice(self.conn, a)
        self.assertEqual((v["status_label"], v["outstanding"]), ("Partly paid", D("1017.50")))
        with self.assertRaises(ValueError):
            db.add_payment(self.conn, a, "2026-11-03", "1017.51", "cash")
        db.add_payment(self.conn, a, "2026-11-03", "1017.50", "cash")
        self.assertEqual(db.get_invoice(self.conn, a)["status_label"], "Paid")

    def test_payment_validation(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        for amt, mode in (("0", "cash"), ("-5", "cash"), ("x", "cash"), ("5", "crypto")):
            with self.assertRaises(ValueError):
                db.add_payment(self.conn, a, "2026-11-02", amt, mode)

    def test_no_payment_on_cancelled(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.cancel_invoice(self.conn, a, "test")
        with self.assertRaises(ValueError):
            db.add_payment(self.conn, a, "2026-11-02", "5", "cash")


class TestDashboard(Base):
    def test_numbers_match_invoice_list(self):
        today = "2026-11-21"
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])  # due 11-16 -> overdue
        b = db.create_invoice(self.conn, self.local, "2026-11-20", [item(rate="100")])  # 315 not overdue
        c = db.create_invoice(self.conn, self.local, "2026-10-05", [item(rate="100")])  # older month
        x = db.create_invoice(self.conn, self.local, "2026-11-02", [item()])
        db.cancel_invoice(self.conn, x, "test")
        db.add_payment(self.conn, a, "2026-11-10", "400", "cash")
        d = db.dashboard(self.conn, today)
        s, e = d["month_start"], d["month_end"]
        month = [i for i in db.list_invoices(self.conn, s, e, today=today) if i["status"] == "active"]
        self.assertEqual(d["invoiced"], sum(i["total"] for i in month))
        self.assertEqual(d["invoiced"], D("1417.50") + D("315.00"))
        self.assertEqual(d["collected"], D("400.00"))
        overdue = db.list_invoices(self.conn, status="overdue", today=today)
        self.assertEqual(d["overdue_count"], len(overdue))
        self.assertEqual(d["overdue_amount"], sum(i["outstanding"] for i in overdue))
        self.assertEqual(d["outstanding"], D("1017.50") + D("315.00") + D("315.00"))


class TestExportsAndLinks(Base):
    def test_sales_register(self):
        a = db.create_invoice(self.conn, self.far, "2026-11-01", [item()])
        db.add_payment(self.conn, a, "2026-11-02", "100", "cash")
        x = db.create_invoice(self.conn, self.local, "2026-11-02", [item()])
        db.cancel_invoice(self.conn, x, "test")
        db.create_invoice(self.conn, self.local, "2026-12-01", [item()])
        raw = exports.sales_register(self.conn, "2026-11")
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 4)  # header, 2 invoices, total
        self.assertEqual(rows[1][2], "रमेश")
        self.assertEqual(rows[-1][0], "TOTAL")
        self.assertEqual(rows[-1][9], "1417.50")
        self.assertEqual(rows[2][10], "Cancelled")

    def test_full_export_zip(self):
        db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        z = zipfile.ZipFile(io.BytesIO(exports.full_export_zip(self.conn)))
        self.assertEqual(set(z.namelist()), {f"{t}.csv" for t in exports.TABLES} | {"billsaathi.db"})
        self.assertNotIn("passcode", z.read("business.csv").decode("utf-8").lower())

    def test_passcode(self):
        self.assertFalse(db.has_passcode(self.conn))
        with self.assertRaises(ValueError):
            db.set_passcode(self.conn, "12")
        db.set_passcode(self.conn, "s3cret")
        self.assertTrue(db.check_passcode(self.conn, "s3cret"))
        self.assertFalse(db.check_passcode(self.conn, "wrong"))
        self.assertTrue(db.get_secret(self.conn))

    def test_whatsapp_link(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        link = db.whatsapp_link(db.get_invoice(self.conn, a), db.get_business(self.conn))
        self.assertTrue(link.startswith("https://wa.me/919876543210?text="))
        self.assertIn("BS/2026-27/0001", link)
        self.assertIn("shop%40upi", link)


if __name__ == "__main__":
    unittest.main()
