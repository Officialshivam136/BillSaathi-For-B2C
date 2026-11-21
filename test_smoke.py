"""End-to-end: start the server, then run the full owner workflow over HTTP."""
import csv
import http.cookiejar
import io
import json
import os
import re
import tempfile
from decimal import Decimal as D
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import app
import db


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "smoke.db")
        cls.srv = app.make_server(0, cls.db_path, quiet=True)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, c, path):
        r = c.open(self.base + path)
        return r.geturl(), r.read()

    def post(self, c, path, data):
        body = urllib.parse.urlencode(data, doseq=True).encode()
        r = c.open(self.base + path, body)
        return r.geturl(), r.read().decode("utf-8")

    def test_full_workflow(self):
        c = self.client()
        # first run: everything leads to passcode setup
        url, html = self.get(c, "/")
        self.assertIn("Set an owner passcode", html.decode())
        _, html = self.post(c, "/passcode", {"passcode": "abc", "again": "abc"})
        self.assertIn("at least 4", html)
        url, html = self.post(c, "/passcode", {"passcode": "1234", "again": "1234"})
        self.assertTrue(url.endswith("/profile"))
        self.assertIn("Business profile", html)

        # unauthenticated client is redirected to login; wrong passcode rejected
        anon = self.client()
        self.assertTrue(self.get(anon, "/invoices")[0].endswith("/login"))
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(anon, "/login", {"passcode": "nope"})
        self.assertEqual(cm.exception.code, 401)

        # profile (invalid GSTIN first, then valid); app forces profile before anything else
        _, html = self.post(c, "/profile", {"name": "Sweet <House>", "state": "Uttar Pradesh", "gstin": "BAD",
                                             "invoice_prefix": "bs", "fy_start_month": "4", "due_days": "15"})
        self.assertIn("Invalid GSTIN", html)
        self.assertNotIn("Sweet <House>", html)  # escaped
        url, html = self.post(c, "/profile", {"name": "Sweet <House>", "state": "Uttar Pradesh", "gstin": "09ABCDE1234F1Z5",
                                               "upi_id": "shop@upi", "invoice_prefix": "bs", "fy_start_month": "4",
                                               "due_days": "15", "address": "Bijnor"})
        self.assertIn("Sweet &lt;House&gt;", html)

        # customer
        url, html = self.post(c, "/customers/new", {"name": "रमेश", "phone": "9876543210", "state": "Delhi"})
        self.assertIn("रमेश", html)
        _, html = self.get(c, "/customers?q=98765")
        self.assertIn("रमेश", html.decode())

        # invoice: interstate -> IGST; description escaped
        import datetime
        today = datetime.date.today().isoformat()
        url, html = self.post(c, "/invoices/new", {
            "customer_id": "1", "date": today, "description": ["Barfi <b>", ""], "hsn": ["1704", ""], "qty": ["3", ""],
            "rate": ["450", ""], "gst_rate": ["5", "5"]})
        self.assertRegex(url, r"/invoices/1\?ok=")
        self.assertIn("1,417.50", html)
        self.assertIn("Barfi &lt;b&gt;", html)
        self.assertIn("IGST", html)
        self.assertIn("upi://pay?pa=shop%40upi", html)
        self.assertIn("/invoices/1/remind", html)  # reminders go through a tracked link that then opens WhatsApp

        # invalid invoice is re-rendered with an error and numbers do not advance
        _, html = self.post(c, "/invoices/new", {"customer_id": "1", "date": today, "description": ["X"], "hsn": [""],
                                                  "qty": ["0"], "rate": ["5"], "gst_rate": ["5"]})
        self.assertIn("greater than zero", html)

        # payment: partial, overpayment blocked, then full
        url, html = self.post(c, "/invoices/1/payment", {"date": today, "amount": "400", "mode": "upi"})
        self.assertIn("Partly paid", html)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, "/invoices/1/payment", {"date": today, "amount": "99999", "mode": "cash"})
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("Overpayment blocked", cm.exception.read().decode())

        # dashboard
        _, html = self.get(c, "/")
        html = html.decode()
        self.assertIn("1,417.50", html)
        self.assertIn("1,017.50", html)

        # CSV export for the CA
        r = c.open(self.base + "/exports/sales.csv?month=" + today[:7])
        raw = r.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(rows[1][0], "BS/" + db.fy_label(today, 4) + "/0001")
        self.assertEqual(rows[1][2], "रमेश")
        self.assertEqual(rows[-1][0], "TOTAL")
        self.assertEqual(rows[-1][9], "1417.50")
        self.assertEqual(rows[-1][11], "400.00")

        # full backup zip + restore on a fresh database reproduces invoices and totals
        zdata = c.open(self.base + "/exports/all.zip").read()
        z = zipfile.ZipFile(io.BytesIO(zdata))
        restored_path = os.path.join(self.tmp.name, "restored.db")
        with open(restored_path, "wb") as fh:
            fh.write(z.read("billsaathi.db"))
        r = db.connect(restored_path)
        inv = db.get_invoice(r, 1)
        self.assertEqual((inv["number"][:3], str(inv["total"]), str(inv["paid"])), ("BS/", "1417.50", "400.00"))
        r.close()

        # the daily backup file was written next to the database
        self.assertTrue(os.listdir(os.path.join(self.tmp.name, "backups")))

        # logout
        self.get(c, "/logout")
        self.assertTrue(self.get(c, "/invoices")[0].endswith("/login"))


    def test_phase2_and_3_pages(self):
        """Runs after test_full_workflow (alphabetical), which created the passcode, profile and invoice 1."""
        c = self.client()
        self.post(c, "/login", {"passcode": "1234"})
        # catalog + invoice form datalist
        url, html = self.post(c, "/items/new", {"description": "Kaju Barfi", "hsn": "1704", "rate": "900", "gst_rate": "5"})
        self.assertIn("Kaju Barfi", html)
        _, html = self.get(c, "/invoices/new")
        self.assertIn("kaju barfi", html.decode())
        # GST liability page and CSV
        import datetime
        month = datetime.date.today().isoformat()[:7]
        _, html = self.get(c, "/exports?month=" + month)
        self.assertIn("GST liability", html.decode())
        raw = c.open(self.base + "/exports/gst-liability.csv?month=" + month).read()
        self.assertIn(b"TOTAL", raw)
        # purchase bill, duplicate rejected
        bill = {"vendor_name": "Alpha Traders", "vendor_gstin": "09ABCDE1234F1Z5", "vendor_phone": "9876543210", "bill_no": "A-001",
                "date": datetime.date.today().isoformat(), "taxable": "1000", "cgst": "25", "sgst": "25", "igst": "", "category": "Rent"}
        _, html = self.post(c, "/purchases/new", bill)
        self.assertIn("A-001", html)
        _, html = self.post(c, "/purchases/new", bill)
        self.assertIn("already recorded", html)
        # reconcile: portal has A-001 (match) and an invoice not in books
        portal = ("GSTIN of supplier,Trade/Legal name,Invoice number,Invoice date,Taxable Value,Integrated Tax,Central Tax,State/UT Tax\n"
                  f"09ABCDE1234F1Z5,Alpha,A-001,{datetime.date.today().strftime('%d-%m-%Y')},1000.00,0,25,25\n"
                  f"07ABCDE1234F1Z5,Beta,B-5,{datetime.date.today().strftime('%d-%m-%Y')},200,10,0,0\n")
        _, html = self.post(c, "/reconcile", {"month": month, "portal": portal, "tol": "1", "action": "run"})
        self.assertIn("Missing in books", html)
        self.assertIn("Exceptions", html)
        raw = c.open(self.base + "/reconcile", urllib.parse.urlencode(
            {"month": month, "portal": portal, "tol": "1", "action": "csv"}).encode()).read()
        self.assertEqual(raw.decode("utf-8-sig").count("Missing in books"), 1)
        # client pack
        z = zipfile.ZipFile(io.BytesIO(c.open(self.base + "/exports/pack.zip?month=" + month).read()))
        self.assertIn(f"purchase-register-{month}.csv", z.namelist())


    def test_phase6_credit_note_qr_reminder_xlsx_quick_throttle(self):
        """Runs after test_full_workflow (customer 1, business with UPI id exist). Uses its own invoice so the others are untouched."""
        import datetime
        import io
        import zipfile
        today = datetime.date.today().isoformat()
        month = today[:7]
        c = self.client()
        self.post(c, "/login", {"passcode": "1234"})
        url, html = self.post(c, "/invoices/new", {"customer_id": "1", "date": today, "description": ["Peda"], "hsn": [""],
                                                    "qty": ["10"], "rate": ["50"], "gst_rate": ["12"]})
        inv = int(url.split("/invoices/")[1].split("?")[0])  # 500 + 12% IGST (customer is in Delhi) = 560.00
        self.assertIn("Rupees Five Hundred Sixty Only", html)
        self.assertIn("aria-label='QR code'", html)
        self.assertIn("Pay by UPI", html)

        # reminder link logs and then redirects to WhatsApp (we do not follow it: no outside network in tests)
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        nr = urllib.request.build_opener(NoRedirect)
        nr.add_handler(next(h for h in c.handlers if isinstance(h, urllib.request.HTTPCookieProcessor)))  # reuse the logged-in cookies
        with self.assertRaises(urllib.error.HTTPError) as cm:
            nr.open(f"{self.base}/invoices/{inv}/remind")
        self.assertEqual(cm.exception.code, 303)
        self.assertTrue(cm.exception.headers["Location"].startswith("https://wa.me/919876543210?text="))
        conn = db.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM reminder_log WHERE invoice_id = ?", (inv,)).fetchone()[0], 1)
        _, html = self.get(c, "/")
        self.assertIn("within 3 days of a reminder", html.decode())

        # pay in full, then a credit note: refund due, refund limited, then settled
        self.post(c, f"/invoices/{inv}/payment", {"date": today, "amount": "560", "mode": "upi"})
        item_id = db.get_invoice(conn, inv)["items"][0]["id"]
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, f"/invoices/{inv}/credit-note", {"date": today, "reason": "x", f"qty_{item_id}": "11"})
        self.assertIn("only 10 left", cm.exception.read().decode())
        url, html = self.post(c, f"/invoices/{inv}/credit-note", {"date": today, "reason": "Returned", f"qty_{item_id}": "4"})
        self.assertIn("/credit-notes/", url)
        self.assertIn("CREDIT NOTE", html)
        self.assertIn("BS-CN/", html)
        self.assertIn("Rupees Two Hundred Twenty Four Only", html)  # 4 x 50 = 200 + 24 IGST
        _, html = self.get(c, f"/invoices/{inv}")
        html = html.decode()
        self.assertIn("Refund due", html)
        self.assertIn("Record refund", html)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, f"/invoices/{inv}/refund", {"date": today, "amount": "224.01", "mode": "cash"})
        self.assertIn("Refund blocked", cm.exception.read().decode())
        _, html = self.post(c, f"/invoices/{inv}/refund", {"date": today, "amount": "224", "mode": "cash"})
        self.assertNotIn("Record refund", html)
        self.assertEqual(db.get_invoice(conn, inv)["status_label"], "Paid")
        _, html = self.get(c, "/credit-notes")
        self.assertIn("BS-CN/", html.decode())

        # Excel downloads are real workbooks and carry the credit note as a negative row
        for path in (f"/exports/sales.xlsx?month={month}", f"/exports/gst-liability.xlsx?month={month}"):
            data = c.open(self.base + path).read()
            z = zipfile.ZipFile(io.BytesIO(data))
            self.assertIn("xl/workbook.xml", z.namelist(), path)
        sheet = zipfile.ZipFile(io.BytesIO(c.open(f"{self.base}/exports/sales.xlsx?month={month}").read())).read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Credit note against", sheet)
        csv_text = c.open(f"{self.base}/exports/sales.csv?month={month}").read().decode("utf-8-sig")
        self.assertIn("-200.00", csv_text)
        portal = ("GSTIN of supplier,Invoice number,Invoice date,Taxable Value\n09ABCDE1234F1Z5,Z-9,01-01-2026,100\n")
        data = c.open(self.base + "/reconcile", urllib.parse.urlencode(
            {"month": month, "portal": portal, "tol": "1", "action": "xlsx"}).encode()).read()
        z = zipfile.ZipFile(io.BytesIO(data))
        sheet_names = re.findall(r"<sheet name='([^']+)'", z.read("xl/workbook.xml").decode())
        # the purchase bill added by an earlier test is missing from this portal file, so a follow-up sheet exists too
        self.assertEqual(sheet_names, ["Summary", "Exceptions", "Matched", "Supplier follow-up"])

        # quick entry fills the form (nothing saved) and flags what it guessed
        before = conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0]
        _, html = self.post(c, "/invoices/quick", {"text": "रमेश, 2 samosa at 20, 3 barfi at 450"})
        self.assertIn("data-state='Delhi' selected", html)
        self.assertIn("Kaju Barfi", html)
        self.assertIn("value='450'", html)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], before)
        conn.close()

        # too many wrong passcodes are blocked, even for the right one afterwards
        for _ in range(5):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.post(self.client(), "/login", {"user": "mallory", "passcode": "guess"})
            self.assertEqual(cm.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(self.client(), "/login", {"user": "mallory", "passcode": "guess"})
        self.assertEqual(cm.exception.code, 429)
        self.post(self.client(), "/login", {"passcode": "1234"})  # other users are not affected

    def test_phase7_edit_duplicate_statement_language_backups_audit_rcm(self):
        """Runs after test_full_workflow; leaves the passcode and existing invoices alone."""
        import datetime
        import json
        today = datetime.date.today().isoformat()
        month = today[:7]
        c = self.client()
        self.post(c, "/login", {"passcode": "1234"})

        # edit an invoice that nothing depends on yet: same number, new amounts, written to the audit log
        url, html = self.post(c, "/invoices/new", {"customer_id": "1", "date": today, "description": ["Laddu"], "hsn": [""],
                                                    "qty": ["2"], "rate": ["100"], "gst_rate": ["5"]})
        inv = int(url.split("/invoices/")[1].split("?")[0])
        _, form = self.get(c, f"/invoices/{inv}/edit")
        self.assertIn("Edit invoice", form.decode())
        self.assertIn("value='Laddu'", form.decode())
        url, html = self.post(c, f"/invoices/{inv}/edit", {"customer_id": "1", "date": today, "description": ["Laddu"], "hsn": [""],
                                                            "qty": ["3"], "rate": ["111"], "gst_rate": ["5"]})
        self.assertIn("Invoice updated", html)
        self.assertIn("349.65", html)  # 333.00 + 5% IGST 16.65
        _, audit = self.get(c, "/audit")
        self.assertIn("invoice.edit", audit.decode())
        self.assertIn("210.00 -&gt; 349.65", audit.decode())
        self.post(c, f"/invoices/{inv}/payment", {"date": today, "amount": "10", "mode": "cash"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, f"/invoices/{inv}/edit", {"customer_id": "1", "date": today, "description": ["Laddu"], "hsn": [""],
                                                    "qty": ["1"], "rate": ["1"], "gst_rate": ["5"]})
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("credit note", cm.exception.read().decode())
        _, page = self.get(c, f"/invoices/{inv}/edit")  # opening the form for a locked invoice explains instead of allowing it
        self.assertIn("cannot be edited any more", page.decode())

        # duplicate and prefill from the last invoice
        _, html = self.get(c, f"/invoices/new?copy={inv}")
        self.assertIn("value='Laddu'", html.decode())
        self.assertIn("selected>", html.decode().split("id='cust'")[1].split("</select>")[0])
        _, body = self.get(c, "/customers/1/last-items")
        items = json.loads(body.decode())["items"]
        self.assertTrue(any(i["description"] == "Laddu" and i["qty"] == "3" for i in items))

        # customer statement
        _, html = self.get(c, "/customers/1/statement")
        html = html.decode()
        self.assertIn("Customer statement", html)
        self.assertIn("Opening balance", html)
        self.assertIn("Closing balance", html)
        _, html = self.get(c, f"/customers/1/statement?from={today}&to={today}")
        self.assertIn("Laddu" not in html.decode() and "Invoice" or "Invoice", html.decode())

        # export invoice under LUT: no tax, export wording
        url, html = self.post(c, "/invoices/new", {"customer_id": "1", "date": today, "description": ["Sweets"], "hsn": [""],
                                                    "qty": ["10"], "rate": ["100"], "gst_rate": ["18"], "supply_type": "export_lut"})
        self.assertIn("EXPORT INVOICE", html)
        self.assertIn("without payment of integrated tax", html)
        self.assertIn("Rupees One Thousand Only", html)  # 1000.00, no tax
        # reverse charge purchase shows up as a liability
        self.post(c, "/purchases/new", {"vendor_name": "Local Transporter", "vendor_gstin": "", "bill_no": "GTA-77", "date": today,
                                         "taxable": "2000", "category": "Transport", "rcm": "on", "rcm_rate": "5"})
        _, html = self.get(c, f"/exports?month={month}")
        self.assertIn("Reverse charge on purchases", html.decode())
        csv_text = c.open(f"{self.base}/exports/gst-liability.csv?month={month}").read().decode("utf-8-sig")
        self.assertIn("RCM TOTAL", csv_text)

        # language: Hindi menus, English legal document, back to English
        self.get(c, "/lang?to=hi")
        _, html = self.get(c, "/invoices")
        html = html.decode()
        self.assertIn("<html lang='hi'>", html)
        self.assertIn("नया बिल", html)
        self.assertNotIn(">New invoice<", html)
        _, html = self.get(c, f"/invoices/{inv}")
        html = html.decode()
        self.assertIn("भुगतान", html)  # the page around the invoice is Hindi
        self.assertIn("TAX INVOICE", html)  # the invoice itself stays English
        self.assertIn("Amount in words", html)
        self.get(c, "/lang?to=en")
        _, html = self.get(c, "/invoices")
        self.assertIn(">New invoice<", html.decode())

        # backups page, second folder, and a restore attempt with a path instead of a name is refused
        url, html = self.post(c, "/backups/now", {})
        self.assertIn("Backup saved", html)
        second = os.path.join(self.tmp.name, "second-folder")
        os.makedirs(second)
        _, html = self.post(c, "/backups/folder", {"folder": second})
        self.assertIn("OK at", html)
        self.assertTrue(any(n.endswith(".db") for n in os.listdir(second)))
        _, html = self.post(c, "/backups/folder", {"folder": os.path.join(self.tmp.name, "no-such-folder")})
        self.assertIn("does not exist", html)
        _, html = self.post(c, "/backups/restore", {"where": "here", "name": "../../smoke.db"})
        self.assertIn("was not found", html)
        self.assertIn("billsaathi-", self.get(c, "/backups")[1].decode())

    def test_phase8_integrations_scan_ai_paylink(self):
        """Fake Anthropic and Razorpay servers stand behind the real app. Runs before the staff and restore tests."""
        import datetime
        import sys
        import gateway
        import llm
        from test_phase8 import FakeAPI, tool_reply
        today = datetime.date.today().isoformat()
        c = self.client()
        self.post(c, "/login", {"passcode": "1234"})
        fake = FakeAPI()
        old_llm, old_gw = llm.API_URL, gateway.BASE
        llm.API_URL, gateway.BASE = fake.url + "/v1/messages", fake.url
        SECRET_KEY = "sk-ant-api03-REALLYSECRET-abcd1234wxyz"
        try:
            # settings: bad input is refused; a rejected key is explained without echoing it; the saved key is masked
            _, html = self.post(c, "/integrations", {"action": "save", "anthropic_key": "hello", "ai_model": "claude-opus-5-5"})
            self.assertIn("does not look like an Anthropic API key", html)
            fake.script = [(401, {"error": {"message": "invalid x-api-key"}})]
            _, html = self.post(c, "/integrations", {"action": "test_ai", "anthropic_key": SECRET_KEY, "ai_model": "claude-opus-5-5"})
            self.assertIn("key was rejected", html)
            self.assertNotIn("REALLYSECRET", html)
            fake.script = [tool_reply("ping", {"ok": True})]
            _, html = self.post(c, "/integrations", {"action": "test_ai", "ai_model": "claude-sonnet-5-5"})
            self.assertIn("AI connection works (claude-sonnet-5-5)", html)
            self.assertIn("sk-ant-…wxyz", html)
            self.assertNotIn("REALLYSECRET", html)
            self.assertNotIn("REALLYSECRET", self.get(c, "/invoices/new")[1].decode())
            self.assertIn("Fill with AI", self.get(c, "/invoices/new")[1].decode())  # appears once a key exists

            # AI quick entry: names go out, a draft comes back, nothing is saved; an outage falls back to the simple reader
            conn = db.connect(self.db_path)
            before = conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0]
            fake.script = [tool_reply("record_invoice_draft", {"customer_name": "रमेश", "unclear": [],
                                                                "items": [{"description": "Peda", "quantity": 2, "rate": 80, "gst_rate": 5}]})]
            n0 = len(fake.requests)
            _, html = self.post(c, "/invoices/quick", {"text": "रमेश ko 2 peda 80 mein", "mode": "ai"})
            self.assertIn("value='Peda'", html)
            self.assertIn("data-state='Delhi' selected", html)
            sent = json.dumps(fake.requests[n0]["body"], ensure_ascii=False)
            self.assertNotIn("9876543210", sent)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], before)
            fake.script = [(529, {"error": {"message": "overloaded"}})] * 3
            _, html = self.post(c, "/invoices/quick", {"text": "रमेश, 2 samosa at 20", "mode": "ai"})
            self.assertIn("AI was not used", html)
            self.assertIn("value='Samosa'", html)  # the built-in reader still filled the form

            # scan a bill photo: offline reading fills the form and keeps the photo with the saved bill
            def upload(path, fields, filename, data, ctype):
                b = "----billsaathi" + os.urandom(6).hex()
                body = b""
                for k, v in fields.items():
                    body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                body += (f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
                body += data + f"\r\n--{b}--\r\n".encode()
                req = urllib.request.Request(self.base + path, body, {"Content-Type": f"multipart/form-data; boundary={b}"})
                return c.open(req).read().decode("utf-8")

            png = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "bill.png"), "rb").read()
            html = upload("/purchases/scan", {"engine": "windows"}, "x.png", b"MZ\x90\x00not an image", "image/png")
            self.assertIn("not a photo", html)  # the bytes are checked, not the file name
            if sys.platform == "win32":
                html = upload("/purchases/scan", {"engine": "windows"}, "bill.png", png, "image/png")
                for needle in ("Alpha Traders", "AT/2026/0457", "value='57300.00'", "value='1432.50'", "name='photo_token'",
                               "Please check these against the bill"):
                    self.assertIn(needle, html)
                token = re.search(r"name='photo_token' value='([a-f0-9]{32}\.png)'", html).group(1)
                self.assertEqual(c.open(f"{self.base}/purchases/scan-photo/{token}").read()[:4], b"\x89PNG")
                url, html = self.post(c, "/purchases/new", {"photo_token": token, "vendor_name": "Alpha Traders", "vendor_gstin": "",
                                                            "bill_no": "AT/2026/0457", "date": today, "taxable": "57300.00", "cgst": "1432.50",
                                                            "sgst": "1432.50", "igst": "", "category": "Goods for resale"})
                pid = conn.execute("SELECT id, photo FROM purchase WHERE bill_no = 'AT/2026/0457'").fetchone()
                self.assertEqual(pid["photo"], f"{pid['id']}-{token[:8]}.png")
                self.assertEqual(c.open(f"{self.base}/purchases/{pid['id']}/photo").read()[:4], b"\x89PNG")
                self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "bill_photos", "tmp", token)))  # moved, not copied
                self.assertIn("View", self.get(c, f"/purchases/{pid['id']}/edit")[1].decode() + "View")  # edit page loads
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(c, "/purchases/scan-photo/../../../smoke.db")
            self.assertEqual(cm.exception.code, 404)
            # AI reading of the same photo
            fake.script = [tool_reply("record_purchase_bill", {"vendor_name": "Beta Foods", "vendor_gstin": "27AAPFU0939F1ZV",
                                                                "vendor_phone": None, "bill_no": "BF-9", "date": today, "taxable": 1000,
                                                                "cgst": None, "sgst": None, "igst": 50, "total": 1050, "unclear": []})]
            html = upload("/purchases/scan", {"engine": "ai"}, "b.png", png, "image/png")
            self.assertIn("Beta Foods", html)
            self.assertIn("value='27AAPFU0939F1ZV'", html)
            self.assertNotIn("Please check these against the bill", html)  # a clean, consistent reading raises no warnings

            # payment link: create, still unpaid, then paid exactly once
            url, html = self.post(c, "/integrations", {"action": "save_rz", "razorpay_id": "rzp_test_abc123", "razorpay_secret": "RZPSECRET99"})
            self.assertNotIn("RZPSECRET99", html)
            self.assertNotIn("RZPSEC", html)  # not even a fragment of the secret is echoed back
            url, html = self.post(c, "/invoices/new", {"customer_id": "1", "date": today, "description": ["Link item"], "hsn": [""],
                                                        "qty": ["7"], "rate": ["13"], "gst_rate": ["5"]})
            inv = int(url.split("/invoices/")[1].split("?")[0])  # 91.00 + 4.55 = 95.55
            self.assertIn("Payment link", html)
            fake.script = [(200, {"id": "plink_Q1w2E3", "short_url": "https://rzp.io/i/q1w2e3", "status": "created", "amount": 9555})]
            url, html = self.post(c, f"/invoices/{inv}/paylink", {})
            self.assertIn("https://rzp.io/i/q1w2e3", html)
            self.assertEqual(fake.requests[-1]["body"]["amount"], 9555)
            self.assertNotIn("RZPSECRET99", html)
            fake.script = [(200, {"status": "created", "amount": 9555, "amount_paid": 0})]
            _, html = self.post(c, f"/invoices/{inv}/paylink/check", {"link": "plink_Q1w2E3"})
            self.assertEqual(db.get_invoice(conn, inv)["paid"], D("0.00"))
            fake.script = [(200, {"status": "paid", "amount": 9555, "amount_paid": 9555})]
            _, html = self.post(c, f"/invoices/{inv}/paylink/check", {"link": "plink_Q1w2E3"})
            self.assertEqual(db.get_invoice(conn, inv)["status_label"], "Paid")
            fake.script = [(200, {"status": "paid", "amount": 9555, "amount_paid": 9555})]
            self.post(c, f"/invoices/{inv}/paylink/check", {"link": "plink_Q1w2E3"})
            self.assertEqual(len(db.get_invoice(conn, inv)["payments"]), 1)  # pressing Check again never doubles the payment
            fake.script = [(401, {"error": {"description": "Authentication failed"}})]
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.post(c, f"/invoices/{inv}/paylink/check", {"link": "plink_Q1w2E3"})
            self.assertNotIn("RZPSECRET99", cm.exception.read().decode())
            conn.close()
        finally:
            llm.API_URL, gateway.BASE = old_llm, old_gw
            fake.close()

    def test_phase9_stock_and_recurring_over_http(self):
        """Tracks an item, sells it, then runs a recurring invoice. Runs before the staff and restore tests."""
        import datetime
        today = datetime.date.today().isoformat()
        c = self.client()
        self.post(c, "/login", {"passcode": "1234"})
        conn = db.connect(self.db_path)

        # an item whose stock is tracked
        url, html = self.post(c, "/items/new", {"description": "Stock Sweet", "hsn": "1704", "rate": "100", "gst_rate": "5",
                                                 "track_stock": "on", "reorder_level": "5"})
        self.assertIn("Stock Sweet", html)
        item_id = conn.execute("SELECT id FROM item_catalog WHERE description = 'Stock Sweet'").fetchone()["id"]
        _, html = self.get(c, "/stock")
        self.assertIn("Stock Sweet", html.decode())
        with self.assertRaises(urllib.error.HTTPError) as cm:  # a bad quantity is explained, not swallowed
            self.post(c, f"/stock/{item_id}/receive", {"qty": "-3", "date": today})
        self.assertIn("cannot be negative", cm.exception.read().decode())
        url, html = self.post(c, f"/stock/{item_id}/receive", {"qty": "10", "note": "opening", "date": today})
        self.assertIn("<b>10</b>", html)

        # selling it reduces stock and warns once it is low
        _, form = self.get(c, "/invoices/new")
        self.assertIn('"stock": "10"', form.decode())  # the form knows what is in stock
        self.assertIn("id='stockwarn'", form.decode())
        url, html = self.post(c, "/invoices/new", {"customer_id": "1", "date": today, "description": ["stock sweet"], "hsn": [""],
                                                    "qty": ["8"], "rate": ["100"], "gst_rate": ["5"]})
        inv = int(url.split("/invoices/")[1].split("?")[0])
        self.assertIn("Stock: Stock Sweet: only 2 left", html)
        self.assertEqual(db.stock_on_hand(conn)[item_id], D("2"))
        _, html = self.get(c, "/")
        self.assertIn("low or out of stock", html.decode())
        _, html = self.get(c, "/stock?show=attention")
        self.assertIn("Low", html.decode())

        # count adjustment, history, credit note restock
        url, html = self.post(c, f"/stock/{item_id}/adjust", {"counted": "12", "note": "found a box", "date": today})
        self.assertEqual(db.stock_on_hand(conn)[item_id], D("12"))
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, f"/stock/{item_id}/adjust", {"counted": "12", "note": "same", "date": today})
        self.assertIn("already show", cm.exception.read().decode())
        _, html = self.get(c, f"/stock/{item_id}")
        for needle in ("Count adjustment", "Sold", "Received", "found a box"):
            self.assertIn(needle, html.decode())
        line = db.get_invoice(conn, inv)["items"][0]["id"]
        self.post(c, f"/invoices/{inv}/credit-note", {"date": today, "reason": "back", f"qty_{line}": "1", "restock": "on"})
        self.assertEqual(db.stock_on_hand(conn)[item_id], D("13"))
        self.post(c, f"/invoices/{inv}/credit-note", {"date": today, "reason": "price fix", f"qty_{line}": "1"})  # box unticked
        self.assertEqual(db.stock_on_hand(conn)[item_id], D("13"))
        _, html = self.post(c, f"/items/{item_id}/delete", {})  # refused, with the reason shown on the item's page
        self.assertIn("stock history", html)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM item_catalog WHERE id = ?", (item_id,)).fetchone()[0], 1)

        # a recurring invoice: set up from an invoice, confirm when due, never created twice
        new_inv = db.create_invoice(conn, 1, today, [{"description": "Stock Sweet", "qty": "1", "rate": "100", "gst_rate": "5"}])
        _, html = self.get(c, f"/recurring/new?invoice={new_inv}")
        self.assertIn("Repeat this invoice", html.decode())
        self.assertIn("Repeat this invoice", self.get(c, f"/invoices/{new_inv}")[1].decode())  # the button on the invoice
        url, html = self.post(c, "/recurring/new", {"invoice": str(new_inv), "frequency": "monthly", "start": today, "end": ""})
        self.assertIn("Schedule saved", html)
        self.assertIn("Due", html)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, "/recurring/new", {"invoice": str(new_inv), "frequency": "monthly", "start": "2026-02-30", "end": ""})
        self.assertEqual(cm.exception.code, 400)
        _, html = self.get(c, "/")
        self.assertIn("recurring invoice(s) are due", html.decode())
        _, html = self.get(c, "/recurring/due")
        self.assertIn("Stock Sweet", html.decode())
        rid = conn.execute("SELECT id FROM recurring").fetchone()["id"]
        before = conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0]
        url, html = self.post(c, "/recurring/run", {f"run_{rid}": "on", f"date_{rid}": today})
        self.assertIn("Created: BS/", html)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], before + 1)
        rec = db.get_recurring(conn, rid)
        self.assertEqual((rec["runs"], rec["next_date"] > today), (1, True))
        self.assertEqual(db.stock_on_hand(conn)[item_id], D("11") + D("0"))  # 13 - 1 (the invoice above) - 1 (the recurring one)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, "/recurring/run", {f"run_{rid}": "on", f"date_{rid}": today})  # a second press
        self.assertIn("not due yet", cm.exception.read().decode())
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], before + 1)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, "/recurring/run", {})
        self.assertIn("Tick at least one", cm.exception.read().decode())
        _, html = self.post(c, f"/recurring/{rid}/pause", {})
        self.assertIn("paused", html)
        _, html = self.post(c, f"/recurring/{rid}/resume", {})
        self.assertIn("resumed", html)
        _, html = self.post(c, f"/recurring/{rid}/delete", {})
        self.assertIn("deleted", html)
        self.assertIsNone(db.get_recurring(conn, rid))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM invoice").fetchone()[0], before + 1)  # invoices stay
        conn.close()

    def test_quick_customer_and_new_dashboard(self):
        import json
        c = self.client()
        self.post(c, "/login", {"passcode": "1234"})
        _, body = self.post(c, "/customers/quick", {"name": "Walk-in Mohan", "phone": "9811122233", "state": "Uttar Pradesh"})
        j = json.loads(body)
        self.assertEqual((j["name"], j["state"]), ("Walk-in Mohan", "Uttar Pradesh"))
        self.assertIn("9811122233", j["label"])
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(c, "/customers/quick", {"name": "  "})
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("required", json.loads(cm.exception.read().decode())["error"])
        _, html = self.get(c, "/")  # redesigned dashboard renders with real data
        html = html.decode()
        for needle in ("class='chart'", "Who owes you", "aria-current='page'"):
            self.assertIn(needle, html)
        _, html = self.get(c, "/invoices/new?customer_id=1")
        self.assertIn("id='cust'", html.decode())
        self.assertIn("Walk-in Mohan", html.decode())  # new customer is in the dropdown

    def test_staff_roles_and_bank_matching(self):
        """Runs after the other smoke tests: passcode 1234, invoice 1 (balance 1017.50) and its customer exist."""
        import datetime
        today = datetime.date.today().isoformat()
        owner, staff = self.client(), self.client()
        self.post(owner, "/login", {"passcode": "1234"})
        _, html = self.post(owner, "/staff/new", {"name": "Sunita", "passcode": "5555"})
        self.assertIn("Sunita", html)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(staff, "/login", {"user": "Sunita", "passcode": "wrong"})
        self.assertEqual(cm.exception.code, 401)
        self.post(staff, "/login", {"user": "sunita", "passcode": "5555"})

        # staff can bill, but cannot see owner pages
        for path in ("/exports", "/profile", "/purchases", "/bank", "/reconcile", "/staff", "/items", "/invoices/1/cancel",
                     "/credit-notes", "/credit-notes/1", "/exports/sales.xlsx", "/stock", "/recurring", "/recurring/due"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as cm:
                self.get(staff, path)
            self.assertEqual(cm.exception.code, 403, path)
        for action in ("cancel", "credit-note", "refund"):
            with self.assertRaises(urllib.error.HTTPError, msg=action) as cm:
                self.post(staff, f"/invoices/1/{action}", {"reason": "x", "amount": "1", "date": today, "mode": "cash"})
            self.assertEqual(cm.exception.code, 403, action)
        url, html = self.get(staff, "/")  # staff home is the invoice form, not the dashboard
        self.assertTrue(url.endswith("/invoices/new"))
        self.assertNotIn("Exports", html.decode())
        url, html = self.post(staff, "/invoices/new", {"customer_id": "1", "date": today, "description": ["Peda"], "hsn": [""],
                                                        "qty": ["1"], "rate": ["100"], "gst_rate": ["5"]})
        self.assertIn("Created by Sunita", html)
        self.assertNotIn("Cancel invoice", html)  # no cancel button for staff
        inv2 = int(url.split("/invoices/")[1].split("?")[0])
        _, body = self.post(staff, "/customers/quick", {"name": "Staff Added", "state": "Delhi"})  # staff may add customers
        self.assertIn("Staff Added", body)

        # bank statement: exact balance of invoice 1 -> suggested; confirm; second import cannot double-apply
        stmt = "Date,Narration,Chq./Ref.No.,Withdrawal Amt.,Deposit Amt.\n" + \
               f"{datetime.date.today().strftime('%d-%m-%Y')},UPI/SOME CUSTOMER,UTR9,,1017.50\n"
        _, html = self.post(owner, "/bank", {"csv": stmt, "action": "preview"})
        self.assertIn("Check this", html)
        self.assertIn("BS/", html)
        _, html = self.post(owner, "/bank", {"csv": stmt, "action": "apply", "choice_2": "1"})
        self.assertIn("1 payment(s) recorded", html)
        _, html = self.get(owner, "/invoices/1")
        self.assertIn("Paid", html.decode())
        _, html = self.post(owner, "/bank", {"csv": stmt, "action": "preview"})
        self.assertIn("Already applied", html)
        _, html = self.post(owner, "/bank", {"csv": stmt, "action": "apply", "choice_2": "1"})
        self.assertIn("already applied", html)

        # disabling staff logs them out at once
        self.post(owner, "/staff/1/active", {"active": "0"})
        self.assertTrue(self.get(staff, "/invoices")[0].endswith("/login"))
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(self.client(), "/login", {"user": "Sunita", "passcode": "5555"})
        self.assertEqual(cm.exception.code, 401)
        self.assertTrue(inv2 > 1)


    def test_zz_restore_and_change_passcode_run_last(self):
        """Restores an earlier backup through the web page, then changes the owner passcode. Runs last (alphabetical) because it
        rolls the data back and changes the passcode."""
        owner, other = self.client(), self.client()
        self.post(owner, "/login", {"passcode": "1234"})
        self.post(other, "/login", {"passcode": "1234"})
        bdir = os.path.join(self.tmp.name, "backups")

        # restore: take a backup, change things, restore, and the change is gone; the state before restore is kept
        self.post(owner, "/backups/now", {})
        snap = sorted(n for n in os.listdir(bdir) if n.count("-") >= 4 and "before-restore" not in n)[-1]
        conn = db.connect(self.db_path)
        customers_then = conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0]
        conn.close()
        self.post(owner, "/customers/quick", {"name": "Added After Backup", "state": "Delhi"})
        _, html = self.post(owner, "/backups/restore", {"where": "here", "name": snap})
        self.assertIn("Restored", html)
        self.post(owner, "/login", {"passcode": "1234"})  # the restored database carries its own session secret
        conn = db.connect(self.db_path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0], customers_then)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM customer WHERE name = 'Added After Backup'").fetchone()[0], 0)
            self.assertIn("backup.restore", [r["action"] for r in db.list_audit(conn)])
        finally:
            conn.close()
        safety = [n for n in os.listdir(bdir) if "before-restore" in n]
        self.assertTrue(safety)
        old = db.connect(os.path.join(bdir, safety[0]))
        try:
            self.assertEqual(old.execute("SELECT COUNT(*) FROM customer WHERE name = 'Added After Backup'").fetchone()[0], 1)  # nothing lost
        finally:
            old.close()

        # change the passcode
        self.post(other, "/login", {"passcode": "1234"})
        _, html = self.post(owner, "/account", {"old": "wrong", "new": "5678", "again": "5678"})
        self.assertIn("current passcode is wrong", html)
        _, html = self.post(owner, "/account", {"old": "1234", "new": "5678", "again": "9999"})
        self.assertIn("do not match", html)
        url, html = self.post(owner, "/account", {"old": "1234", "new": "5678", "again": "5678"})
        self.assertIn("Passcode changed", html)  # this browser stays signed in
        self.assertTrue(self.get(owner, "/invoices")[0].endswith("/invoices"))
        self.assertTrue(self.get(other, "/invoices")[0].endswith("/login"))  # every other session is signed out
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(self.client(), "/login", {"passcode": "1234"})
        self.assertEqual(cm.exception.code, 401)
        fresh = self.client()
        self.post(fresh, "/login", {"passcode": "5678"})
        self.assertTrue(self.get(fresh, "/invoices")[0].endswith("/invoices"))


if __name__ == "__main__":
    unittest.main()
