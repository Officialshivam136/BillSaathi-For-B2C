"""BillSaathi web server (standard library only). Run: python app.py [port]"""
import datetime
import hashlib
import hmac
import os
import re
import sys
import time
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import threading

import secrets
import shutil

import ai
import backups
import db
import bank
import exports
import gateway
import i18n
import llm
import multipart
import quick
import scan
import reconcile as rc
import tally
import templates as t

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LOGIN_LIMIT, LOGIN_WINDOW = 5, 300  # wrong attempts allowed per user and address, within this many seconds
_FAILS, _FAILS_LOCK = {}, threading.Lock()


def login_blocked(key, now=None):
    now = time.time() if now is None else now
    with _FAILS_LOCK:
        recent = [x for x in _FAILS.get(key, []) if now - x < LOGIN_WINDOW]
        _FAILS[key] = recent
        return len(recent) >= LOGIN_LIMIT


def login_failed(key):
    with _FAILS_LOCK:
        _FAILS.setdefault(key, []).append(time.time())


def login_ok(key):
    with _FAILS_LOCK:
        _FAILS.pop(key, None)


def dmy_(iso):
    return f"{iso[8:10]}-{iso[5:7]}-{iso[:4]}"

COOKIE = "bs_session"
SESSION_SECONDS = 30 * 24 * 3600
MAX_BODY = 8_000_000  # GSTR-2B CSVs can be large
MAX_UPLOAD = 10_000_000  # a bill photo (8 MB) plus the form around it
PHOTO_TOKEN = re.compile(r"[a-f0-9]{32}\.(?:png|jpg|gif|webp|bmp)")
PHOTO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}


def sign(secret, msg):
    return hmac.new(secret.encode(), str(msg).encode(), hashlib.sha256).hexdigest()


def make_session(secret, uid=0):
    """uid 0 is the owner; any other value is a staff id. The token is signed, so it cannot be edited."""
    msg = f"{uid}.{int(time.time()) + SESSION_SECONDS}"
    return f"{msg}.{sign(secret, msg)}"


def read_session(secret, token):
    """Return the uid in a valid, unexpired token, else None."""
    try:
        uid, exp, sig = token.split(".")
        if secret and int(exp) > time.time() and hmac.compare_digest(sig, sign(secret, f"{uid}.{exp}")):
            return int(uid)
    except (ValueError, AttributeError):
        pass
    return None


# Staff may use only these. Everything else is owner-only (profile, exports, purchases, bank, reconcile, items, staff, cancel).
STAFF_ALLOWED = (r"/", r"/customers(/new|/quick|/\d+/edit|/\d+/last-items)?", r"/invoices(/new|/quick|/\d+|/\d+/payment|/\d+/remind)?")


