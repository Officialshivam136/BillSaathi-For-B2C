import unittest

import i18n


class TestTranslate(unittest.TestCase):
    def test_english_is_untouched(self):
        html = "<html lang='en'><body><a>Dashboard</a></body></html>"
        self.assertEqual(i18n.translate(html, "en"), html)
        self.assertEqual(i18n.translate(html, ""), html)

    def test_text_and_attributes(self):
        html = "<html lang='en'><title>Dashboard - BillSaathi</title><a>Dashboard</a> <button>  Save invoice </button><input placeholder='Search name or phone'></html>"
        out = i18n.translate(html, "hi")
        self.assertIn("<html lang='hi'>", out)
        self.assertIn("<title>डैशबोर्ड - BillSaathi</title>", out)
        self.assertIn(">डैशबोर्ड<", out)
        self.assertIn(">  बिल सेव करें <", out)  # the original two leading spaces and one trailing space are kept
        self.assertIn("placeholder='नाम या फ़ोन से खोजें'", out)

    def test_scripts_styles_and_legal_documents_are_never_translated(self):
        html = ("<style>a>Dashboard<b{}</style><p>Dashboard</p><script>if(a>b){x='Dashboard'}else{y=1<2}</script>"
                "<!--noxl--><div class='inv'><h2>Invoices</h2><td>Total</td></div><!--/noxl--><td>Total</td>")
        out = i18n.translate(html, "hi")
        self.assertIn("<style>a>Dashboard<b{}</style>", out)
        self.assertIn("<script>if(a>b){x='Dashboard'}else{y=1<2}</script>", out)
        self.assertIn("<!--noxl--><div class='inv'><h2>Invoices</h2><td>Total</td></div><!--/noxl-->", out)
        self.assertIn("<p>डैशबोर्ड</p>", out)
        self.assertTrue(out.endswith("<td>कुल</td>"))

    def test_unknown_text_numbers_and_names_are_left_alone(self):
        html = "<td>रमेश Kumar</td><td>1,417.50</td><td>Sharma &amp; Sons</td><td>Some sentence we have no translation for.</td>"
        self.assertEqual(i18n.translate(html, "hi"), html)

    def test_dot_separated_status_text(self):
        out = i18n.translate("<span>Partly paid · overdue</span>", "hi")
        self.assertEqual(out, "<span>आंशिक भुगतान · देर से</span>")

    def test_numbers_months_and_mixed_text(self):
        tr = lambda s: i18n.translate(f"<p>{s}</p>", "hi")[3:-4]
        self.assertEqual(tr("3 invoice(s) past due"), "3 बिल देर से")
        self.assertEqual(tr("1 inv."), "1 बिल")
        self.assertEqual(tr("November 2026"), "नवंबर 2026")
        self.assertEqual(tr("12 shown · billed ₹1,23,456.00 · outstanding ₹9,000.50"),
                         "12 दिख रहे · बिल किया ₹1,23,456.00 · बाकी ₹9,000.50")
        self.assertEqual(tr("They owe you ₹4,615.00"), "ग्राहक पर बाकी ₹4,615.00")
        self.assertEqual(tr("2 of 5"), "5 में से 2")
        self.assertEqual(tr("Owner ·"), "मालिक ·")
        # text that only looks similar is left alone
        self.assertEqual(tr("3 invoices past due, please call"), "3 invoices past due, please call")
        self.assertEqual(tr("Marchers 2026"), "Marchers 2026")

    def test_every_translation_is_real_devanagari_or_a_kept_term(self):
        for en, hi in i18n.HI.items():
            self.assertTrue(hi.strip(), en)
            self.assertTrue(any("ऀ" <= ch <= "ॿ" for ch in hi) or hi == en, f"{en!r} -> {hi!r}")

    def test_idempotent_on_already_translated_page(self):
        once = i18n.translate("<a>Dashboard</a><b>Save</b>", "hi")
        self.assertEqual(i18n.translate(once, "hi"), once)


if __name__ == "__main__":
    unittest.main()
