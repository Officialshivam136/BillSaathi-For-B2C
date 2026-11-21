"""SQLite schema, migration and queries. Money is Decimal stored as TEXT; dates are ISO strings."""
import calendar
import datetime
import os
import re
import shutil
import sqlite3
from decimal import Decimal

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "billsaathi.db")
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")

sqlite3.register_adapter(Decimal, str)
sqlite3.register_converter("DECIMALTEXT", lambda b: Decimal(b.decode()))

SCHEMA_V1 = """
CREATE TABLE business (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    gstin TEXT,
    state TEXT NOT NULL,
    address TEXT,
    upi_id TEXT,
    invoice_prefix TEXT NOT NULL DEFAULT 'BS',
    fy_start_month INTEGER NOT NULL DEFAULT 4,
    due_days INTEGER NOT NULL DEFAULT 15
);
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE customer (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    gstin TEXT,
    state TEXT,
    address TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE invoice (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    fy TEXT NOT NULL,
    prefix TEXT NOT NULL,
    seq INTEGER NOT NULL,
    date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customer(id),
    is_interstate INTEGER NOT NULL,
    taxable DECIMALTEXT NOT NULL,
    cgst DECIMALTEXT NOT NULL,
    sgst DECIMALTEXT NOT NULL,
    igst DECIMALTEXT NOT NULL,
    total DECIMALTEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
    created_at TEXT NOT NULL,
    UNIQUE (prefix, fy, seq)
);
CREATE TABLE invoice_item (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoice(id),
    line_no INTEGER NOT NULL,
    description TEXT NOT NULL,
    hsn TEXT,
    qty DECIMALTEXT NOT NULL,
    rate DECIMALTEXT NOT NULL,
    gst_rate DECIMALTEXT NOT NULL,
    taxable DECIMALTEXT NOT NULL,
    tax DECIMALTEXT NOT NULL
);
CREATE TABLE payment (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoice(id),
    date TEXT NOT NULL,
    amount DECIMALTEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('cash','upi','bank','other')),
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_invoice_date ON invoice(date);
CREATE INDEX idx_payment_invoice ON payment(invoice_id);
CREATE INDEX idx_customer_phone ON customer(phone);
"""

SCHEMA_V2 = """
ALTER TABLE customer ADD COLUMN due_days INTEGER;
ALTER TABLE invoice ADD COLUMN cancel_reason TEXT;
ALTER TABLE invoice ADD COLUMN cancelled_at TEXT;
CREATE TABLE item_catalog (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL UNIQUE COLLATE NOCASE,
    hsn TEXT,
    rate DECIMALTEXT NOT NULL,
    gst_rate DECIMALTEXT NOT NULL
);
"""

SCHEMA_V3 = """
CREATE TABLE purchase (
    id INTEGER PRIMARY KEY,
    vendor_name TEXT NOT NULL,
    vendor_gstin TEXT,
    vendor_phone TEXT,
    bill_no TEXT NOT NULL,
    date TEXT NOT NULL,
    taxable DECIMALTEXT NOT NULL,
    cgst DECIMALTEXT NOT NULL,
    sgst DECIMALTEXT NOT NULL,
    igst DECIMALTEXT NOT NULL,
    total DECIMALTEXT NOT NULL,
    category TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_purchase_date ON purchase(date);
"""

SCHEMA_V4 = """
CREATE TABLE staff (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    passcode TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
ALTER TABLE invoice ADD COLUMN created_by TEXT;
ALTER TABLE payment ADD COLUMN created_by TEXT;
CREATE TABLE bank_applied (
    key TEXT PRIMARY KEY,
    payment_id INTEGER NOT NULL REFERENCES payment(id),
    applied_at TEXT NOT NULL
);
"""

SCHEMA_V5 = """
CREATE TABLE reminder_log (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoice(id),
    sent_at TEXT NOT NULL,
    by TEXT
);
CREATE INDEX idx_reminder_invoice ON reminder_log(invoice_id);
CREATE TABLE credit_note (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    fy TEXT NOT NULL,
    prefix TEXT NOT NULL,
    seq INTEGER NOT NULL,
    date TEXT NOT NULL,
    invoice_id INTEGER NOT NULL REFERENCES invoice(id),
    reason TEXT NOT NULL,
    taxable DECIMALTEXT NOT NULL,
    cgst DECIMALTEXT NOT NULL,
    sgst DECIMALTEXT NOT NULL,
    igst DECIMALTEXT NOT NULL,
    total DECIMALTEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    UNIQUE (prefix, fy, seq)
);
CREATE TABLE credit_note_item (
    id INTEGER PRIMARY KEY,
    credit_note_id INTEGER NOT NULL REFERENCES credit_note(id),
    invoice_item_id INTEGER NOT NULL REFERENCES invoice_item(id),
    line_no INTEGER NOT NULL,
    description TEXT NOT NULL,
    hsn TEXT,
    qty DECIMALTEXT NOT NULL,
    rate DECIMALTEXT NOT NULL,
    gst_rate DECIMALTEXT NOT NULL,
    taxable DECIMALTEXT NOT NULL,
    tax DECIMALTEXT NOT NULL
);
CREATE INDEX idx_credit_note_invoice ON credit_note(invoice_id);
CREATE INDEX idx_credit_note_item_line ON credit_note_item(invoice_item_id);
"""

SCHEMA_V6 = """
ALTER TABLE business ADD COLUMN scheme TEXT NOT NULL DEFAULT 'regular';
ALTER TABLE invoice ADD COLUMN supply_type TEXT NOT NULL DEFAULT 'regular';
ALTER TABLE purchase ADD COLUMN rcm INTEGER NOT NULL DEFAULT 0;
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    by TEXT,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id INTEGER,
    detail TEXT
);
CREATE INDEX idx_audit_at ON audit_log(at);
"""

SCHEMA_V7 = """
ALTER TABLE purchase ADD COLUMN photo TEXT;
CREATE TABLE gateway_link (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoice(id),
    link_id TEXT NOT NULL UNIQUE,
    short_url TEXT NOT NULL,
    amount DECIMALTEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    payment_id INTEGER REFERENCES payment(id),
    checked_at TEXT
);
CREATE INDEX idx_gateway_invoice ON gateway_link(invoice_id);
"""

SCHEMA_V8 = """
ALTER TABLE item_catalog ADD COLUMN track_stock INTEGER NOT NULL DEFAULT 0;
ALTER TABLE item_catalog ADD COLUMN reorder_level DECIMALTEXT;
ALTER TABLE invoice_item ADD COLUMN catalog_id INTEGER REFERENCES item_catalog(id);
CREATE TABLE stock_move (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES item_catalog(id),
    date TEXT NOT NULL,
    qty DECIMALTEXT NOT NULL,
    kind TEXT NOT NULL,
    invoice_id INTEGER REFERENCES invoice(id),
    credit_note_id INTEGER REFERENCES credit_note(id),
    note TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE INDEX idx_stock_item ON stock_move(item_id);
CREATE INDEX idx_stock_invoice ON stock_move(invoice_id);
CREATE TABLE recurring (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customer(id),
    frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'monthly', 'quarterly', 'yearly')),
    anchor_day INTEGER NOT NULL,
    next_date TEXT NOT NULL,
    end_date TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    supply_type TEXT NOT NULL DEFAULT 'regular',
    note TEXT,
    last_invoice_id INTEGER REFERENCES invoice(id),
    last_run TEXT,
    runs INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE TABLE recurring_item (
    id INTEGER PRIMARY KEY,
    recurring_id INTEGER NOT NULL REFERENCES recurring(id),
    line_no INTEGER NOT NULL,
    description TEXT NOT NULL,
    hsn TEXT,
    qty DECIMALTEXT NOT NULL,
    rate DECIMALTEXT NOT NULL,
    gst_rate DECIMALTEXT NOT NULL
);
CREATE INDEX idx_recurring_next ON recurring(next_date);
"""

MIGRATIONS = [SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, SCHEMA_V6, SCHEMA_V7, SCHEMA_V8]  # index i migrates user_version i -> i+1


def connect(path=None):
    """Open a connection (autocommit; use `tx` for transactions) and migrate."""
    conn = sqlite3.connect(path or DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn):
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    for i in range(v, len(MIGRATIONS)):
        conn.executescript("BEGIN;" + MIGRATIONS[i] + f"PRAGMA user_version = {i + 1};COMMIT;")


