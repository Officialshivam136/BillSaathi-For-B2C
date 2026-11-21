"""GST calculation, GSTIN validation and interstate detection. Money is Decimal."""
import re
from decimal import Decimal, ROUND_HALF_UP

GST_RATES = (Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28"))
_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_TWO = Decimal("0.01")


def money(x):
    """Round to 2 decimal places, half-up."""
    return Decimal(x).quantize(_TWO, rounding=ROUND_HALF_UP)


def validate_gstin(gstin):
    """15 characters, correct pattern, state code 01-38 (plus 97/99)."""
    if not isinstance(gstin, str):
        return False
    g = gstin.strip().upper()
    if not _GSTIN_RE.match(g):
        return False
    return 1 <= int(g[:2]) <= 38 or g[:2] in ("97", "99")


def is_interstate(business_state, customer_state):
    """Return (interstate, state_missing). Missing customer state counts as intra-state."""
    b = (business_state or "").strip().lower()
    c = (customer_state or "").strip().lower()
    if not c or not b:
        return False, True
    return b != c, False


def calc_line(qty, rate, gst_rate, interstate):
    """Tax for one line. Intra-state: SGST = tax - CGST so they always sum to tax."""
    taxable = money(Decimal(qty) * Decimal(rate))
    tax = money(taxable * Decimal(gst_rate) / 100)
    if interstate:
        cgst = sgst = Decimal("0.00")
        igst = tax
    else:
        cgst = money(tax / 2)
        sgst = tax - cgst
        igst = Decimal("0.00")
    return {"taxable": taxable, "tax": tax, "cgst": cgst, "sgst": sgst, "igst": igst}


def calc_invoice(items, interstate):
    """items: iterable of dicts with qty, rate, gst_rate. Returns lines, totals, per-rate breakup."""
    lines, breakup = [], {}
    tot = {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")}
    for it in items:
        gr = Decimal(it["gst_rate"])
        if gr not in GST_RATES:
            raise ValueError(f"Invalid GST rate: {gr}")
        line = calc_line(it["qty"], it["rate"], gr, interstate)
        lines.append(line)
        b = breakup.setdefault(gr, {k: Decimal("0.00") for k in ("taxable", "cgst", "sgst", "igst")})
        for k in tot:
            tot[k] += line[k]
            b[k] += line[k]
    tot["total"] = tot["taxable"] + tot["cgst"] + tot["sgst"] + tot["igst"]
    return {"lines": lines, "totals": tot, "breakup": breakup}
