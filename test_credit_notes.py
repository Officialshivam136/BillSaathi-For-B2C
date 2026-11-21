import unittest
from decimal import Decimal as D

import db
from test_invoices import Base, item


class TestCreditNotes(Base):
    def setUp(self):
        super().setUp()
        # two lines: 3 x 450 @5% = 1350 + 67.50 ; 2 x 100 @18% = 200 + 36 ;  total 1653.50
        self.inv = db.create_invoice(self.conn, self.local, "2026-11-01",
                                     [item(), item(desc="Peda", qty="2", rate="100", gst_rate="18")])
        self.items = [r["id"] for r in db.get_invoice(self.conn, self.inv)["items"]]

    def cn(self, quantities, date="2026-11-05", reason="Goods returned"):
        return db.create_credit_note(self.conn, self.inv, date, quantities, reason, by="Owner")

    def test_partial_credit_amounts_numbering_and_status(self):
        a = self.cn({self.items[0]: "1"})  # 1 x 450 @5% = 450 + 22.50
        v = db.get_credit_note(self.conn, a)
        self.assertEqual((v["number"], v["taxable"], v["cgst"], v["sgst"], v["total"]),
                         ("BS-CN/2026-27/0001", D("450.00"), D("11.25"), D("11.25"), D("472.50")))
        b = self.cn({self.items[1]: "2"})  # 200 + 36 = 236
        self.assertEqual(db.get_credit_note(self.conn, b)["number"], "BS-CN/2026-27/0002")
        inv = db.get_invoice(self.conn, self.inv)
        self.assertEqual((inv["credited"], inv["net_total"], inv["outstanding"], inv["status_label"]),
                         (D("708.50"), D("945.00"), D("945.00"), "Unpaid"))

    def test_cannot_credit_more_than_sold_across_notes(self):
        self.cn({self.items[0]: "2"})
        with self.assertRaises(ValueError) as cm:
            self.cn({self.items[0]: "1.001"})
        self.assertIn("only 1 left", str(cm.exception))
        self.cn({self.items[0]: "1"})  # exactly the rest is fine
        with self.assertRaises(ValueError):
            self.cn({self.items[0]: "0.001"})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM credit_note").fetchone()[0], 2)

    def test_full_credit_marks_invoice_credited_and_blocks_payment(self):
        self.cn({self.items[0]: "3", self.items[1]: "2"})
        inv = db.get_invoice(self.conn, self.inv)
        self.assertEqual((inv["status_label"], inv["outstanding"], inv["credited"]), ("Credited", D("0.00"), inv["total"]))
        with self.assertRaises(ValueError):
            db.add_payment(self.conn, self.inv, "2026-11-06", "1", "cash")
        self.assertFalse(inv["overdue"])

    def test_credit_after_payment_creates_refund_due_then_refund(self):
        db.add_payment(self.conn, self.inv, "2026-11-02", "1653.50", "upi")  # paid in full
        self.assertEqual(db.get_invoice(self.conn, self.inv)["status_label"], "Paid")
        self.cn({self.items[1]: "2"})  # 236 credited
        inv = db.get_invoice(self.conn, self.inv)
        self.assertEqual((inv["status_label"], inv["refund_due"], inv["outstanding"]), ("Refund due", D("236.00"), D("0.00")))
        with self.assertRaises(ValueError):
            db.add_refund(self.conn, self.inv, "2026-11-06", "236.01", "cash")  # more than is owed back
        db.add_refund(self.conn, self.inv, "2026-11-06", "100", "cash", "part", by="Owner")
        self.assertEqual(db.get_invoice(self.conn, self.inv)["refund_due"], D("136.00"))
        db.add_refund(self.conn, self.inv, "2026-11-07", "136", "cash")
        inv = db.get_invoice(self.conn, self.inv)
        self.assertEqual((inv["status_label"], inv["paid"], inv["refund_due"]), ("Paid", D("1417.50"), D("0.00")))
        with self.assertRaises(ValueError):
            db.add_refund(self.conn, self.inv, "2026-11-08", "1", "cash")  # nothing left to return

    def test_validation(self):
        for q, reason, date in (({}, "x", "2026-11-05"), ({self.items[0]: "1"}, "  ", "2026-11-05"),
                                ({self.items[0]: "abc"}, "x", "2026-11-05"), ({self.items[0]: "0"}, "x", "2026-11-05"),
                                ({self.items[0]: "-1"}, "x", "2026-11-05"), ({self.items[0]: "1"}, "x", "2026-10-31"),
                                ({999999: "1"}, "x", "2026-11-05")):
            with self.assertRaises(ValueError, msg=(q, reason, date)):
                self.cn(q, date, reason)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM credit_note").fetchone()[0], 0)

    def test_cancelled_invoice_and_cancel_blocked_after_credit(self):
        x = db.create_invoice(self.conn, self.local, "2026-11-02", [item()])
        db.cancel_invoice(self.conn, x, "dup")
        with self.assertRaises(ValueError):
            db.create_credit_note(self.conn, x, "2026-11-03", {1: "1"}, "r")
        self.cn({self.items[0]: "1"})
        with self.assertRaises(ValueError):
            db.cancel_invoice(self.conn, self.inv, "wrong")

    def test_interstate_credit_uses_igst(self):
        far = db.create_invoice(self.conn, self.far, "2026-11-02", [item()])
        it = db.get_invoice(self.conn, far)["items"][0]["id"]
        cn = db.get_credit_note(self.conn, db.create_credit_note(self.conn, far, "2026-11-03", {it: "3"}, "r"))
        self.assertEqual((cn["cgst"], cn["sgst"], cn["igst"], cn["total"]), (D("0.00"), D("0.00"), D("67.50"), D("1417.50")))

    def test_numbering_restarts_each_financial_year(self):
        self.cn({self.items[0]: "1"}, date="2027-03-31")
        n = db.get_credit_note(self.conn, self.cn({self.items[0]: "1"}, date="2027-04-01"))
        self.assertEqual(n["number"], "BS-CN/2027-28/0001")

    def test_filter_and_listing(self):
        self.cn({self.items[0]: "3", self.items[1]: "2"})
        self.assertEqual([r["number"] for r in db.list_invoices(self.conn, status="credited")], ["BS/2026-27/0001"])
        self.assertEqual(len(db.list_credit_notes(self.conn, *db.month_range("2026-11"))), 1)
        self.assertEqual(len(db.list_credit_notes(self.conn, *db.month_range("2026-12"))), 0)

    def test_dashboard_series_and_liability_net_of_credits(self):
        today = "2026-11-21"
        self.cn({self.items[1]: "2"})  # 236 credited in November
        d = db.dashboard(self.conn, today)
        self.assertEqual((d["invoiced"], d["credited"]), (D("1653.50") - D("236.00"), D("236.00")))
        self.assertEqual(db.monthly_series(self.conn, today, 2)[1]["invoiced"], D("1417.50"))
        rows, tot = db.gst_liability(self.conn, "2026-11")
        by = {r["rate"]: r for r in rows}
        self.assertEqual((by[D("18")]["taxable"], by[D("18")]["tax"]), (D("0.00"), D("0.00")))  # 18% line fully credited
        self.assertEqual((by[D("5")]["taxable"], by[D("5")]["tax"]), (D("1350.00"), D("67.50")))
        self.assertEqual(d["outstanding"], D("1417.50"))

    def test_liability_credit_in_later_month_goes_negative_there(self):
        self.cn({self.items[1]: "2"}, date="2026-12-03")
        rows, tot = db.gst_liability(self.conn, "2026-12")
        self.assertEqual((tot["taxable"], tot["tax"]), (D("-200.00"), D("-36.00")))
        self.assertEqual(db.gst_liability(self.conn, "2026-11")[1]["tax"], D("103.50"))  # November unchanged


