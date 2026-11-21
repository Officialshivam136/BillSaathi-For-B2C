import csv
import io
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D

import db
import exports
from test_invoices import Base, item


class TestPhase2(Base):
    def test_migration_upgrades_v1_database(self):
        path = os.path.join(self.tmp.name, "old.db")
        raw = sqlite3.connect(path)
        raw.executescript("BEGIN;" + db.SCHEMA_V1 + "PRAGMA user_version = 1;COMMIT;")
        raw.execute("INSERT INTO customer (name, created_at) VALUES ('Old', 'x')")
        raw.commit()
        raw.close()
        c = db.connect(path)
        try:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))
            self.assertEqual(db.search_customers(c)[0]["name"], "Old")
            self.assertIsNone(db.get_customer(c, 1)["due_days"])
        finally:
            c.close()

    def test_due_days_per_customer(self):
        slow = db.add_customer(self.conn, "Slow Payer", state="Uttar Pradesh", due_days="45")
        a = db.get_invoice(self.conn, db.create_invoice(self.conn, slow, "2026-11-01", [item()]))
        b = db.get_invoice(self.conn, db.create_invoice(self.conn, self.local, "2026-11-01", [item()]))
        self.assertEqual(a["due_date"], "2026-12-16")  # customer setting
        self.assertEqual(b["due_date"], "2026-11-16")  # business default 15
        with self.assertRaises(ValueError):
            db.add_customer(self.conn, "X", due_days="abc")
        with self.assertRaises(ValueError):
            db.add_customer(self.conn, "X", due_days="-1")

    def test_cancel_requires_reason_and_records_it(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        with self.assertRaises(ValueError):
            db.cancel_invoice(self.conn, a, "  ")
        db.cancel_invoice(self.conn, a, "Wrong customer")
        v = db.get_invoice(self.conn, a)
        self.assertEqual((v["status_label"], v["cancel_reason"]), ("Cancelled", "Wrong customer"))
        with self.assertRaises(ValueError):
            db.cancel_invoice(self.conn, a, "again")

    def test_catalog(self):
        i = db.add_catalog_item(self.conn, "Kaju Barfi", "1704", "900", "5")
        with self.assertRaises(ValueError):
            db.add_catalog_item(self.conn, "kaju barfi", "", "1", "5")  # case-insensitive duplicate
        with self.assertRaises(ValueError):
            db.add_catalog_item(self.conn, "Bad", "", "1", "7")
        db.update_catalog_item(self.conn, i, "Kaju Barfi", "1704", "950.50", "5")
        row = db.list_catalog(self.conn)[0]
        self.assertEqual((row["rate"], row["gst_rate"]), (D("950.50"), D("5")))
        db.delete_catalog_item(self.conn, i)
        self.assertEqual(db.list_catalog(self.conn), [])

    def test_customer_filter(self):
        db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        db.create_invoice(self.conn, self.far, "2026-11-01", [item()])
        rows = db.list_invoices(self.conn, customer_id=self.far)
        self.assertEqual([r["customer_name"] for r in rows], ["रमेश"])

    def test_gst_liability_matches_invoices(self):
        db.create_invoice(self.conn, self.local, "2026-11-01", [item(), item(rate="101.01", gst_rate="18")])
        db.create_invoice(self.conn, self.far, "2026-11-05", [item(gst_rate="12")])
        x = db.create_invoice(self.conn, self.local, "2026-11-06", [item()])
        db.cancel_invoice(self.conn, x, "dup")
        db.create_invoice(self.conn, self.local, "2026-12-01", [item()])  # other month
        rows, tot = db.gst_liability(self.conn, "2026-11")
        self.assertEqual([r["rate"] for r in rows], [D("5"), D("12"), D("18")])
        invs = [i for i in db.list_invoices(self.conn, *db.month_range("2026-11")) if i["status"] == "active"]
        for k in ("taxable", "cgst", "sgst", "igst"):
            self.assertEqual(tot[k], sum(i[k] for i in invs), k)
        raw = exports.gst_liability(self.conn, "2026-11")
        rows_csv = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(rows_csv[-1][0], "TOTAL")
        self.assertEqual(rows_csv[1][0], "5%")


if __name__ == "__main__":
    unittest.main()
