"""Bank statement CSV parsing and matching of receipts to open invoices. Pure functions.

Matching never decides alone on unclear cases: every line gets a level and the owner confirms.
  confident - the narration names the invoice number, or the amount equals one invoice's balance and the customer name appears
  suggested - one plausible invoice (exact balance, or customer name with a part payment)
  unclear   - several equally plausible invoices; nothing is preselected
  none      - no invoice can take this amount
  applied   - this exact line was already applied in an earlier import
"""
import csv
import hashlib
import io
import re
from decimal import Decimal

import reconcile as rc  # reuse date and amount parsing

ZERO = Decimal("0.00")
ALIASES = {
    "date": ("date", "txndate", "transactiondate", "valuedate", "postdate", "trandate", "postingdate"),
    "desc": ("description", "narration", "particulars", "remarks", "transactiondescription", "details", "transactionremarks",
             "transactiondetails"),
    "credit": ("credit", "deposit", "depositamt", "depositamount", "creditamount", "credits", "cr", "creditamt", "depositsrs"),
    "debit": ("debit", "withdrawal", "withdrawalamt", "withdrawalamount", "debitamount", "debits", "dr", "debitamt", "withdrawals"),
    "amount": ("amount", "transactionamount", "amt", "amountinr"),
    "type": ("type", "drcr", "crdr", "transactiontype", "creditdebit"),
    "ref": ("reference", "refno", "referenceno", "chqrefno", "chequeno", "utr", "utrno", "transactionid", "txnid", "refnumber",
            "referencenumber", "chqno"),
}


def parse_statement(text):
    """Return (credits, debits_skipped, errors). Raises ValueError if the columns cannot be identified."""
    text = (text or "").lstrip("﻿").strip()
    if not text:
        return [], 0, []
    lines = text.splitlines()
    delim = "\t" if lines[0].count("\t") > lines[0].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header = next(reader)
    col = {}
    for i, h in enumerate(header):
        for field, names in ALIASES.items():
            if rc._h(h) in names and field not in col:
                col[field] = i
    if "date" not in col or not ({"credit", "amount"} & set(col)):
        raise ValueError("Could not find the date and credit/amount columns in the statement")
    credits, skipped, errors, seen = [], 0, [], {}
    for n, rec in enumerate(reader, 2):
        if not any(c.strip() for c in rec):
            continue

        def get(f):
            return rec[col[f]].strip() if f in col and col[f] < len(rec) else ""

        try:
            amount = None
            if "credit" in col and get("credit"):
                amount = rc.parse_amount(get("credit"))
            elif "debit" in col and get("debit"):
                skipped += 1
                continue
            elif "amount" in col and get("amount"):
                a = rc.parse_amount(get("amount").replace("(", "-").replace(")", ""))
                kind = get("type").lower()
                if kind.startswith("d") or a < 0:
                    skipped += 1
                    continue
                amount = a
            if amount is None or amount <= 0:
                continue
            date = rc.parse_date(get("date"))
        except ValueError as exc:
            errors.append(f"Line {n}: {exc}")
            continue
        desc, ref = get("desc"), get("ref")
        base = f"{date}|{amount}|{ref.upper()}|{re.sub(r'[^A-Z0-9]', '', desc.upper())}"
        seen[base] = seen.get(base, 0) + 1  # two identical lines in one statement are two receipts
        key = hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest()
        credits.append({"line": n, "date": date, "desc": desc, "ref": ref, "amount": amount, "key": key})
    return credits, skipped, errors


def _words(s):
    return set(re.findall(r"[A-Z]{3,}", (s or "").upper()))


def _alnum(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def match(credits, open_invoices, applied_keys=()):
    """open_invoices: dicts from db.list_invoices with outstanding > 0 and status active.
    Returns one entry per credit: {row, level, pick (invoice id or None), cands (invoices that can take the amount)}."""
    out = []
    for row in credits:
        if row["key"] in applied_keys:
            out.append({"row": row, "level": "applied", "pick": None, "cands": []})
            continue
        narr_words, narr_flat = _words(row["desc"] + " " + row["ref"]), _alnum(row["desc"] + row["ref"])
        scored = []
        for inv in open_invoices:
            if inv["outstanding"] < row["amount"]:
                continue
            num_hit = _alnum(inv["number"]) in narr_flat
            name_hit = bool(_words(inv["customer_name"]) & narr_words)
            exact = inv["outstanding"] == row["amount"]
            scored.append({"inv": inv, "num": num_hit, "name": name_hit, "exact": exact})
        scored.sort(key=lambda s: (-(s["num"] * 100 + s["name"] * 5 + s["exact"] * 10), s["inv"]["date"], s["inv"]["id"]))
        cands = [s["inv"] for s in scored[:15]]
        level, pick = "none", None
        if scored:
            nums = [s for s in scored if s["num"]]
            both = [s for s in scored if s["exact"] and s["name"]]
            names = [s for s in scored if s["name"]]
            exacts = [s for s in scored if s["exact"]]
            if nums:
                level, pick = "confident", nums[0]["inv"]["id"]
            elif len(both) == 1:
                level, pick = "confident", both[0]["inv"]["id"]
            elif both:
                level = "unclear"
            elif len(names) == 1:
                level, pick = "suggested", names[0]["inv"]["id"]
            elif len(names) > 1:
                level = "unclear"
            elif len(exacts) == 1:
                level, pick = "suggested", exacts[0]["inv"]["id"]
            elif len(exacts) > 1:
                level = "unclear"
            else:
                level = "none"
        out.append({"row": row, "level": level, "pick": pick, "cands": cands})
    return out