class tx:
    """Context manager: BEGIN IMMEDIATE ... COMMIT / ROLLBACK."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def normalize_phone(phone):
    """Digits only; 10-digit numbers get the 91 prefix."""
    d = "".join(c for c in (phone or "") if c.isdigit())
    if len(d) == 10:
        d = "91" + d
    elif len(d) == 11 and d.startswith("0"):
        d = "91" + d[1:]
    return d


# ---- business ----
def get_business(conn):
    return conn.execute("SELECT * FROM business WHERE id = 1").fetchone()


def save_business(conn, name, state, gstin=None, address="", upi_id="", invoice_prefix="BS", fy_start_month=4, due_days=15,
                  scheme="regular"):
    import gst

    if scheme not in ("regular", "composition"):
        raise ValueError("Invalid GST scheme")
    if scheme == "composition" and not (gstin or "").strip():
        raise ValueError("A composition dealer needs a GSTIN")
    name, state = (name or "").strip(), (state or "").strip()
    if not name or not state:
        raise ValueError("Business name and state are required")
    gstin = (gstin or "").strip().upper() or None
    if gstin and not gst.validate_gstin(gstin):
        raise ValueError("Invalid GSTIN")
    if not 1 <= int(fy_start_month) <= 12:
        raise ValueError("Invalid financial year start month")
    prefix = (invoice_prefix or "BS").strip().upper()
    vals = (name, gstin, state, address, upi_id, prefix, int(fy_start_month), int(due_days), scheme)
    if get_business(conn):
        conn.execute(
            "UPDATE business SET name=?, gstin=?, state=?, address=?, upi_id=?, invoice_prefix=?, "
            "fy_start_month=?, due_days=?, scheme=? WHERE id=1", vals)
    else:
        conn.execute(
            "INSERT INTO business (id, name, gstin, state, address, upi_id, invoice_prefix, fy_start_month, due_days, scheme) "
            "VALUES (1,?,?,?,?,?,?,?,?,?)", vals)


# ---- customers ----
def _clean_customer(name, phone, gstin, state, address, due_days=None):
    import gst

    name = (name or "").strip()
    if not name:
        raise ValueError("Customer name is required")
    gstin = (gstin or "").strip().upper() or None
    if gstin and not gst.validate_gstin(gstin):
        raise ValueError("Invalid customer GSTIN")
    due = None
    if str(due_days if due_days is not None else "").strip() != "":
        try:
            due = int(str(due_days).strip())
        except ValueError:
            raise ValueError("Due days must be a whole number")
        if not 0 <= due <= 365:
            raise ValueError("Due days must be between 0 and 365")
    return name, normalize_phone(phone), gstin, (state or "").strip(), (address or "").strip(), due


def add_customer(conn, name, phone="", gstin=None, state="", address="", due_days=None):
    vals = _clean_customer(name, phone, gstin, state, address, due_days)
    cur = conn.execute(
        "INSERT INTO customer (name, phone, gstin, state, address, due_days, created_at) VALUES (?,?,?,?,?,?,?)",
        vals + (now(),))
    return cur.lastrowid


def update_customer(conn, cid, name, phone="", gstin=None, state="", address="", due_days=None):
    vals = _clean_customer(name, phone, gstin, state, address, due_days)
    conn.execute("UPDATE customer SET name=?, phone=?, gstin=?, state=?, address=?, due_days=? WHERE id=?", vals + (cid,))


def get_customer(conn, cid):
    return conn.execute("SELECT * FROM customer WHERE id = ?", (cid,)).fetchone()


def search_customers(conn, q=""):
    q = (q or "").strip()
    if not q:
        return conn.execute("SELECT * FROM customer ORDER BY name COLLATE NOCASE").fetchall()
    like = f"%{q}%"
    digits = "".join(c for c in q if c.isdigit())
    return conn.execute(
        "SELECT * FROM customer WHERE name LIKE ? OR (? != '' AND phone LIKE ?) ORDER BY name COLLATE NOCASE",
        (like, digits, f"%{digits}%")).fetchall()


# ---- backups ----
def backup_now(conn, backup_dir=None, label=""):
    """Copy the database into backups/ right now, with a timestamp so it never overwrites an earlier copy."""
    backup_dir = backup_dir or BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
    dest = os.path.join(backup_dir, f"billsaathi-{label + '-' if label else ''}{stamp}.db")
    out = sqlite3.connect(dest)
    try:
        conn.backup(out)
    finally:
        out.close()
    return dest


def backup_if_due(conn, backup_dir=None, today=None):
    """Copy the database into backups/ once per day. Returns the path, or None if already done."""
    backup_dir = backup_dir or BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    today = today or datetime.date.today().isoformat()
    dest = os.path.join(backup_dir, f"billsaathi-{today}.db")
    if os.path.exists(dest):
        return None
    out = sqlite3.connect(dest)
    try:
        conn.backup(out)
    finally:
        out.close()
    return dest


# ---- settings / passcode ----
import hashlib
import hmac
import secrets

import gst


def get_setting(conn, key):
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else None


def set_setting(conn, key, value):
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))


def _hash(passcode, salt):
    return hashlib.pbkdf2_hmac("sha256", passcode.encode(), salt, 200_000).hex()


def has_passcode(conn):
    return get_setting(conn, "passcode") is not None


def set_passcode(conn, passcode):
    if len(passcode or "") < 4:
        raise ValueError("Passcode must be at least 4 characters")
    salt = os.urandom(16)
    set_setting(conn, "passcode", salt.hex() + "$" + _hash(passcode, salt))
    if get_setting(conn, "secret") is None:
        set_setting(conn, "secret", secrets.token_hex(32))


def check_passcode(conn, passcode):
    stored = get_setting(conn, "passcode")
    if not stored:
        return False
    salt, h = stored.split("$")
    return hmac.compare_digest(_hash(passcode or "", bytes.fromhex(salt)), h)


def get_secret(conn):
    return get_setting(conn, "secret") or ""


# ---- money / date parsing ----
def parse_decimal(value, field, places=2, allow_zero=True):
    from decimal import InvalidOperation

    try:
        v = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if v.is_finite() and v < 0:
        raise ValueError(f"{field} cannot be negative")
    if not v.is_finite() or v >= Decimal("1000000000"):
        raise ValueError(f"{field} is out of range")
    if v != v.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f"{field} can have at most {places} decimal places")
    if v == 0 and not allow_zero:
        raise ValueError(f"{field} must be greater than zero")
    return v.quantize(Decimal(1).scaleb(-places))  # always stored as 100.00 (money) or 3.000 (quantity), never as typed


def parse_date(value, field="Date"):
    try:
        return datetime.date.fromisoformat((value or "").strip()).isoformat()
    except ValueError:
        raise ValueError(f"{field} is not a valid date")


def fy_label(date_iso, fy_start_month):
    d = datetime.date.fromisoformat(date_iso)
    y = d.year if d.month >= fy_start_month else d.year - 1
    return str(y) if fy_start_month == 1 else f"{y}-{(y + 1) % 100:02d}"


def month_range(ym):
    """'2026-11' -> ('2026-11-01', '2026-12-01') half-open."""
    y, m = (int(x) for x in ym.split("-"))
    start = datetime.date(y, m, 1)
    end = datetime.date(y + (m == 12), m % 12 + 1, 1)
    return start.isoformat(), end.isoformat()


# ---- invoices ----
MAX_ITEMS = 10


def _clean_items(items):
    out = []
    for i, it in enumerate(items, 1):
        desc = (it.get("description") or "").strip()
        if not desc:
            raise ValueError(f"Line {i}: description is required")
        qty = parse_decimal(it.get("qty"), f"Line {i} quantity", 3, allow_zero=False)
        rate = parse_decimal(it.get("rate"), f"Line {i} rate", 2)
        try:
            gr = Decimal(str(it.get("gst_rate")))
        except Exception:
            raise ValueError(f"Line {i}: invalid GST rate")
        if gr not in gst.GST_RATES:
            raise ValueError(f"Line {i}: GST rate must be one of 0, 5, 12, 18, 28")
        out.append({"description": desc, "hsn": (it.get("hsn") or "").strip() or None,
                    "qty": qty, "rate": rate, "gst_rate": gr})
    if not out:
        raise ValueError("At least one line item is required")
    if len(out) > MAX_ITEMS:
        raise ValueError(f"At most {MAX_ITEMS} line items are allowed")
    return out


SUPPLY_TYPES = ("regular", "export_lut", "export_igst")


def _prepare_invoice(conn, customer_id, date, items, due_days, supply_type):
    """Validate an invoice and work out its tax. Shared by create_invoice and update_invoice."""
    biz = get_business(conn)
    if not biz:
        raise ValueError("Set up the business profile first")
    cust = get_customer(conn, customer_id)
    if not cust:
        raise ValueError("Select a customer")
    if supply_type not in SUPPLY_TYPES:
        raise ValueError("Invalid supply type")
    date = parse_date(date)
    items = _clean_items(items)
    composition, export = biz["scheme"] == "composition", supply_type != "regular"
    if composition and export:
        raise ValueError("Exports are not available under the composition scheme")
    interstate, _missing = gst.is_interstate(biz["state"], cust["state"])
    if export:
        interstate = True  # exports are treated as inter-state supplies (IGST, or zero-rated under LUT)
    if composition and interstate:
        raise ValueError("A composition dealer cannot supply to another state")
    if composition or supply_type == "export_lut":
        for it in items:
            it["gst_rate"] = Decimal("0")  # no tax is charged on a bill of supply or on an export under LUT
    calc = gst.calc_invoice(items, interstate)
    if due_days is not None:
        days = int(due_days)
    elif cust["due_days"] is not None:
        days = cust["due_days"]  # per-customer setting overrides the business default
    else:
        days = biz["due_days"]
    due = (datetime.date.fromisoformat(date) + datetime.timedelta(days=days)).isoformat()
    return {"biz": biz, "cust": cust, "date": date, "items": items, "interstate": interstate, "calc": calc, "due": due,
            "fy": fy_label(date, biz["fy_start_month"]), "prefix": biz["invoice_prefix"]}


def _write_items(conn, inv_id, items, calc, date=None, by=None):
    """Write the invoice lines. A line whose description matches a saved item is linked to it, and when that item's stock
    is tracked, the sale is recorded as a stock movement."""
    for n, (it, line) in enumerate(zip(items, calc["lines"]), 1):
        cat = conn.execute("SELECT id, track_stock FROM item_catalog WHERE description = ? COLLATE NOCASE",
                           (it["description"],)).fetchone()
        conn.execute(
            "INSERT INTO invoice_item (invoice_id, line_no, description, hsn, qty, rate, gst_rate, taxable, tax, catalog_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (inv_id, n, it["description"], it["hsn"], it["qty"], it["rate"], it["gst_rate"], line["taxable"], line["tax"],
             cat["id"] if cat else None))
        if cat and cat["track_stock"]:
            _stock_move(conn, cat["id"], date or now()[:10], -it["qty"], "sale", inv_id, None, by)


def create_invoice(conn, customer_id, date, items, due_days=None, by=None, supply_type="regular"):
    """Create an invoice atomically; the number is assigned inside BEGIN IMMEDIATE."""
    p = _prepare_invoice(conn, customer_id, date, items, due_days, supply_type)
    t = p["calc"]["totals"]
    with tx(conn):
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM invoice WHERE prefix = ? AND fy = ?",
                           (p["prefix"], p["fy"])).fetchone()[0]
        number = f"{p['prefix']}/{p['fy']}/{seq:04d}"
        inv_id = conn.execute(
            "INSERT INTO invoice (number, fy, prefix, seq, date, due_date, customer_id, is_interstate, taxable, cgst, sgst,"
            " igst, total, status, created_at, created_by, supply_type) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)",
            (number, p["fy"], p["prefix"], seq, p["date"], p["due"], customer_id, int(p["interstate"]), t["taxable"], t["cgst"],
             t["sgst"], t["igst"], t["total"], now(), by, supply_type)).lastrowid
        _write_items(conn, inv_id, p["items"], p["calc"], p["date"], by)
    return inv_id


def update_invoice(conn, inv_id, customer_id, date, items, due_days=None, by=None, supply_type="regular"):
    """Correct an invoice that nothing depends on yet. The number never changes, and every edit is written to the audit log.
    Once a payment or credit note exists, fix mistakes with a credit note instead."""
    p = _prepare_invoice(conn, customer_id, date, items, due_days, supply_type)
    t = p["calc"]["totals"]
    with tx(conn):
        inv = conn.execute("SELECT * FROM invoice WHERE id = ?", (inv_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found")
        if inv["status"] != "active":
            raise ValueError("A cancelled invoice cannot be edited")
        if conn.execute("SELECT 1 FROM payment WHERE invoice_id = ?", (inv_id,)).fetchone():
            raise ValueError("This invoice has payments, so it cannot be edited. Issue a credit note instead.")
        if conn.execute("SELECT 1 FROM credit_note WHERE invoice_id = ?", (inv_id,)).fetchone():
            raise ValueError("This invoice has credit notes, so it cannot be edited.")
        if p["fy"] != inv["fy"]:
            raise ValueError(f"The date must stay in the same financial year as the invoice number ({inv['fy']})")
        old_customer = conn.execute("SELECT name FROM customer WHERE id = ?", (inv["customer_id"],)).fetchone()["name"]
        conn.execute(
            "UPDATE invoice SET date=?, due_date=?, customer_id=?, is_interstate=?, taxable=?, cgst=?, sgst=?, igst=?, total=?, "
            "supply_type=? WHERE id=?",
            (p["date"], p["due"], customer_id, int(p["interstate"]), t["taxable"], t["cgst"], t["sgst"], t["igst"], t["total"],
             supply_type, inv_id))
        _reverse_invoice_stock(conn, inv_id, p["date"], by, "edit")  # the old lines' stock effect is undone, then the new lines apply
        conn.execute("DELETE FROM invoice_item WHERE invoice_id = ?", (inv_id,))
        _write_items(conn, inv_id, p["items"], p["calc"], p["date"], by)
        audit(conn, by, "invoice.edit", "invoice", inv_id,
              f"{inv['number']}: total {inv['total']} -> {t['total']}; customer {old_customer} -> {p['cust']['name']}; "
              f"date {inv['date']} -> {p['date']}")


# ---- audit log, passcode change, statements ----
def audit(conn, by, action, entity=None, entity_id=None, detail=""):
    """Record who did what. No transaction of its own, so it commits or rolls back with the change it describes."""
    conn.execute("INSERT INTO audit_log (at, by, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
                 (now(), by, action, entity, entity_id, (detail or "")[:500]))


def list_audit(conn, entity=None, q=None, limit=300):
    sql, args = "SELECT * FROM audit_log WHERE 1=1", []
    if entity:
        sql += " AND entity = ?"
        args.append(entity)
    if q:
        sql += " AND (detail LIKE ? OR action LIKE ? OR by LIKE ?)"
        args += [f"%{q}%"] * 3
    return conn.execute(sql + " ORDER BY id DESC LIMIT ?", args + [int(limit)]).fetchall()


def change_passcode(conn, old, new, by=None):
    """Owner passcode change. Needs the current passcode, and signs everyone else out by replacing the session secret."""
    if not check_passcode(conn, old):
        raise ValueError("The current passcode is wrong")
    if old == new:
        raise ValueError("The new passcode must be different")
    set_passcode(conn, new)
    set_setting(conn, "secret", secrets.token_hex(32))
    audit(conn, by or "Owner", "passcode.change", "owner", 0, "Owner passcode changed; all sessions signed out")


def last_invoice_items(conn, customer_id):
    """Items of the customer's most recent active invoice, ready to prefill a new one."""
    inv = conn.execute("SELECT id FROM invoice WHERE customer_id = ? AND status = 'active' ORDER BY date DESC, id DESC LIMIT 1",
                       (customer_id,)).fetchone()
    if not inv:
        return []
    return [{"description": r["description"], "hsn": r["hsn"] or "", "qty": format(r["qty"].normalize(), "f"), "rate": str(r["rate"]),
             "gst_rate": format(r["gst_rate"].normalize(), "f")}
            for r in conn.execute("SELECT * FROM invoice_item WHERE invoice_id = ? ORDER BY line_no", (inv["id"],))]


