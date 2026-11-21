import io
import unittest
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal as D

import db
import tally
from test_invoices import Base, item


class TestTally(Base):
    def setUp(self):
        super().setUp()
        self.a = db.create_invoice(self.conn, self.local, "2026-11-01", [item(), item(rate="101.01", gst_rate="18")])
        self.b = db.create_invoice(self.conn, self.far, "2026-11-05", [item(gst_rate="12")])  # interstate -> IGST
        x = db.create_invoice(self.conn, self.local, "2026-11-06", [item()])
        db.cancel_invoice(self.conn, x, "dup")
        db.create_invoice(self.conn, self.local, "2026-12-01", [item()])  # other month
        db.add_payment(self.conn, self.a, "2026-11-10", "500", "cash")
        db.add_payment(self.conn, self.b, "2026-11-11", "100", "upi")
        db.add_purchase(self.conn, "Alpha & Sons <Traders>", "09ABCDE1234F1Z5", "", "A-1", "2026-11-03", "1000", "25", "25", "0", "Rent")
        db.add_purchase(self.conn, "Beta Foods", "07ABCDE1234F1Z5", "", "B-1", "2026-11-04", "500", "0", "0", "25", "Goods for resale")

    def parse(self):
        masters, vouchers, counts = tally.export(self.conn, "2026-11", "Sweet House")
        return ET.fromstring(masters), ET.fromstring(vouchers), counts

    def test_counts_and_cancelled_excluded(self):
        _, v, counts = self.parse()
        self.assertEqual(counts, {"sales": 2, "purchases": 2, "receipts": 2, "credit_notes": 0, "refunds": 0})
        self.assertEqual(len(v.findall(".//VOUCHER")), 6)
        numbers = [x.findtext("VOUCHERNUMBER") for x in v.findall(".//VOUCHER")]
        self.assertNotIn("BS/2026-27/0003", numbers)  # cancelled
        self.assertNotIn("BS/2026-27/0004", numbers)  # December

    def test_every_voucher_balances_to_zero(self):
        _, v, _ = self.parse()
        for vch in v.findall(".//VOUCHER"):
            amounts = [D(e.findtext("AMOUNT")) for e in vch.findall("ALLLEDGERENTRIES.LIST")]
            self.assertEqual(sum(amounts), D("0"), vch.findtext("VOUCHERNUMBER"))

    def test_sales_voucher_shape(self):
        _, v, _ = self.parse()
        s = next(x for x in v.findall(".//VOUCHER") if x.findtext("VOUCHERNUMBER") == "BS/2026-27/0001")
        inv = db.get_invoice(self.conn, self.a)
        by_name = {e.findtext("LEDGERNAME"): e for e in s.findall("ALLLEDGERENTRIES.LIST")}
        self.assertEqual(by_name["Ramesh"].findtext("ISDEEMEDPOSITIVE"), "Yes")  # customer is debited
        self.assertEqual(D(by_name["Ramesh"].findtext("AMOUNT")), -inv["total"])
        self.assertEqual(D(by_name["Sales"].findtext("AMOUNT")), inv["taxable"])
        self.assertEqual(D(by_name["Output CGST"].findtext("AMOUNT")), inv["cgst"])
        self.assertNotIn("Output IGST", by_name)
        self.assertEqual(s.findtext("DATE"), "20261101")

    def test_interstate_uses_igst_and_purchase_uses_input_ledgers(self):
        _, v, _ = self.parse()
        s2 = next(x for x in v.findall(".//VOUCHER") if x.findtext("VOUCHERNUMBER") == "BS/2026-27/0002")
        names = {e.findtext("LEDGERNAME") for e in s2.findall("ALLLEDGERENTRIES.LIST")}
        self.assertIn("Output IGST", names)
        self.assertNotIn("Output CGST", names)
        p = next(x for x in v.findall(".//VOUCHER") if x.findtext("VOUCHERNUMBER") == "A-1")
        by = {e.findtext("LEDGERNAME"): e for e in p.findall("ALLLEDGERENTRIES.LIST")}
        self.assertEqual(by["Alpha & Sons <Traders>"].findtext("ISDEEMEDPOSITIVE"), "No")  # vendor credited, special chars survive XML
        self.assertEqual(D(by["Input SGST"].findtext("AMOUNT")), D("-25.00"))

    def test_receipts_and_ledger_masters(self):
        m, v, _ = self.parse()
        r = [x for x in v.findall(".//VOUCHER") if x.get("VCHTYPE") == "Receipt"]
        banks = {x.findtext("ALLLEDGERENTRIES.LIST/LEDGERNAME") for x in r}
        self.assertEqual(banks, {"Cash", "Bank Account"})  # cash vs upi
        parents = {l.findtext("NAME"): l.findtext("PARENT") for l in m.findall(".//LEDGER")}
        self.assertEqual(parents["Ramesh"], "Sundry Debtors")
        self.assertEqual(parents["Beta Foods"], "Sundry Creditors")
        self.assertEqual(parents["Output CGST"], "Duties & Taxes")
        self.assertEqual(parents["रमेश"], "Sundry Debtors")

    def test_credit_notes_and_refunds(self):
        it = db.get_invoice(self.conn, self.a)["items"][1]["id"]  # the 2 x 101.01 @18% line
        cn = db.create_credit_note(self.conn, self.a, "2026-11-12", {it: "2"}, "Returned")
        db.add_payment(self.conn, self.a, "2026-11-13", db.get_invoice(self.conn, self.a)["outstanding"], "bank")  # settle the rest
        # a refund needs money owed back: pay the credited amount too, via a second invoice credited after payment
        db.add_payment(self.conn, self.b, "2026-11-14", db.get_invoice(self.conn, self.b)["outstanding"], "bank")
        itb = db.get_invoice(self.conn, self.b)["items"][0]["id"]
        db.create_credit_note(self.conn, self.b, "2026-11-15", {itb: "1"}, "Returned")
        db.add_refund(self.conn, self.b, "2026-11-16", "100", "cash", "part")
        _, v, counts = self.parse()
        self.assertEqual((counts["credit_notes"], counts["refunds"]), (2, 1))
        for vch in v.findall(".//VOUCHER"):
            self.assertEqual(sum(D(e.findtext("AMOUNT")) for e in vch.findall("ALLLEDGERENTRIES.LIST")), D("0"), vch.findtext("VOUCHERNUMBER"))
        c = next(x for x in v.findall(".//VOUCHER") if x.get("VCHTYPE") == "Credit Note" and x.findtext("PARTYLEDGERNAME") == "Ramesh")
        by = {e.findtext("LEDGERNAME"): e for e in c.findall("ALLLEDGERENTRIES.LIST")}
        self.assertEqual(by["Ramesh"].findtext("ISDEEMEDPOSITIVE"), "No")  # customer credited
        self.assertEqual(by["Sales"].findtext("ISDEEMEDPOSITIVE"), "Yes")  # sales reversed
        self.assertIn("Output CGST", by)
        pay = next(x for x in v.findall(".//VOUCHER") if x.get("VCHTYPE") == "Payment")
        self.assertEqual(pay.findtext("ALLLEDGERENTRIES.LIST/LEDGERNAME"), "रमेश")  # customer debited first
        receipts = [x for x in v.findall(".//VOUCHER") if x.get("VCHTYPE") == "Receipt"]
        self.assertTrue(all(D(x.findall("ALLLEDGERENTRIES.LIST")[0].findtext("AMOUNT")) < 0 for x in receipts))  # refund is not a receipt
        self.assertIsNotNone(cn)

    def test_zip_package(self):
        data, counts = tally.export_zip(self.conn, "2026-11", "Sweet House")
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertEqual(sorted(z.namelist()), ["1-ledgers.xml", "2-vouchers-2026-11.xml", "README.txt"])
        ET.fromstring(z.read("2-vouchers-2026-11.xml"))  # well-formed
        self.assertIn("TEST company", z.read("README.txt").decode())


if __name__ == "__main__":
    unittest.main()
