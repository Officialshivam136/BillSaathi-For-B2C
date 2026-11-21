import os
import unittest
from decimal import Decimal as D

import bank
import db
from test_invoices import Base, item

STATEMENT = """Date,Narration,Chq./Ref.No.,Withdrawal Amt.,Deposit Amt.,Balance
05-11-2026,UPI/RAMESH KUMAR/pay,UTR100,,1417.50,5000
06-11-2026,NEFT-ACME-SUPPLIES,UTR101,2000.00,,3000
07-11-2026,UPI/UNKNOWN PERSON,UTR102,,100.00,3100
08-11-2026,UPI/UNKNOWN PERSON,UTR102,,100.00,3200
"""


class TestBankParse(unittest.TestCase):
    def test_credits_only_and_dedupe_keys(self):
        credits, skipped, errs = bank.parse_statement(STATEMENT)
        self.assertEqual((len(credits), skipped, errs), (3, 1, []))
        self.assertEqual(credits[0]["amount"], D("1417.50"))
        self.assertEqual(credits[0]["date"], "2026-11-05")
        self.assertEqual(len({c["key"] for c in credits}), 3)

    def test_identical_lines_in_one_statement_get_different_keys(self):
        text = "Date,Narration,Credit\n01-11-2026,CASH DEP,50\n01-11-2026,CASH DEP,50\n"
        credits, _, _ = bank.parse_statement(text)
        self.assertEqual(len(credits), 2)
        self.assertNotEqual(credits[0]["key"], credits[1]["key"])

    def test_single_amount_column_with_type(self):
        text = "Txn Date,Description,Amount,Dr/Cr\n2026-11-01,IN,500,CR\n2026-11-02,OUT,200,DR\n"
        credits, skipped, _ = bank.parse_statement(text)
        self.assertEqual((len(credits), skipped), (1, 1))

    def test_bad_statement(self):
        with self.assertRaises(ValueError):
            bank.parse_statement("foo,bar\n1,2")
        _, _, errs = bank.parse_statement("Date,Narration,Credit\nnotadate,x,5\n")
        self.assertIn("Line 2", errs[0])


class TestBankMatch(Base):
    def open_invoices(self):
        return [i for i in db.list_invoices(self.conn) if i["status"] == "active" and i["outstanding"] > 0]

    def test_levels(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])  # Ramesh 1417.50
        b = db.create_invoice(self.conn, self.far, "2026-11-02", [item(rate="100")])  # रमेश 315.00 (name has no latin words)
        credits, _, _ = bank.parse_statement(STATEMENT)
        res = bank.match(credits, self.open_invoices())
        self.assertEqual((res[0]["level"], res[0]["pick"]), ("confident", a))  # exact + name RAMESH
        # 100.00 matches neither a name nor an exact balance, so nothing is preselected (the owner may still pick one)
        self.assertEqual((res[1]["level"], res[1]["pick"]), ("none", None))
        self.assertEqual([c["id"] for c in res[1]["cands"]], [a, b])  # both can take 100; oldest first

    def test_invoice_number_in_narration_is_confident(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        text = "Date,Narration,Credit\n05-11-2026,PAYMENT FOR BS/2026-27/0001,400\n"
        credits, _, _ = bank.parse_statement(text)
        r = bank.match(credits, self.open_invoices())[0]
        self.assertEqual((r["level"], r["pick"]), ("confident", a))

    def test_ambiguous_exact_amounts_are_unclear(self):
        db.create_invoice(self.conn, self.local, "2026-11-01", [item(rate="100")])
        db.create_invoice(self.conn, self.far, "2026-11-02", [item(rate="100")])
        text = "Date,Narration,Credit\n05-11-2026,CASH DEPOSIT,315\n"
        r = bank.match(bank.parse_statement(text)[0], self.open_invoices())[0]
        self.assertEqual((r["level"], r["pick"], len(r["cands"])), ("unclear", None, 2))

    def test_single_exact_amount_is_suggested_and_too_large_is_none(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        text = "Date,Narration,Credit\n05-11-2026,CASH DEPOSIT,1417.50\n05-11-2026,CASH DEPOSIT,99999\n"
        r = bank.match(bank.parse_statement(text)[0], self.open_invoices())
        self.assertEqual((r[0]["level"], r[0]["pick"]), ("suggested", a))
        self.assertEqual(r[1]["level"], "none")

    def test_apply_once_only(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        credits, _, _ = bank.parse_statement("Date,Narration,Credit\n05-11-2026,UPI RAMESH,1417.50\n")
        c = credits[0]
        db.add_payment(self.conn, a, c["date"], c["amount"], "bank", "Bank", by="Owner", bank_key=c["key"])
        self.assertEqual(db.get_invoice(self.conn, a)["status_label"], "Paid")
        with self.assertRaises(ValueError):
            db.add_payment(self.conn, a, c["date"], c["amount"], "bank", "Bank", bank_key=c["key"])
        res = bank.match(credits, self.open_invoices(), db.applied_bank_keys(self.conn))
        self.assertEqual(res[0]["level"], "applied")

    def test_failed_payment_does_not_mark_line_applied(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        with self.assertRaises(ValueError):
            db.add_payment(self.conn, a, "2026-11-05", "99999", "bank", bank_key="k1")  # overpayment
        self.assertNotIn("k1", db.applied_bank_keys(self.conn))


class TestStaff(Base):
    def test_staff_lifecycle(self):
        sid = db.add_staff(self.conn, "Sunita", "1111")
        self.assertEqual(db.check_staff(self.conn, "sunita", "1111"), sid)  # name is case-insensitive
        self.assertIsNone(db.check_staff(self.conn, "Sunita", "bad"))
        db.set_staff_active(self.conn, sid, False)
        self.assertIsNone(db.check_staff(self.conn, "Sunita", "1111"))
        db.set_staff_active(self.conn, sid, True)
        db.reset_staff_passcode(self.conn, sid, "2222")
        self.assertIsNone(db.check_staff(self.conn, "Sunita", "1111"))
        self.assertEqual(db.check_staff(self.conn, "Sunita", "2222"), sid)

    def test_staff_validation(self):
        db.add_staff(self.conn, "Sunita", "1111")
        for name, pc in (("Sunita", "9999"), ("owner", "1234"), ("", "1234"), ("Raju", "12")):
            with self.assertRaises(ValueError):
                db.add_staff(self.conn, name, pc)

    def test_created_by_recorded(self):
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()], by="Sunita")
        db.add_payment(self.conn, a, "2026-11-02", "10", "cash", by="Sunita")
        self.assertEqual(db.get_invoice(self.conn, a)["created_by"], "Sunita")
        self.assertEqual(db.get_invoice(self.conn, a)["payments"][0]["created_by"], "Sunita")


if __name__ == "__main__":
    unittest.main()
