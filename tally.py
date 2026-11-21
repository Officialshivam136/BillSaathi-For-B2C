"""Tally Prime / ERP 9 XML export: ledger masters plus Sales, Purchase and Receipt vouchers for one month.

Import in Tally: Gateway of Tally > Import > Data (XML). Always try it first on a test company.
Sign convention in Tally XML: a debit entry has ISDEEMEDPOSITIVE=Yes and a negative AMOUNT; a credit has No and a positive AMOUNT.
Every voucher's amounts sum to zero.
"""
from xml.sax.saxutils import escape

import db

SALES, PURCHASE = "Sales", "Purchases"
OUT = {"cgst": "Output CGST", "sgst": "Output SGST", "igst": "Output IGST"}
INP = {"cgst": "Input CGST", "sgst": "Input SGST", "igst": "Input IGST"}
RCM = {"cgst": "RCM CGST Payable", "sgst": "RCM SGST Payable", "igst": "RCM IGST Payable"}
BANK, CASH = "Bank Account", "Cash"


def _d(iso):
    return iso.replace("-", "")


def _entry(ledger, amount, debit):
    """amount is positive; debit=True makes it a debit entry."""
    sign = "-" if debit else ""
    return (f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{escape(ledger)}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{'Yes' if debit else 'No'}</ISDEEMEDPOSITIVE><AMOUNT>{sign}{amount}</AMOUNT></ALLLEDGERENTRIES.LIST>")


def _voucher(vtype, number, date, party, entries, narration=""):
    return (f"<TALLYMESSAGE xmlns:UDF=\"TallyUDF\"><VOUCHER VCHTYPE=\"{vtype}\" ACTION=\"Create\" OBJVIEW=\"Accounting Voucher View\">"
            f"<DATE>{_d(date)}</DATE><VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME><VOUCHERNUMBER>{escape(number)}</VOUCHERNUMBER>"
            f"<PARTYLEDGERNAME>{escape(party)}</PARTYLEDGERNAME><NARRATION>{escape(narration)}</NARRATION>"
            f"{''.join(entries)}</VOUCHER></TALLYMESSAGE>")


def _ledger(name, parent, gstin=None):
    extra = f"<PARTYGSTIN>{escape(gstin)}</PARTYGSTIN>" if gstin else ""
    bill = "<ISBILLWISEON>Yes</ISBILLWISEON>" if parent in ("Sundry Debtors", "Sundry Creditors") else ""
    return (f"<TALLYMESSAGE xmlns:UDF=\"TallyUDF\"><LEDGER NAME=\"{escape(name, {chr(34): '&quot;'})}\" ACTION=\"Create\">"
            f"<NAME>{escape(name)}</NAME><PARENT>{escape(parent)}</PARENT>{bill}{extra}</LEDGER></TALLYMESSAGE>")


def build(conn, ym, company):
    """Return (ledger-masters XML str, voucher XML fragments str, counts). Cancelled invoices are left out."""
    start, end = db.month_range(ym)
    ledgers = {}  # name -> (parent, gstin); first definition wins so a name is created only once
    for name, parent in ((SALES, "Sales Accounts"), (PURCHASE, "Purchase Accounts"), (BANK, "Bank Accounts"), (CASH, "Cash-in-Hand"),
                         *[(n, "Duties & Taxes") for n in (*OUT.values(), *INP.values(), *RCM.values())]):
        ledgers[name] = (parent, None)
    vouchers = []
    counts = {"sales": 0, "purchases": 0, "receipts": 0, "credit_notes": 0, "refunds": 0}

    for inv in sorted(db.list_invoices(conn, start, end), key=lambda i: (i["date"], i["id"])):
        if inv["status"] != "active":
            continue
        ledgers.setdefault(inv["customer_name"], ("Sundry Debtors", inv["customer_gstin"]))
        entries = [_entry(inv["customer_name"], inv["total"], True), _entry(SALES, inv["taxable"], False)]
        entries += [_entry(OUT[k], inv[k], False) for k in ("cgst", "sgst", "igst") if inv[k] > 0]
        vouchers.append(_voucher("Sales", inv["number"], inv["date"], inv["customer_name"], entries, f"Invoice {inv['number']}"))
        counts["sales"] += 1

    for p in sorted(db.list_purchases(conn, start, end), key=lambda p: (p["date"], p["id"])):
        ledgers.setdefault(p["vendor_name"], ("Sundry Creditors", p["vendor_gstin"]))
        entries = [_entry(p["vendor_name"], p["total"], False), _entry(PURCHASE, p["taxable"], True)]
        entries += [_entry(INP[k], p[k], True) for k in ("cgst", "sgst", "igst") if p[k] > 0]
        if p["rcm"]:  # reverse charge: the vendor is paid the taxable value; the tax is claimed as input AND owed as payable
            entries += [_entry(RCM[k], p[k], False) for k in ("cgst", "sgst", "igst") if p[k] > 0]
        vouchers.append(_voucher("Purchase", p["bill_no"], p["date"], p["vendor_name"], entries,
                                 f"{p['category']}" + (" (reverse charge)" if p["rcm"] else "") + (f" - {p['note']}" if p["note"] else "")))
        counts["purchases"] += 1

    for n in sorted(db.list_credit_notes(conn, start, end), key=lambda n: (n["date"], n["id"])):
        ledgers.setdefault(n["customer_name"], ("Sundry Debtors", n["customer_gstin"]))
        # a credit note reverses a sale: the customer is credited, sales and output tax are debited
        entries = [_entry(n["customer_name"], n["total"], False), _entry(SALES, n["taxable"], True)]
        entries += [_entry(OUT[k], n[k], True) for k in ("cgst", "sgst", "igst") if n[k] > 0]
        vouchers.append(_voucher("Credit Note", n["number"], n["date"], n["customer_name"], entries,
                                 f"Against {n['invoice_number']}: {n['reason']}"))
        counts["credit_notes"] += 1

    q = ("SELECT p.id, p.date, p.amount, p.mode, i.number, c.name FROM payment p JOIN invoice i ON i.id = p.invoice_id "
         "JOIN customer c ON c.id = i.customer_id WHERE p.date >= ? AND p.date < ? AND i.status = 'active' ORDER BY p.date, p.id")
    for r in conn.execute(q, (start, end)):
        ledgers.setdefault(r["name"], ("Sundry Debtors", None))
        money = CASH if r["mode"] == "cash" else BANK
        if r["amount"] > 0:
            entries = [_entry(money, r["amount"], True), _entry(r["name"], r["amount"], False)]
            vouchers.append(_voucher("Receipt", f"R-{r['id']}", r["date"], r["name"], entries, f"Against {r['number']} ({r['mode']})"))
            counts["receipts"] += 1
        else:  # a refund: money paid out, so the customer is debited and cash or bank is credited
            entries = [_entry(r["name"], -r["amount"], True), _entry(money, -r["amount"], False)]
            vouchers.append(_voucher("Payment", f"P-{r['id']}", r["date"], r["name"], entries, f"Refund against {r['number']} ({r['mode']})"))
            counts["refunds"] += 1

    masters = "".join(_ledger(n, parent, g) for n, (parent, g) in ledgers.items())
    xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA>"
           "<REQUESTDESC><REPORTNAME>All Masters</REPORTNAME><STATICVARIABLES>"
           f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA>{masters}</REQUESTDATA>"
           "</IMPORTDATA></BODY></ENVELOPE>")
    return xml, "".join(vouchers), counts


def export(conn, ym, company):
    """Two complete XML documents (ledgers, vouchers) as bytes, because Tally imports one envelope per file."""
    masters, vouchers, counts = build(conn, ym, company)
    voucher_xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA>"
                   "<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES>"
                   f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA>{vouchers}</REQUESTDATA>"
                   "</IMPORTDATA></BODY></ENVELOPE>")
    return masters.encode("utf-8"), voucher_xml.encode("utf-8"), counts


def export_zip(conn, ym, company):
    import io
    import zipfile

    masters, vouchers, counts = export(conn, ym, company)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("1-ledgers.xml", masters)
        z.writestr(f"2-vouchers-{ym}.xml", vouchers)
        z.writestr("README.txt", "Import 1-ledgers.xml first, then 2-vouchers file, in Tally: Gateway of Tally > Import > Data.\r\n"
                                 "Try it on a TEST company first and have your CA check the result.\r\n"
                                 f"Contents: {counts['sales']} sales, {counts['purchases']} purchases, {counts['receipts']} receipts, "
                                 f"{counts['credit_notes']} credit notes, {counts['refunds']} refunds.\r\n")
    return mem.getvalue(), counts