def customer_statement(conn, customer_id, start=None, end=None):
    """Running account for one customer: invoices and refunds add to what they owe; credit notes and payments reduce it.
    start/end are inclusive ISO dates. Returns {customer, opening, rows, closing, debit, credit}."""
    cust = get_customer(conn, customer_id)
    if not cust:
        return None
    events = []  # (date, order, kind, ref, text, debit, credit)
    for i in conn.execute("SELECT * FROM invoice WHERE customer_id = ? AND status = 'active'", (customer_id,)):
        events.append((i["date"], 0, "Invoice", i["number"], "", i["total"], Decimal("0.00"), i["id"]))
    for n in conn.execute("SELECT cn.*, i.number AS inv_number FROM credit_note cn JOIN invoice i ON i.id = cn.invoice_id "
                          "WHERE i.customer_id = ? AND i.status = 'active'", (customer_id,)):
        events.append((n["date"], 1, "Credit note", n["number"], f"against {n['inv_number']}: {n['reason']}", Decimal("0.00"), n["total"], n["invoice_id"]))
    for p in conn.execute("SELECT p.*, i.number AS inv_number FROM payment p JOIN invoice i ON i.id = p.invoice_id "
                          "WHERE i.customer_id = ? AND i.status = 'active'", (customer_id,)):
        text = f"against {p['inv_number']} ({p['mode']})" + (f": {p['note']}" if p["note"] else "")
        if p["amount"] > 0:
            events.append((p["date"], 2, "Payment", "", text, Decimal("0.00"), p["amount"], p["invoice_id"]))
        else:
            events.append((p["date"], 3, "Refund", "", text, -p["amount"], Decimal("0.00"), p["invoice_id"]))
    events.sort(key=lambda e: (e[0], e[1]))
    zero = Decimal("0.00")
    opening = sum((e[5] - e[6] for e in events if start and e[0] < start), zero)
    rows, balance = [], opening
    for e in events:
        if (start and e[0] < start) or (end and e[0] > end):
            continue
        balance += e[5] - e[6]
        rows.append({"date": e[0], "kind": e[2], "ref": e[3], "text": e[4], "debit": e[5], "credit": e[6], "balance": balance,
                     "invoice_id": e[7]})
    return {"customer": cust, "opening": opening, "rows": rows, "closing": balance,
            "debit": sum((r["debit"] for r in rows), zero), "credit": sum((r["credit"] for r in rows), zero)}


def _paid_map(conn):
    paid = {}
    for r in conn.execute("SELECT invoice_id, amount FROM payment"):
        paid[r["invoice_id"]] = paid.get(r["invoice_id"], Decimal("0.00")) + r["amount"]
    return paid


def _credit_map(conn):
    credited = {}
    for r in conn.execute("SELECT invoice_id, total FROM credit_note"):
        credited[r["invoice_id"]] = credited.get(r["invoice_id"], Decimal("0.00")) + r["total"]
    return credited


