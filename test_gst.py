import unittest
from decimal import Decimal as D

import gst


class TestGst(unittest.TestCase):
    def test_intra_split_sums_to_tax(self):
        r = gst.calc_line(1, "100.10", 5, False)  # tax 5.005 -> 5.01
        self.assertEqual(r["cgst"] + r["sgst"], r["tax"])

    def test_odd_paise_sgst_is_remainder(self):
        r = gst.calc_line(1, "1.00", 5, False)  # tax 0.05 -> cgst 0.03, sgst 0.02
        self.assertEqual(r["cgst"], D("0.03"))
        self.assertEqual(r["sgst"], D("0.02"))

    def test_interstate_is_igst_only(self):
        r = gst.calc_line(3, "450", 5, True)
        self.assertEqual(r["igst"], D("67.50"))
        self.assertEqual(r["cgst"] + r["sgst"], 0)

    def test_zero_rate(self):
        r = gst.calc_line(2, "10", 0, False)
        self.assertEqual(r["tax"], D("0.00"))

    def test_invoice_totals_and_breakup(self):
        res = gst.calc_invoice(
            [{"qty": 1, "rate": "100", "gst_rate": 5}, {"qty": 2, "rate": "50", "gst_rate": 18}], False
        )
        self.assertEqual(res["totals"]["taxable"], D("200.00"))
        self.assertEqual(res["totals"]["total"], D("223.00"))
        self.assertEqual(set(res["breakup"]), {D("5"), D("18")})

    def test_invalid_rate_rejected(self):
        with self.assertRaises(ValueError):
            gst.calc_invoice([{"qty": 1, "rate": "1", "gst_rate": 7}], False)

    def test_fractional_qty(self):
        r = gst.calc_line("2.5", "450", 5, False)
        self.assertEqual(r["taxable"], D("1125.00"))

    def test_interstate_detection(self):
        self.assertEqual(gst.is_interstate("Uttar Pradesh", "Delhi"), (True, False))
        self.assertEqual(gst.is_interstate("Uttar Pradesh", "uttar pradesh"), (False, False))

    def test_missing_state_is_intra_and_flagged(self):
        self.assertEqual(gst.is_interstate("Uttar Pradesh", ""), (False, True))

    def test_gstin(self):
        self.assertTrue(gst.validate_gstin("09ABCDE1234F1Z5"))
        self.assertFalse(gst.validate_gstin("09ABCDE1234F1Y5"))
        self.assertFalse(gst.validate_gstin("99ABCDE1234F1Z"))
        self.assertFalse(gst.validate_gstin("45ABCDE1234F1Z5"))
        self.assertFalse(gst.validate_gstin(None))


if __name__ == "__main__":
    unittest.main()
