"""The invoice form shows live totals computed in the browser. They must equal what the server saves, to the paisa."""
import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal as D

import db
import gst
import templates as t
from test_invoices import Base, item


def shipped_math():
    html = t.invoice_form_page([], {}, today="2026-11-01", biz_state="Uttar Pradesh")
    return html.split("/*MATH*/")[1].split("/*ENDMATH*/")[0]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestFormMath(unittest.TestCase):
    def run_js(self, cases):
        script = ("const vm=require('vm'),fs=require('fs');const ctx={};vm.createContext(ctx);"
                  "vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';this.big=big;this.money=money;this.lineCalc=lineCalc',ctx);"
                  "const cases=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
                  "fs.writeFileSync(process.argv[3],JSON.stringify(cases.map(c=>{const r=ctx.lineCalc(c[0],c[1],c[2],c[3]);"
                  "return r?[ctx.money(r.tx),ctx.money(r.c),ctx.money(r.s),ctx.money(r.i)]:null})),'utf8')")
        with tempfile.TemporaryDirectory() as d:  # files, not env vars: Windows would mangle the rupee sign
            m, c, o = (os.path.join(d, n) for n in ("math.js", "cases.json", "out.json"))
            for path, text in ((m, shipped_math()), (c, json.dumps(cases))):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            r = subprocess.run(["node", "-e", script, m, c, o], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(o, encoding="utf-8") as fh:
                return json.load(fh)

    def test_matches_server_rounding_on_random_inputs(self):
        rng = random.Random(7)
        cases = []
        for _ in range(600):
            qty = f"{rng.randint(1, 9999)}.{rng.randint(0, 999):03d}"[: rng.choice([4, 5, 6, 7])].rstrip(".")
            rate = f"{rng.randint(0, 99999)}.{rng.randint(0, 99):02d}"
            cases.append([qty, rate, str(rng.choice([0, 5, 12, 18, 28])), rng.random() < 0.5])
        out = self.run_js(cases)
        for (qty, rate, g, inter), js in zip(cases, out):
            py = gst.calc_line(D(qty), D(rate), D(g), inter)
            fmt = lambda x: t.inr(x).join(["₹", ""])
            self.assertEqual(js, [fmt(py["taxable"]), fmt(py["cgst"]), fmt(py["sgst"]), fmt(py["igst"])], (qty, rate, g, inter))

    def test_odd_paise_goes_to_sgst_remainder_and_bad_input_is_ignored(self):
        out = self.run_js([["1", "1.00", "5", False], ["", "5", "5", False], ["1", "abc", "5", False], ["1.", "10", "18", True]])
        self.assertEqual(out[0], ["₹1.00", "₹0.03", "₹0.02", "₹0.00"])  # same as the server's odd-paise rule
        self.assertIsNone(out[1])
        self.assertIsNone(out[2])
        self.assertEqual(out[3], ["₹10.00", "₹0.00", "₹0.00", "₹1.80"])

    def test_indian_grouping(self):
        out = self.run_js([["1", "12345678.90", "0", False]])
        self.assertEqual(out[0][0], "₹1,23,45,678.90")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestScriptsParse(Base):
    def test_every_inline_script_is_valid_javascript(self):
        import re
        pages = {
            "invoice form": t.invoice_form_page([], {}, today="2026-11-01", biz_state="Delhi"),
            "invoice form with data": t.invoice_form_page(db.search_customers(self.conn), {"items": [{"description": "a'b\"c<"}]},
                                                          "err", "2026-11-01", [], "Delhi"),
            "bank": t.bank_page({}),
            "reconcile": t.reconcile_page({}),
        }
        for name, html in pages.items():
            scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
            self.assertTrue(scripts, name)
            for n, js in enumerate(scripts):
                with tempfile.TemporaryDirectory() as d:
                    p = os.path.join(d, "s.js")
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(js)
                    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, f"{name} script {n}: {r.stderr}")


class TestNewPages(Base):
    def test_series_and_aging(self):
        today = "2026-11-21"
        a = db.create_invoice(self.conn, self.local, "2026-11-01", [item()])  # 1417.50, due 11-16: 5 days late
        db.create_invoice(self.conn, self.local, "2026-09-01", [item(rate="100")])  # 315, due 09-16: 66 days late
        db.create_invoice(self.conn, self.local, "2026-11-20", [item(rate="100")])  # 315, due 12-05: not yet due
        db.add_payment(self.conn, a, "2026-10-15", "400", "cash")
        s = db.monthly_series(self.conn, today, 6)
        self.assertEqual([x["ym"] for x in s], ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"])
        self.assertEqual(s[3]["invoiced"], D("315.00"))
        self.assertEqual(s[5]["invoiced"], D("1732.50"))
        self.assertEqual(s[4]["collected"], D("400.00"))
        ag = {x["label"]: (x["amount"], x["count"]) for x in db.aging(self.conn, today)}
        self.assertEqual(ag["Not yet due"], (D("315.00"), 1))
        self.assertEqual(ag["1-15 days late"], (D("1017.50"), 1))
        self.assertEqual(ag["Over 60 days"], (D("315.00"), 1))
        self.assertEqual(sum(v[0] for v in ag.values()), db.dashboard(self.conn, today)["outstanding"])

    def test_series_crosses_year_boundary(self):
        s = db.monthly_series(self.conn, "2027-02-10", 4)
        self.assertEqual([x["ym"] for x in s], ["2026-11", "2026-12", "2027-01", "2027-02"])

    def test_dashboard_and_form_render(self):
        db.create_invoice(self.conn, self.local, "2026-09-01", [item()])
        today = "2026-11-21"
        biz = db.get_business(self.conn)
        html = t.dashboard_page(db.dashboard(self.conn, today), db.list_invoices(self.conn, today=today), biz,
                                db.monthly_series(self.conn, today), db.aging(self.conn, today),
                                db.list_invoices(self.conn, status="overdue", today=today))
        for needle in ("<svg class='chart'", "Who owes you", "Needs attention", "/remind"):
            self.assertIn(needle, html)
        empty = t.dashboard_page(db.dashboard(self.conn, "2030-01-01"), [], biz, db.monthly_series(self.conn, "2030-01-01"),
                                 db.aging(self.conn, "2030-01-01"), [])
        self.assertIn("Nothing is overdue", empty)

    def test_nav_marks_current_page_and_hides_owner_links_from_staff(self):
        t._ctx.role, t._ctx.user, t._ctx.path = "owner", "Owner", "/invoices/5"
        html = t.layout("x", "")
        self.assertEqual(html.count("aria-current"), 1)
        self.assertRegex(html, r"<a href='/invoices' class='on' aria-current='page'>")  # detail page keeps "Invoices" lit
        self.assertIn("Exports", html)
        t._ctx.role, t._ctx.path = "staff", "/invoices/new"
        html = t.layout("x", "")
        self.assertNotIn("Exports", html)
        self.assertNotIn("Profile", html)
        t._ctx.role = "owner"


if __name__ == "__main__":
    unittest.main()