def status_label(inv_status, total, paid, credited=Decimal("0.00")):
    """paid is net of refunds; credited is the sum of credit notes against the invoice."""
    if inv_status == "cancelled":
        return "Cancelled"
    net = total - credited
    if paid > net:
        return "Refund due"
    if net <= 0:
        return "Credited"
    if paid >= net:
        return "Paid"
    return "Partly paid" if paid > 0 else "Unpaid"


def _decorate(row, paid, today, credited=Decimal("0.00")):
    d = dict(row)
    active = d["status"] == "active"
    net = d["total"] - credited
    d["paid"] = paid
    d["credited"] = credited
    d["net_total"] = net
    d["outstanding"] = max(net - paid, Decimal("0.00")) if active else Decimal("0.00")
    d["refund_due"] = max(paid - net, Decimal("0.00")) if active else Decimal("0.00")
    d["status_label"] = status_label(d["status"], d["total"], paid, credited)
    d["overdue"] = active and d["outstanding"] > 0 and d["due_date"] < today
    return d


def list_invoices(conn, start=None, end=None, status=None, q=None, today=None, customer_id=None):
    """start inclusive, end exclusive (ISO). status: unpaid|partly|paid|cancelled|overdue."""
    today = today or datetime.date.today().isoformat()
    sql = ("SELECT i.*, c.name AS customer_name, c.phone AS customer_phone, c.gstin AS customer_gstin, "
           "c.state AS customer_state FROM invoice i JOIN customer c ON c.id = i.customer_id WHERE 1=1")
    args = []
    if start:
        sql += " AND i.date >= ?"
        args.append(start)
    if end:
        sql += " AND i.date < ?"
        args.append(end)
    if customer_id:
        sql += " AND i.customer_id = ?"
        args.append(int(customer_id))
    if q:
        sql += " AND (i.number LIKE ? OR c.name LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY i.date DESC, i.id DESC"
    paid, credited = _paid_map(conn), _credit_map(conn)
    rows = [_decorate(r, paid.get(r["id"], Decimal("0.00")), today, credited.get(r["id"], Decimal("0.00")))
            for r in conn.execute(sql, args)]
    want = {"unpaid": "Unpaid", "partly": "Partly paid", "paid": "Paid", "cancelled": "Cancelled", "credited": "Credited",
            "refund": "Refund due"}
    if status == "overdue":
        rows = [r for r in rows if r["overdue"]]
    elif status in want:
        rows = [r for r in rows if r["status_label"] == want[status]]
    return rows


