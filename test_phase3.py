import csv
import io
import zipfile
import unittest
from decimal import Decimal as D

import db
import exports
import reconcile as rc
from test_invoices import Base, item

G1, G2 = "09ABCDE1234F1Z5", "07ABCDE1234F1Z5"
PORTAL = """GSTIN of supplier,Trade/Legal name,Invoice number,Invoice date,Taxable Value (₹),Integrated Tax(₹),Central Tax(₹),State/UT Tax(₹)
09ABCDE1234F1Z5,Alpha Traders,A-001,05-11-2026,"1,000.00",0,25.00,25.00
09ABCDE1234F1Z5,Alpha Traders,A-002,06/11/2026,2000.00,0,50.00,50.00
07ABCDE1234F1Z5,Beta Foods,B/77,2026-11-08,500.00,25.00,0,0
07ABCDE1234F1Z5,Beta Foods,B-99,10-11-2026,100.00,5.00,0,0
"""


def book(gstin, inv, date, taxable, cgst="0", sgst="0", igst="0", name="X", phone=""):
    return {"gstin": gstin, "name": name, "inv_raw": inv, "inv_key": rc.inv_key(inv), "date": date, "taxable": D(taxable),
            "cgst": D(cgst), "sgst": D(sgst), "igst": D(igst), "tax": D(cgst) + D(sgst) + D(igst), "phone": phone, "line": 0}


class TestReconcile(unittest.TestCase):
    def test_parse_portal_csv_with_portal_headers(self):
        rows, errs = rc.parse_csv(PORTAL)
        self.assertEqual((len(rows), errs), (4, []))
        self.assertEqual(rows[0]["taxable"], D("1000.00"))
        self.assertEqual(rows[0]["tax"], D("50.00"))
        self.assertEqual(rows[1]["date"], "2026-11-06")
        self.assertEqual(rows[2]["igst"], D("25.00"))

    def test_parse_errors_and_missing_columns(self):
        with self.assertRaises(ValueError) as cm:
            rc.parse_csv("a,b\n1,2")
        self.assertIn("supplier GSTIN", str(cm.exception))
        rows, errs = rc.parse_csv("GSTIN,Invoice number,Date,Taxable\n" + f"{G1},1,notadate,5\n{G1},2,01-11-2026,5")
        self.assertEqual(len(rows), 1)
        self.assertIn("Line 2", errs[0])

    def test_inv_key_ignores_case_punctuation_zeros(self):
        self.assertEqual(rc.inv_key("inv/0042"), rc.inv_key("INV-42"))

    def test_match_categories(self):
        portal, _ = rc.parse_csv(PORTAL)
        books = [
            book(G1, "a-001", "2026-11-05", "1000", "25", "25"),            # clean match (case differs)
            book(G1, "A-002", "2026-11-06", "2000", "50", "50.00"),         # clean
            book(G2, "B/77", "2026-11-08", "500", igst="20"),               # tax mismatch (25 vs 20)
            book(G2, "B99", "2026-11-10", "100", igst="5"),                 # invoice number differs? B99 == B-99 key -> match
            book(G1, "Z-1", "2026-11-12", "300", "7.5", "7.5", name="Gamma"),  # missing in 2B
        ]
        r = rc.match(books, portal)
        self.assertEqual((len(r["matched"]), len(r["mismatched"]), len(r["books_only"]), len(r["portal_only"])), (3, 1, 1, 0))
        self.assertEqual(r["mismatched"][0]["note"], "tax differs by 5.00")

    def test_probable_match_when_invoice_number_differs(self):
        portal, _ = rc.parse_csv(PORTAL)
        books = [book(G2, "INV-B-99-X", "2026-11-11", "100", igst="5.50")]  # 1 day, within tolerance, other number
        r = rc.match(books, portal[3:])
        self.assertEqual(len(r["probable"]), 1)

    def test_portal_only_and_tolerance(self):
        portal, _ = rc.parse_csv(PORTAL)
        books = [book(G1, "A-001", "2026-11-05", "1000.50", "25.20", "25")]  # within +/- 1.00
        r = rc.match(books, portal[:1])
        self.assertEqual(len(r["matched"]), 1)
        r2 = rc.match([], portal)
        self.assertEqual(len(r2["portal_only"]), 4)

    def test_followup_groups_itc_at_risk(self):
        r = rc.match([book(G1, "Z-1", "2026-11-12", "300", "7.5", "7.5", name="Gamma", phone="9876543210"),
                      book(G1, "Z-2", "2026-11-13", "100", "2.5", "2.5", name="Gamma")], [])
        g = rc.supplier_followup(r["books_only"])
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0]["itc_at_risk"], g[0]["invoices"]), (D("20.00"), ["Z-1", "Z-2"]))
        link = rc.followup_link(g[0], "Sweet House")
        self.assertTrue(link.startswith("https://wa.me/919876543210?text="))

    def test_exceptions_csv_has_only_exceptions(self):
        portal, _ = rc.parse_csv(PORTAL)
        r = rc.match([book(G1, "A-001", "2026-11-05", "1000", "25", "25"), book(G1, "Z-1", "2026-11-12", "300", "7.5", "7.5")], portal)
        raw = rc.exceptions_csv(r)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        kinds = [x[0] for x in rows[1:]]
        self.assertEqual(sorted(kinds), ["Missing in GSTR-2B"] + ["Missing in books"] * 3)


