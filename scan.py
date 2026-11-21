"""Purchase bill scanning: photo -> fields for the purchase form. The owner always reviews and confirms; nothing is saved here.

Engines: Windows built-in OCR (offline, nothing leaves the computer) and, optionally, Claude vision (ai.py).
This module holds the shared parts: reading images, rebuilding table rows from OCR words, correcting OCR mix-ups in GSTINs,
pulling fields out of the rows, and checking the result.
"""
import datetime
import json
import os
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation

import gst

PS_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "winocr.ps1")
MAX_IMAGE_BYTES = 8_000_000
ZERO = Decimal("0.00")


class ScanError(Exception):
    """Something the owner can act on (wrong file type, no OCR available, unreadable photo)."""


def sniff_image(data):
    """Return (extension, mime) from the file's first bytes, or None. The file name is never trusted."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:4] == b"GIF8":
        return "gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if data[:2] == b"BM":
        return "bmp", "image/bmp"
    return None


def windows_ocr_available():
    return sys.platform == "win32" and os.path.exists(PS_SCRIPT)


def ocr_words(path):
    """Run Windows OCR on an image file. Returns a list of {t, x, y, w, h}."""
    if not windows_ocr_available():
        raise ScanError("Offline scanning needs Windows 10 or 11. Use AI reading instead, or type the bill in by hand.")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", PS_SCRIPT,
                            "-Path", path], capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        raise ScanError("The scanner took too long or could not start. Try a smaller or clearer photo.")
    if r.returncode == 3:
        raise ScanError("Windows has no text-recognition language installed. Add one in Settings > Time & language > Language.")
    if r.returncode != 0:
        raise ScanError("The scanner could not read that image. Try a JPG or PNG photo.")
    try:
        words = json.loads(r.stdout.decode("utf-8", "replace").strip() or "[]")
    except ValueError:
        raise ScanError("The scanner returned something unreadable.")
    return [words] if isinstance(words, dict) else words


def rows_from_words(words):
    """Group OCR words into visual rows (by vertical position) and join each row left to right. OCR engines report table
    columns separately, so without this a label like 'Taxable Value' is detached from its amount."""
    words = [w for w in words if str(w.get("t", "")).strip()]
    if not words:
        return []
    med = sorted(w["h"] for w in words)[len(words) // 2] or 10
    items = sorted(words, key=lambda w: w["y"] + w["h"] / 2)
    groups, cur, cy = [], [items[0]], items[0]["y"] + items[0]["h"] / 2
    for w in items[1:]:
        c = w["y"] + w["h"] / 2
        if abs(c - cy) <= 0.6 * med:
            cur.append(w)
            cy = sum(x["y"] + x["h"] / 2 for x in cur) / len(cur)
        else:
            groups.append(cur)
            cur, cy = [w], c
    groups.append(cur)
    rows = []
    for g in groups:
        g.sort(key=lambda w: w["x"])
        text = g[0]["t"]
        for prev, w in zip(g, g[1:]):
            text += ("  " if w["x"] - (prev["x"] + prev["w"]) > 1.5 * med else " ") + w["t"]
        rows.append(text)
    return rows


# ---- GSTIN: fix the letters OCR confuses with digits (and back) by position, then validate ----
_TO_DIGIT = {"I": "1", "L": "1", "|": "1", "O": "0", "Q": "0", "D": "0", "S": "5", "B": "8", "Z": "2", "G": "6"}
_TO_ALPHA = {"1": "I", "0": "O", "5": "S", "8": "B", "2": "Z", "6": "G"}
# position kinds: d = digit, a = letter, x = digit or letter, Z = literal Z
_GSTIN_SHAPE = "ddaaaaaddddaxZx"


def fix_gstin(token):
    t = re.sub(r"[^A-Za-z0-9|]", "", token or "").upper()
    if len(t) != 15:
        return None
    out = []
    for ch, kind in zip(t, _GSTIN_SHAPE):
        if kind == "d" and ch.isalpha() or kind == "d" and ch == "|":
            ch = _TO_DIGIT.get(ch, ch)
        elif kind == "a" and ch.isdigit():
            ch = _TO_ALPHA.get(ch, ch)
        elif kind == "Z" and ch != "Z":
            ch = "Z" if ch in ("2", "7") else ch
        elif kind == "x" and ch == "|":
            ch = "1"
        out.append(ch)
    fixed = "".join(out)
    if not gst.validate_gstin(fixed):
        return None
    # Positions 13 and 15 may legally be a digit or a letter, so shape alone cannot tell "1" from "I". The check digit can:
    # try the look-alike readings of those two positions and keep one whose checksum is right.
    alts = lambda ch: {ch} | {a for grp in _LOOKALIKES if ch in grp for a in grp}
    for c12 in sorted(alts(fixed[12])):
        for c14 in sorted(alts(fixed[14])):
            cand = fixed[:12] + c12 + fixed[13] + c14
            if gst.validate_gstin(cand) and gstin_checksum_ok(cand):
                return cand
    if fixed[12] in "IL":  # no reading passes: entity code 'I' is almost never real, '1' is common
        fixed = fixed[:12] + "1" + fixed[13:]
    return fixed


_LOOKALIKES = ("1IL", "0OQD", "5S", "8B", "2Z", "6G")
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum_ok(g):
    """The last character of a real GSTIN is a check digit (base-36 weighted sum of the first 14)."""
    if not g or len(g) != 15 or any(c not in _B36 for c in g):
        return False
    total = 0
    for i, ch in enumerate(g[:14]):
        prod = _B36.index(ch) * (1 if i % 2 == 0 else 2)
        total += prod // 36 + prod % 36
    return _B36[(36 - total % 36) % 36] == g[14]


def find_gstins(rows):
    found = []
    for row in rows:
        for tok in re.findall(r"[0-9A-Za-z|]{15}", re.sub(r"[\s:.-]", "", row) if len(row) < 40 else row):
            g = fix_gstin(tok)
            if g and g not in found:
                found.append(g)
        for tok in row.replace(":", " ").split():
            g = fix_gstin(tok)
            if g and g not in found:
                found.append(g)
    return found


# ---- amounts, dates, labels ----
_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d{1,2})?)(?!\s*%)(?![\d.])")
_LABELS = {
    "total": re.compile(r"grand\s*total|total\s*amount|invoice\s*(?:total|value)|net\s*payable|amount\s*payable|total\s*payable|\btotal\b", re.I),
    "taxable": re.compile(r"taxable|assessable|sub\s*-?\s*total|amount\s*before\s*tax", re.I),
    "cgst": re.compile(r"\bc\s?\.?\s?g\s?\.?\s?s\s?\.?\s?t\b|central\s*tax", re.I),
    "sgst": re.compile(r"\bs\s?\.?\s?g\s?\.?\s?s\s?\.?\s?t\b|\bu\s?\.?\s?t\s?\.?\s?g\s?\.?\s?s\s?\.?\s?t\b|state\s*(?:/\s*ut\s*)?tax", re.I),
    "igst": re.compile(r"\bi\s?\.?\s?g\s?\.?\s?s\s?\.?\s?t\b|integrated\s*tax", re.I),
}
_DATE_NUM = re.compile(r"\b(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4}|\d{2})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_MON = re.compile(r"\b(\d{1,2})[-/ ]([A-Za-z]{3})[a-z]*[-/ ,]*(\d{4}|\d{2})\b")
_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def _dec(s):
    try:
        return Decimal(s.replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def row_amount(row):
    """The amount at the end of a labelled row. Percentages ('2.5%') are skipped; amounts with paise are preferred."""
    nums = [m.group(1) for m in _NUM.finditer(row)]
    with_paise = [n for n in nums if "." in n]
    pick = (with_paise or nums or [None])[-1]
    return _dec(pick) if pick else None


def find_date(rows):
    def parse(row):
        m = _DATE_ISO.search(row)
        if m:
            y, mo, d = (int(x) for x in m.groups())
        else:
            m = _DATE_NUM.search(row)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                m = _DATE_MON.search(row)
                if not m or m.group(2).lower()[:3] not in _MONTHS:
                    return None
                d, mo, y = int(m.group(1)), _MONTHS[m.group(2).lower()[:3]], int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return datetime.date(y, mo, d).isoformat()
        except ValueError:
            return None

    for row in rows:  # a row that says "date" first
        if re.search(r"\bdate\b|dt\.?", row, re.I) and parse(row):
            return parse(row)
    for row in rows:
        if parse(row):
            return parse(row)
    return None


_BILLNO = re.compile(r"(?:invoice|inv|bill|voucher|tax\s*invoice)\s*(?:no|number|num|#)\b\.?\s*[:.\-#]*\s*([A-Z0-9][A-Z0-9/\-._]{1,24})", re.I)


def find_bill_no(rows):
    for row in rows:
        m = _BILLNO.search(row)
        if m and re.search(r"\d", m.group(1)):
            return m.group(1).rstrip(".-")
    return None


_SKIP_NAME = re.compile(r"invoice|bill|gstin|gst|tax|phone|mob|email|date|original|duplicate|copy|cash|memo|\bno\b|www|@|^\W*$", re.I)


def find_vendor(rows):
    for row in rows[:10]:
        r = row.strip()
        letters = sum(ch.isalpha() for ch in r)
        if 3 <= len(r) <= 60 and letters >= 3 and letters >= 0.6 * len(r.replace(" ", "")) and not _SKIP_NAME.search(r):
            return r.title() if r.isupper() else r
    return None


def find_phone(rows):
    for row in rows:
        m = re.search(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)", row.replace(" ", "") if len(row) < 30 else row)
        if m:
            return m.group(1)
    return None


def parse_rows(rows, own_gstin=None):
    """Pull the purchase fields out of OCR rows. Returns a dict of raw values (None when not found)."""
    f = {"vendor_name": find_vendor(rows), "vendor_gstin": None, "vendor_phone": find_phone(rows), "bill_no": find_bill_no(rows),
         "date": find_date(rows), "taxable": None, "cgst": None, "sgst": None, "igst": None, "total": None}
    gstins = [g for g in find_gstins(rows) if g != (own_gstin or "").upper()]
    f["vendor_gstin"] = gstins[0] if gstins else None
    found = {k: [] for k in _LABELS}
    for row in rows:
        kinds = [k for k, pat in _LABELS.items() if pat.search(row)]
        if not kinds:
            continue
        amt = row_amount(row)
        if amt is None:
            continue
        # a row that names a tax is that tax, even though it may also contain the word "total"
        kind = next((k for k in ("cgst", "sgst", "igst", "taxable") if k in kinds), "total" if "total" in kinds else None)
        if kind:
            found[kind].append((row, amt))
    for k in ("cgst", "sgst", "igst", "taxable"):
        if found[k]:
            f[k] = found[k][0][1]
    totals = found["total"]
    grand = [a for r, a in totals if re.search(r"grand|net\s*payable|amount\s*payable|total\s*payable|invoice\s*(total|value)", r, re.I)]
    pool = grand or [a for r, a in totals if "." in r]
    f["total"] = max(pool) if pool else (max(a for r, a in totals) if totals else None)
    return f


def finalize(f, own_gstin=None):
    """Clean raw fields into form values and list what needs a human look. Returns (values, warnings)."""
    warnings = []
    g = (f.get("vendor_gstin") or "").strip().upper() or None
    if g and not gst.validate_gstin(g):
        warnings.append(f"The vendor GSTIN {g} on the scan is not valid. Check it against the bill.")
        g = None
    if g and g == (own_gstin or "").upper():
        warnings.append("The only GSTIN found is your own. Enter the vendor's GSTIN by hand.")
        g = None
    if g and not gstin_checksum_ok(g):
        warnings.append(f"The vendor GSTIN {g} fails its check digit, so a character may be misread. Compare it with the bill, "
                        "character by character.")
    if not g:
        warnings.append("No vendor GSTIN found. Without it you cannot claim input credit on this bill.")
    date = f.get("date")
    if date:
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            warnings.append(f"The date '{date}' is not valid.")
            date = None
    if not date:
        warnings.append("Bill date not found: enter it.")
    if not f.get("bill_no"):
        warnings.append("Bill number not found: enter it.")
    if not f.get("vendor_name"):
        warnings.append("Vendor name not found: enter it.")
    taxable, cgst, sgst, igst, total = (f.get(k) for k in ("taxable", "cgst", "sgst", "igst", "total"))
    taxes = (cgst or ZERO) + (sgst or ZERO) + (igst or ZERO)
    if taxable is None and total is not None:
        taxable = total - taxes
        warnings.append("Taxable value was worked out from the total minus tax. Check it.")
    if taxable is None:
        warnings.append("Taxable value not found: enter it.")
    if igst and (cgst or sgst):
        warnings.append("The scan shows both IGST and CGST/SGST. A bill has one or the other; check the amounts.")
    if taxable is not None and total is not None and abs(taxable + taxes - total) > Decimal("1.00"):
        warnings.append(f"Taxable value + tax ({taxable + taxes}) does not match the total on the bill ({total}). "
                        "Check every amount against the photo.")
    if cgst is not None and sgst is not None and cgst != sgst:
        warnings.append("CGST and SGST differ; they are normally equal. Check them.")
    vals = {"vendor_name": f.get("vendor_name") or "", "vendor_gstin": g or "", "vendor_phone": f.get("vendor_phone") or "",
            "bill_no": f.get("bill_no") or "", "date": date or "", "taxable": f"{taxable:.2f}" if taxable is not None else "",
            "cgst": f"{cgst:.2f}" if cgst else "", "sgst": f"{sgst:.2f}" if sgst else "", "igst": f"{igst:.2f}" if igst else ""}
    return vals, warnings


def scan_with_windows(path, own_gstin=None):
    rows = rows_from_words(ocr_words(path))
    if not rows:
        raise ScanError("No text was found in that photo. Try a brighter, flatter, closer photo.")
    return finalize(parse_rows(rows, own_gstin), own_gstin), rows
