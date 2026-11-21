"""Purchase register vs GSTR-2B reconciliation. Pure functions; no database access.

Rows are dicts: gstin, name, inv_raw, inv_key, date (ISO), taxable, cgst, sgst, igst, tax, phone, line.
The output is an exceptions list: only what did not match needs a human to look at it.
"""
import csv
import datetime
import io
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

ZERO = Decimal("0.00")
# normalized header (lowercase, letters and digits only) -> field
ALIASES = {
    "gstin": ("gstin", "gstinofsupplier", "suppliergstin", "vendorgstin", "gstinuin", "gstinofsupplierwithgstin"),
    "inv": ("invoicenumber", "invoiceno", "invoice", "billno", "billnumber", "invno", "documentnumber", "invoicenumberofsupplier"),
    "date": ("invoicedate", "date", "billdate", "documentdate"),
    "taxable": ("taxablevalue", "taxable", "taxablevaluers", "taxablevalue"),
    "cgst": ("centraltax", "cgst", "centraltaxrs"),
    "sgst": ("stateuttax", "statetax", "sgst", "sgstutgst", "stateuttaxrs"),
    "igst": ("integratedtax", "igst", "integratedtaxrs"),
    "name": ("tradelegalname", "tradename", "legalname", "suppliername", "vendorname", "name"),
    "phone": ("phone", "vendorphone", "mobile"),
}
REQUIRED = ("gstin", "inv", "date", "taxable")
DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%y", "%d %b %Y")


def _h(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def inv_key(s):
    """Compare invoice numbers ignoring case, punctuation and leading zeros."""
    s = re.sub(r"(?<![0-9])0+(?=[0-9])", "", (s or "").upper())  # leading zeros of every digit run
    return re.sub(r"[^A-Z0-9]", "", s)


def parse_date(s):
    s = (s or "").strip()
    for f in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date '{s}'")


def parse_amount(s):
    s = re.sub(r"[,\s₹]|Rs\.?", "", (s or "").strip()) or "0"
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"bad amount '{s}'")


def parse_csv(text):
    """Return (rows, errors). Raises ValueError if required columns are missing."""
    text = (text or "").lstrip("﻿").strip()
    if not text:
        return [], []
    first = text.splitlines()[0]
    delim = "\t" if first.count("\t") > first.count(",") else ("," if first.count(",") >= first.count(";") else ";")
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header = next(reader)
    col = {}
    for i, h in enumerate(header):
        for field, names in ALIASES.items():
            if _h(h) in names and field not in col:
                col[field] = i
    missing = [f for f in REQUIRED if f not in col]
    if missing:
        names = {"gstin": "supplier GSTIN", "inv": "invoice number", "date": "invoice date", "taxable": "taxable value"}
        raise ValueError("Missing column(s): " + ", ".join(names[m] for m in missing))
    rows, errors = [], []
    for n, rec in enumerate(reader, 2):
        if not any(c.strip() for c in rec):
            continue

        def get(f):
            return rec[col[f]].strip() if f in col and col[f] < len(rec) else ""

        try:
            r = {"gstin": get("gstin").upper(), "name": get("name"), "inv_raw": get("inv"), "inv_key": inv_key(get("inv")),
                 "date": parse_date(get("date")), "taxable": parse_amount(get("taxable")), "cgst": parse_amount(get("cgst")),
                 "sgst": parse_amount(get("sgst")), "igst": parse_amount(get("igst")), "phone": get("phone"), "line": n}
            if not r["gstin"] or not r["inv_key"]:
                raise ValueError("supplier GSTIN and invoice number are required")
        except ValueError as exc:
            errors.append(f"Line {n}: {exc}")
            continue
        r["tax"] = r["cgst"] + r["sgst"] + r["igst"]
        rows.append(r)
    return rows, errors


def _amount_diff(b, p):
    return abs(b["taxable"] - p["taxable"]), abs(b["tax"] - p["tax"])


def match(books, portal, tol=Decimal("1.00"), date_days=3):
    """Return dict: matched, mismatched, probable, books_only, portal_only (lists of entries)."""
    left = list(portal)
    res = {"matched": [], "mismatched": [], "probable": [], "books_only": [], "portal_only": []}
    unmatched = []
    for b in books:  # pass 1: same supplier GSTIN and invoice number
        cand = next((p for p in left if p["gstin"] == b["gstin"] and p["inv_key"] == b["inv_key"]), None)
        if not cand:
            unmatched.append(b)
            continue
        left.remove(cand)
        dt, dx = _amount_diff(b, cand)
        notes = []
        if dt > tol:
            notes.append(f"taxable differs by {dt}")
        if dx > tol:
            notes.append(f"tax differs by {dx}")
        if b["date"] != cand["date"]:
            notes.append("date differs")
        res["mismatched" if (dt > tol or dx > tol) else "matched"].append({"book": b, "portal": cand, "note": "; ".join(notes)})
    still = []
    for b in unmatched:  # pass 2: same supplier, amounts and date line up, invoice number written differently
        bd = datetime.date.fromisoformat(b["date"])
        cand = next((p for p in left if p["gstin"] == b["gstin"] and all(d <= tol for d in _amount_diff(b, p))
                     and abs((datetime.date.fromisoformat(p["date"]) - bd).days) <= date_days), None)
        if cand:
            left.remove(cand)
            res["probable"].append({"book": b, "portal": cand, "note": "invoice number written differently - confirm"})
        else:
            still.append(b)
    res["books_only"] = [{"book": b, "portal": None, "note": "not in GSTR-2B: input tax credit at risk"} for b in still]
    res["portal_only"] = [{"book": None, "portal": p, "note": "in GSTR-2B but not in your books"} for p in left]
    return res


