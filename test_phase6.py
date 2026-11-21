import io
import re
import unittest
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal as D

import qr
import quick
import words
import xlsx


class TestWords(unittest.TestCase):
    def test_examples(self):
        cases = {
            "0": "Rupees Zero Only", "1": "Rupees One Only", "19": "Rupees Nineteen Only", "21": "Rupees Twenty One Only",
            "100": "Rupees One Hundred Only", "1417.50": "Rupees One Thousand Four Hundred Seventeen and Fifty Paise Only",
            "100000": "Rupees One Lakh Only", "123456": "Rupees One Lakh Twenty Three Thousand Four Hundred Fifty Six Only",
            "10000000": "Rupees One Crore Only", "0.05": "Rupees Zero and Five Paise Only",
            "12345678.9": "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight and Ninety Paise Only",
        }
        for amount, expected in cases.items():
            self.assertEqual(words.rupees_in_words(D(amount)), expected, amount)

    def test_rounds_half_up_to_paise(self):
        self.assertEqual(words.rupees_in_words(D("1.005")), "Rupees One and One Paise Only")


class TestQr(unittest.TestCase):
    def test_reed_solomon_known_vector(self):
        # Standard worked example (HELLO WORLD, level Q, version 1): 13 data codewords -> 13 EC codewords
        data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236]
        self.assertEqual(qr.rs_remainder(data, 13), [168, 72, 22, 82, 217, 54, 156, 0, 46, 15, 180, 122, 16])

    def test_format_bits_known_values(self):
        self.assertEqual(format(qr.format_bits(0), "015b"), "101010000010010")  # level M, mask 0 (ISO 18004 table)
        self.assertEqual(format(qr.format_bits(5), "015b"), "100000011001110")  # level M, mask 5

    def test_structure(self):
        for text, version in (("A", 1), ("x" * 62, 4), ("y" * 152, 8), ("z" * 213, 10)):
            m = qr.make_qr(text)
            n = len(m)
            self.assertEqual(n, 17 + 4 * version, text[:3])
            for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):  # three finder patterns
                self.assertTrue(all(m[r0][c0 + i] and m[r0 + 6][c0 + i] and m[r0 + i][c0] and m[r0 + i][c0 + 6] for i in range(7)))
                self.assertFalse(m[r0 + 1][c0 + 1] or m[r0 + 1][c0 + 5])  # ring inside is light
                self.assertTrue(m[r0 + 3][c0 + 3])  # dark centre
            self.assertTrue(m[n - 8][8])  # dark module
            self.assertTrue(all(m[6][i] == (i % 2 == 0) for i in range(8, n - 8)))  # timing

    def test_limits_and_svg(self):
        with self.assertRaises(ValueError):
            qr.make_qr("x" * 214)
        svg = qr.to_svg(qr.make_qr("upi://pay?pa=a@b&am=1"))
        self.assertTrue(svg.startswith("<svg") and "<path" in svg and svg.endswith("</svg>"))
        ET.fromstring(svg)  # well-formed

    def test_deterministic(self):
        self.assertEqual(qr.make_qr("same"), qr.make_qr("same"))


class TestXlsx(unittest.TestCase):
    NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    def test_package_is_well_formed_and_values_round_trip(self):
        data = xlsx.workbook([("Sales", [["Invoice", "रमेश & <Co>", "Total"], ["BS/1", "x\x01y", D("1417.50")], ["TOTAL", "", D("1417.50")]]),
                              ("Sales", [["a"], [5]])])
        z = zipfile.ZipFile(io.BytesIO(data))
        for name in z.namelist():
            ET.fromstring(z.read(name))  # every part is valid XML
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") for s in wb.iter("{%s}sheet" % self.NS["m"])]
        self.assertEqual(names, ["Sales", "Sales 2"])  # duplicate names made unique
        s1 = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        texts = ["".join(t.itertext()) for t in s1.iter("{%s}is" % self.NS["m"])]
        self.assertIn("रमेश & <Co>", texts)
        self.assertIn("xy", texts)  # control character stripped
        nums = [c.find("m:v", self.NS).text for c in s1.iter("{%s}c" % self.NS["m"]) if c.find("m:v", self.NS) is not None]
        self.assertEqual(nums, ["1417.50", "1417.50"])

    def test_sheet_name_rules(self):
        data = xlsx.workbook([("A/B:C*?[x]" + "z" * 40, [["h"]])])
        wb = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("xl/workbook.xml"))
        name = next(wb.iter("{%s}sheet" % self.NS["m"])).get("name")
        self.assertLessEqual(len(name), 31)
        self.assertFalse(re.search(r"[\[\]:*?/\\]", name))

    def test_empty(self):
        zipfile.ZipFile(io.BytesIO(xlsx.workbook([])))  # does not raise