class TestReminderLog(Base):
    def test_stats(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        b = db.create_invoice(self.conn, self.far, "2026-11-01", [item()])
        c = db.create_invoice(self.conn, self.local, "2026-11-02", [item()])
        for inv in (a, b):
            db.log_reminder(self.conn, inv, "Owner")
        self.conn.execute("UPDATE reminder_log SET sent_at = '2026-11-10T10:00:00'")
        db.add_payment(self.conn, a, "2026-11-12", "100", "upi")  # 2 days after reminder: counts
        db.add_payment(self.conn, b, "2026-11-15", "100", "upi")  # 5 days after: does not
        db.add_payment(self.conn, c, "2026-11-12", "100", "upi")  # never reminded
        db.add_payment(self.conn, a, "2026-11-09", "10", "cash")  # before the reminder: does not
        s = db.reminder_stats(self.conn, "2026-11-21")
        self.assertEqual((s["payments"], s["driven"], s["reminders"]), (4, 1, 2))

    def test_old_payments_outside_window_ignored(self):
        a = db.create_invoice(self.conn, self.local, "2026-01-01", [item()])
        db.add_payment(self.conn, a, "2026-01-05", "10", "cash")
        self.assertEqual(db.reminder_stats(self.conn, "2026-11-21")["payments"], 0)


if __name__ == "__main__":
    unittest.main()
