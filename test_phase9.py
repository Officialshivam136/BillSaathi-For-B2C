import datetime
import unittest
from decimal import Decimal as D

import db
from test_invoices import Base, item


class StockBase(Base):
    def setUp(self):
        super().setUp()
        self.barfi = db.add_catalog_item(self.conn, "Kaju Barfi", "1704", "450", "5", track_stock=True, reorder_level="5")
        self.plain = db.add_catalog_item(self.conn, "Plain Item", "", "10", "5")  # not tracked

    def on_hand(self, item_id=None):
        return db.stock_on_hand(self.conn).get(item_id or self.barfi, D("0"))

    def sell(self, qty="3", desc="Kaju Barfi", date="2026-11-01", customer=None):
        return db.create_invoice(self.conn, customer or self.local, date, [item(desc=desc, qty=qty)], by="Owner")


class TestStock(StockBase):
    def test_receive_sell_edit_cancel(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "20", "opening count", "Owner", kind="opening")
        self.assertEqual(self.on_hand(), D("20"))
        inv = self.sell("3", desc="kaju BARFI")  # matched by name, any capitalisation
        self.assertEqual(self.on_hand(), D("17"))
        line = db.get_invoice(self.conn, inv)["items"][0]
        self.assertEqual(line["catalog_id"], self.barfi)
        db.update_invoice(self.conn, inv, self.local, "2026-11-01", [item(desc="Kaju Barfi", qty="5")], by="Owner")
        self.assertEqual(self.on_hand(), D("15"))  # the 3 went back, 5 went out
        db.cancel_invoice(self.conn, inv, "customer changed mind", by="Owner")
        self.assertEqual(self.on_hand(), D("20"))
        kinds = [m["kind"] for m in reversed(db.stock_history(self.conn, self.barfi))]
        self.assertEqual(kinds, ["opening", "sale", "edit", "sale", "cancel"])  # history is kept, never deleted
        self.assertEqual(sum(m["qty"] for m in db.stock_history(self.conn, self.barfi)), D("20"))

    def test_untracked_items_and_unknown_names_never_touch_stock(self):
        self.sell("4", desc="Plain Item")
        self.sell("1", desc="Something not saved")
        self.assertEqual(db.stock_on_hand(self.conn), {})
        self.assertIsNotNone(db.get_invoice(self.conn, 1)["items"][0]["catalog_id"])  # linked, but nothing to track

    def test_credit_note_restocks_only_when_goods_came_back(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "10")
        inv = self.sell("4")
        line = db.get_invoice(self.conn, inv)["items"][0]["id"]
        self.assertEqual(self.on_hand(), D("6"))
        cn = db.create_credit_note(self.conn, inv, "2026-11-02", {line: "1"}, "returned", restock=True)
        self.assertEqual(self.on_hand(), D("7"))
        self.assertIn(db.get_credit_note(self.conn, cn)["number"], db.stock_history(self.conn, self.barfi)[0]["credit_note_number"])
        db.create_credit_note(self.conn, inv, "2026-11-03", {line: "1"}, "price correction", restock=False)
        self.assertEqual(self.on_hand(), D("7"))  # a price correction moves no goods

    def test_status_and_alerts(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "8")
        self.assertEqual(db.stock_levels(self.conn)[0]["status"], "ok")
        inv = self.sell("3")  # 5 left = the reorder level
        self.assertEqual(db.stock_levels(self.conn)[0]["status"], "low")
        self.assertEqual(db.stock_alerts_for_invoice(self.conn, inv), ["Kaju Barfi: only 5 left"])
        inv = self.sell("5")  # 0 left
        self.assertEqual(db.stock_levels(self.conn)[0]["status"], "out")
        self.assertEqual(db.stock_alerts_for_invoice(self.conn, inv), ["Kaju Barfi: out of stock"])
        inv = self.sell("2")  # sold more than held: allowed, with a warning
        self.assertEqual(self.on_hand(), D("-2"))
        self.assertIn("below zero", db.stock_alerts_for_invoice(self.conn, inv)[0])
        self.assertEqual(len(db.stock_levels(self.conn, only_attention=True)), 1)
        self.assertEqual(db.stock_alerts_for_invoice(self.conn, self.sell("1", desc="Plain Item")), [])

    def test_adjustment_to_a_physical_count(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "15")
        db.adjust_stock(self.conn, self.barfi, "2026-11-05", "12", "stock count", "Owner")
        self.assertEqual(self.on_hand(), D("12"))
        self.assertEqual(db.stock_history(self.conn, self.barfi)[0]["qty"], D("-3.000"))
        db.adjust_stock(self.conn, self.barfi, "2026-11-06", "20", "found a box")
        self.assertEqual(self.on_hand(), D("20"))
        db.adjust_stock(self.conn, self.barfi, "2026-11-07", "0", "all expired")
        self.assertEqual(self.on_hand(), D("0"))
        with self.assertRaises(ValueError):  # the count already matches the books
            db.adjust_stock(self.conn, self.barfi, "2026-11-07", "0", "same")
        with self.assertRaises(ValueError):  # a negative count is not a count
            db.adjust_stock(self.conn, self.barfi, "2026-11-07", "-1", "typo")
        with self.assertRaises(ValueError):
            db.adjust_stock(self.conn, self.barfi, "2026-11-07", "5", "  ")  # a reason is required

    def test_validation(self):
        with self.assertRaises(ValueError):
            db.receive_stock(self.conn, self.plain, "2026-11-01", "5")  # not tracked
        for bad in ("0", "-2", "abc", "1.0005", ""):
            with self.assertRaises(ValueError, msg=bad):
                db.receive_stock(self.conn, self.barfi, "2026-11-01", bad)
        with self.assertRaises(ValueError):
            db.receive_stock(self.conn, self.barfi, "2026-13-01", "5")
        with self.assertRaises(ValueError):
            db.receive_stock(self.conn, 9999, "2026-11-01", "5")
        with self.assertRaises(ValueError):
            db.add_catalog_item(self.conn, "Bad level", "", "1", "5", track_stock=True, reorder_level="x")
        self.assertEqual(db.stock_on_hand(self.conn), {})

    def test_deleting_items(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "5")
        with self.assertRaises(ValueError) as cm:
            db.delete_catalog_item(self.conn, self.barfi)
        self.assertIn("stock history", str(cm.exception))
        inv = self.sell("1", desc="Plain Item")
        db.delete_catalog_item(self.conn, self.plain)  # no history: allowed, and the old invoice line just loses its link
        self.assertIsNone(db.get_invoice(self.conn, inv)["items"][0]["catalog_id"])
        db.update_catalog_item(self.conn, self.barfi, "Kaju Barfi", "1704", "450", "5", track_stock=False)  # stop tracking instead
        self.assertEqual(db.stock_levels(self.conn), [])
        self.sell("2")  # no longer tracked: no movement
        self.assertEqual(len(db.stock_history(self.conn, self.barfi)), 1)

    def test_tracking_started_later_counts_from_the_opening_balance(self):
        old = self.sell("2", desc="Plain Item")
        db.update_catalog_item(self.conn, self.plain, "Plain Item", "", "10", "5", track_stock=True)
        self.assertEqual(self.on_hand(self.plain), D("0"))  # earlier sales are not retro-counted
        db.receive_stock(self.conn, self.plain, "2026-11-05", "30", "opening", kind="opening")
        self.sell("4", desc="Plain Item", date="2026-11-06")
        self.assertEqual(self.on_hand(self.plain), D("26"))
        db.cancel_invoice(self.conn, old, "x")  # cancelling an invoice from before tracking must not invent stock
        self.assertEqual(self.on_hand(self.plain), D("26"))

    def test_renaming_a_saved_item_keeps_old_links(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "10")
        inv = self.sell("2")
        db.update_catalog_item(self.conn, self.barfi, "Kaju Katli", "1704", "450", "5", track_stock=True, reorder_level="5")
        self.assertEqual(db.get_invoice(self.conn, inv)["items"][0]["catalog_id"], self.barfi)
        db.cancel_invoice(self.conn, inv, "x")
        self.assertEqual(self.on_hand(), D("10"))  # the cancel still finds the right item