def supplier_followup(books_only):
    """Group missing-in-2B invoices by supplier with the ITC at risk."""
    groups = {}
    for e in books_only:
        b = e["book"]
        g = groups.setdefault(b["gstin"], {"gstin": b["gstin"], "name": b["name"], "phone": b["phone"], "invoices": [],
                                           "itc_at_risk": ZERO})
        g["invoices"].append(b["inv_raw"])
        g["itc_at_risk"] += b["tax"]
        g["phone"] = g["phone"] or b["phone"]
    return sorted(groups.values(), key=lambda g: g["itc_at_risk"], reverse=True)


def followup_link(group, business_name):
    phone = "".join(c for c in (group["phone"] or "") if c.isdigit())
    if len(phone) == 10:
        phone = "91" + phone
    msg = (f"Hello {group['name'] or 'Sir/Madam'}, we could not find your invoice(s) {', '.join(group['invoices'])} in our "
           f"GSTR-2B. Please check that they are filed in your GSTR-1 so we can claim input tax credit "
           f"(Rs {group['itc_at_risk']}). Thank you. - {business_name}")
    return f"https://wa.me/{phone}?text={quote(msg)}"


def exceptions_xlsx(result, followups=()):
    """Multi-sheet workbook for the CA: Summary, Exceptions, Matched, Supplier follow-up."""
    import xlsx

    def row(label, e):
        b, p = e["book"], e["portal"]
        ref = b or p
        return [label, ref["gstin"], ref["name"], b["inv_raw"] if b else "", p["inv_raw"] if p else "", b["date"] if b else "",
                p["date"] if p else "", b["taxable"] if b else None, p["taxable"] if p else None, b["tax"] if b else None,
                p["tax"] if p else None, e["note"]]

    head = ["Exception", "Supplier GSTIN", "Supplier", "Invoice (books)", "Invoice (GSTR-2B)", "Date (books)", "Date (GSTR-2B)",
            "Taxable (books)", "Taxable (GSTR-2B)", "Tax (books)", "Tax (GSTR-2B)", "Note"]
    labels = (("mismatched", "Amount mismatch"), ("probable", "Probable match"), ("books_only", "Missing in GSTR-2B"),
              ("portal_only", "Missing in books"))
    at_risk = sum((e["book"]["tax"] for e in result["books_only"]), ZERO)
    summary = [["Result", "Count"]] + [[name, len(result[k])] for name, k in (
        ("Matched", "matched"), ("Amount mismatch", "mismatched"), ("Probable match", "probable"),
        ("Missing in GSTR-2B", "books_only"), ("Missing in books", "portal_only"))] + [["ITC at risk (missing in GSTR-2B)", at_risk]]
    sheets = [("Summary", summary),
              ("Exceptions", [head] + [row(l, e) for k, l in labels for e in result[k]]),
              ("Matched", [head] + [row("Matched", e) for e in result["matched"]])]
    if followups:
        sheets.append(("Supplier follow-up", [["Supplier GSTIN", "Supplier", "Phone", "Invoices", "ITC at risk"]] + [
            [g["gstin"], g["name"], g["phone"], ", ".join(g["invoices"]), g["itc_at_risk"]] for g in followups]))
    return xlsx.workbook(sheets)


def exceptions_csv(result):
    """Everything that is not a clean match, as UTF-8 BOM CSV."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Exception", "Supplier GSTIN", "Supplier", "Invoice (books)", "Invoice (GSTR-2B)", "Date (books)", "Date (GSTR-2B)",
                "Taxable (books)", "Taxable (GSTR-2B)", "Tax (books)", "Tax (GSTR-2B)", "ITC at risk", "Note"])
    labels = (("mismatched", "Amount mismatch"), ("probable", "Probable match"), ("books_only", "Missing in GSTR-2B"),
              ("portal_only", "Missing in books"))
    for key, label in labels:
        for e in result[key]:
            b, p = e["book"], e["portal"]
            ref = b or p
            w.writerow([label, ref["gstin"], ref["name"], b["inv_raw"] if b else "", p["inv_raw"] if p else "",
                        b["date"] if b else "", p["date"] if p else "", b["taxable"] if b else "", p["taxable"] if p else "",
                        b["tax"] if b else "", p["tax"] if p else "", b["tax"] if key == "books_only" else "", e["note"]])
    return ("﻿" + buf.getvalue()).encode("utf-8")
