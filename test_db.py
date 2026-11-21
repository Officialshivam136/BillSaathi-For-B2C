import os
import tempfile
import unittest
from decimal import Decimal as D

import db


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "t.db")
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_migration_sets_version_and_is_idempotent(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))
        self.conn.close()
        self.conn = db.connect(self.path)  # reopen must not fail
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))

    def test_business_roundtrip_and_first_run(self):
        self.assertIsNone(db.get_business(self.conn))
        db.save_business(self.conn, "Sweet House", "Uttar Pradesh", "09ABCDE1234F1Z5", upi_id="a@upi", invoice_prefix="sh")
        b = db.get_business(self.conn)
        self.assertEqual((b["name"], b["invoice_prefix"], b["fy_start_month"]), ("Sweet House", "SH", 4))
        db.save_business(self.conn, "Sweet House 2", "Uttar Pradesh")
        self.assertEqual(db.get_business(self.conn)["name"], "Sweet House 2")

    def test_invalid_gstin_rejected(self):
        with self.assertRaises(ValueError):
            db.save_business(self.conn, "X", "Delhi", "BADGSTIN")

    def test_customer_add_edit_search(self):
        cid = db.add_customer(self.conn, "Ramesh", "98765 43210", state="Delhi")
        db.add_customer(self.conn, "Suresh", "9000000001")
        self.assertEqual(db.get_customer(self.conn, cid)["phone"], "919876543210")
        self.assertEqual([r["name"] for r in db.search_customers(self.conn, "rame")], ["Ramesh"])
        self.assertEqual([r["name"] for r in db.search_customers(self.conn, "98765")], ["Ramesh"])
        db.update_customer(self.conn, cid, "Ramesh K", "9876543210")
        self.assertEqual(db.get_customer(self.conn, cid)["name"], "Ramesh K")
        with self.assertRaises(ValueError):
            db.add_customer(self.conn, "  ")

    def test_normalize_phone(self):
        self.assertEqual(db.normalize_phone("9876543210"), "919876543210")
        self.assertEqual(db.normalize_phone("+91 98765-43210"), "919876543210")
        self.assertEqual(db.normalize_phone("09876543210"), "919876543210")

    def test_decimal_roundtrip(self):
        cid = db.add_customer(self.conn, "A")
        with db.tx(self.conn):
            self.conn.execute(
                "INSERT INTO invoice (number,fy,prefix,seq,date,due_date,customer_id,is_interstate,taxable,cgst,sgst,igst,total,created_at)"
                " VALUES ('BS/2026-27/0001','2026-27','BS',1,'2026-11-01','2026-11-16',?,0,?,?,?,?,?,?)",
                (cid, D("100.10"), D("2.50"), D("2.51"), D("0"), D("105.11"), db.now()))
        r = self.conn.execute("SELECT * FROM invoice").fetchone()
        self.assertEqual(r["total"], D("105.11"))
        self.assertIsInstance(r["total"], D)
        self.assertEqual(str(r["total"]), "105.11")
        # stored as text, never as a float
        self.assertEqual(self.conn.execute("SELECT typeof(total) FROM invoice").fetchone()[0], "text")
        with db.tx(self.conn):
            self.conn.execute("UPDATE invoice SET total = ?", (D("1417.50"),))
        self.assertEqual(str(self.conn.execute("SELECT total FROM invoice").fetchone()[0]), "1417.50")

    def test_tx_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with db.tx(self.conn):
                self.conn.execute("INSERT INTO customer (name, created_at) VALUES ('x', 'y')")
                raise RuntimeError
        self.assertEqual(len(db.search_customers(self.conn)), 0)

    def test_backup_once_per_day_and_restorable(self):
        db.add_customer(self.conn, "Keep Me")
        bdir = os.path.join(self.tmp.name, "backups")
        p = db.backup_if_due(self.conn, bdir, today="2026-11-21")
        self.assertTrue(os.path.exists(p))
        self.assertIsNone(db.backup_if_due(self.conn, bdir, today="2026-11-21"))
        restored = db.connect(p)
        self.assertEqual(db.search_customers(restored)[0]["name"], "Keep Me")
        restored.close()


if __name__ == "__main__":
    unittest.main()