class Handler(BaseHTTPRequestHandler):
    server_version = "BillSaathi"

    def log_message(self, fmt, *args):
        if not getattr(self.server, "quiet", False):
            super().log_message(fmt, *args)

    # ---- plumbing ----
    def _lang(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return "hi" if "lang" in c and c["lang"].value == "hi" else "en"

    def _bdir(self):
        return os.path.join(os.path.dirname(os.path.abspath(self.server.db_path)), "backups")

    def audit(self, conn, action, entity=None, entity_id=None, detail=""):
        db.audit(conn, getattr(self, "user", {}).get("name", "?"), action, entity, entity_id, detail)

    def _send(self, body, status=200, ctype="text/html; charset=utf-8", headers=()):
        if isinstance(body, str) and ctype.startswith("text/html"):
            body = i18n.translate(body, self._lang())
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, loc, headers=()):
        self._send(b"", 303, headers=[("Location", loc), *headers])

    def _download(self, data, name, ctype):
        self._send(data, 200, ctype, [("Content-Disposition", f'attachment; filename="{name}"')])

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Request too large")
        return parse_qs(self.rfile.read(n).decode("utf-8"), keep_blank_values=True)

    def _multipart(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            self.rfile.read(0)
            raise ValueError("That upload is too large (the limit is 8 MB for a photo)")
        return multipart.parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(n))

    def _photos_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(self.server.db_path)), "bill_photos")

    def _send_photo(self, path, name):
        if not os.path.isfile(path):
            return self._send(t.layout("Not found", "<h1>Photo not found</h1>"), 404)
        with open(path, "rb") as fh:
            data = fh.read()
        self._send(data, 200, PHOTO_TYPES.get(name.rsplit(".", 1)[-1], "application/octet-stream"),
                   [("X-Content-Type-Options", "nosniff"), ("Content-Disposition", "inline")])

    def _current_user(self, conn):
        """Return {'id', 'name', 'role'} for a valid session, else None. Disabled staff are logged out at once."""
        c = SimpleCookie(self.headers.get("Cookie", ""))
        uid = read_session(db.get_secret(conn), c[COOKIE].value) if COOKIE in c else None
        if uid is None:
            return None
        if uid == 0:
            return {"id": 0, "name": "Owner", "role": "owner"}
        s = db.get_staff(conn, uid)
        return {"id": uid, "name": s["name"], "role": "staff"} if s and s["active"] else None

    def handle_one(self, method):
        url = urlparse(self.path)
        path, query = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
        conn = db.connect(self.server.db_path)
        t._ctx.role, t._ctx.user, t._ctx.path, t._ctx.lang = "owner", "", path, self._lang()  # no stale values from a previous request
        t._ctx.stock_fn = lambda: {}
        try:
            try:
                if db.backup_if_due(conn, self._bdir()):  # first request of the day: keep 60 days, and copy to the second folder
                    backups.prune(self._bdir())
                    backups.sync_extra(conn, self._bdir())
            except OSError:
                pass
            self.route(conn, method, path, query)
        except Exception as exc:  # last resort; show a plain error, keep serving
            import traceback

            traceback.print_exc()
            self._send(t.layout("Error", f"<h1>Something went wrong</h1><p>{t.e(exc)}</p>"), 500)
        finally:
            conn.close()

    def do_GET(self):
        self.handle_one("GET")

    def do_POST(self):
        self.handle_one("POST")

    # ---- routing ----
    def route(self, conn, method, path, q):
        if path == "/lang":  # works before sign-in too; sends the visitor back to the page they were on
            back = urlparse(self.headers.get("Referer", "")).path or "/"
            back = back if back.startswith("/") and not back.startswith("//") else "/"
            lang = "hi" if q.get("to") == "hi" else "en"
            return self._redirect(back, [("Set-Cookie", f"lang={lang}; Path=/; Max-Age=31536000; SameSite=Lax")])
        # auth gate
        if not db.has_passcode(conn):
            if path == "/passcode" and method == "POST":
                return self.post_passcode(conn)
            return self._send(t.passcode_page())
        if path == "/login":
            return self.post_login(conn) if method == "POST" else self._send(t.login_page())
        user = self._current_user(conn)
        if not user:
            return self._redirect("/login")
        self.user = user
        t._ctx.role, t._ctx.user, t._ctx.path = user["role"], user["name"], path
        t._ctx.stock_fn = lambda: db.stock_on_hand(conn)
        if path == "/logout":
            return self._redirect("/login", [("Set-Cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")])
        if user["role"] == "staff" and not any(re.fullmatch(p, path) for p in STAFF_ALLOWED):
            return self._send(t.forbidden_page(), 403)

        biz = db.get_business(conn)
        if path == "/profile":
            return self.post_profile(conn, biz) if method == "POST" else self._send(
                t.profile_page(dict(biz) if biz else {}, first=biz is None))
        if biz is None:
            return self._redirect("/profile")

        today = datetime.date.today().isoformat()
        m = None
        if path == "/" and method == "GET":
            if user["role"] == "staff":
                return self._redirect("/invoices/new")
            d = db.dashboard(conn, today)
            overdue = sorted(db.list_invoices(conn, status="overdue", today=today), key=lambda i: i["due_date"])[:5]
            extras = {"recurring_due": len(db.recurring_due(conn, today)), "low_stock": len(db.stock_levels(conn, only_attention=True))}
            return self._send(t.dashboard_page(d, db.list_invoices(conn, today=today)[:8], biz,
                                               db.monthly_series(conn, today), db.aging(conn, today), overdue,
                                               db.reminder_stats(conn, today), extras))
        if path == "/customers" and method == "GET":
            return self._send(t.customers_page(db.search_customers(conn, q.get("q", "")), q.get("q", "")))
        if path == "/customers/quick" and method == "POST":
            return self.quick_customer(conn)
        if path == "/customers/new":
            return self.save_customer(conn, None) if method == "POST" else self._send(t.customer_form_page({}))
        if (m := re.fullmatch(r"/customers/(\d+)/edit", path)):
            cid = int(m.group(1))
            c = db.get_customer(conn, cid)
            if not c:
                return self._send(t.layout("Not found", "<h1>Customer not found</h1>"), 404)
            return self.save_customer(conn, cid) if method == "POST" else self._send(t.customer_form_page(dict(c), cid=cid))
        if path == "/invoices" and method == "GET":
            return self.list_invoices(conn, q, biz, today)
        if path == "/invoices/new":
            if method == "POST":
                return self.post_invoice(conn, today)
            vals = {}
            if q.get("copy", "").isdigit() and user["role"] == "owner":  # "Duplicate": same customer and items, today's date
                src = db.get_invoice(conn, int(q["copy"]), today)
                if src:
                    vals = {"customer_id": src["customer_id"], "supply_type": src["supply_type"], "items": self._item_vals(src["items"])}
            return self._send(t.invoice_form_page(db.search_customers(conn), vals, today=today, catalog=db.list_catalog(conn),
                                                  biz_state=biz["state"], scheme=biz["scheme"], ai_enabled=self._ai_on(conn)))
        if (m := re.fullmatch(r"/invoices/(\d+)/edit", path)):
            return self.edit_invoice(conn, int(m.group(1)), biz, today, method)
        if (m := re.fullmatch(r"/customers/(\d+)/(statement|last-items)", path)) and method == "GET":
            return self.customer_extra(conn, int(m.group(1)), m.group(2), biz, q)
        if path == "/account":
            return self.account(conn, method, q)
        if path == "/audit" and method == "GET":
            return self._send(t.audit_page(db.list_audit(conn, q.get("entity") or None, q.get("q") or None), q))
        if path.startswith("/backups"):
            return self.backups_route(conn, method, path)
        if path == "/invoices/quick" and method == "POST":
            return self.post_quick(conn, today)
        if (m := re.fullmatch(r"/invoices/(\d+)", path)) and method == "GET":
            return self.view_invoice(conn, int(m.group(1)), biz, today, q.get("ok"))
        if (m := re.fullmatch(r"/invoices/(\d+)/remind", path)) and method == "GET":
            return self.remind(conn, int(m.group(1)), biz, today)
        if (m := re.fullmatch(r"/invoices/(\d+)/(payment|cancel|credit-note|refund)", path)) and method == "POST":
            return self.invoice_action(conn, int(m.group(1)), m.group(2), biz, today)
        if path == "/credit-notes" and method == "GET":
            return self._send(t.credit_notes_page(db.list_credit_notes(conn)))
        if (m := re.fullmatch(r"/credit-notes/(\d+)", path)) and method == "GET":
            cn = db.get_credit_note(conn, int(m.group(1)))
            if not cn:
                return self._send(t.layout("Not found", "<h1>Credit note not found</h1>"), 404)
            return self._send(t.credit_note_page(cn, biz, q.get("ok")))
        if path == "/staff" and method == "GET":
            return self._send(t.staff_page(db.list_staff(conn)))
        if path == "/staff/new" and method == "POST":
            f = {k: v[0] for k, v in self._form().items()}
            try:
                sid = db.add_staff(conn, f.get("name"), f.get("passcode"))
            except ValueError as exc:
                return self._send(t.staff_page(db.list_staff(conn), str(exc)))
            self.audit(conn, "staff.add", "staff", sid, f.get("name"))
            return self._redirect("/staff")
        if (m := re.fullmatch(r"/staff/(\d+)/(active|passcode)", path)) and method == "POST":
            f = {k: v[0] for k, v in self._form().items()}
            sid = int(m.group(1))
            if not db.get_staff(conn, sid):
                return self._send(t.layout("Not found", "<h1>Staff member not found</h1>"), 404)
            try:
                if m.group(2) == "active":
                    db.set_staff_active(conn, sid, f.get("active") == "1")
                else:
                    db.reset_staff_passcode(conn, sid, f.get("passcode"))
            except ValueError as exc:
                return self._send(t.staff_page(db.list_staff(conn), str(exc)))
            self.audit(conn, "staff.disable" if m.group(2) == "active" and f.get("active") != "1" else
                       "staff.enable" if m.group(2) == "active" else "staff.passcode_reset", "staff", sid, db.get_staff(conn, sid)["name"])
            return self._redirect("/staff")
        if path == "/bank":
            return self.post_bank(conn, today) if method == "POST" else self._send(t.bank_page({}))
        if path == "/items" and method == "GET":
            return self._send(t.catalog_page(db.list_catalog(conn), {l["id"]: l for l in db.stock_levels(conn)}))
        if path == "/items/new":
            return self.save_item(conn, None) if method == "POST" else self._send(t.catalog_form_page({}))
        if (m := re.fullmatch(r"/items/(\d+)/(edit|delete)", path)):
            item_id = int(m.group(1))
            it = db.get_catalog_item(conn, item_id)
            if not it:
                return self._send(t.layout("Not found", "<h1>Item not found</h1>"), 404)
            if m.group(2) == "delete" and method == "POST":
                try:
                    db.delete_catalog_item(conn, item_id)
                except ValueError as exc:
                    return self._send(t.catalog_form_page(dict(it), str(exc), item_id))
                self.audit(conn, "item.delete", "item", item_id, it["description"])
                return self._redirect("/items")
            return self.save_item(conn, item_id) if method == "POST" else self._send(t.catalog_form_page(dict(it), item_id=item_id))
        if path == "/integrations":
            return self.integrations(conn, method)
        if path == "/stock" or path.startswith("/stock/"):
            return self.stock_route(conn, method, path, q, today)
        if path == "/recurring" or path.startswith("/recurring/"):
            return self.recurring_route(conn, method, path, q, today)
        if path == "/purchases/scan":
            return self.purchase_scan(conn, biz, today, method)
        if (m := re.fullmatch(r"/purchases/scan-photo/(" + PHOTO_TOKEN.pattern + ")", path)) and method == "GET":
            return self._send_photo(os.path.join(self._photos_dir(), "tmp", m.group(1)), m.group(1))
        if (m := re.fullmatch(r"/purchases/(\d+)/photo", path)) and method == "GET":
            p = db.get_purchase(conn, int(m.group(1)))
            if not p or not p["photo"] or not re.fullmatch(r"\d+-[a-f0-9]{8}\.(?:png|jpg|gif|webp|bmp)", p["photo"]):
                return self._send(t.layout("Not found", "<h1>No photo for this bill</h1>"), 404)
            return self._send_photo(os.path.join(self._photos_dir(), p["photo"]), p["photo"])
        if (m := re.fullmatch(r"/invoices/(\d+)/paylink(/check)?", path)) and method == "POST":
            return self.paylink(conn, int(m.group(1)), bool(m.group(2)), biz, today)
        if path == "/purchases" and method == "GET":
            month = q.get("month", "")
            start = end = None
            if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                start, end = db.month_range(month)
            cat = q.get("category") or None
            return self._send(t.purchases_page(db.list_purchases(conn, start, end, cat), q, db.CATEGORIES))
        if path == "/purchases/new":
            return self.save_purchase(conn, None) if method == "POST" else self._send(
                t.purchase_form_page({"date": today}, db.CATEGORIES))
        if (m := re.fullmatch(r"/purchases/(\d+)/(edit|delete)", path)):
            pid = int(m.group(1))
            p = db.get_purchase(conn, pid)
            if not p:
                return self._send(t.layout("Not found", "<h1>Purchase bill not found</h1>"), 404)
            if m.group(2) == "delete" and method == "POST":
                db.delete_purchase(conn, pid)
                self.audit(conn, "purchase.delete", "purchase", pid, f"{p['vendor_name']} bill {p['bill_no']} total {p['total']}")
                return self._redirect("/purchases")
            return self.save_purchase(conn, pid) if method == "POST" else self._send(
                t.purchase_form_page(dict(p), db.CATEGORIES, pid=pid, photo_url=f"/purchases/{pid}/photo" if p["photo"] else ""))
        if path == "/reconcile":
            return self.post_reconcile(conn, biz, today) if method == "POST" else self._send(
                t.reconcile_page({"month": today[:7]}))
        if path == "/exports" and method == "GET":
            month = q.get("month", today[:7])
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                month = today[:7]
            return self._send(t.exports_page(month, db.gst_liability(conn, month), db.rcm_liability(conn, month)))
        if path.startswith("/exports/") and method == "GET":
            return self.export(conn, path, q, today)
        self._send(t.layout("Not found", "<h1>Page not found</h1>"), 404)

    # ---- handlers ----
    def post_passcode(self, conn):
        f = self._form()
        pc, again = f.get("passcode", [""])[0], f.get("again", [""])[0]
        try:
            if pc != again:
                raise ValueError("Passcodes do not match")
            db.set_passcode(conn, pc)
        except ValueError as exc:
            return self._send(t.passcode_page(str(exc)))
        self._redirect("/profile", [self._cookie(conn)])

    def _cookie(self, conn, uid=0):
        return ("Set-Cookie", f"{COOKIE}={make_session(db.get_secret(conn), uid)}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_SECONDS}")

    def post_login(self, conn):
        f = self._form()
        who = f.get("user", [""])[0].strip()
        pc = f.get("passcode", [""])[0]
        key = (self.client_address[0], who.lower() or "owner")
        if login_blocked(key):
            return self._send(t.login_page(f"Too many wrong attempts. Wait {LOGIN_WINDOW // 60} minutes and try again."), 429)
        if who.lower() in ("", "owner"):
            uid = 0 if db.check_passcode(conn, pc) else None
        else:
            uid = db.check_staff(conn, who, pc)
        if uid is not None:
            login_ok(key)
            return self._redirect("/", [self._cookie(conn, uid)])
        login_failed(key)
        self._send(t.login_page("Wrong user or passcode"), 401)

    def post_profile(self, conn, biz):
        f = {k: v[0] for k, v in self._form().items()}
        try:
            db.save_business(conn, f.get("name"), f.get("state"), f.get("gstin"), f.get("address", ""), f.get("upi_id", ""),
                             f.get("invoice_prefix", "BS"), f.get("fy_start_month", 4), f.get("due_days", 15) or 15,
                             f.get("scheme", "regular"))
        except ValueError as exc:
            return self._send(t.profile_page(f, str(exc), first=biz is None))
        self.audit(conn, "business.save", "business", 1, f"{f.get('name')} · scheme {f.get('scheme', 'regular')}")
        self._redirect("/")

    def quick_customer(self, conn):
        """Add a customer from the invoice form without leaving it. Returns JSON."""
        import json

        f = {k: v[0] for k, v in self._form().items()}
        try:
            cid = db.add_customer(conn, f.get("name"), f.get("phone", ""), None, f.get("state", ""), "")
        except ValueError as exc:
            return self._send(json.dumps({"error": str(exc)}), 400, "application/json")
        c = db.get_customer(conn, cid)
        self.audit(conn, "customer.add", "customer", cid, c["name"])
        label = c["name"] + (" · " + c["phone"] if c["phone"] else "")
        self._send(json.dumps({"id": cid, "name": c["name"], "state": c["state"] or "", "label": label}), 200, "application/json")

    def save_customer(self, conn, cid):
        f = {k: v[0] for k, v in self._form().items()}
        try:
            args = (f.get("name"), f.get("phone", ""), f.get("gstin"), f.get("state", ""), f.get("address", ""),
                    f.get("due_days", ""))
            if cid:
                db.update_customer(conn, cid, *args)
            else:
                cid = db.add_customer(conn, *args)
                self.audit(conn, "customer.add", "customer", cid, f.get("name"))
                return self._redirect("/customers")
        except ValueError as exc:
            return self._send(t.customer_form_page(f, str(exc), cid))
        self.audit(conn, "customer.edit", "customer", cid, f.get("name"))
        self._redirect("/customers")

    def save_item(self, conn, item_id):
        f = {k: v[0] for k, v in self._form().items()}
        try:
            args = (f.get("description"), f.get("hsn", ""), f.get("rate", ""), f.get("gst_rate", "5"), bool(f.get("track_stock")),
                    f.get("reorder_level", ""))
            if item_id:
                db.update_catalog_item(conn, item_id, *args)
            else:
                item_id = db.add_catalog_item(conn, *args)
        except ValueError as exc:
            return self._send(t.catalog_form_page(f, str(exc), item_id))
        self.audit(conn, "item.save", "item", item_id, f"{f.get('description')} @ {f.get('rate')}")
        self._redirect("/items")

    def save_purchase(self, conn, pid):
        f = {k: v[0] for k, v in self._form().items()}
        try:
            args = (f.get("vendor_name"), f.get("vendor_gstin"), f.get("vendor_phone"), f.get("bill_no"), f.get("date"),
                    f.get("taxable"), f.get("cgst"), f.get("sgst"), f.get("igst"), f.get("category"), f.get("note", ""),
                    bool(f.get("rcm")), f.get("rcm_rate", ""), bool(f.get("rcm_inter")))
            if pid:
                db.update_purchase(conn, pid, *args)
                action = "purchase.edit"
            else:
                pid = db.add_purchase(conn, *args)
                action = "purchase.add"
        except ValueError as exc:
            tok = f.get("photo_token", "")
            tok = tok if PHOTO_TOKEN.fullmatch(tok) else ""
            return self._send(t.purchase_form_page(f, db.CATEGORIES, str(exc), pid, photo_token=tok,
                                                   photo_url=f"/purchases/scan-photo/{tok}" if tok else ""))
        tok = f.get("photo_token", "")
        tmp = os.path.join(self._photos_dir(), "tmp", tok)
        if PHOTO_TOKEN.fullmatch(tok) and os.path.isfile(tmp):  # keep the scanned photo with the bill it belongs to
            name = f"{pid}-{tok[:8]}.{tok.rsplit('.', 1)[1]}"  # unique per scan, so a restored older database never points at the wrong photo
            shutil.move(tmp, os.path.join(self._photos_dir(), name))
            db.set_purchase_photo(conn, pid, name)
        self.audit(conn, action, "purchase", pid, f"{f.get('vendor_name')} bill {f.get('bill_no')}" + (" (reverse charge)" if f.get("rcm") else ""))
        self._redirect("/purchases")

    def post_bank(self, conn, today):
        f = {k: v[0] for k, v in self._form().items()}
        try:
            credits, skipped, errors = bank.parse_statement(f.get("csv", ""))
        except ValueError as exc:
            return self._send(t.bank_page(f, str(exc)))
        if not credits:
            return self._send(t.bank_page(f, "No received-money lines found in that statement"))
        if f.get("action") == "apply":
            applied, failed = [], []
            for c in credits:
                choice = f.get(f"choice_{c['line']}", "")
                if not choice.isdigit():
                    continue
                label = f"{dmy_(c['date'])} ₹{c['amount']} {c['desc'][:40]}"
                try:
                    pid = db.add_payment(conn, int(choice), c["date"], c["amount"], "bank",
                                         f"Bank: {c['ref'] or c['desc'][:60]}", by=self.user["name"], bank_key=c["key"])
                    self.audit(conn, "payment.bank_import", "payment", pid, f"₹{c['amount']} to invoice id {choice}: {c['desc'][:60]}")
                    applied.append(label)
                except ValueError as exc:
                    failed.append(f"{label} - {exc}")
            return self._send(t.bank_page({}, summary={"applied": applied, "failed": failed}))
        open_invs = [i for i in db.list_invoices(conn, today=today) if i["status"] == "active" and i["outstanding"] > 0]
        entries = bank.match(credits, open_invs, db.applied_bank_keys(conn))
        self._send(t.bank_page(f, None, entries, skipped, errors))

    def post_reconcile(self, conn, biz, today):
        f = {k: v[0] for k, v in self._form().items()}
        notes = []
        try:
            if not f.get("portal", "").strip():
                raise ValueError("Paste or load the GSTR-2B CSV first")
            portal, perr = rc.parse_csv(f["portal"])
            tol = db.parse_decimal(f.get("tol") or "1", "Tolerance", 2)
            if f.get("books", "").strip():
                books, berr = rc.parse_csv(f["books"])
            else:
                month = f.get("month") or today[:7]
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                    raise ValueError("Choose a valid month")
                start, end = db.month_range(month)
                rows = db.list_purchases(conn, start, end)
                no_gstin = sum(1 for p in rows if not p["vendor_gstin"])
                berr = [f"{no_gstin} bill(s) without a vendor GSTIN were left out: no input credit can be claimed on them."] if no_gstin else []
                books = [{"gstin": p["vendor_gstin"], "name": p["vendor_name"], "inv_raw": p["bill_no"], "inv_key": rc.inv_key(p["bill_no"]),
                          "date": p["date"], "taxable": p["taxable"], "cgst": p["cgst"], "sgst": p["sgst"], "igst": p["igst"],
                          "tax": p["cgst"] + p["sgst"] + p["igst"], "phone": p["vendor_phone"] or "", "line": 0}
                         for p in rows if p["vendor_gstin"]]
                if not books:
                    raise ValueError("No purchase bills with a vendor GSTIN in that month. Add bills on the Purchases page or paste your register.")
            notes = ["GSTR-2B: " + x for x in perr] + berr
            if biz["scheme"] == "composition":
                notes.append("Your business is on the composition scheme: input tax credit cannot be claimed. Use this only to check that suppliers filed.")
            result = rc.match(books, portal, tol)
        except ValueError as exc:
            return self._send(t.reconcile_page(f, str(exc)))
        if f.get("action") == "csv":
            return self._download(rc.exceptions_csv(result), "reconciliation-exceptions.csv", "text/csv; charset=utf-8")
        groups = rc.supplier_followup(result["books_only"])
        for g in groups:
            g["link"] = rc.followup_link(g, biz["name"])
        if f.get("action") == "xlsx":
            return self._download(rc.exceptions_xlsx(result, groups), "reconciliation.xlsx", XLSX)
        self._send(t.reconcile_page(f, None, result, groups, notes))

    def list_invoices(self, conn, q, biz, today):
        month = q.get("month", "")
        start = end = None
        if re.fullmatch(r"\d{4}-\d{2}", month):
            try:
                start, end = db.month_range(month)
            except ValueError:
                start = end = None
        cust = q.get("customer_id") if (q.get("customer_id") or "").isdigit() else None
        rows = db.list_invoices(conn, start, end, q.get("status"), q.get("q") or None, today, cust)
        self._send(t.invoices_page(rows, q, biz, db.search_customers(conn)))

    @staticmethod
    def _item_vals(items):
        """Invoice item rows -> the plain strings the invoice form expects."""
        return [{"description": i["description"], "hsn": i["hsn"] or "", "qty": format(i["qty"].normalize(), "f"), "rate": str(i["rate"]),
                 "gst_rate": format(i["gst_rate"].normalize(), "f")} for i in items]

    def _invoice_form(self, today):
        f = self._form()
        items = []
        for i in range(len(f.get("description", []))):
            it = {k: (f.get(k, [])[i] if i < len(f.get(k, [])) else "") for k in ("description", "hsn", "qty", "rate", "gst_rate")}
            if any(it[k].strip() for k in ("description", "hsn", "qty", "rate")):
                items.append(it)
        return {"customer_id": f.get("customer_id", [""])[0], "date": f.get("date", [today])[0], "items": items,
                "supply_type": f.get("supply_type", ["regular"])[0]}

    def post_invoice(self, conn, today):
        vals = self._invoice_form(today)
        try:
            inv_id = db.create_invoice(conn, int(vals["customer_id"] or 0), vals["date"], vals["items"], by=self.user["name"],
                                       supply_type=vals["supply_type"])
        except ValueError as exc:
            biz = db.get_business(conn)
            return self._send(t.invoice_form_page(db.search_customers(conn), vals, str(exc), today, db.list_catalog(conn),
                                                  biz["state"], scheme=biz["scheme"], ai_enabled=self._ai_on(conn)))
        row = conn.execute("SELECT number, total FROM invoice WHERE id = ?", (inv_id,)).fetchone()
        self.audit(conn, "invoice.create", "invoice", inv_id, f"{row['number']} total {row['total']}")
        alerts = db.stock_alerts_for_invoice(conn, inv_id)
        self._redirect(f"/invoices/{inv_id}?ok={quote('Invoice saved' + ('. Stock: ' + '; '.join(alerts) if alerts else ''))}")

    def edit_invoice(self, conn, inv_id, biz, today, method):
        """Correct an invoice that has no payments or credit notes. Owner only (staff are blocked by the route gate)."""
        inv = db.get_invoice(conn, inv_id, today)
        if not inv:
            return self._send(t.layout("Not found", "<h1>Invoice not found</h1>"), 404)
        if self.user["role"] != "owner":
            return self._send(t.forbidden_page(), 403)
        if method == "POST":
            vals = self._invoice_form(today)
            try:
                db.update_invoice(conn, inv_id, int(vals["customer_id"] or 0), vals["date"], vals["items"], by=self.user["name"],
                                  supply_type=vals["supply_type"])
            except ValueError as exc:
                return self._send(t.invoice_form_page(db.search_customers(conn), vals, str(exc), today, db.list_catalog(conn),
                                                      biz["state"], scheme=biz["scheme"], edit_id=inv_id, edit_number=inv["number"]), 400)
            return self._redirect(f"/invoices/{inv_id}?ok=Invoice+updated")
        if inv["status"] != "active" or inv["payments"] or inv["credit_notes"]:  # a normal page that explains, not an error status
            return self._send(t.invoice_view_page(inv, biz, "This invoice cannot be edited any more. Issue a credit note instead.", None, today))
        vals = {"customer_id": inv["customer_id"], "date": inv["date"], "supply_type": inv["supply_type"],
                "items": self._item_vals(inv["items"])}
        self._send(t.invoice_form_page(db.search_customers(conn), vals, None, today, db.list_catalog(conn), biz["state"],
                                       scheme=biz["scheme"], edit_id=inv_id, edit_number=inv["number"]))

    def customer_extra(self, conn, cid, what, biz, q):
        """/customers/<id>/statement (owner) and /customers/<id>/last-items (JSON, used to prefill an invoice)."""
        import json

        if what == "last-items":
            return self._send(json.dumps({"items": db.last_invoice_items(conn, cid)}), 200, "application/json")
        if self.user["role"] != "owner":
            return self._send(t.forbidden_page(), 403)
        start = q.get("from") or None
        end = q.get("to") or None
        try:
            start = db.parse_date(start) if start else None
            end = db.parse_date(end) if end else None
        except ValueError:
            start = end = None
        st = db.customer_statement(conn, cid, start, end)
        if not st:
            return self._send(t.layout("Not found", "<h1>Customer not found</h1>"), 404)
        self._send(t.statement_page(st, biz, start or "", end or ""))

    def account(self, conn, method, q=None):
        if self.user["role"] != "owner":
            return self._send(t.forbidden_page(), 403)
        if method != "POST":
            return self._send(t.account_page(notice=(q or {}).get("ok")))
        f = {k: v[0] for k, v in self._form().items()}
        try:
            if f.get("new") != f.get("again"):
                raise ValueError("The new passcodes do not match")
            db.change_passcode(conn, f.get("old"), f.get("new"), by=self.user["name"])
        except ValueError as exc:
            return self._send(t.account_page(str(exc)))
        # the session secret changed, so sign this browser in again with the new one
        self._redirect("/account?ok=Passcode+changed", [self._cookie(conn, 0)])

    def backups_route(self, conn, method, path):
        if self.user["role"] != "owner":
            return self._send(t.forbidden_page(), 403)
        bdir = self._bdir()
        extra = db.get_setting(conn, "extra_backup_dir") or ""

        def page(notice=None, error=None):
            rows = backups.list_backups([("This computer", bdir), ("Second folder", extra)])
            for r in rows:
                r["where_key"] = "second" if r["where"] == "Second folder" else "here"
            return self._send(t.backups_page(rows, extra, db.get_setting(conn, "extra_backup_status") or "", notice, error))

        if method == "GET":
            return page(parse_qs(urlparse(self.path).query).get("ok", [None])[0])
        f = {k: v[0] for k, v in self._form().items()}
        try:
            if path == "/backups/now":
                p = db.backup_now(conn, bdir)
                backups.sync_extra(conn, bdir)
                self.audit(conn, "backup.manual", "backup", 0, os.path.basename(p))
                return self._redirect("/backups?ok=Backup+saved")
            if path == "/backups/folder":
                folder = backups.set_extra_dir(conn, f.get("folder"))
                if folder:
                    backups.sync_extra(conn, bdir)
                self.audit(conn, "backup.folder", "backup", 0, folder or "turned off")
                return self._redirect("/backups?ok=Folder+saved")
            if path == "/backups/sync":
                backups.sync_extra(conn, bdir)
                return self._redirect("/backups?ok=Copy+finished")
            if path == "/backups/restore":
                folder = extra if f.get("where") == "second" else bdir
                name = os.path.basename(f.get("name", ""))  # a name from the list, never a path
                if not folder or not backups.ANY.match(name) or not os.path.isfile(os.path.join(folder, name)):
                    raise ValueError("That backup file was not found")
                safety = backups.restore(conn, os.path.join(folder, name), bdir)
                self.audit(conn, "backup.restore", "backup", 0, f"restored {name}; previous data saved as {os.path.basename(safety)}")
                return self._redirect("/backups?ok=Restored.+Your+previous+data+was+saved+as+a+before-restore+copy")
        except ValueError as exc:
            return page(error=str(exc))
        self._send(t.layout("Not found", "<h1>Page not found</h1>"), 404)

    def view_invoice(self, conn, inv_id, biz, today, ok=None, error=None):
        inv = db.get_invoice(conn, inv_id, today)
        if not inv:
            return self._send(t.layout("Not found", "<h1>Invoice not found</h1>"), 404)
        g = db.get_integrations(conn)
        links = db.list_gateway_links(conn, inv_id) if self.user["role"] == "owner" else ()
        self._send(t.invoice_view_page(inv, biz, error, ok, today, links, bool(g["razorpay_key_id"] and g["razorpay_key_secret"])),
                   400 if error else 200)

    def stock_route(self, conn, method, path, q, today):
        """Stock page, an item's movement history, and the Receive and Set-count actions."""
        def page(error=None, notice=None):
            return self._send(t.stock_page(db.stock_levels(conn), q.get("show", ""), error, notice), 400 if error else 200)

        if method == "GET":
            if path == "/stock":
                return page(notice=q.get("ok"))
            m = re.fullmatch(r"/stock/(\d+)", path)
            item = db.get_catalog_item(conn, int(m.group(1))) if m else None
            if not item:
                return self._send(t.layout("Not found", "<h1>Item not found</h1>"), 404)
            return self._send(t.stock_history_page(item, db.stock_history(conn, item["id"]), db.stock_on_hand(conn, item["id"]).get(item["id"], 0)))
        m = re.fullmatch(r"/stock/(\d+)/(receive|adjust)", path)
        if not m:
            return self._send(t.layout("Not found", "<h1>Page not found</h1>"), 404)
        item_id, action = int(m.group(1)), m.group(2)
        f = {k: v[0] for k, v in self._form().items()}
        try:
            if action == "receive":
                db.receive_stock(conn, item_id, f.get("date") or today, f.get("qty"), f.get("note", ""), self.user["name"])
                self.audit(conn, "stock.receive", "item", item_id, f"+{f.get('qty')} {f.get('note', '')}".strip())
            else:
                db.adjust_stock(conn, item_id, f.get("date") or today, f.get("counted"), f.get("note"), self.user["name"])
                self.audit(conn, "stock.adjust", "item", item_id, f"counted {f.get('counted')}: {f.get('note')}")
        except ValueError as exc:
            return page(error=str(exc))
        return self._redirect("/stock?ok=Saved")

    def recurring_route(self, conn, method, path, q, today):
        """Schedules for repeat invoices. Nothing is created without the owner confirming on the 'due' page."""
        def listing(**kw):
            return self._send(t.recurring_page(db.list_recurring(conn, today), **kw), 400 if kw.get("error") else 200)

        if path == "/recurring" and method == "GET":
            return listing(notice=q.get("ok"))
        if path == "/recurring/due" and method == "GET":
            return self._send(t.recurring_due_page(db.recurring_due(conn, today), today))
        if path == "/recurring/new":
            f = {k: v[0] for k, v in self._form().items()} if method == "POST" else q
            inv = db.get_invoice(conn, int(f["invoice"]), today) if (f.get("invoice") or "").isdigit() else None
            if not inv or inv["status"] != "active":
                return self._send(t.layout("Not found", "<h1>That invoice cannot be repeated</h1>"), 404)
            if method == "POST":
                try:
                    rid = db.create_recurring_from_invoice(conn, inv["id"], f.get("frequency"), f.get("start"), f.get("end", ""), self.user["name"])
                except ValueError as exc:
                    return self._send(t.recurring_new_page(inv, {"frequency": f.get("frequency"), "start": f.get("start"), "end": f.get("end")}, str(exc)), 400)
                self.audit(conn, "recurring.create", "recurring", rid, f"{inv['customer_name']} {f.get('frequency')} from {f.get('start')}")
                return self._redirect("/recurring?ok=Schedule+saved")
            nxt = inv["date"]
            while nxt <= today:  # first date still to come
                nxt = db.next_occurrence(nxt, "monthly", int(inv["date"][8:10]))
            return self._send(t.recurring_new_page(inv, {"frequency": "monthly", "start": nxt, "end": ""}))
        if method != "POST":
            return self._send(t.layout("Not found", "<h1>Page not found</h1>"), 404)
        if path == "/recurring/run":
            f = {k: v[0] for k, v in self._form().items()}
            made, problems = [], []
            for key in f:
                if not (key.startswith("run_") and key[4:].isdigit()):
                    continue
                rid = int(key[4:])
                rec = db.get_recurring(conn, rid)
                label = rec["customer_name"] if rec else f"schedule {rid}"
                try:
                    inv_id, skipped = db.run_recurring(conn, rid, f.get(f"date_{rid}") or today, today, self.user["name"])
                    number = conn.execute("SELECT number FROM invoice WHERE id = ?", (inv_id,)).fetchone()["number"]
                    self.audit(conn, "recurring.run", "invoice", inv_id, f"{number} for {label}" + (f" ({skipped} earlier period(s) skipped)" if skipped else ""))
                    made.append(f"{number} ({label})" + "".join(f" - {a}" for a in db.stock_alerts_for_invoice(conn, inv_id)))
                except ValueError as exc:
                    problems.append(f"{label}: {exc}")
            if not made and not problems:
                problems.append("Tick at least one invoice to create.")
            return listing(notice=("Created: " + "; ".join(made)) if made else None, error="  ".join(problems) or None)
        m = re.fullmatch(r"/recurring/(\d+)/(pause|resume|delete)", path)
        if not m or not db.get_recurring(conn, int(m.group(1))):
            return self._send(t.layout("Not found", "<h1>Schedule not found</h1>"), 404)
        rid, action = int(m.group(1)), m.group(2)
        if action == "delete":
            db.delete_recurring(conn, rid)
        else:
            db.set_recurring_active(conn, rid, action == "resume")
        self.audit(conn, f"recurring.{action}", "recurring", rid, "")
        return self._redirect(f"/recurring?ok={quote('Schedule ' + {'pause': 'paused', 'resume': 'resumed', 'delete': 'deleted'}[action])}")

    def integrations(self, conn, method):
        """Owner settings for the optional AI and payment-link features. Secrets are never shown back in full."""
        def page(**kw):
            return self._send(t.integrations_page(db.get_integrations(conn), scan.windows_ocr_available(), **kw))

        if method != "POST":
            return page(notice=parse_qs(urlparse(self.path).query).get("ok", [None])[0])
        f = {k: v[0] for k, v in self._form().items()}
        action = f.get("action", "save")
        try:
            if action in ("save", "test_ai"):
                key = "" if f.get("clear_anthropic") else (f.get("anthropic_key", "").strip() or None)
                db.save_integrations(conn, anthropic_key=key, ai_model=f.get("ai_model"))
                self.audit(conn, "integrations.ai", "integrations", 0, "AI key removed" if key == "" else "AI settings saved")
                if action == "test_ai":
                    g = db.get_integrations(conn)
                    ping = {"name": "ping", "description": "Reply that the connection works.",
                            "input_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
                                             "additionalProperties": False}}
                    llm.call_tool(g["anthropic_api_key"], g["ai_model"], "Call the ping tool with ok=true.",
                                  [{"role": "user", "content": "ping"}], ping, max_tokens=200, timeout=60)
                    return page(test_result=(True, f"AI connection works ({g['ai_model']})."))
            else:
                rid = "" if f.get("clear_razorpay") else f.get("razorpay_id", "").strip()
                secret = "" if f.get("clear_razorpay") else (f.get("razorpay_secret", "").strip() or None)
                db.save_integrations(conn, razorpay_id=rid, razorpay_secret=secret)
                self.audit(conn, "integrations.razorpay", "integrations", 0, "keys removed" if f.get("clear_razorpay") else "keys saved")
                if action == "test_rz":
                    g = db.get_integrations(conn)
                    gateway.test_keys(g["razorpay_key_id"], g["razorpay_key_secret"])
                    return page(test_result=(True, "Razorpay accepted the keys."))
        except (ValueError, llm.LLMError, gateway.GatewayError) as exc:
            return page(test_result=(False, str(exc))) if isinstance(exc, (llm.LLMError, gateway.GatewayError)) else page(error=str(exc))
        return self._redirect("/integrations?ok=Saved")

    def purchase_scan(self, conn, biz, today, method):
        """Photo of a supplier bill -> prefilled purchase form to check and save. Nothing is saved here."""
        g = db.get_integrations(conn)
        ocr_ok, ai_ok = scan.windows_ocr_available(), bool(g["anthropic_api_key"])
        if method != "POST":
            return self._send(t.scan_page(ocr_ok, ai_ok))
        tmpdir = os.path.join(self._photos_dir(), "tmp")
        os.makedirs(tmpdir, exist_ok=True)
        for old in os.listdir(tmpdir):  # unsaved scans older than a day are cleared
            p = os.path.join(tmpdir, old)
            try:
                if os.path.isfile(p) and time.time() - os.path.getmtime(p) > 86400:
                    os.remove(p)
            except OSError:
                pass
        try:
            fields, files = self._multipart()
            photo = files.get("photo")
            if not photo or not photo[2]:
                raise ValueError("Choose a photo first")
            data = photo[2]
            if len(data) > scan.MAX_IMAGE_BYTES:
                raise ValueError("That photo is larger than 8 MB. Take it at a lower quality or crop it.")
            kind = scan.sniff_image(data)
            if not kind:
                raise ValueError("That file is not a photo (JPG or PNG).")
            ext, mime = kind
            engine = fields.get("engine", "windows")
            if engine == "ai" and not ai_ok:
                raise ValueError("Add an AI key on the Integrations page first.")
            if engine != "ai" and not ocr_ok:
                raise ValueError("Offline scanning is not available on this computer.")
            token = f"{secrets.token_hex(16)}.{ext}"
            path = os.path.join(tmpdir, token)
            with open(path, "wb") as fh:
                fh.write(data)
            if engine == "ai":
                vals, warnings = ai.read_bill(g["anthropic_api_key"], g["ai_model"], data, mime, biz["gstin"])
            else:
                (vals, warnings), _rows = scan.scan_with_windows(path, biz["gstin"])
        except (ValueError, scan.ScanError, llm.LLMError) as exc:
            return self._send(t.scan_page(ocr_ok, ai_ok, error=str(exc)))
        self.audit(conn, "purchase.scan", "purchase", 0, f"{'AI' if engine == 'ai' else 'offline'} reading: {vals['vendor_name']} {vals['bill_no']}")
        form = dict(vals, category="Goods for resale")
        form["date"] = form["date"] or today
        self._send(t.purchase_form_page(form, db.CATEGORIES, warnings=warnings, photo_token=token, photo_url=f"/purchases/scan-photo/{token}"))

    def paylink(self, conn, inv_id, check, biz, today):
        """Create a Razorpay payment link for what is still owed, or ask Razorpay whether a link has been paid."""
        if self.user["role"] != "owner":
            return self._send(t.forbidden_page(), 403)
        g = db.get_integrations(conn)
        f = {k: v[0] for k, v in self._form().items()}
        try:
            inv = db.get_invoice(conn, inv_id, today)
            if not inv or inv["status"] != "active":
                raise gateway.GatewayError("That invoice cannot take a payment link.")
            if not check:
                if inv["outstanding"] <= 0:
                    raise gateway.GatewayError("Nothing is outstanding on this invoice.")
                n = len(db.list_gateway_links(conn, inv_id)) + 1
                link = gateway.create_link(g["razorpay_key_id"], g["razorpay_key_secret"], inv["outstanding"], f"{inv['number']}-{n}",
                                           f"Invoice {inv['number']} - {biz['name']}", inv["customer_name"], inv["customer_phone"] or "")
                db.add_gateway_link(conn, inv_id, link["id"], link["short_url"], link["amount"], link["status"], self.user["name"])
                self.audit(conn, "paylink.create", "invoice", inv_id, f"{link['id']} for ₹{link['amount']}")
                return self._redirect(f"/invoices/{inv_id}?ok=Payment+link+created")
            row = next((r for r in db.list_gateway_links(conn, inv_id) if r["link_id"] == f.get("link")), None)
            if not row:
                raise gateway.GatewayError("That payment link was not found.")
            st = gateway.get_link(g["razorpay_key_id"], g["razorpay_key_secret"], row["link_id"])
            msg = db.settle_gateway_link(conn, row, st["status"], st["amount_paid"], self.user["name"], today)
            self.audit(conn, "paylink.check", "invoice", inv_id, f"{row['link_id']}: {msg}")
            from urllib.parse import quote
            return self._redirect(f"/invoices/{inv_id}?ok={quote('Payment link ' + msg)}")
        except gateway.GatewayError as exc:
            return self.view_invoice(conn, inv_id, biz, today, error=str(exc))

    def _ai_on(self, conn):
        return bool(db.get_integrations(conn)["anthropic_api_key"])

    def post_quick(self, conn, today):
        """Quick text entry: fill the invoice form from a message. Nothing is saved until the owner submits the form.
        mode=ai uses Claude when a key is set; if the AI is unavailable it falls back to the built-in reader and says so."""
        f = {k: v[0] for k, v in self._form().items()}
        text = f.get("text", "")
        customers, catalog = db.search_customers(conn), db.list_catalog(conn)
        r = None
        if f.get("mode") == "ai":
            g = db.get_integrations(conn)
            try:
                r = ai.draft_invoice(g["anthropic_api_key"], g["ai_model"], text, customers, catalog)
                self.audit(conn, "ai.invoice_draft", "invoice", 0, f"{len(r['items'])} item(s) from a typed/spoken message")
            except llm.LLMError as exc:
                r = quick.parse(text, customers, catalog)
                r["warnings"].insert(0, f"AI was not used ({exc}) so the simple reader filled this in instead.")
        if r is None:
            r = quick.parse(text, customers, catalog)
        vals = {"customer_id": r["customer_id"] or "", "date": today, "items": r["items"]}
        biz = db.get_business(conn)
        self._send(t.invoice_form_page(customers, vals, None, today, catalog, biz["state"], r["warnings"], text,
                                       scheme=biz["scheme"], ai_enabled=self._ai_on(conn)))

    def remind(self, conn, inv_id, biz, today):
        """Log that a reminder was opened, then go to WhatsApp with the message filled in."""
        inv = db.get_invoice(conn, inv_id, today)
        if not inv or inv["status"] != "active" or inv["outstanding"] <= 0:
            return self._send(t.layout("Reminder", "<h1>Nothing is due on this invoice</h1>"), 404)
        db.log_reminder(conn, inv_id, self.user["name"])
        self._redirect(db.whatsapp_link(inv, biz))

    def invoice_action(self, conn, inv_id, action, biz, today):
        f = {k: v[0] for k, v in self._form().items()}
        try:
            if action == "payment":
                pid = db.add_payment(conn, inv_id, f.get("date"), f.get("amount"), f.get("mode"), f.get("note", ""), by=self.user["name"])
                self.audit(conn, "payment.add", "payment", pid, f"₹{f.get('amount')} {f.get('mode')} on invoice id {inv_id}")
                return self._redirect(f"/invoices/{inv_id}?ok=Payment+saved")
            if self.user["role"] != "owner":
                return self._send(t.forbidden_page(), 403)
            if action == "cancel":
                db.cancel_invoice(conn, inv_id, f.get("reason"), by=self.user["name"])
                self.audit(conn, "invoice.cancel", "invoice", inv_id, f.get("reason"))
                return self._redirect(f"/invoices/{inv_id}?ok=Invoice+cancelled")
            if action == "refund":
                pid = db.add_refund(conn, inv_id, f.get("date"), f.get("amount"), f.get("mode"), f.get("note", ""), by=self.user["name"])
                self.audit(conn, "payment.refund", "payment", pid, f"₹{f.get('amount')} {f.get('mode')} on invoice id {inv_id}")
                return self._redirect(f"/invoices/{inv_id}?ok=Refund+saved")
            qtys = {int(k[4:]): v for k, v in f.items() if k.startswith("qty_") and k[4:].isdigit()}
            cn_id = db.create_credit_note(conn, inv_id, f.get("date"), qtys, f.get("reason"), by=self.user["name"], restock="restock" in f)
            self.audit(conn, "credit_note.create", "credit_note", cn_id, f"on invoice id {inv_id}: {f.get('reason')}")
            return self._redirect(f"/credit-notes/{cn_id}?ok=Credit+note+issued")
        except ValueError as exc:
            return self.view_invoice(conn, inv_id, biz, today, error=str(exc))

    def export(self, conn, path, q, today):
        if path == "/exports/sales.csv":
            month = q.get("month", today[:7])
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                return self._send(t.layout("Export", "<h1>Choose a valid month</h1>"), 400)
            return self._download(exports.sales_register(conn, month), f"sales-register-{month}.csv", "text/csv; charset=utf-8")
        if path in ("/exports/sales.xlsx", "/exports/gst-liability.xlsx"):
            month = q.get("month", today[:7])
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                return self._send(t.layout("Export", "<h1>Choose a valid month</h1>"), 400)
            if path == "/exports/sales.xlsx":
                return self._download(exports.sales_register_xlsx(conn, month), f"sales-register-{month}.xlsx", XLSX)
            return self._download(exports.gst_liability_xlsx(conn, month), f"gst-liability-{month}.xlsx", XLSX)
        if path == "/exports/gst-liability.csv":
            month = q.get("month", today[:7])
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                return self._send(t.layout("Export", "<h1>Choose a valid month</h1>"), 400)
            return self._download(exports.gst_liability(conn, month), f"gst-liability-{month}.csv", "text/csv; charset=utf-8")
        if path == "/exports/tally.zip":
            month = q.get("month") or today[:7]
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                return self._send(t.layout("Export", "<h1>Choose a valid month</h1>"), 400)
            data, _ = tally.export_zip(conn, month, (db.get_business(conn)["name"]))
            return self._download(data, f"tally-{month}.zip", "application/zip")
        if path in ("/exports/purchases.csv", "/exports/pack.zip"):
            month = q.get("month") or today[:7]
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                return self._send(t.layout("Export", "<h1>Choose a valid month</h1>"), 400)
            if path.endswith(".zip"):
                return self._download(exports.client_pack(conn, month), f"ca-pack-{month}.zip", "application/zip")
            return self._download(exports.purchase_register(conn, month), f"purchase-register-{month}.csv", "text/csv; charset=utf-8")
        if path == "/exports/invoices.csv":
            return self._download(exports.invoice_list(conn), "invoices.csv", "text/csv; charset=utf-8")
        if path == "/exports/payments.csv":
            return self._download(exports.payment_register(conn), "payments.csv", "text/csv; charset=utf-8")
        if path == "/exports/all.zip":
            return self._download(exports.full_export_zip(conn), f"billsaathi-backup-{today}.zip", "application/zip")
        self._send(t.layout("Not found", "<h1>Page not found</h1>"), 404)


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind a port that is already in use, so keep it off there.
    allow_reuse_address = os.name != "nt"


def make_server(port=8000, db_path=None, quiet=False):
    srv = Server(("127.0.0.1", port), Handler)
    srv.db_path = db_path or db.DB_PATH
    srv.quiet = quiet
    db.connect(srv.db_path).close()  # create and migrate up front
    return srv


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = make_server(port)
    url = f"http://localhost:{port}"
    print(f"BillSaathi running at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