class TestRecurringDates(unittest.TestCase):
    def test_month_end_clamping_does_not_drift(self):
        a = 31
        d = "2027-01-31"
        seen = []
        for _ in range(5):
            d = db.next_occurrence(d, "monthly", a)
            seen.append(d)
        self.assertEqual(seen, ["2027-02-28", "2027-03-31", "2027-04-30", "2027-05-31", "2027-06-30"])  # back to the 31st, not stuck on the 28th
        self.assertEqual(db.next_occurrence("2027-11-30", "monthly", 30), "2027-12-30")

    def test_other_frequencies(self):
        self.assertEqual(db.next_occurrence("2026-11-21", "weekly", 21), "2026-11-28")
        self.assertEqual(db.next_occurrence("2026-12-30", "weekly", 30), "2027-01-06")
        self.assertEqual(db.next_occurrence("2026-11-15", "quarterly", 15), "2027-02-15")
        self.assertEqual(db.next_occurrence("2026-12-15", "monthly", 15), "2027-01-15")
        self.assertEqual(db.next_occurrence("2028-02-29", "yearly", 29), "2029-02-28")  # leap day
        self.assertEqual(db.next_occurrence("2029-02-28", "yearly", 29), "2030-02-28")


class TestRecurring(StockBase):
    def make(self, start="2026-11-01", freq="monthly", end="", customer=None, items=None):
        items = [item(desc="Kaju Barfi", qty="2")] if items is None else items
        return db.create_recurring(self.conn, customer or self.local, freq, start, end, items, by="Owner")

    def test_create_from_an_invoice_and_list(self):
        inv = self.sell("3", date="2026-10-01")
        rid = db.create_recurring_from_invoice(self.conn, inv, "monthly", "2026-11-01", "2027-03-31", by="Owner")
        rec = db.get_recurring(self.conn, rid)
        self.assertEqual((rec["customer_name"], rec["frequency"], rec["anchor_day"], rec["next_date"], rec["end_date"], len(rec["items"])),
                         ("Ramesh", "monthly", 1, "2026-11-01", "2027-03-31", 1))
        self.assertIn("Repeats BS/2026-27/0001", rec["note"])
        row = db.list_recurring(self.conn, "2026-10-15")[0]
        self.assertEqual((row["due"], row["estimate"]), (False, D("1417.50")))
        self.assertTrue(db.list_recurring(self.conn, "2026-11-01")[0]["due"])
        self.assertEqual(db.recurring_due(self.conn, "2026-10-31"), [])

    def test_run_creates_the_invoice_and_moves_the_schedule_on(self):
        rid = self.make("2026-11-01")
        inv, skipped = db.run_recurring(self.conn, rid, "2026-11-21", "2026-11-21", by="Owner")
        self.assertEqual(skipped, 0)
        v = db.get_invoice(self.conn, inv)
        self.assertEqual((v["date"], v["customer_name"], v["created_by"], len(v["items"]), v["total"]), ("2026-11-21", "Ramesh", "Owner", 1, D("945.00")))
        rec = db.get_recurring(self.conn, rid)
        self.assertEqual((rec["next_date"], rec["runs"], rec["last_invoice_id"], rec["active"]), ("2026-12-01", 1, inv, 1))
        with self.assertRaises(ValueError) as cm:  # pressing the button again changes nothing
            db.run_recurring(self.conn, rid, "2026-11-21", "2026-11-21")
        self.assertIn("not due yet", str(cm.exception))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 1)

    def test_missed_periods_are_reported_not_billed_back(self):
        rid = self.make("2026-08-15")
        inv, skipped = db.run_recurring(self.conn, rid, "2026-11-21", "2026-11-21")
        self.assertEqual(skipped, 3)  # Aug, Sep, Oct were missed; only one invoice now
        self.assertEqual(db.get_recurring(self.conn, rid)["next_date"], "2026-12-15")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 1)

    def test_end_date_finishes_the_schedule(self):
        rid = self.make("2026-11-01", end="2026-11-30")
        db.run_recurring(self.conn, rid, "2026-11-02", "2026-11-02")
        rec = db.get_recurring(self.conn, rid)
        self.assertEqual((rec["active"], rec["next_date"]), (0, "2026-12-01"))
        self.assertEqual(db.recurring_due(self.conn, "2027-01-01"), [])
        rid2 = self.make("2026-11-01", end="2026-11-30")
        self.conn.execute("UPDATE recurring SET next_date = '2026-12-01' WHERE id = ?", (rid2,))
        with self.assertRaises(ValueError):
            db.run_recurring(self.conn, rid2, "2026-12-02", "2026-12-02")  # past its end date

    def test_a_failed_run_leaves_the_schedule_due(self):
        rid = self.make("2026-11-01", customer=self.far, items=[item(desc="Kaju Barfi", qty="1")])  # inter-state customer
        db.save_business(self.conn, "Tiny Shop", "Uttar Pradesh", "09ABCDE1234F1Z5", scheme="composition")  # which a composition dealer cannot bill
        with self.assertRaises(ValueError):
            db.run_recurring(self.conn, rid, "2026-11-21", "2026-11-21")
        self.assertEqual(db.get_recurring(self.conn, rid)["next_date"], "2026-11-01")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], 0)
        self.assertIsNone(db.list_recurring(self.conn, "2026-11-21")[0]["estimate"])  # the page can show that it needs attention
        self.assertTrue(db.list_recurring(self.conn, "2026-11-21")[0]["due"])

    def test_pause_resume_delete(self):
        inv = self.sell("1")
        rid = self.make("2026-11-01")
        db.set_recurring_active(self.conn, rid, False)
        self.assertEqual(db.recurring_due(self.conn, "2026-11-21"), [])
        with self.assertRaises(ValueError):
            db.run_recurring(self.conn, rid, "2026-11-21", "2026-11-21")
        db.set_recurring_active(self.conn, rid, True)
        made, _ = db.run_recurring(self.conn, rid, "2026-11-21", "2026-11-21")
        db.delete_recurring(self.conn, rid)
        self.assertIsNone(db.get_recurring(self.conn, rid))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM recurring_item").fetchone()[0], 0)
        self.assertIsNotNone(db.get_invoice(self.conn, made))  # invoices it created are untouched
        self.assertIsNotNone(db.get_invoice(self.conn, inv))

    def test_validation(self):
        for kw in ({"freq": "daily"}, {"end": "2026-10-01"}, {"start": "2026-13-01"}, {"items": []}, {"items": [item(qty="0")]}):
            with self.assertRaises(ValueError, msg=kw):
                self.make(**kw)
        with self.assertRaises(ValueError):
            db.create_recurring_from_invoice(self.conn, 999, "monthly", "2026-11-01")
        x = self.sell("1")
        db.cancel_invoice(self.conn, x, "dup")
        with self.assertRaises(ValueError):
            db.create_recurring_from_invoice(self.conn, x, "monthly", "2026-11-01")
        self.assertEqual(db.list_recurring(self.conn), [])

    def test_a_recurring_invoice_moves_stock_like_any_other(self):
        db.receive_stock(self.conn, self.barfi, "2026-10-30", "10")
        rid = self.make("2026-11-01")
        inv, _ = db.run_recurring(self.conn, rid, "2026-11-01", "2026-11-01")
        self.assertEqual(self.on_hand(), D("8"))
        self.assertEqual(db.stock_alerts_for_invoice(self.conn, inv), [])


if __name__ == "__main__":
    unittest.main()