class TestPurchases(Base):
    def add(self, **kw):
        d = dict(vendor_name="Alpha Traders", vendor_gstin=G1, vendor_phone="9876543210", bill_no="A-001", date="2026-11-05",
                 taxable="1000", cgst="25", sgst="25", igst="0", category="Goods for resale", note="")
        d.update(kw)
        return db.add_purchase(self.conn, **d)

    def test_add_total_and_listing(self):
        pid = self.add()
        p = db.get_purchase(self.conn, pid)
        self.assertEqual((p["total"], p["vendor_phone"]), (D("1050.00"), "919876543210"))
        self.add(bill_no="A-002", date="2026-12-01")
        self.assertEqual(len(db.list_purchases(self.conn, *db.month_range("2026-11"))), 1)
        self.assertEqual(len(db.list_purchases(self.conn, category="Rent")), 0)

    def test_validation_and_duplicates(self):
        self.add()
        with self.assertRaises(ValueError):
            self.add(bill_no="a-001")  # same vendor bill
        with self.assertRaises(ValueError):
            self.add(bill_no="B", igst="5")  # igst with cgst/sgst
        with self.assertRaises(ValueError):
            self.add(bill_no="B", vendor_gstin="BAD")
        with self.assertRaises(ValueError):
            self.add(bill_no="B", taxable="x")
        self.add(bill_no="NOGST", vendor_gstin="")  # unregistered vendor is fine

    def test_edit_and_delete(self):
        pid = self.add()
        db.update_purchase(self.conn, pid, "Alpha", G1, "", "A-001", "2026-11-05", "2000", "50", "50", "0", "Rent", "x")
        self.assertEqual(db.get_purchase(self.conn, pid)["total"], D("2100.00"))
        db.delete_purchase(self.conn, pid)
        self.assertIsNone(db.get_purchase(self.conn, pid))

    def test_purchase_register_and_client_pack(self):
        self.add()
        db.create_invoice(self.conn, self.local, "2026-11-01", [item()])
        raw = exports.purchase_register(self.conn, "2026-11")
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(rows[-1][0], "TOTAL")
        self.assertEqual(rows[-1][9], "1050.00")
        z = zipfile.ZipFile(io.BytesIO(exports.client_pack(self.conn, "2026-11")))
        self.assertEqual(set(z.namelist()), {"sales-register-2026-11.csv", "sales-register-2026-11.xlsx", "purchase-register-2026-11.csv",
                                             "gst-liability-2026-11.csv", "payments.csv", "invoices.csv"})


if __name__ == "__main__":
    unittest.main()
