"""CSV exports. All CSV is UTF-8 with BOM so Excel shows Hindi names correctly."""
import csv
import io
import os
import sqlite3
import tempfile
import zipfile
from decimal import Decimal

import db
import xlsx

BOM = "﻿"
ZERO = Decimal("0.00")


def _csv(rows, header):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    return (BOM + buf.getvalue()).encode("utf-8")


def _dmy(iso):
    return f"{iso[8:10]}-{iso[5:7]}-{iso[:4]}"


def _sales_table(conn, ym):
    """Header and rows of the monthly sales register. Cancelled invoices keep their number with zero amounts.
    Credit notes follow the invoices as negative rows, so the TOTAL row is the net figure for the month."""
    start, end = db.month_range(ym)
    invs = sorted(db.list_invoices(conn, start, end), key=lambda i: (i["date"], i["id"]))
    rows, tot = [], {k: ZERO for k in ("taxable", "cgst", "sgst", "igst", "total", "paid")}
    for i in invs:
        cancelled = i["status"] == "cancelled"
        vals = {k: (ZERO if cancelled else i[k]) for k in ("taxable", "cgst", "sgst", "igst", "total")}
        vals["paid"] = i["paid"]
        for k in tot:
            tot[k] += vals[k]
        rows.append([i["number"], _dmy(i["date"]), i["customer_name"], i["customer_gstin"] or "", i["customer_state"] or "",
                     vals["taxable"], vals["cgst"], vals["sgst"], vals["igst"], vals["total"], i["status_label"],
                     vals["paid"]])
    for n in sorted(db.list_credit_notes(conn, start, end), key=lambda n: (n["date"], n["id"])):
        vals = {k: -n[k] for k in ("taxable", "cgst", "sgst", "igst", "total")}
        for k in vals:
            tot[k] += vals[k]
        rows.append([n["number"], _dmy(n["date"]), n["customer_name"], n["customer_gstin"] or "", n["customer_state"] or "",
                     vals["taxable"], vals["cgst"], vals["sgst"], vals["igst"], vals["total"],
                     f"Credit note against {n['invoice_number']}", ZERO])
    rows.append(["TOTAL", "", "", "", "", tot["taxable"], tot["cgst"], tot["sgst"], tot["igst"], tot["total"], "", tot["paid"]])
    header = ["Invoice number", "Invoice date", "Customer name", "Customer GSTIN", "Customer state", "Taxable value",
              "CGST", "SGST", "IGST", "Total", "Status", "Amount paid"]
    return header, rows


def sales_register(conn, ym):
    header, rows = _sales_table(conn, ym)
    return _csv(rows, header)


def sales_register_xlsx(conn, ym):
    header, rows = _sales_table(conn, ym)
    return xlsx.workbook([(f"Sales {ym}", [header] + rows)])


def gst_liability_xlsx(conn, ym):
    rows, tot = db.gst_liability(conn, ym)
    out = [["GST rate", "Taxable value", "CGST", "SGST", "IGST", "Total tax"]]
    out += [[f"{r['rate'].normalize():f}%", r["taxable"], r["cgst"], r["sgst"], r["igst"], r["tax"]] for r in rows]
    out.append(["TOTAL", tot["taxable"], tot["cgst"], tot["sgst"], tot["igst"], tot["tax"]])
    sheets = [(f"GST liability {ym}", out)]
    rrows, rtot = db.rcm_liability(conn, ym)
    if rrows:
        sheets.append(("Reverse charge", [["GST rate", "Taxable value", "CGST", "SGST", "IGST", "Total tax"]] + [
            [f"{r['rate'].normalize():f}%", r["taxable"], r["cgst"], r["sgst"], r["igst"], r["tax"]] for r in rrows]
            + [["TOTAL", rtot["taxable"], rtot["cgst"], rtot["sgst"], rtot["igst"], rtot["tax"]]]))
    return xlsx.workbook(sheets)