def get_invoice(conn, inv_id, today=None):
    today = today or datetime.date.today().isoformat()
    row = conn.execute(
        "SELECT i.*, c.name AS customer_name, c.phone AS customer_phone, c.gstin AS customer_gstin, "
        "c.state AS customer_state, c.address AS customer_address FROM invoice i JOIN customer c ON c.id = i.customer_id "
        "WHERE i.id = ?", (inv_id,)).fetchone()
    if not row:
        return None
    payments = conn.execute("SELECT * FROM payment WHERE invoice_id = ? ORDER BY date, id", (inv_id,)).fetchall()
    paid = sum((p["amount"] for p in payments), Decimal("0.00"))
    notes = conn.execute("SELECT * FROM credit_note WHERE invoice_id = ? ORDER BY date, id", (inv_id,)).fetchall()
    d = _decorate(row, paid, today, sum((n["total"] for n in notes), Decimal("0.00")))
    d["payments"] = payments
    d["credit_notes"] = notes
    d["items"] = conn.execute("SELECT * FROM invoice_item WHERE invoice_id = ? ORDER BY line_no", (inv_id,)).fetchall()
    d["remaining_qty"] = {it["id"]: _remaining_qty(conn, it) for it in d["items"]}
    breakup = {}
    for it in d["items"]:
        line = gst.calc_line(1, it["taxable"], it["gst_rate"], bool(d["is_interstate"]))
        b = breakup.setdefault(it["gst_rate"], {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")})
        for k in b:
            b[k] += line[k]
    d["breakup"] = dict(sorted(breakup.items()))
    return d


def cancel_invoice(conn, inv_id, reason, by=None):
    """Cancel keeps the number and records why. Blocked while payments exist. Tracked stock goes back on the shelf."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required to cancel an invoice")
    with tx(conn):
        inv = conn.execute("SELECT status FROM invoice WHERE id = ?", (inv_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found")
        if conn.execute("SELECT 1 FROM payment WHERE invoice_id = ?", (inv_id,)).fetchone():
            raise ValueError("Invoice has payments; it cannot be cancelled")
        if conn.execute("SELECT 1 FROM credit_note WHERE invoice_id = ?", (inv_id,)).fetchone():
            raise ValueError("Invoice has credit notes; it cannot be cancelled")
        if inv["status"] == "cancelled":
            raise ValueError("Invoice is already cancelled")
        conn.execute("UPDATE invoice SET status = 'cancelled', cancel_reason = ?, cancelled_at = ? WHERE id = ?",
                     (reason, now(), inv_id))
        _reverse_invoice_stock(conn, inv_id, now()[:10], by, "cancel")


def add_payment(conn, inv_id, date, amount, mode, note="", by=None, bank_key=None):
    """bank_key marks a bank-statement line as applied, in the same transaction, so it can never be applied twice."""
    date = parse_date(date, "Payment date")
    amount = parse_decimal(amount, "Amount", 2, allow_zero=False)
    if mode not in ("cash", "upi", "bank", "other"):
        raise ValueError("Invalid payment mode")
    with tx(conn):
        if bank_key and conn.execute("SELECT 1 FROM bank_applied WHERE key = ?", (bank_key,)).fetchone():
            raise ValueError("This bank line was already applied")
        inv = conn.execute("SELECT status, total FROM invoice WHERE id = ?", (inv_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found")
        if inv["status"] == "cancelled":
            raise ValueError("Cannot record a payment on a cancelled invoice")
        paid = sum((r["amount"] for r in conn.execute("SELECT amount FROM payment WHERE invoice_id = ?", (inv_id,))),
                   Decimal("0.00"))
        credited = sum((r["total"] for r in conn.execute("SELECT total FROM credit_note WHERE invoice_id = ?", (inv_id,))),
                       Decimal("0.00"))
        due = inv["total"] - credited - paid
        if amount > due:
            raise ValueError(f"Overpayment blocked: only {max(due, Decimal('0.00'))} is outstanding")
        cur = conn.execute("INSERT INTO payment (invoice_id, date, amount, mode, note, created_at, created_by) VALUES (?,?,?,?,?,?,?)",
                           (inv_id, date, amount, mode, (note or "").strip() or None, now(), by))
        if bank_key:
            conn.execute("INSERT INTO bank_applied (key, payment_id, applied_at) VALUES (?,?,?)", (bank_key, cur.lastrowid, now()))
    return cur.lastrowid


def applied_bank_keys(conn):
    return {r["key"] for r in conn.execute("SELECT key FROM bank_applied")}


def dashboard(conn, today=None):
    today = today or datetime.date.today().isoformat()
    start, end = month_range(today[:7])
    invs = list_invoices(conn, today=today)
    active = [i for i in invs if i["status"] == "active"]
    zero = Decimal("0.00")
    month_inv = [i for i in active if start <= i["date"] < end]
    overdue = [i for i in active if i["overdue"]]
    collected = sum((p["amount"] for p in conn.execute(
        "SELECT p.amount FROM payment p JOIN invoice i ON i.id = p.invoice_id "
        "WHERE p.date >= ? AND p.date < ? AND i.status = 'active'", (start, end))), zero)  # refunds are negative payments
    credits = sum((r["total"] for r in conn.execute("SELECT total FROM credit_note WHERE date >= ? AND date < ?", (start, end))), zero)
    return {
        "invoiced": sum((i["total"] for i in month_inv), zero) - credits,
        "credited": credits,
        "collected": collected,
        "outstanding": sum((i["outstanding"] for i in active), zero),
        "overdue_count": len(overdue),
        "overdue_amount": sum((i["outstanding"] for i in overdue), zero),
        "month_start": start, "month_end": end,
    }


def whatsapp_link(inv, biz):
    from urllib.parse import quote

    d = datetime.date.fromisoformat(inv["date"]).strftime("%d-%m-%Y")
    pay = f" You can pay by UPI to {biz['upi_id']}." if biz["upi_id"] else ""
    msg = (f"Namaste {inv['customer_name']}, a gentle reminder: invoice {inv['number']} dated {d} has an outstanding "
           f"balance of Rs {inv['outstanding']}.{pay} Thank you! - {biz['name']}")
    phone = normalize_phone(inv.get("customer_phone"))
    return f"https://wa.me/{phone}?text={quote(msg)}"



# ---- item catalog (Phase 2) ----
def _clean_catalog(description, hsn, rate, gst_rate, track_stock=False, reorder_level=""):
    description = (description or "").strip()
    if not description:
        raise ValueError("Item description is required")
    rate = parse_decimal(rate, "Rate", 2)
    try:
        gr = Decimal(str(gst_rate))
    except Exception:
        raise ValueError("Invalid GST rate")
    if gr not in gst.GST_RATES:
        raise ValueError("GST rate must be one of 0, 5, 12, 18, 28")
    reorder = None
    if str(reorder_level if reorder_level is not None else "").strip() != "":
        reorder = parse_decimal(reorder_level, "Reorder level", 3)
    return description, (hsn or "").strip() or None, rate, gr, 1 if track_stock else 0, reorder


def add_catalog_item(conn, description, hsn, rate, gst_rate, track_stock=False, reorder_level=""):
    vals = _clean_catalog(description, hsn, rate, gst_rate, track_stock, reorder_level)
    try:
        return conn.execute("INSERT INTO item_catalog (description, hsn, rate, gst_rate, track_stock, reorder_level) VALUES (?,?,?,?,?,?)",
                            vals).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("An item with this name already exists")


def update_catalog_item(conn, item_id, description, hsn, rate, gst_rate, track_stock=False, reorder_level=""):
    vals = _clean_catalog(description, hsn, rate, gst_rate, track_stock, reorder_level)
    try:
        conn.execute("UPDATE item_catalog SET description=?, hsn=?, rate=?, gst_rate=?, track_stock=?, reorder_level=? WHERE id=?",
                     vals + (item_id,))
    except sqlite3.IntegrityError:
        raise ValueError("An item with this name already exists")


def delete_catalog_item(conn, item_id):
    """A saved item is only a saved price, so it can be deleted, unless it has stock history (then stop tracking it instead)."""
    if conn.execute("SELECT 1 FROM stock_move WHERE item_id = ?", (item_id,)).fetchone():
        raise ValueError("This item has stock history, so it cannot be deleted. Turn off 'Track stock' instead.")
    conn.execute("UPDATE invoice_item SET catalog_id = NULL WHERE catalog_id = ?", (item_id,))
    conn.execute("DELETE FROM item_catalog WHERE id = ?", (item_id,))


def get_catalog_item(conn, item_id):
    return conn.execute("SELECT * FROM item_catalog WHERE id = ?", (item_id,)).fetchone()


def list_catalog(conn):
    return conn.execute("SELECT * FROM item_catalog ORDER BY description COLLATE NOCASE").fetchall()


# ---- GST liability summary (Phase 2) ----
def gst_liability(conn, ym):
    """Per-GST-rate output tax for active invoices in a month. Returns (rows, totals)."""
    start, end = month_range(ym)
    by_rate = {}
    q = ("SELECT it.taxable, it.gst_rate, i.is_interstate FROM invoice_item it JOIN invoice i ON i.id = it.invoice_id "
         "WHERE i.status = 'active' AND i.date >= ? AND i.date < ?")
    for r in conn.execute(q, (start, end)):
        line = gst.calc_line(1, r["taxable"], r["gst_rate"], bool(r["is_interstate"]))
        b = by_rate.setdefault(r["gst_rate"], {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")})
        for k in b:
            b[k] += line[k]
    q = ("SELECT cni.taxable, cni.gst_rate, i.is_interstate FROM credit_note_item cni JOIN credit_note cn ON cn.id = cni.credit_note_id "
         "JOIN invoice i ON i.id = cn.invoice_id WHERE cn.date >= ? AND cn.date < ?")
    for r in conn.execute(q, (start, end)):  # credit notes reduce the liability of the month they are issued in
        line = gst.calc_line(1, r["taxable"], r["gst_rate"], bool(r["is_interstate"]))
        b = by_rate.setdefault(r["gst_rate"], {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")})
        for k in b:
            b[k] -= line[k]
    rows = [dict(rate=rate, **b, tax=b["cgst"] + b["sgst"] + b["igst"]) for rate, b in sorted(by_rate.items())]
    zero = Decimal("0.00")
    totals = {k: sum((r[k] for r in rows), zero) for k in ("taxable", "cgst", "sgst", "igst", "tax")}
    return rows, totals



# ---- purchases (Phase 3) ----
CATEGORIES = ("Goods for resale", "Raw material", "Packaging", "Rent", "Electricity", "Transport", "Repairs",
              "Professional fees", "Office and misc", "Other")


def _clean_purchase(vendor_name, vendor_gstin, vendor_phone, bill_no, date, taxable, cgst, sgst, igst, category, note,
                    rcm=False, rcm_rate="", rcm_inter=False):
    """With reverse charge (rcm) the vendor charged no tax: the buyer works it out from rcm_rate and owes it to the government,
    and pays the vendor only the taxable value. Any tax amounts typed on the form are ignored in that case."""
    vendor_name = (vendor_name or "").strip()
    bill_no = (bill_no or "").strip()
    if not vendor_name:
        raise ValueError("Vendor name is required")
    if not bill_no:
        raise ValueError("Bill number is required")
    gstin = (vendor_gstin or "").strip().upper() or None
    if gstin and not gst.validate_gstin(gstin):
        raise ValueError("Invalid vendor GSTIN")
    date = parse_date(date, "Bill date")
    taxable = parse_decimal(taxable, "Taxable value", 2)
    cgst, sgst, igst = (parse_decimal(v or "0", n, 2) for v, n in ((cgst, "CGST"), (sgst, "SGST"), (igst, "IGST")))
    if rcm:
        try:
            rate = Decimal(str(rcm_rate))
        except Exception:
            raise ValueError("Choose the GST rate for reverse charge")
        if rate not in gst.GST_RATES or rate == 0:
            raise ValueError("Reverse charge needs a GST rate of 5, 12, 18 or 28")
        line = gst.calc_line(1, taxable, rate, bool(rcm_inter))
        cgst, sgst, igst = line["cgst"], line["sgst"], line["igst"]
        total = taxable  # the vendor is paid the taxable value only
    else:
        if igst > 0 and (cgst > 0 or sgst > 0):
            raise ValueError("A bill has either IGST or CGST+SGST, not both")
        total = taxable + cgst + sgst + igst
    category = (category or "").strip() or "Other"
    return (vendor_name, gstin, normalize_phone(vendor_phone) or None, bill_no, date, taxable, cgst, sgst, igst, total,
            category, (note or "").strip() or None, 1 if rcm else 0)


def _check_duplicate_purchase(conn, vals, exclude_id=None):
    gstin, bill_no = vals[1], vals[3]
    if gstin:
        r = conn.execute("SELECT id FROM purchase WHERE vendor_gstin = ? AND bill_no = ? COLLATE NOCASE AND id != ?",
                         (gstin, bill_no, exclude_id or 0)).fetchone()
        if r:
            raise ValueError("This vendor bill is already recorded")


def add_purchase(conn, vendor_name, vendor_gstin, vendor_phone, bill_no, date, taxable, cgst="0", sgst="0", igst="0",
                 category="Other", note="", rcm=False, rcm_rate="", rcm_inter=False):
    vals = _clean_purchase(vendor_name, vendor_gstin, vendor_phone, bill_no, date, taxable, cgst, sgst, igst, category, note,
                           rcm, rcm_rate, rcm_inter)
    with tx(conn):
        _check_duplicate_purchase(conn, vals)
        return conn.execute(
            "INSERT INTO purchase (vendor_name, vendor_gstin, vendor_phone, bill_no, date, taxable, cgst, sgst, igst, total,"
            " category, note, rcm, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (now(),)).lastrowid


def update_purchase(conn, pid, vendor_name, vendor_gstin, vendor_phone, bill_no, date, taxable, cgst="0", sgst="0", igst="0",
                    category="Other", note="", rcm=False, rcm_rate="", rcm_inter=False):
    vals = _clean_purchase(vendor_name, vendor_gstin, vendor_phone, bill_no, date, taxable, cgst, sgst, igst, category, note,
                           rcm, rcm_rate, rcm_inter)
    with tx(conn):
        _check_duplicate_purchase(conn, vals, pid)
        conn.execute(
            "UPDATE purchase SET vendor_name=?, vendor_gstin=?, vendor_phone=?, bill_no=?, date=?, taxable=?, cgst=?, sgst=?,"
            " igst=?, total=?, category=?, note=?, rcm=? WHERE id=?", vals + (pid,))


def rcm_liability(conn, ym):
    """Reverse-charge tax self-assessed on purchases in a month, by rate. Returns (rows, totals). The same amounts are
    claimable as input credit by a regular dealer."""
    start, end = month_range(ym)
    by_rate = {}
    for p in conn.execute("SELECT * FROM purchase WHERE rcm = 1 AND date >= ? AND date < ?", (start, end)):
        tax = p["cgst"] + p["sgst"] + p["igst"]
        rate = (tax * 100 / p["taxable"]).quantize(Decimal("1")) if p["taxable"] else Decimal("0")
        b = by_rate.setdefault(rate, {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")})
        for k in b:
            b[k] += p[k]
    rows = [dict(rate=r, **b, tax=b["cgst"] + b["sgst"] + b["igst"]) for r, b in sorted(by_rate.items())]
    zero = Decimal("0.00")
    return rows, {k: sum((r[k] for r in rows), zero) for k in ("taxable", "cgst", "sgst", "igst", "tax")}


def delete_purchase(conn, pid):
    conn.execute("DELETE FROM purchase WHERE id = ?", (pid,))


def get_purchase(conn, pid):
    return conn.execute("SELECT * FROM purchase WHERE id = ?", (pid,)).fetchone()


def list_purchases(conn, start=None, end=None, category=None):
    sql, args = "SELECT * FROM purchase WHERE 1=1", []
    if start:
        sql += " AND date >= ?"
        args.append(start)
    if end:
        sql += " AND date < ?"
        args.append(end)
    if category:
        sql += " AND category = ?"
        args.append(category)
    return conn.execute(sql + " ORDER BY date DESC, id DESC", args).fetchall()



# ---- staff accounts (Phase 4) ----
RESERVED_NAMES = ("owner",)


def _make_hash(passcode):
    salt = os.urandom(16)
    return salt.hex() + "$" + _hash(passcode, salt)


def _verify_hash(stored, passcode):
    salt, h = stored.split("$")
    return hmac.compare_digest(_hash(passcode or "", bytes.fromhex(salt)), h)


def add_staff(conn, name, passcode):
    name = (name or "").strip()
    if not name or len(name) > 40:
        raise ValueError("Staff name is required (up to 40 characters)")
    if name.lower() in RESERVED_NAMES:
        raise ValueError("That name is reserved")
    if len(passcode or "") < 4:
        raise ValueError("Passcode must be at least 4 characters")
    try:
        return conn.execute("INSERT INTO staff (name, passcode, created_at) VALUES (?,?,?)",
                            (name, _make_hash(passcode), now())).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("A staff member with this name already exists")


def list_staff(conn):
    return conn.execute("SELECT id, name, active, created_at FROM staff ORDER BY name COLLATE NOCASE").fetchall()


def get_staff(conn, staff_id):
    return conn.execute("SELECT id, name, active FROM staff WHERE id = ?", (staff_id,)).fetchone()


def set_staff_active(conn, staff_id, active):
    conn.execute("UPDATE staff SET active = ? WHERE id = ?", (1 if active else 0, staff_id))


def reset_staff_passcode(conn, staff_id, passcode):
    if len(passcode or "") < 4:
        raise ValueError("Passcode must be at least 4 characters")
    conn.execute("UPDATE staff SET passcode = ? WHERE id = ?", (_make_hash(passcode), staff_id))


def check_staff(conn, name, passcode):
    """Return the staff id if the name and passcode are right and the account is active, else None."""
    r = conn.execute("SELECT id, passcode, active FROM staff WHERE name = ?", ((name or "").strip(),)).fetchone()
    if r and r["active"] and _verify_hash(r["passcode"], passcode):
        return r["id"]
    return None



# ---- dashboard analytics ----
def monthly_series(conn, today=None, n=6):
    """Invoiced and collected per month for the last n months, oldest first (active invoices only)."""
    today = today or datetime.date.today().isoformat()
    y, m = int(today[:4]), int(today[5:7])
    months = []
    for _ in range(n):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    zero = Decimal("0.00")
    inv = {k: zero for k in months}
    col = {k: zero for k in months}
    for r in conn.execute("SELECT date, total FROM invoice WHERE status = 'active' AND date >= ?", (months[0] + "-01",)):
        if r["date"][:7] in inv:
            inv[r["date"][:7]] += r["total"]
    for r in conn.execute("SELECT date, total FROM credit_note WHERE date >= ?", (months[0] + "-01",)):
        if r["date"][:7] in inv:
            inv[r["date"][:7]] -= r["total"]  # credit notes reduce what was invoiced in their month
    for r in conn.execute("SELECT p.date, p.amount FROM payment p JOIN invoice i ON i.id = p.invoice_id "
                          "WHERE i.status = 'active' AND p.date >= ?", (months[0] + "-01",)):
        if r["date"][:7] in col:
            col[r["date"][:7]] += r["amount"]
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return [{"ym": k, "label": names[int(k[5:]) - 1], "invoiced": inv[k], "collected": col[k]} for k in months]


def aging(conn, today=None):
    """Outstanding amount by how late it is, measured from each invoice's due date."""
    today = today or datetime.date.today().isoformat()
    t = datetime.date.fromisoformat(today)
    buckets = [("Not yet due", 0), ("1-15 days late", 0), ("16-30 days late", 0), ("31-60 days late", 0), ("Over 60 days", 0)]
    amounts = [Decimal("0.00")] * 5
    counts = [0] * 5
    for i in list_invoices(conn, today=today):
        if i["status"] != "active" or i["outstanding"] <= 0:
            continue
        late = (t - datetime.date.fromisoformat(i["due_date"])).days
        idx = 0 if late <= 0 else 1 if late <= 15 else 2 if late <= 30 else 3 if late <= 60 else 4
        amounts[idx] += i["outstanding"]
        counts[idx] += 1
    return [{"label": b[0], "amount": a, "count": c} for b, a, c in zip(buckets, amounts, counts)]



# ---- credit notes, refunds, reminders ----
def _remaining_qty(conn, item):
    """Quantity of an invoice line that has not been credited yet."""
    used = sum((r["qty"] for r in conn.execute("SELECT qty FROM credit_note_item WHERE invoice_item_id = ?", (item["id"],))),
               Decimal("0"))
    return item["qty"] - used


def create_credit_note(conn, invoice_id, date, quantities, reason, by=None, restock=True):
    """Credit part or all of an invoice. quantities: {invoice_item_id: quantity to credit}. Own number series: <prefix>-CN/<FY>/<seq>.
    restock=True puts credited goods of tracked items back into stock (use False for a price correction with no goods returned)."""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required for a credit note")
    date = parse_date(date, "Credit note date")
    biz = get_business(conn)
    if not biz:
        raise ValueError("Set up the business profile first")
    with tx(conn):
        inv = conn.execute("SELECT * FROM invoice WHERE id = ?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found")
        if inv["status"] == "cancelled":
            raise ValueError("Cannot issue a credit note on a cancelled invoice")
        if date < inv["date"]:
            raise ValueError("A credit note cannot be dated before its invoice")
        lines = []
        for item in conn.execute("SELECT * FROM invoice_item WHERE invoice_id = ? ORDER BY line_no", (invoice_id,)).fetchall():
            raw = str(quantities.get(item["id"], "") or "").strip()
            if not raw:
                continue
            qty = parse_decimal(raw, f"Credit quantity for line {item['line_no']}", 3, allow_zero=False)
            left = _remaining_qty(conn, item)
            if qty > left:
                raise ValueError(f"Line {item['line_no']} ({item['description']}): only {left.normalize():f} left to credit")
            lines.append((item, qty, gst.calc_line(qty, item["rate"], item["gst_rate"], bool(inv["is_interstate"]))))
        if not lines:
            raise ValueError("Enter a quantity for at least one line")
        t = {k: sum((l[2][k] for l in lines), Decimal("0.00")) for k in ("taxable", "cgst", "sgst", "igst")}
        total = t["taxable"] + t["cgst"] + t["sgst"] + t["igst"]
        fy, prefix = fy_label(date, biz["fy_start_month"]), biz["invoice_prefix"] + "-CN"
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM credit_note WHERE prefix = ? AND fy = ?", (prefix, fy)).fetchone()[0]
        number = f"{prefix}/{fy}/{seq:04d}"
        cn_id = conn.execute(
            "INSERT INTO credit_note (number, fy, prefix, seq, date, invoice_id, reason, taxable, cgst, sgst, igst, total, created_at, created_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (number, fy, prefix, seq, date, invoice_id, reason, t["taxable"], t["cgst"], t["sgst"], t["igst"], total, now(), by)).lastrowid
        for n, (item, qty, calc) in enumerate(lines, 1):
            conn.execute(
                "INSERT INTO credit_note_item (credit_note_id, invoice_item_id, line_no, description, hsn, qty, rate, gst_rate, taxable, tax)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cn_id, item["id"], n, item["description"], item["hsn"], qty, item["rate"], item["gst_rate"], calc["taxable"], calc["tax"]))
            if restock and item["catalog_id"]:
                cat = conn.execute("SELECT track_stock FROM item_catalog WHERE id = ?", (item["catalog_id"],)).fetchone()
                if cat and cat["track_stock"]:
                    _stock_move(conn, item["catalog_id"], date, qty, "return", None, f"Credit note {number}", by, cn_id)
    return cn_id


def get_credit_note(conn, cn_id):
    row = conn.execute(
        "SELECT cn.*, i.number AS invoice_number, i.date AS invoice_date, i.is_interstate, c.name AS customer_name, "
        "c.phone AS customer_phone, c.gstin AS customer_gstin, c.state AS customer_state, c.address AS customer_address "
        "FROM credit_note cn JOIN invoice i ON i.id = cn.invoice_id JOIN customer c ON c.id = i.customer_id WHERE cn.id = ?",
        (cn_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["items"] = conn.execute("SELECT * FROM credit_note_item WHERE credit_note_id = ? ORDER BY line_no", (cn_id,)).fetchall()
    breakup = {}
    for it in d["items"]:
        line = gst.calc_line(1, it["taxable"], it["gst_rate"], bool(d["is_interstate"]))
        b = breakup.setdefault(it["gst_rate"], {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")})
        for k in b:
            b[k] += line[k]
    d["breakup"] = dict(sorted(breakup.items()))
    return d


def list_credit_notes(conn, start=None, end=None):
    sql = ("SELECT cn.*, i.number AS invoice_number, c.name AS customer_name, c.gstin AS customer_gstin, c.state AS customer_state "
           "FROM credit_note cn JOIN invoice i ON i.id = cn.invoice_id JOIN customer c ON c.id = i.customer_id WHERE 1=1")
    args = []
    if start:
        sql += " AND cn.date >= ?"
        args.append(start)
    if end:
        sql += " AND cn.date < ?"
        args.append(end)
    return conn.execute(sql + " ORDER BY cn.date DESC, cn.id DESC", args).fetchall()


def add_refund(conn, inv_id, date, amount, mode, note="", by=None):
    """Money handed back to a customer after a credit note. Stored as a negative payment; limited to what is owed back."""
    date = parse_date(date, "Refund date")
    amount = parse_decimal(amount, "Refund amount", 2, allow_zero=False)
    if mode not in ("cash", "upi", "bank", "other"):
        raise ValueError("Invalid payment mode")
    with tx(conn):
        inv = conn.execute("SELECT status, total FROM invoice WHERE id = ?", (inv_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found")
        paid = sum((r["amount"] for r in conn.execute("SELECT amount FROM payment WHERE invoice_id = ?", (inv_id,))), Decimal("0.00"))
        credited = sum((r["total"] for r in conn.execute("SELECT total FROM credit_note WHERE invoice_id = ?", (inv_id,))), Decimal("0.00"))
        owed_back = paid - (inv["total"] - credited)
        if owed_back <= 0:
            raise ValueError("Nothing is due back to the customer on this invoice")
        if amount > owed_back:
            raise ValueError(f"Refund blocked: only {owed_back} is due back")
        text = ("Refund: " + (note or "").strip()).strip().rstrip(":")
        return conn.execute("INSERT INTO payment (invoice_id, date, amount, mode, note, created_at, created_by) VALUES (?,?,?,?,?,?,?)",
                            (inv_id, date, -amount, mode, text, now(), by)).lastrowid


def log_reminder(conn, inv_id, by=None):
    conn.execute("INSERT INTO reminder_log (invoice_id, sent_at, by) VALUES (?,?,?)", (inv_id, now(), by))


def reminder_stats(conn, today=None, days=90, window=3):
    """Of the payments received in the last `days` days, how many came within `window` days after a reminder."""
    today = today or datetime.date.today().isoformat()
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    reminders = {}
    for r in conn.execute("SELECT invoice_id, sent_at FROM reminder_log"):
        reminders.setdefault(r["invoice_id"], []).append(datetime.date.fromisoformat(r["sent_at"][:10]))
    total = driven = 0
    for p in conn.execute("SELECT invoice_id, date, amount FROM payment WHERE amount > 0 AND date >= ? AND date <= ?", (since, today)):
        total += 1
        d = datetime.date.fromisoformat(p["date"])
        if any(s <= d <= s + datetime.timedelta(days=window) for s in reminders.get(p["invoice_id"], ())):
            driven += 1
    return {"payments": total, "driven": driven, "reminders": sum(len(v) for v in reminders.values()), "days": days, "window": window}


# ---- integrations: API keys, bill photos, payment links ----
INTEGRATION_KEYS = ("anthropic_api_key", "ai_model", "razorpay_key_id", "razorpay_key_secret")


def mask_secret(value):
    """Show just enough of a secret to recognise it: sk-ant-…a1b2."""
    v = value or ""
    return "" if not v else (v[:7] + "…" + v[-4:] if len(v) > 14 else "…" + v[-2:])


def get_integrations(conn):
    """Settings used by the AI and payment-link features. The environment variable ANTHROPIC_API_KEY is a fallback."""
    out = {k: get_setting(conn, k) or "" for k in INTEGRATION_KEYS}
    if not out["anthropic_api_key"]:
        out["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    out["ai_model"] = out["ai_model"] or "claude-opus-5-5"
    return out


def save_integrations(conn, anthropic_key=None, ai_model=None, razorpay_id=None, razorpay_secret=None):
    """None leaves a value unchanged; an empty string removes it."""
    for key, value in (("anthropic_api_key", anthropic_key), ("ai_model", ai_model), ("razorpay_key_id", razorpay_id),
                       ("razorpay_key_secret", razorpay_secret)):
        if value is None:
            continue
        value = value.strip()
        if key == "anthropic_api_key" and value and not value.startswith("sk-ant-"):
            raise ValueError("That does not look like an Anthropic API key (it should start with sk-ant-).")
        if key == "razorpay_key_id" and value and not re.fullmatch(r"rzp_(test|live)_[A-Za-z0-9]+", value):
            raise ValueError("A Razorpay key id looks like rzp_test_xxxx or rzp_live_xxxx.")
        if key == "ai_model" and value and value not in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
            raise ValueError("Choose one of the listed models.")
        if value:
            set_setting(conn, key, value)
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def set_purchase_photo(conn, pid, filename):
    conn.execute("UPDATE purchase SET photo = ? WHERE id = ?", (filename, pid))


def add_gateway_link(conn, invoice_id, link_id, short_url, amount, status, by=None):
    return conn.execute("INSERT INTO gateway_link (invoice_id, link_id, short_url, amount, status, created_at, created_by) "
                        "VALUES (?,?,?,?,?,?,?)", (invoice_id, link_id, short_url, amount, status, now(), by)).lastrowid


def list_gateway_links(conn, invoice_id=None, only_open=False):
    sql, args = "SELECT * FROM gateway_link WHERE 1=1", []
    if invoice_id:
        sql += " AND invoice_id = ?"
        args.append(invoice_id)
    if only_open:
        sql += " AND status NOT IN ('paid', 'cancelled', 'expired') AND payment_id IS NULL"
    return conn.execute(sql + " ORDER BY id DESC", args).fetchall()


def settle_gateway_link(conn, link_row, status, amount_paid, by=None, today=None):
    """Record what Razorpay reported. When the link is fully paid, the payment is added to the invoice exactly once
    (the same link can never be recorded twice). Returns a short message for the owner."""
    today = today or datetime.date.today().isoformat()
    conn.execute("UPDATE gateway_link SET status = ?, checked_at = ? WHERE id = ?", (status, now(), link_row["id"]))
    if status != "paid" or link_row["payment_id"]:
        return {"paid": "already recorded", "partially_paid": "partly paid: waiting for the rest"}.get(status, f"status: {status}")
    try:
        pid = add_payment(conn, link_row["invoice_id"], today, amount_paid, "upi", f"Payment link {link_row['link_id']}", by=by,
                          bank_key=f"gw:{link_row['link_id']}")
    except ValueError as exc:
        return f"paid on Razorpay but not recorded: {exc}"
    conn.execute("UPDATE gateway_link SET payment_id = ? WHERE id = ?", (pid, link_row["id"]))
    return "paid: payment recorded on the invoice"


# ---- stock tracking ----
def _stock_move(conn, item_id, date, qty, kind, invoice_id=None, note=None, by=None, credit_note_id=None):
    return conn.execute(
        "INSERT INTO stock_move (item_id, date, qty, kind, invoice_id, credit_note_id, note, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
        (item_id, date, Decimal(qty).quantize(Decimal("0.001")), kind, invoice_id, credit_note_id, note, now(), by)).lastrowid


def _reverse_invoice_stock(conn, inv_id, date, by, kind):
    """Undo whatever an invoice has done to stock so far (used when it is edited or cancelled). History is kept: nothing is deleted."""
    net = {}
    for r in conn.execute("SELECT item_id, qty FROM stock_move WHERE invoice_id = ?", (inv_id,)):
        net[r["item_id"]] = net.get(r["item_id"], Decimal("0")) + r["qty"]
    why = "Invoice cancelled" if kind == "cancel" else "Invoice edited"
    for item_id, q in net.items():
        if q != 0:
            _stock_move(conn, item_id, date, -q, kind, inv_id, why, by)


def stock_on_hand(conn, item_id=None):
    """{item_id: quantity in stock}, from the movement history."""
    sums = {}
    sql, args = "SELECT item_id, qty FROM stock_move", ()
    if item_id:
        sql, args = sql + " WHERE item_id = ?", (item_id,)
    for r in conn.execute(sql, args):
        sums[r["item_id"]] = sums.get(r["item_id"], Decimal("0")) + r["qty"]
    return sums


def stock_levels(conn, only_attention=False):
    """Every tracked item with its quantity in stock and a status: ok, low (at or below the reorder level) or out (zero or less)."""
    on_hand = stock_on_hand(conn)
    out = []
    for r in conn.execute("SELECT * FROM item_catalog WHERE track_stock = 1 ORDER BY description COLLATE NOCASE"):
        q = on_hand.get(r["id"], Decimal("0"))
        status = "out" if q <= 0 else "low" if r["reorder_level"] is not None and q <= r["reorder_level"] else "ok"
        if only_attention and status == "ok":
            continue
        out.append(dict(r, on_hand=q, status=status))
    return out


def _tracked_item(conn, item_id):
    item = conn.execute("SELECT * FROM item_catalog WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ValueError("Item not found")
    if not item["track_stock"]:
        raise ValueError("Stock is not tracked for this item. Turn on 'Track stock' on the Items page first.")
    return item


def receive_stock(conn, item_id, date, qty, note="", by=None, kind="received"):
    """Goods coming in (a delivery from a supplier) or an opening balance (kind='opening')."""
    if kind not in ("received", "opening"):
        raise ValueError("Invalid stock entry type")
    _tracked_item(conn, item_id)
    date = parse_date(date, "Date")
    qty = parse_decimal(qty, "Quantity", 3, allow_zero=False)
    return _stock_move(conn, item_id, date, qty, kind, None, (note or "").strip() or None, by)


def adjust_stock(conn, item_id, date, counted, note, by=None):
    """Set the stock to what you actually counted. The difference is recorded, with a reason, as an adjustment."""
    note = (note or "").strip()
    if not note:
        raise ValueError("Give a reason for the adjustment (for example: stock count, damaged, expired)")
    with tx(conn):
        _tracked_item(conn, item_id)
        date = parse_date(date, "Date")
        counted = parse_decimal(counted, "Counted quantity", 3)
        diff = counted - stock_on_hand(conn, item_id).get(item_id, Decimal("0"))
        if diff == 0:
            raise ValueError("The count matches what the books already show")
        return _stock_move(conn, item_id, date, diff, "adjust", None, note, by)


def stock_history(conn, item_id, limit=300):
    return conn.execute(
        "SELECT m.*, i.number AS invoice_number, cn.number AS credit_note_number FROM stock_move m "
        "LEFT JOIN invoice i ON i.id = m.invoice_id LEFT JOIN credit_note cn ON cn.id = m.credit_note_id "
        "WHERE m.item_id = ? ORDER BY m.date DESC, m.id DESC LIMIT ?", (item_id, int(limit))).fetchall()


def stock_alerts_for_invoice(conn, inv_id):
    """After an invoice is saved: plain-language warnings for tracked items it has pushed to zero, below zero, or to the reorder level."""
    ids = {r["catalog_id"] for r in conn.execute("SELECT catalog_id FROM invoice_item WHERE invoice_id = ? AND catalog_id IS NOT NULL", (inv_id,))}
    alerts = []
    for lvl in stock_levels(conn):
        if lvl["id"] in ids and lvl["status"] != "ok":
            q = lvl["on_hand"].normalize()
            qs = format(q, "f")
            alerts.append(f"{lvl['description']}: {'out of stock' if q == 0 else f'{qs} in stock (below zero: check your count)' if q < 0 else f'only {qs} left'}")
    return alerts


# ---- recurring invoices ----
FREQUENCIES = ("weekly", "monthly", "quarterly", "yearly")


def add_months(d, months, anchor_day):
    """d moved forward by whole months, landing on anchor_day or the month's last day if it is shorter (31st -> 28th/30th)."""
    idx = d.month - 1 + months
    y, m = d.year + idx // 12, idx % 12 + 1
    return datetime.date(y, m, min(anchor_day, calendar.monthrange(y, m)[1]))


def next_occurrence(iso, frequency, anchor_day):
    d = datetime.date.fromisoformat(iso)
    if frequency == "weekly":
        return (d + datetime.timedelta(days=7)).isoformat()
    return add_months(d, {"monthly": 1, "quarterly": 3, "yearly": 12}[frequency], anchor_day).isoformat()


def create_recurring(conn, customer_id, frequency, start_date, end_date, items, supply_type="regular", note="", by=None):
    """A template that comes due on a schedule. It never creates an invoice by itself: due ones wait for the owner to confirm."""
    if frequency not in FREQUENCIES:
        raise ValueError("Choose how often it repeats")
    start = parse_date(start_date, "First date")
    end = parse_date(end_date, "End date") if (end_date or "").strip() else None
    if end and end < start:
        raise ValueError("The end date is before the first date")
    p = _prepare_invoice(conn, customer_id, start, items, None, supply_type)  # rejects anything that could not become an invoice
    with tx(conn):
        rid = conn.execute(
            "INSERT INTO recurring (customer_id, frequency, anchor_day, next_date, end_date, supply_type, note, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (customer_id, frequency, int(start[8:10]), start, end, supply_type, (note or "").strip() or None, now(), by)).lastrowid
        for n, it in enumerate(p["items"], 1):
            conn.execute("INSERT INTO recurring_item (recurring_id, line_no, description, hsn, qty, rate, gst_rate) VALUES (?,?,?,?,?,?,?)",
                         (rid, n, it["description"], it["hsn"], it["qty"], it["rate"], it["gst_rate"]))
    return rid


def create_recurring_from_invoice(conn, inv_id, frequency, start_date, end_date="", by=None):
    inv = get_invoice(conn, inv_id)
    if not inv or inv["status"] != "active":
        raise ValueError("Only an active invoice can be repeated")
    items = [{"description": i["description"], "hsn": i["hsn"] or "", "qty": str(i["qty"]), "rate": str(i["rate"]),
              "gst_rate": format(i["gst_rate"].normalize(), "f")} for i in inv["items"]]
    return create_recurring(conn, inv["customer_id"], frequency, start_date, end_date, items, inv["supply_type"], f"Repeats {inv['number']}", by)


def get_recurring(conn, rid):
    row = conn.execute("SELECT r.*, c.name AS customer_name FROM recurring r JOIN customer c ON c.id = r.customer_id WHERE r.id = ?",
                       (rid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["items"] = conn.execute("SELECT * FROM recurring_item WHERE recurring_id = ? ORDER BY line_no", (rid,)).fetchall()
    return d


def _recurring_items(rec):
    return [{"description": i["description"], "hsn": i["hsn"] or "", "qty": str(i["qty"]), "rate": str(i["rate"]),
             "gst_rate": format(i["gst_rate"].normalize(), "f")} for i in rec["items"]]


def recurring_estimate(conn, rec):
    """The total the next invoice would have today, or None if it could not be created (for example the customer was changed)."""
    try:
        return _prepare_invoice(conn, rec["customer_id"], rec["next_date"], _recurring_items(rec), None, rec["supply_type"])["calc"]["totals"]["total"]
    except ValueError:
        return None


def list_recurring(conn, today=None):
    today = today or datetime.date.today().isoformat()
    out = []
    for r in conn.execute("SELECT id FROM recurring ORDER BY active DESC, next_date, id"):
        rec = get_recurring(conn, r["id"])
        rec["estimate"] = recurring_estimate(conn, rec)
        rec["due"] = bool(rec["active"] and rec["next_date"] <= today and (not rec["end_date"] or rec["next_date"] <= rec["end_date"]))
        rec["missed"] = 0
        if rec["due"]:  # earlier periods that passed unbilled (the app was not opened); only the latest one is created
            n, nxt = 0, rec["next_date"]
            while nxt <= today:
                nxt = next_occurrence(nxt, rec["frequency"], rec["anchor_day"])
                n += 1
            rec["missed"] = n - 1
        out.append(rec)
    return out


def recurring_due(conn, today=None):
    return [r for r in list_recurring(conn, today) if r["due"]]


def set_recurring_active(conn, rid, active):
    conn.execute("UPDATE recurring SET active = ? WHERE id = ?", (1 if active else 0, rid))


def delete_recurring(conn, rid):
    """Removes the schedule only. Invoices it already created stay exactly as they are."""
    with tx(conn):
        conn.execute("DELETE FROM recurring_item WHERE recurring_id = ?", (rid,))
        conn.execute("DELETE FROM recurring WHERE id = ?", (rid,))


def run_recurring(conn, rid, invoice_date, today=None, by=None):
    """Create the invoice for a due schedule. Returns (invoice_id, skipped) where skipped counts earlier due dates that were
    missed (the app was not opened) and are not billed retroactively. The run is claimed before the invoice is made, so pressing
    the button twice, or two browsers at once, can never create it twice."""
    today = today or datetime.date.today().isoformat()
    invoice_date = parse_date(invoice_date, "Invoice date")
    rec = get_recurring(conn, rid)
    if not rec or not rec["active"]:
        raise ValueError("This recurring invoice is not active")
    old = rec["next_date"]
    if old > today:
        raise ValueError("This one is not due yet")
    if rec["end_date"] and old > rec["end_date"]:
        raise ValueError("This schedule has ended")
    nxt, passed = old, 0
    while nxt <= today:
        nxt = next_occurrence(nxt, rec["frequency"], rec["anchor_day"])
        passed += 1
    claimed = conn.execute("UPDATE recurring SET next_date = ? WHERE id = ? AND next_date = ? AND active = 1", (nxt, rid, old)).rowcount
    if claimed != 1:
        raise ValueError("This recurring invoice was already created")
    try:
        inv_id = create_invoice(conn, rec["customer_id"], invoice_date, _recurring_items(rec), by=by or "Recurring", supply_type=rec["supply_type"])
    except Exception:
        conn.execute("UPDATE recurring SET next_date = ? WHERE id = ?", (old, rid))  # nothing was created, so the schedule stays due
        raise
    still_active = 0 if (rec["end_date"] and nxt > rec["end_date"]) else 1
    conn.execute("UPDATE recurring SET last_invoice_id = ?, last_run = ?, runs = runs + 1, active = ? WHERE id = ?",
                 (inv_id, today, still_active, rid))
    return inv_id, passed - 1