class TestQuickEntry(unittest.TestCase):
    CUSTOMERS = [{"id": 1, "name": "Ramesh Kumar"}, {"id": 2, "name": "Hotel Aman"}, {"id": 3, "name": "Anita Gupta"}]
    CATALOG = [{"description": "Kaju Barfi", "hsn": "1704", "rate": D("900"), "gst_rate": D("5")},
               {"description": "Samosa", "hsn": "1905", "rate": D("20"), "gst_rate": D("5")},
               {"description": "Cold Drink", "hsn": "2202", "rate": D("40"), "gst_rate": D("12")}]

    def p(self, text):
        return quick.parse(text, self.CUSTOMERS, self.CATALOG)

    def test_spec_example(self):
        r = self.p("Ramesh, 3 kg barfi at 450")
        self.assertEqual(r["customer_id"], 1)
        self.assertEqual(r["items"], [{"description": "Kaju Barfi", "hsn": "1704", "qty": "3", "rate": "450", "gst_rate": "5"}])

    def test_several_items_and_formats(self):
        r = self.p("Hotel Aman: 2 samosa at 20, 5 cold drink @ 45, barfi 1.5 kg at 1,200")
        self.assertEqual(r["customer_id"], 2)
        self.assertEqual([(i["description"], i["qty"], i["rate"], i["gst_rate"]) for i in r["items"]],
                         [("Samosa", "2", "20", "5"), ("Cold Drink", "5", "45", "12"), ("Kaju Barfi", "1.5", "1200", "5")])

    def test_rate_from_saved_item_and_explicit_gst(self):
        r = self.p("Anita 4 samosa")
        self.assertEqual((r["customer_id"], r["items"][0]["rate"]), (3, "20"))
        r = self.p("bill Ramesh 2 pcs dress at 500 gst 18")
        self.assertEqual((r["customer_id"], r["items"][0]["gst_rate"], r["items"][0]["description"]), (1, "18", "Dress"))

    def test_typo_in_names_and_word_boundaries(self):
        r = self.p("Rameshh, 2 kaju barfee at 800, 3 dates at 100")
        self.assertEqual(r["customer_id"], 1)
        self.assertEqual(r["items"][0]["description"], "Kaju Barfi")
        self.assertEqual(r["items"][1]["description"], "Dates")  # "dates" is not split at the "at" inside it

    def test_grams_converted_with_warning(self):
        r = self.p("Ramesh 500 g barfi at 900")
        self.assertEqual((r["items"][0]["qty"], r["items"][0]["rate"]), ("0.5", "900"))
        self.assertTrue(any("0.5 kg" in w for w in r["warnings"]))

    def test_warnings_not_guesses(self):
        r = self.p("Nobody Known, 2 widget at 10")
        self.assertIsNone(r["customer_id"])
        self.assertTrue(any("No customer matches" in w for w in r["warnings"]))
        self.assertTrue(any("GST assumed 5%" in w for w in r["warnings"]))
        r = self.p("hello there")
        self.assertEqual(r["items"], [])
        r = self.p("")
        self.assertEqual((r["items"], r["customer_id"]), ([], None))
        r = self.p("Ramesh, 3 widget")  # no price anywhere
        self.assertEqual(r["items"], [])
        self.assertTrue(any("No price given" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