def gst_liability(conn, ym):
    """Monthly output-tax summary by GST rate (active invoices only), with a total row."""
    rows, tot = db.gst_liability(conn, ym)
    out = [[f"{r['rate'].normalize():f}%", r["taxable"], r["cgst"], r["sgst"], r["igst"], r["tax"]] for r in rows]
    out.append(["TOTAL", tot["taxable"], tot["cgst"], tot["sgst"], tot["igst"], tot["tax"]])
    rrows, rtot = db.rcm_liability(conn, ym)
    if rrows:  # reverse-charge tax is shown as its own block under the output tax
        out.append([])
        out.append(["Reverse charge on purchases", "", "", "", "", ""])
        out += [[f"{r['rate'].normalize():f}%", r["taxable"], r["cgst"], r["sgst"], r["igst"], r["tax"]] for r in rrows]
        out.append(["RCM TOTAL", rtot["taxable"], rtot["cgst"], rtot["sgst"], rtot["igst"], rtot["tax"]])
    return _csv(out, ["GST rate", "Taxable value", "CGST", "SGST", "IGST", "Total tax"])


def purchase_register(conn, ym):
    start, end = db.month_range(ym)
    rows, tot = [], {k: ZERO for k in ("taxable", "cgst", "sgst", "igst", "total")}
    for p in sorted(db.list_purchases(conn, start, end), key=lambda p: (p["date"], p["id"])):
        for k in tot:
            tot[k] += p[k]
        rows.append([p["bill_no"], _dmy(p["date"]), p["vendor_name"], p["vendor_gstin"] or "", p["category"], p["taxable"],
                     p["cgst"], p["sgst"], p["igst"], p["total"], "Yes" if p["rcm"] else ""])
    rows.append(["TOTAL", "", "", "", "", tot["taxable"], tot["cgst"], tot["sgst"], tot["igst"], tot["total"], ""])
    return _csv(rows, ["Bill number", "Bill date", "Vendor", "Vendor GSTIN", "Category", "Taxable value", "CGST", "SGST",
                       "IGST", "Total", "Reverse charge"])


def client_pack(conn, ym):
    """One zip for the CA: sales and purchase registers, GST liability, invoices and payments."""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"sales-register-{ym}.csv", sales_register(conn, ym))
        z.writestr(f"sales-register-{ym}.xlsx", sales_register_xlsx(conn, ym))
        z.writestr(f"purchase-register-{ym}.csv", purchase_register(conn, ym))
        z.writestr(f"gst-liability-{ym}.csv", gst_liability(conn, ym))
        z.writestr("payments.csv", payment_register(conn))
        z.writestr("invoices.csv", invoice_list(conn))
    return mem.getvalue()


def invoice_list(conn):
    rows = [[i["number"], _dmy(i["date"]), _dmy(i["due_date"]), i["customer_name"], i["total"], i["paid"], i["outstanding"],
             i["status_label"]] for i in db.list_invoices(conn)]
    return _csv(rows, ["Invoice number", "Date", "Due date", "Customer", "Total", "Paid", "Outstanding", "Status"])


def payment_register(conn):
    q = ("SELECT p.date, i.number, c.name, p.amount, p.mode, p.note FROM payment p JOIN invoice i ON i.id = p.invoice_id "
         "JOIN customer c ON c.id = i.customer_id ORDER BY p.date, p.id")
    rows = [[_dmy(r["date"]), r["number"], r["name"], r["amount"], r["mode"], r["note"] or ""] for r in conn.execute(q)]
    return _csv(rows, ["Date", "Invoice number", "Customer", "Amount", "Mode", "Note"])


TABLES = ("business", "customer", "invoice", "invoice_item", "payment", "item_catalog", "purchase", "credit_note",
          "credit_note_item", "reminder_log", "audit_log")


def full_export_zip(conn):
    """Zip with one CSV per table plus a consistent SQLite snapshot."""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for t in TABLES:
            cur = conn.execute(f"SELECT * FROM {t}")
            cols = [c[0] for c in cur.description]
            z.writestr(f"{t}.csv", _csv([[r[c] for c in cols] for r in cur], cols))
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            out = sqlite3.connect(path)
            conn.backup(out)
            out.close()
            z.write(path, "billsaathi.db")
        finally:
            os.remove(path)
    return mem.getvalue()
