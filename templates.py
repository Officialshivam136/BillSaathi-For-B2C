"""HTML templates. Every dynamic value goes through e() (html.escape)."""
import datetime
import threading
from decimal import Decimal
from html import escape
from urllib.parse import quote

GST_CHOICES = ("0", "5", "12", "18", "28")
STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Chandigarh",
    "Puducherry", "Andaman and Nicobar Islands", "Dadra and Nagar Haveli and Daman and Diu", "Lakshadweep",
)

CSS = """
:root{--bg:#f4f6fb;--surface:#fff;--ink:#141b2d;--muted:#667085;--line:#e3e8f0;--brand:#2b50d8;--brand-ink:#fff;--brand-soft:#eaefff;
--ok:#127a43;--ok-bg:#e3f6ec;--warn:#8a5a00;--warn-bg:#fff3d1;--bad:#b42318;--bad-bg:#fde8e6;--b2:#2bb673;--radius:12px;
--shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08)}
@media (prefers-color-scheme:dark){:root{--bg:#0e1424;--surface:#161e33;--ink:#e8ecf6;--muted:#97a3bd;--line:#26314d;--brand:#7d96ff;
--brand-ink:#0b1226;--brand-soft:#1d2a52;--ok:#5ad19a;--ok-bg:#12332a;--warn:#f5c451;--warn-bg:#3a2f10;--bad:#ff8a80;--bad-bg:#3d1a1a}}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 system-ui,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}
a{color:var(--brand)}h1{font-size:24px;margin:0 0 4px;letter-spacing:-.01em}h2{font-size:16px;margin:22px 0 10px}
.app{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}
.side{background:var(--surface);border-right:1px solid var(--line);padding:16px 12px;display:flex;flex-direction:column;gap:2px;position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{font-weight:700;font-size:18px;padding:4px 10px 16px;display:flex;gap:10px;align-items:center}
.brand i{width:30px;height:30px;border-radius:9px;background:var(--brand);color:var(--brand-ink);display:grid;place-items:center;font-style:normal;font-size:16px}
.side a{display:flex;gap:11px;align-items:center;padding:9px 10px;border-radius:9px;color:var(--ink);text-decoration:none;font-weight:500}
.side a:hover{background:var(--brand-soft)}.side a.on{background:var(--brand-soft);color:var(--brand)}
.side svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
.side .grow{flex:1}.side .who{padding:8px 10px;color:var(--muted);font-size:13px}
.side .who a{display:inline;padding:0;font-weight:600;color:var(--brand)}.side .who a:hover{background:none;text-decoration:underline}
main{padding:26px 30px 48px;max-width:1120px;width:100%}main.auth{margin:8vh auto 0;max-width:420px;padding:16px}
.pagehead{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.sub{color:var(--muted);font-size:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;margin-bottom:14px;box-shadow:var(--shadow)}
.card>h2:first-child{margin-top:0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:14px}
.stat{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--c,var(--brand));border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow)}
.stat span{display:block;color:var(--muted);font-size:13px}.stat b{display:block;font-size:26px;letter-spacing:-.02em;margin-top:2px}.stat small{color:var(--muted)}
.cols{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:14px}
@media(max-width:980px){.cols{grid-template-columns:1fr}}
.legend{display:flex;gap:16px;font-size:13px;color:var(--muted);margin-bottom:6px}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
svg.chart{width:100%;height:auto;display:block}svg.chart text{fill:var(--muted);font-size:11px;font-family:inherit}
svg.chart .b1{fill:var(--brand)}svg.chart .b2{fill:var(--b2)}svg.chart line{stroke:var(--line)}
.age{display:grid;grid-template-columns:110px 1fr auto;gap:8px 10px;align-items:center;font-size:13px}
.age .bar{height:10px;border-radius:6px;background:var(--brand-soft);overflow:hidden}.age .bar i{display:block;height:100%;background:var(--brand);border-radius:6px}
.age .late i{background:var(--bad)}.age .num{text-align:right;font-variant-numeric:tabular-nums}
label{display:block;font-size:13px;font-weight:500;color:var(--muted);margin:10px 0 4px}
input,select,textarea{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:9px;font:inherit;background:var(--surface);color:var(--ink)}
input:focus,select:focus,textarea:focus{outline:2px solid var(--brand);outline-offset:-1px;border-color:transparent}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0 14px}
button,.btn{background:var(--brand);color:var(--brand-ink);border:0;border-radius:9px;padding:9px 16px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}
button:hover,.btn:hover{filter:brightness(1.08)}button:disabled{opacity:.5;cursor:not-allowed}
.btn.alt,button.alt{background:var(--brand-soft);color:var(--brand)}.btn.warn,button.warn{background:var(--bad);color:#fff}.btn.wa{background:#1a8d4b;color:#fff}
.btn.sm,button.sm{padding:5px 10px;font-size:13px}.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}
.wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%}th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
tr:last-child td{border-bottom:0}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600;background:transparent}
tbody tr:hover td,table tr:hover td{background:color-mix(in srgb,var(--brand-soft) 45%,transparent)}.r{text-align:right;font-variant-numeric:tabular-nums}
.small{font-size:12px;color:var(--muted)}.empty{padding:28px;text-align:center;color:var(--muted)}
.err,.ok,.warnbox{padding:10px 14px;border-radius:10px;margin:0 0 12px}
.err{background:var(--bad-bg);color:var(--bad)}.ok{background:var(--ok-bg);color:var(--ok)}.warnbox{background:var(--warn-bg);color:var(--warn)}
.toast{position:fixed;right:18px;bottom:18px;z-index:50;padding:11px 16px;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.2);animation:fade 5s forwards}
.toast.ok{background:var(--ok);color:#fff}@keyframes fade{0%,85%{opacity:1;transform:none}100%{opacity:0;transform:translateY(8px);visibility:hidden}}
.tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;background:var(--brand-soft);color:var(--brand)}
.tag.Paid{background:var(--ok-bg);color:var(--ok)}.tag.Unpaid{background:var(--bad-bg);color:var(--bad)}.tag.Partly{background:var(--warn-bg);color:var(--warn)}
.tag.Cancelled{background:var(--line);color:var(--muted);text-decoration:line-through}
.tag.Credited{background:var(--line);color:var(--muted)}.tag.Refund{background:var(--warn-bg);color:var(--warn)}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px}.chip{padding:6px 13px;border-radius:999px;background:var(--surface);border:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:13px;font-weight:500}
.chip.on{background:var(--brand);border-color:var(--brand);color:var(--brand-ink)}
.filters{display:flex;gap:8px;flex-wrap:wrap}.filters input,.filters select{width:auto;min-width:150px}
.avatar{width:34px;height:34px;border-radius:50%;background:var(--brand-soft);color:var(--brand);display:inline-grid;place-items:center;font-weight:700;margin-right:10px;vertical-align:middle}
.invform{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}
@media(max-width:980px){.invform{grid-template-columns:1fr}}
.lines{display:grid;gap:8px}
.line{display:grid;grid-template-columns:minmax(110px,3fr) 66px 66px 88px 66px 90px 30px;gap:8px;align-items:center}
.line input,.line select{padding:9px 8px;min-width:0}
.line.head{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
.line .amt{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.line .rm{background:transparent;color:var(--muted);padding:4px 8px}.line .rm:hover{color:var(--bad)}
@media(max-width:700px){.line.head{display:none}.line{grid-template-columns:1fr 1fr 1fr;padding:10px;border:1px solid var(--line);border-radius:10px}
.line [name=description]{grid-column:1/-1}.line .amt{text-align:right}.line .rm{justify-self:end}}
.totals{position:sticky;top:16px}.totals .t{display:flex;justify-content:space-between;padding:6px 0;font-variant-numeric:tabular-nums}
.totals .grand{border-top:1px solid var(--line);margin-top:6px;padding-top:12px;font-size:22px;font-weight:700}.totals button{width:100%;justify-content:center;margin-top:12px;padding:12px}
dialog{border:1px solid var(--line);border-radius:14px;padding:20px 22px;background:var(--surface);color:var(--ink);width:min(440px,92vw)}
dialog::backdrop{background:rgba(10,15,30,.5)}
.inv,.inv *{color:#111}.inv{background:#fff;padding:24px;border:1px solid #ddd;max-width:794px;margin:0 auto;border-radius:6px}
.inv a{color:#0b5cad}.inv h1{margin:0}.inv .two{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.inv .wrap{border:0;box-shadow:none;background:#fff}.inv th,.inv td{padding:5px 6px;font-size:13px;background:#fff;border-bottom:1px solid #e5e5e5}
.inv th{background:#f1f3f6;color:#333}.inv .small{color:#555}
.auth .card{padding:26px}.auth .brand{justify-content:center;padding-bottom:8px;font-size:22px}
@media(max-width:860px){.app{display:block}.side{position:static;height:auto;flex-direction:row;overflow-x:auto;padding:8px;border-right:0;border-bottom:1px solid var(--line);gap:2px}
.side a{white-space:nowrap;padding:8px 11px}.brand,.side .grow,.side .who{display:none}main{padding:16px 14px 40px}}
@media print{.side,.noprint,.toast{display:none!important}.app{display:block}body{background:#fff}main{padding:0;max-width:none}
.inv{border:0;padding:0;max-width:none}@page{size:A4;margin:12mm}}
"""


def e(x):
    return escape("" if x is None else str(x), quote=True)


def inr(x):
    """Indian digit grouping: 1,23,456.50"""
    s = f"{Decimal(x):.2f}"
    whole, frac = s.split(".")
    neg = whole.startswith("-")
    whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + whole + "." + frac


def dmy(iso):
    return f"{iso[8:10]}-{iso[5:7]}-{iso[:4]}" if iso else ""


_ctx = threading.local()  # set per request by app.py: .role ('owner' or 'staff') and .user (display name)


_ICONS = {
    "home": "M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
    "plus": "M12 5v14M5 12h14",
    "file": "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
    "users": "M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M21 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
    "tag": "M20 12l-8 8-9-9V3h8zM7.5 7.5h.01",
    "cart": "M6 6h15l-2 9H8zM6 6L5 3H2M9 20h.01M18 20h.01",
    "bank": "M3 10l9-6 9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 21h18",
    "check": "M20 6L9 17l-5-5",
    "download": "M12 3v12M7 10l5 5 5-5M5 21h14",
    "user": "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
    "sliders": "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
    "logout": "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
}


OWNER_NAV = (("/", "Dashboard", "home"), ("/invoices/new", "New invoice", "plus"), ("/invoices", "Invoices", "file"),
             ("/credit-notes", "Credit notes", "file"), ("/customers", "Customers", "users"), ("/items", "Items", "tag"), ("/stock", "Stock", "tag"),
             ("/recurring", "Recurring", "check"), ("/purchases", "Purchases", "cart"), ("/bank", "Bank", "bank"), ("/reconcile", "Reconcile", "check"),
             ("/exports", "Exports", "download"), ("/backups", "Backups", "download"), ("/audit", "Audit log", "check"), ("/integrations", "Integrations", "sliders"),
             ("/staff", "Staff", "user"), ("/account", "Account", "user"), ("/profile", "Profile", "sliders"))


STAFF_NAV = (("/invoices/new", "New invoice", "plus"), ("/invoices", "Invoices", "file"), ("/customers", "Customers", "users"))


def _icon(name):
    return f"<svg viewBox='0 0 24 24' aria-hidden='true'><path d='{_ICONS[name]}'/></svg>"


def _active(href, path):
    if href == "/":
        return path == "/"
    if href == "/invoices":
        return path.startswith("/invoices") and path != "/invoices/new"
    return path == href or path.startswith(href + "/")


def _compact(x):
    x = float(x)
    for lim, suf in ((1e7, "Cr"), (1e5, "L"), (1e3, "k")):
        if x >= lim:
            return f"{x / lim:.1f}".rstrip("0").rstrip(".") + suf
    return f"{x:.0f}"


def _bars(series):
    W, H, base = 620, 220, 190
    mx = max([float(s["invoiced"]) for s in series] + [float(s["collected"]) for s in series] + [1.0])
    slot = (W - 20) / len(series)
    bw = slot * 0.3
    out = [f"<line x1='10' y1='{base}' x2='{W - 10}' y2='{base}'/>"]
    for i, s in enumerate(series):
        x0 = 10 + i * slot + slot * 0.17
        for j, (k, cls, word) in enumerate((("invoiced", "b1", "Invoiced"), ("collected", "b2", "Collected"))):
            v = float(s[k])
            h = (base - 26) * v / mx
            x, y = x0 + j * (bw + 5), base - h
            out.append(f"<rect class='{cls}' x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{max(h, 0):.1f}' rx='3'>"
                       f"<title>{s['label']} {word}: ₹{inr(s[k])}</title></rect>")
            if v > 0:
                out.append(f"<text x='{x + bw / 2:.1f}' y='{y - 4:.1f}' text-anchor='middle'>{_compact(v)}</text>")
        out.append(f"<text x='{x0 + bw + 2.5:.1f}' y='{base + 16}' text-anchor='middle'>{s['label']}</text>")
    return (f"<svg class='chart' viewBox='0 0 {W} {H}' role='img' aria-label='Invoiced and collected per month'>{''.join(out)}</svg>"
            "<div class='legend'><span><i style='background:var(--brand)'></i>Invoiced</span>"
            "<span><i style='background:var(--b2)'></i>Collected</span></div>")


def _qs(f, **over):
    from urllib.parse import urlencode

    d = {k: v for k, v in {**f, **over}.items() if v and k in ("month", "status", "q", "customer_id")}
    return "?" + urlencode(d) if d else ""


def _tax_tables(doc, inter, show_tax=True):
    """(breakup table, tax total rows) shared by invoices and credit notes. A bill of supply shows no tax at all."""
    if not show_tax:
        return "", f"<tr><td>Taxable value</td><td class='r'>{inr(doc['taxable'])}</td></tr>"
    if inter:
        head, cols = "<th>Rate</th><th class='r'>Taxable</th><th class='r'>IGST</th>", ("igst",)
    else:
        head, cols = "<th>Rate</th><th class='r'>Taxable</th><th class='r'>CGST</th><th class='r'>SGST</th>", ("cgst", "sgst")
    brk = "".join(
        f"<tr><td>{inr(r).rstrip('0').rstrip('.')}%</td><td class='r'>{inr(b['taxable'])}</td>" +
        "".join(f"<td class='r'>{inr(b[c])}</td>" for c in cols) + "</tr>" for r, b in doc["breakup"].items())
    tot = f"<tr><td>Taxable value</td><td class='r'>{inr(doc['taxable'])}</td></tr>"
    if inter:
        tot += f"<tr><td>IGST</td><td class='r'>{inr(doc['igst'])}</td></tr>"
    else:
        tot += f"<tr><td>CGST</td><td class='r'>{inr(doc['cgst'])}</td></tr><tr><td>SGST</td><td class='r'>{inr(doc['sgst'])}</td></tr>"
    return f"<table><tr>{head}</tr>{brk}</table>", tot


def _line_rows(items):
    return "".join(
        f"<tr><td>{n}</td><td>{e(it['description'])}</td><td>{e(it['hsn'])}</td><td class='r'>{e(format(it['qty'].normalize(), 'f'))}</td>"
        f"<td class='r'>{inr(it['rate'])}</td><td class='r'>{inr(it['gst_rate']).rstrip('0').rstrip('.')}%</td>"
        f"<td class='r'>{inr(it['taxable'])}</td></tr>" for n, it in enumerate(items, 1))


def _upi_block(biz, inv):
    """UPI text, deep link and a scannable QR for the amount still due."""
    import qr

    if not biz["upi_id"] or inv["outstanding"] <= 0:
        return ""
    uri = f"upi://pay?pa={quote(biz['upi_id'])}&pn={quote(biz['name'])}&am={inv['outstanding']}&cu=INR&tn={quote(inv['number'])}"
    try:
        code = qr.to_svg(qr.make_qr(uri), size_px=118)
    except ValueError:
        code = ""
    return (f"<div style='display:flex;gap:14px;align-items:center;margin-top:10px;flex-wrap:wrap'>{code}<div><b>Pay by UPI</b><br>"
            f"{e(biz['upi_id'])}<br>Amount due: ₹{inr(inv['outstanding'])}<br><a href='{e(uri)}'>Open UPI app</a></div></div>")


def credit_note_page(cn, biz, notice=None):
    import words

    inter = bool(cn["is_interstate"])
    brk_table, totrows = _tax_tables(cn, inter, show_tax=biz["scheme"] != "composition")
    totrows += f"<tr><th>Credit total</th><th class='r'>₹{inr(cn['total'])}</th></tr>"
    return layout(cn["number"], f"""<div class='actions noprint'><button onclick='window.print()'>Print / Save PDF</button>
<a class='btn alt' href='/invoices/{cn['invoice_id']}'>Back to invoice</a></div>
<!--noxl--><div class='inv'><div class='two'><div><h1>{e(biz['name'])}</h1><div>{e(biz['address'])}</div>
{'<div>GSTIN: ' + e(biz['gstin']) + '</div>' if biz['gstin'] else ''}<div>State: {e(biz['state'])}</div></div>
<div style='text-align:right'><h2 style='margin:0'>CREDIT NOTE</h2><div><b>{e(cn['number'])}</b></div><div>Date: {dmy(cn['date'])}</div>
<div>Against invoice {e(cn['invoice_number'])} dated {dmy(cn['invoice_date'])}</div></div></div>
<hr><div><b>Customer:</b> {e(cn['customer_name'])}<br>{e(cn['customer_address'])}
{'<br>GSTIN: ' + e(cn['customer_gstin']) if cn['customer_gstin'] else ''}{'<br>State: ' + e(cn['customer_state']) if cn['customer_state'] else ''}</div>
<p><b>Reason:</b> {e(cn['reason'])}</p>
<div class='wrap'><table><tr><th>#</th><th>Description</th><th>HSN</th><th class='r'>Qty</th><th class='r'>Rate</th><th class='r'>GST</th>
<th class='r'>Taxable</th></tr>{_line_rows(cn['items'])}</table></div>
<div class='two' style='margin-top:10px'><div style='flex:1;min-width:240px'>{brk_table}</div><div style='min-width:240px'><table>{totrows}</table></div></div>
<p style='margin:10px 0 0'><b>Amount in words:</b> {e(words.rupees_in_words(cn['total']))}</p>
<p class='small'>This credit note reduces the amount payable on the invoice above. Computer-generated; please verify with your CA.</p></div><!--/noxl-->""", notice=notice)


def credit_notes_page(rows):
    trs = "".join(f"<tr><td><a href='/credit-notes/{n['id']}'>{e(n['number'])}</a></td><td>{dmy(n['date'])}</td>"
                  f"<td><a href='/invoices/{n['invoice_id']}'>{e(n['invoice_number'])}</a></td><td>{e(n['customer_name'])}</td>"
                  f"<td>{e(n['reason'])}</td><td class='r'>{inr(n['total'])}</td></tr>" for n in rows)
    table = (f"<div class='wrap'><table><tr><th>Number</th><th>Date</th><th>Invoice</th><th>Customer</th><th>Reason</th><th class='r'>Amount</th></tr>{trs}</table></div>"
             if trs else "<div class='card empty'>No credit notes yet. Open an invoice and choose Issue credit note.</div>")
    return layout("Credit notes", f"<div class='pagehead'><div><h1>Credit notes</h1><div class='sub'>{len(rows)} issued</div></div></div>{table}")


def _lang_link():
    other, label = ("en", "English") if getattr(_ctx, "lang", "en") == "hi" else ("hi", "हिन्दी")
    return f"<a href='/lang?to={other}' class='langlink'>{label}</a>"


SUPPLY_NOTES = {
    "export_lut": "Supply meant for export under Letter of Undertaking (LUT) without payment of integrated tax.",
    "export_igst": "Supply meant for export on payment of integrated tax.",
}


def _doc_title(biz, inv):
    if biz["scheme"] == "composition":
        return "BILL OF SUPPLY"
    if inv["supply_type"] != "regular":
        return "EXPORT INVOICE"
    return "TAX INVOICE" if biz["gstin"] else "INVOICE"


def statement_page(st, biz, start="", end=""):
    import urllib.parse as up

    c = st["customer"]
    rows = "".join(
        f"<tr><td>{dmy(r['date'])}</td><td>{e(r['kind'])}</td><td><a href='/invoices/{r['invoice_id']}'>{e(r['ref'] or 'view')}</a>"
        f"<div class='small'>{e(r['text'])}</div></td><td class='r'>{inr(r['debit']) if r['debit'] else ''}</td>"
        f"<td class='r'>{inr(r['credit']) if r['credit'] else ''}</td><td class='r'>{inr(r['balance'])}</td></tr>" for r in st["rows"])
    closing = st["closing"]
    owed = (f"They owe you ₹{inr(closing)}" if closing > 0 else f"You owe them ₹{inr(-closing)}" if closing < 0 else "Settled: nothing owed")
    msg = (f"Namaste {c['name']}, your account with {biz['name']} shows a balance of Rs {closing} due." if closing > 0 else "")
    phone = "".join(ch for ch in (c["phone"] or "") if ch.isdigit())
    wa = (f"<a class='btn wa' target='_blank' rel='noopener' href='https://wa.me/{phone}?text={up.quote(msg)}'>WhatsApp the balance</a>"
          if msg and phone else "")
    return layout("Statement", f"""<div class='pagehead'><div><h1>{e(c['name'])}</h1><div class='sub'>Customer statement · {e(owed)}</div></div>
<div class='actions noprint'><button onclick='window.print()'>Print / Save PDF</button>{wa}<a class='btn alt' href='/customers'>Back</a></div></div>
<form method='get' class='filters noprint'><label style='margin:0;align-self:center'>From</label><input type='date' name='from' value='{e(start)}'>
<label style='margin:0;align-self:center'>To</label><input type='date' name='to' value='{e(end)}'><button class='alt'>Show</button></form>
<div style='height:12px'></div><div class='wrap'><table><tr><th>Date</th><th>Type</th><th>Details</th><th class='r'>Debit</th><th class='r'>Credit</th><th class='r'>Balance</th></tr>
<tr><td colspan='5'><b>Opening balance</b></td><td class='r'><b>{inr(st['opening'])}</b></td></tr>{rows}
<tr><td colspan='3'><b>Closing balance</b></td><td class='r'><b>{inr(st['debit'])}</b></td><td class='r'><b>{inr(st['credit'])}</b></td><td class='r'><b>{inr(closing)}</b></td></tr></table></div>
<p class='small'>Debit = billed or refunded to the customer. Credit = payments and credit notes. Cancelled invoices are left out.</p>""")


def account_page(error=None, notice=None):
    return layout("Account", f"""<div class='pagehead'><div><h1>Account</h1><div class='sub'>Owner passcode</div></div></div>
<div class='card' style='max-width:480px'>{_err(error)}<form method='post' action='/account'><label>Current passcode</label>
<input type='password' name='old' required autocomplete='current-password'><label>New passcode (4+ characters)</label>
<input type='password' name='new' required autocomplete='new-password'><label>Repeat new passcode</label>
<input type='password' name='again' required autocomplete='new-password'>
<p class='small'>Everyone else (staff, and the owner on other devices) is signed out when you change it.</p>
<p><button>Change passcode</button></p></form></div>""", notice=notice)


def audit_page(rows, f):
    ents = ("", "invoice", "payment", "credit_note", "customer", "purchase", "owner", "staff", "backup", "business", "item")
    opts = "".join(f"<option value='{x}'{' selected' if x == (f.get('entity') or '') else ''}>{x or 'All'}</option>" for x in ents)
    trs = "".join(f"<tr><td>{e(r['at'].replace('T', ' '))}</td><td>{e(r['by'])}</td><td>{e(r['action'])}</td><td>{e(r['detail'])}</td></tr>"
                  for r in rows) or "<tr><td colspan='4' class='empty'>Nothing recorded yet.</td></tr>"
    return layout("Audit log", f"""<div class='pagehead'><div><h1>Audit log</h1><div class='sub'>Who changed what. The newest {len(rows)} entries.</div></div></div>
<form method='get' class='filters'><select name='entity'>{opts}</select><input name='q' value='{e(f.get('q'))}' placeholder='Search' type='search'>
<button class='alt'>Filter</button></form><div style='height:12px'></div>
<div class='wrap'><table><tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr>{trs}</table></div>""")


def backups_page(rows, extra_dir="", extra_status="", notice=None, error=None):
    def size(n):
        return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"

    trs = "".join(
        f"<tr><td>{e(r['name'])}</td><td>{e(r['where'])}</td><td>{e(r['kind'])}</td><td class='r'>{size(r['size'])}</td>"
        f"<td>{e(r['mtime'].replace('T', ' '))}</td><td><form method='post' action='/backups/restore' style='margin:0' "
        f"onsubmit=\"return confirm('Replace ALL current data with this backup? A copy of the current data is saved first.')\">"
        f"<input type='hidden' name='where' value='{e(r['where_key'])}'><input type='hidden' name='name' value='{e(r['name'])}'>"
        f"<button class='alt sm'>Restore</button></form></td></tr>" for r in rows) or "<tr><td colspan='6' class='empty'>No backups yet.</td></tr>"
    status = ""
    if extra_dir:
        bad = extra_status.startswith("FAILED")
        status = f"<div class='{'err' if bad else 'ok'}' style='margin-top:10px'>{e(extra_status or 'Not copied yet')}</div>"
    return layout("Backups", f"""<div class='pagehead'><div><h1>Backups</h1><div class='sub'>A copy is saved automatically once a day and kept for 60 days.</div></div>
<form method='post' action='/backups/now' style='margin:0'><button>Back up now</button></form></div>{_err(error)}
<div class='card'><h2>Second backup folder</h2>
<p class='sub' style='margin-top:0'>A backup on the same computer is lost if the computer fails. Choose a folder on a USB drive, or a OneDrive / Google Drive folder that syncs, and every backup is copied there too.</p>
<form method='post' action='/backups/folder' class='filters'><input name='folder' value='{e(extra_dir)}' placeholder='e.g. E:\\BillSaathiBackups' style='flex:1;min-width:260px'>
<button>Save folder</button></form>{status}
{"<form method='post' action='/backups/sync' style='margin-top:10px'><button class='alt'>Copy now</button></form>" if extra_dir else ""}</div>
<h2>Available backups</h2><div class='wrap'><table><tr><th>File</th><th>Where</th><th>Type</th><th class='r'>Size</th><th>Saved</th><th></th></tr>{trs}</table></div>
<p class='small'>Restoring replaces everything with the chosen copy. Before it does, a "before restore" copy of the current data is saved, so you can undo it.</p>""", notice=notice)


def integrations_page(g, ocr_ok, notice=None, error=None, test_result=None):
    import llm

    models = "".join(f"<option value='{v}'{' selected' if v == g['ai_model'] else ''}>{e(l)}</option>" for v, l in llm.MODELS)
    key = db_mask(g["anthropic_api_key"])
    rz = "•••• saved" if g["razorpay_key_secret"] else ""  # a secret is never echoed back, not even in part
    result = f"<div class='{'ok' if test_result[0] else 'err'}'>{e(test_result[1])}</div>" if test_result else ""
    return layout("Integrations", f"""<div class='pagehead'><div><h1>Integrations</h1><div class='sub'>Optional features that use outside services. Everything else works without them.</div></div></div>
{_err(error)}{result}
<div class='card'><h2>Bill scanning (offline)</h2>
<p class='sub' style='margin-top:0'>{'Ready. Photos of supplier bills are read on this computer by Windows. Nothing is sent anywhere.' if ocr_ok else 'Not available on this computer (it needs Windows 10 or 11). You can still use AI reading below.'}</p></div>
<form method='post' action='/integrations' class='card'><h2>AI (Claude)</h2>
<p class='sub' style='margin-top:0'>Adds <b>Fill with AI</b> to quick entry (understands Hindi, Hinglish and English) and an <b>AI reading</b> option when scanning bills.
When you press an AI button, the typed message and your customer and item <i>names</i> (or the bill photo) are sent to Anthropic's Claude service. Phone numbers, GSTINs and amounts owed are not sent.
Usage is billed to your own Anthropic account. Nothing is sent unless you press an AI button.</p>
<div class='row'><div><label>Anthropic API key {('(saved: ' + e(key) + ')') if key else ''}</label>
<input type='password' name='anthropic_key' placeholder='{'leave blank to keep the saved key' if key else 'sk-ant-...'}' autocomplete='off'></div>
<div><label>Model</label><select name='ai_model'>{models}</select></div></div>
<label style='display:flex;gap:8px;align-items:center'><input type='checkbox' name='clear_anthropic' style='width:auto'> Remove the saved key</label>
<div class='actions'><button name='action' value='save'>Save</button><button name='action' value='test_ai' class='alt'>Save and test AI</button></div></form>
<form method='post' action='/integrations' class='card'><h2>Payment links (Razorpay)</h2>
<p class='sub' style='margin-top:0'>Creates a Razorpay payment link for an invoice that you can send to the customer. This computer cannot receive notifications, so after the customer pays you press <b>Check payment</b> on the invoice and BillSaathi records it.
You need your own Razorpay account. Start with <b>test</b> keys (rzp_test_...). Razorpay charges its own fees on each payment.</p>
<div class='row'><div><label>Key id</label><input name='razorpay_id' value='{e(g['razorpay_key_id'])}' placeholder='rzp_test_...' autocomplete='off'></div>
<div><label>Key secret {('(saved: ' + e(rz) + ')') if rz else ''}</label><input type='password' name='razorpay_secret' placeholder='{'leave blank to keep the saved secret' if rz else ''}' autocomplete='off'></div></div>
<label style='display:flex;gap:8px;align-items:center'><input type='checkbox' name='clear_razorpay' style='width:auto'> Remove the saved keys</label>
<div class='actions'><button name='action' value='save_rz'>Save</button><button name='action' value='test_rz' class='alt'>Save and test</button></div></form>
<p class='small'>Keys are stored in your BillSaathi database. Backups and the full-export zip contain them, so keep those private. You can also set <code>ANTHROPIC_API_KEY</code> as a Windows environment variable instead of saving it here.</p>""", notice=notice)


def db_mask(v):
    import db

    return db.mask_secret(v)


def scan_page(ocr_ok, ai_ok, error=None):
    engines = ""
    if ocr_ok:
        engines += "<option value='windows'>Offline (Windows, nothing leaves this computer)</option>"
    if ai_ok:
        engines += "<option value='ai'>AI reading (sends the photo to Claude)</option>"
    if not engines:
        return layout("Scan a bill", "<h1>Scan a purchase bill</h1><div class='card'>Scanning is not available: it needs Windows 10/11, or an AI key on the Integrations page.</div>")
    return layout("Scan a bill", f"""<div class='pagehead'><div><h1>Scan a purchase bill</h1><div class='sub'>Take or choose a photo of a supplier bill. You check and save the details; nothing is saved until you do.</div></div></div>
{_err(error)}<form method='post' action='/purchases/scan' enctype='multipart/form-data' class='card' style='max-width:560px'>
<label>Photo of the bill (JPG or PNG, up to 8 MB)</label><input type='file' name='photo' accept='image/*' capture='environment' required>
<label>Reading method</label><select name='engine'>{engines}</select>
<p class='small'>For best results: flat bill, good light, the whole page in the photo, text not blurred. Always compare the filled-in form with the photo.</p>
<p><button>Read the bill</button> <a class='btn alt' href='/purchases/new'>Enter by hand instead</a></p></form>""")


def _paylink_block(inv, links, ready, owner):
    if not owner or inv["status"] != "active":
        return ""
    can = inv["outstanding"] > 0
    if not ready:
        return ""
    rows = "".join(
        f"<tr><td><a href='{e(l['short_url'])}' target='_blank' rel='noopener'>{e(l['short_url'])}</a></td><td class='r'>{inr(l['amount'])}</td>"
        f"<td>{e(l['status'])}</td><td>{dmy(l['created_at'][:10])}</td><td>" +
        (f"<form method='post' action='/invoices/{inv['id']}/paylink/check' style='margin:0'><input type='hidden' name='link' value='{e(l['link_id'])}'>"
         "<button class='alt sm'>Check payment</button></form>" if not l['payment_id'] and l['status'] not in ('cancelled', 'expired') else "") +
        "</td></tr>" for l in links)
    table = (f"<div class='wrap'><table><tr><th>Link</th><th class='r'>Amount</th><th>Status</th><th>Created</th><th></th></tr>{rows}</table></div>"
             if rows else "")
    create = (f"<form method='post' action='/invoices/{inv['id']}/paylink' style='margin:8px 0 0'><button class='alt'>Create payment link for ₹{inr(inv['outstanding'])}</button></form>"
              if can else "")
    return f"<div class='card noprint'><b>Payment link</b><p class='small' style='margin:4px 0'>Send the link to the customer. After they pay, press Check payment.</p>{table}{create}</div>"


def stock_page(levels, show="", error=None, notice=None):
    today = datetime.date.today().isoformat()
    shown = [l for l in levels if show != "attention" or l["status"] != "ok"]
    chips = "".join(f"<a class='chip{' on' if show == v else ''}' href='/stock{('?show=' + v) if v else ''}'>{l}</a>"
                    for v, l in (("", "All"), ("attention", "Needs attention")))
    rows = ""
    for l in shown:
        q = format(l["on_hand"].normalize(), "f")
        cls = {"out": "Unpaid", "low": "Partly"}.get(l["status"], "Paid")
        word = {"out": "Out" if l["on_hand"] == 0 else "Below zero", "low": "Low", "ok": "OK"}[l["status"]]
        lvl = format(l["reorder_level"].normalize(), "f") if l["reorder_level"] is not None else "-"
        rows += (f"<tr><td><a href='/stock/{l['id']}'>{e(l['description'])}</a></td><td class='r'><b>{e(q)}</b></td><td class='r'>{e(lvl)}</td>"
                 f"<td><span class='tag {cls}'>{word}</span></td><td>"
                 f"<form method='post' action='/stock/{l['id']}/receive' class='filters' style='margin:0;gap:4px'>"
                 f"<input name='qty' placeholder='Qty in' inputmode='decimal' style='width:80px;min-width:0' required>"
                 f"<input name='note' placeholder='Note (optional)' style='width:140px;min-width:0'><input type='hidden' name='date' value='{today}'>"
                 f"<button class='alt sm'>Receive</button></form></td><td>"
                 f"<form method='post' action='/stock/{l['id']}/adjust' class='filters' style='margin:0;gap:4px'>"
                 f"<input name='counted' placeholder='Counted' inputmode='decimal' style='width:80px;min-width:0' required>"
                 f"<input name='note' placeholder='Reason' style='width:120px;min-width:0' required><input type='hidden' name='date' value='{today}'>"
                 f"<button class='alt sm'>Set count</button></form></td></tr>")
    table = (f"<div class='wrap'><table><tr><th>Item</th><th class='r'>In stock</th><th class='r'>Reorder at</th><th>Status</th>"
             f"<th>Goods received</th><th>Physical count</th></tr>{rows}</table></div>" if rows else
             "<div class='card empty'>Nothing here yet. Open <a href='/items'>Items</a>, edit an item and turn on <b>Track stock</b>, then record what you have with <b>Receive</b>.</div>"
             if not levels else "<div class='card empty'>Nothing needs attention.</div>")
    return layout("Stock", f"""<div class='pagehead'><div><h1>Stock</h1><div class='sub'>{len(levels)} tracked item(s). Invoices reduce it automatically; deliveries and counts are entered here.</div></div>
<a class='btn alt' href='/items'>Items</a></div>{_err(error)}<div class='chips'>{chips}</div>{table}
<p class='small'>Receive adds goods that arrived. Set count replaces the book figure with what you counted and records the difference with your reason. Nothing is ever deleted: every movement stays in the item's history.</p>""", notice=notice)


def _stock_ref(m):
    if m["invoice_id"]:
        return f"<a href='/invoices/{m['invoice_id']}'>{e(m['invoice_number'])}</a>"
    return e(m["credit_note_number"] or "")


def stock_history_page(item, moves, on_hand):
    labels = {"opening": "Opening", "received": "Received", "adjust": "Count adjustment", "sale": "Sold", "return": "Returned",
              "edit": "Invoice edited", "cancel": "Invoice cancelled"}
    trs = "".join(
        f"<tr><td>{dmy(m['date'])}</td><td>{e(labels.get(m['kind'], m['kind']))}</td>"
        f"<td class='r' style='color:var(--{'ok' if m['qty'] > 0 else 'bad'})'>{'+' if m['qty'] > 0 else ''}{e(format(m['qty'].normalize(), 'f'))}</td>"
        f"<td>{_stock_ref(m)}"
        f"<div class='small'>{e(m['note'])}</div></td><td>{e(m['created_by'])}</td></tr>" for m in moves) or "<tr><td colspan='5' class='empty'>No movements yet.</td></tr>"
    return layout("Stock history", f"""<div class='pagehead'><div><h1>{e(item['description'])}</h1><div class='sub'>In stock now: <b>{e(format(on_hand.normalize(), 'f'))}</b></div></div>
<a class='btn alt' href='/stock'>Back to stock</a></div><div class='wrap'><table><tr><th>Date</th><th>What</th><th class='r'>Quantity</th><th>Reference</th><th>By</th></tr>{trs}</table></div>""")


_FREQ_LABEL = {"weekly": "Every week", "monthly": "Every month", "quarterly": "Every 3 months", "yearly": "Every year"}


def _items_text(items):
    return ", ".join(f"{format(i['qty'].normalize(), 'f')} × {i['description']}" for i in items)


def recurring_page(rows, notice=None, error=None):
    due = [r for r in rows if r["due"]]
    banner = (f"<div class='warnbox'><b>{len(due)} recurring invoice(s) are due.</b> <a class='btn sm' href='/recurring/due'>Review and create</a></div>" if due else "")
    trs = ""
    for r in rows:
        state = ("<span class='tag Partly'>Due</span>" if r["due"] else "<span class='tag Paid'>Scheduled</span>" if r["active"]
                 else "<span class='tag Cancelled'>Paused or ended</span>")
        est = f"₹{inr(r['estimate'])}" if r["estimate"] is not None else "<span class='tag Unpaid'>needs attention</span>"
        toggle = (f"<form method='post' action='/recurring/{r['id']}/{'pause' if r['active'] else 'resume'}' style='display:inline'>"
                  f"<button class='alt sm'>{'Pause' if r['active'] else 'Resume'}</button></form>")
        trs += (f"<tr><td><b>{e(r['customer_name'])}</b><div class='small'>{e(_items_text(r['items']))}</div></td><td>{_FREQ_LABEL[r['frequency']]}</td>"
                f"<td>{dmy(r['next_date'])}{(' · until ' + dmy(r['end_date'])) if r['end_date'] else ''}</td><td class='r'>{est}</td><td>{state}</td>"
                f"<td class='r'>{r['runs']}</td><td>{toggle} <form method='post' action='/recurring/{r['id']}/delete' style='display:inline' "
                f"onsubmit=\"return confirm('Delete this schedule? Invoices already created are kept.')\"><button class='warn sm'>Delete</button></form></td></tr>")
    table = (f"<div class='wrap'><table><tr><th>Customer and items</th><th>Repeats</th><th>Next</th><th class='r'>Amount</th><th>Status</th>"
             f"<th class='r'>Created</th><th></th></tr>{trs}</table></div>" if trs else
             "<div class='card empty'>No recurring invoices yet. Open any invoice and press <b>Repeat this invoice</b>.</div>")
    return layout("Recurring", f"""<div class='pagehead'><div><h1>Recurring invoices</h1><div class='sub'>Invoices you send on a schedule. BillSaathi never creates one by itself: when one is due you confirm it here.</div></div></div>
{_err(error)}{banner}{table}
<p class='small'>The items and prices are copied from the invoice when you set it up. To change them, delete the schedule and repeat an updated invoice. Prices are not updated automatically.</p>""", notice=notice)


def recurring_due_page(due, today, error=None):
    rows = ""
    for r in due:
        ok = r["estimate"] is not None
        miss = (f"<div class='small'>{r['missed']} earlier period(s) were missed and will not be billed back.</div>" if r["missed"] else "")
        rows += (f"<tr><td><input type='checkbox' name='run_{r['id']}' style='width:auto'{' checked' if ok else ' disabled'}></td>"
                 f"<td><b>{e(r['customer_name'])}</b><div class='small'>{e(_items_text(r['items']))}</div>{miss}"
                 f"{'' if ok else '<div class=small style=color:var(--bad)>Cannot be created now. Check the customer, items and business settings.</div>'}</td>"
                 f"<td>{dmy(r['next_date'])}</td><td class='r'>{('₹' + inr(r['estimate'])) if ok else '-'}</td>"
                 f"<td><input type='date' name='date_{r['id']}' value='{today}' style='min-width:150px'></td></tr>")
    body = (f"<form method='post' action='/recurring/run'><div class='wrap'><table><tr><th></th><th>Customer and items</th><th>Scheduled</th>"
            f"<th class='r'>Amount</th><th>Invoice date</th></tr>{rows}</table></div>"
            f"<p><button>Create the selected invoices</button> <a class='btn alt' href='/recurring'>Back</a></p></form>"
            if rows else "<div class='card empty'>Nothing is due.</div><p><a class='btn alt' href='/recurring'>Back</a></p>")
    return layout("Recurring due", f"<div class='pagehead'><div><h1>Due recurring invoices</h1><div class='sub'>Untick any you do not want this time. Each one is numbered and dated when you create it.</div></div></div>{_err(error)}{body}")


def recurring_new_page(inv, vals, error=None):
    freq = "".join(f"<option value='{k}'{' selected' if vals.get('frequency') == k else ''}>{v}</option>" for k, v in _FREQ_LABEL.items())
    return layout("Repeat invoice", f"""<div class='pagehead'><div><h1>Repeat this invoice</h1><div class='sub'>{e(inv['number'])} for {e(inv['customer_name'])}: {e(_items_text(inv['items']))}</div></div></div>
{_err(error)}<form method='post' action='/recurring/new' class='card' style='max-width:520px'><input type='hidden' name='invoice' value='{inv['id']}'>
<label>How often</label><select name='frequency'>{freq}</select>
<label>First one is due on</label><input type='date' name='start' value='{e(vals.get('start'))}' required>
<label>Stop after (optional)</label><input type='date' name='end' value='{e(vals.get('end'))}'>
<p class='small'>Same customer, items and prices as this invoice (₹{inr(inv['total'])} today). When one is due, BillSaathi asks you to confirm before creating it.</p>
<p><button>Save schedule</button> <a class='btn alt' href='/invoices/{inv['id']}'>Cancel</a></p></form>""")


def _dash_banners(extras):
    if not extras:
        return ""
    out = ""
    if extras.get("recurring_due"):
        out += f"<div class='warnbox'><b>{extras['recurring_due']} recurring invoice(s) are due.</b> <a class='btn sm' href='/recurring/due'>Review and create</a></div>"
    if extras.get("low_stock"):
        out += f"<div class='warnbox'><b>{extras['low_stock']} item(s) are low or out of stock.</b> <a class='btn alt sm' href='/stock?show=attention'>See stock</a></div>"
    return out


def layout(title, body, nav=True, notice=None):
    flash = f"<div class='toast ok' role='status'>{e(notice)}</div>" if notice else ""
    head = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='light dark'>"
            f"<title>{e(title)} - BillSaathi</title><style>{CSS}</style></head><body>")
    if not nav:
        return head + f"<main class='auth'>{flash}{body}<p style='text-align:center' class='small'>{_lang_link()}</p></main></body></html>"
    path = getattr(_ctx, "path", "")
    items = STAFF_NAV if getattr(_ctx, "role", "owner") == "staff" else OWNER_NAV
    on = " class='on' aria-current='page'"
    links = "".join(f"<a href='{h}'{on if _active(h, path) else ''}>{_icon(i)}<span>{l}</span></a>" for h, l, i in items)
    side = (f"<aside class='side noprint'><div class='brand'><i>₹</i>BillSaathi</div>{links}<div class='grow'></div>"
            f"<div class='who'>{e(getattr(_ctx, 'user', ''))} · {_lang_link()}</div><a href='/logout'>{_icon('logout')}<span>Logout</span></a></aside>")
    return head + f"<div class='app'>{side}<main>{flash}{body}</main></div></body></html>"


def _err(error):
    return f"<div class='err'>{e(error)}</div>" if error else ""


def _state_select(name, value, required=False):
    opts = "<option value=''>-- select --</option>" + "".join(
        f"<option{' selected' if s == value else ''}>{e(s)}</option>" for s in STATES)
    return f"<select name='{name}'{' required' if required else ''}>{opts}</select>"


# ---------- auth ----------
def passcode_page(error=None):
    return layout("Set passcode", f"""<div class='brand'><i>₹</i>BillSaathi</div><div class='card'><h1>Welcome</h1>
<p class='sub'>Set an owner passcode. You will need it every time you open the app.</p>{_err(error)}
<form method='post' action='/passcode'><label>New passcode (4+ characters)</label><input type='password' name='passcode' required autofocus>
<label>Repeat passcode</label><input type='password' name='again' required>
<p><button style='width:100%;justify-content:center;padding:11px'>Save passcode</button></p></form></div>""", nav=False)


def login_page(error=None):
    return layout("Login", f"""<div class='brand'><i>₹</i>BillSaathi</div><div class='card'><h1>Sign in</h1>{_err(error)}
<form method='post' action='/login'><label>User (leave blank for owner)</label><input name='user' autocomplete='username'>
<label>Passcode</label><input type='password' name='passcode' required autofocus>
<p><button style='width:100%;justify-content:center;padding:11px'>Open</button></p></form></div>""", nav=False)


# ---------- profile ----------
def profile_page(v, error=None, first=False, notice=None):
    intro = "<p>Fill in your business details once. They appear on every invoice.</p>" if first else ""
    months = ("January February March April May June July August September October November December").split()
    mopts = "".join(f"<option value='{i}'{' selected' if str(v.get('fy_start_month', 4)) == str(i) else ''}>{m}</option>"
                    for i, m in enumerate(months, 1))
    scheme = v.get("scheme") or "regular"
    body = f"""<h1>Business profile</h1>{intro}<div class='card'>{_err(error)}<form method='post' action='/profile'>
<div class='row'><div><label>Business name *</label><input name='name' value='{e(v.get('name'))}' required></div>
<div><label>GSTIN (leave blank if not registered)</label><input name='gstin' value='{e(v.get('gstin'))}' maxlength='15'></div>
<div><label>State *</label>{_state_select('state', v.get('state'), True)}</div>
<div><label>UPI ID</label><input name='upi_id' value='{e(v.get('upi_id'))}' placeholder='shop@bank'></div>
<div><label>Invoice prefix</label><input name='invoice_prefix' value='{e(v.get('invoice_prefix') or 'BS')}' maxlength='6'></div>
<div><label>Financial year starts in</label><select name='fy_start_month'>{mopts}</select></div>
<div><label>Payment due after (days)</label><input type='number' min='0' name='due_days' value='{e(v.get('due_days', 15))}'></div>
<div><label>GST scheme</label><select name='scheme'><option value='regular'{' selected' if scheme == 'regular' else ''}>Regular</option>
<option value='composition'{' selected' if scheme == 'composition' else ''}>Composition scheme</option></select></div></div>
<p class='small'>Composition dealers issue a Bill of Supply with no tax, cannot sell to other states and cannot export. Ask your CA before choosing it.</p>
<label>Address</label><textarea name='address' rows='2'>{e(v.get('address'))}</textarea>
<p><button>Save profile</button></p></form></div>"""
    return layout("Profile", body, nav=not first, notice=notice)


# ---------- dashboard ----------
def dashboard_page(d, recent, biz, series=None, aging=None, attention=None, rstats=None, extras=None):
    import db

    credited = d.get("credited")
    stats = "".join(
        f"<div class='stat' style='--c:{c}'><span>{l}</span><b>{v}</b><small>{s}</small></div>" for l, v, s, c in (
            ("Invoiced this month", "₹" + inr(d["invoiced"]),
             f"net of ₹{inr(credited)} credit notes" if credited else "billed to customers", "var(--brand)"),
            ("Collected this month", "₹" + inr(d["collected"]), "payments received", "var(--b2)"),
            ("Outstanding", "₹" + inr(d["outstanding"]), "yet to be received", "#e0a100"),
            ("Overdue", "₹" + inr(d["overdue_amount"]), f"{d['overdue_count']} invoice(s) past due", "var(--bad)")))
    chart = f"<div class='card'><h2>Last 6 months</h2>{_bars(series)}</div>" if series else ""
    age = ""
    if aging is not None:
        mx = max([float(a["amount"]) for a in aging] + [1.0])
        rows = "".join(
            f"<div>{e(a['label'])}</div><div class='bar{' late' if n else ''}'><i style='width:{float(a['amount']) / mx * 100:.0f}%'></i></div>"
            f"<div class='num'>₹{inr(a['amount'])}<div class='small'>{a['count']} inv.</div></div>"
            for n, a in enumerate(aging))
        age = f"<div class='card'><h2>Who owes you</h2><div class='age'>{rows}</div></div>"
    att = ""
    if attention is not None:
        if attention:
            trs = "".join(
                f"<tr><td><a href='/invoices/{i['id']}'>{e(i['number'])}</a><div class='small'>{e(i['customer_name'])} · due {dmy(i['due_date'])}</div></td>"
                f"<td class='r'>₹{inr(i['outstanding'])}</td><td class='r'><a class='btn wa sm' target='_blank' rel='noopener' "
                f"href='/invoices/{i['id']}/remind'>Remind</a></td></tr>" for i in attention)
            att = f"<h2>Needs attention</h2><div class='wrap'><table>{trs}</table></div>"
        else:
            att = "<h2>Needs attention</h2><div class='ok'>Nothing is overdue. Nice work.</div>"
    rem = ""
    if rstats is not None:
        if rstats["reminders"] == 0:
            rem = "<div class='card'><h2>Reminders</h2><p class='sub' style='margin:0'>No reminders sent yet. Use Remind on an overdue invoice and BillSaathi will track what it brings in.</p></div>"
        else:
            share = f"{rstats['driven'] * 100 // rstats['payments']}%" if rstats["payments"] else "-"
            rem = (f"<div class='card'><h2>Reminders</h2><div style='font-size:26px;font-weight:700'>{rstats['driven']} of {rstats['payments']}</div>"
                   f"<div class='sub'>payments in the last {rstats['days']} days came within {rstats['window']} days of a reminder ({share}). "
                   f"{rstats['reminders']} reminder(s) sent in total.</div></div>")
    return layout("Dashboard", f"""<div class='pagehead'><div><h1>{e(biz['name'])}</h1><div class='sub'>{datetime.date.fromisoformat(d['month_start']).strftime('%B %Y')}</div></div>
<a class='btn' href='/invoices/new'>+ New invoice</a></div>{_dash_banners(extras)}<div class='stats'>{stats}</div>
<div class='cols'><div>{chart}{att}</div><div>{age}{rem}</div></div><h2>Recent invoices</h2>{invoice_table(recent)}""")


# ---------- customers ----------
def customers_page(rows, q=""):
    trs = "".join(
        f"<tr><td><span class='avatar'>{e((c['name'] or '?')[:1].upper())}</span><b>{e(c['name'])}</b></td><td>{e(c['phone'])}</td>"
        f"<td>{e(c['state'])}</td><td>{e(c['gstin'])}</td><td class='r'><a href='/invoices/new?customer_id={c['id']}'>Bill</a> · "
        + (f"<a href='/customers/{c['id']}/statement'>Statement</a> · " if getattr(_ctx, "role", "owner") == "owner" else "")
        + f"<a href='/customers/{c['id']}/edit'>Edit</a></td></tr>" for c in rows)
    table = (f"<div class='wrap'><table><tr><th>Customer</th><th>Phone</th><th>State</th><th>GSTIN</th><th></th></tr>{trs}</table></div>"
             if trs else "<div class='card empty'>No customers yet. Add your first customer to start billing.</div>")
    return layout("Customers", f"""<div class='pagehead'><div><h1>Customers</h1><div class='sub'>{len(rows)} in your list</div></div>
<a class='btn' href='/customers/new'>+ Add customer</a></div>
<form method='get' class='filters'><input name='q' value='{e(q)}' placeholder='Search name or phone' type='search'><button class='alt'>Search</button></form>
<div style='height:12px'></div>{table}""")


def customer_form_page(v, error=None, cid=None):
    action = f"/customers/{cid}/edit" if cid else "/customers/new"
    return layout("Customer", f"""<h1>{'Edit' if cid else 'Add'} customer</h1><div class='card'>{_err(error)}
<form method='post' action='{action}'><div class='row'>
<div><label>Name *</label><input name='name' value='{e(v.get('name'))}' required></div>
<div><label>Phone</label><input name='phone' value='{e(v.get('phone'))}' inputmode='tel'></div>
<div><label>State (decides CGST+SGST or IGST)</label>{_state_select('state', v.get('state'))}</div>
<div><label>GSTIN (optional)</label><input name='gstin' value='{e(v.get('gstin'))}' maxlength='15'></div>
<div><label>Payment due after (days) - blank uses business default</label><input type='number' min='0' max='365' name='due_days' value='{e(v.get('due_days'))}'></div></div>
<label>Address</label><textarea name='address' rows='2'>{e(v.get('address'))}</textarea>
<p><button>Save</button> <a class='btn alt' href='/customers'>Cancel</a></p></form></div>""")


# ---------- invoices ----------
def _tag(inv):
    cls = inv["status_label"].split()[0]
    return f"<span class='tag {e(cls)}'>{e(inv['status_label'])}{' · overdue' if inv['overdue'] else ''}</span>"


def invoice_table(rows, with_remind=False, biz=None):
    import db

    def remind(i):
        if with_remind and biz and i["outstanding"] > 0 and i["status"] == "active":
            return f" <a class='btn wa sm' target='_blank' rel='noopener' href='/invoices/{i['id']}/remind'>Remind</a>"
        return ""

    trs = "".join(
        f"<tr><td><a href='/invoices/{i['id']}'>{e(i['number'])}</a></td><td>{dmy(i['date'])}</td><td>{e(i['customer_name'])}</td>"
        f"<td class='r'>{inr(i['total'])}</td><td class='r'>{inr(i['outstanding'])}</td><td>{_tag(i)}{remind(i)}</td></tr>"
        for i in rows) or "<tr><td colspan='6'>No invoices.</td></tr>"
    return (f"<div class='wrap'><table><tr><th>Number</th><th>Date</th><th>Customer</th><th class='r'>Total</th>"
            f"<th class='r'>Outstanding</th><th>Status</th></tr>{trs}</table></div>")


def catalog_page(rows, levels=None):
    levels = levels or {}

    def stock_cell(r):
        if not r["track_stock"]:
            return "<span class='small'>not tracked</span>"
        lv = levels.get(r["id"])
        q = format(lv["on_hand"].normalize(), "f") if lv else "0"
        cls = {"out": "Unpaid", "low": "Partly"}.get(lv["status"] if lv else "out", "Paid")
        return f"<span class='tag {cls}'>{e(q)}</span>"

    trs = "".join(f"<tr><td>{e(r['description'])}</td><td>{e(r['hsn'])}</td><td class='r'>{inr(r['rate'])}</td>"
                  f"<td class='r'>{e(format(r['gst_rate'].normalize(), 'f'))}%</td><td>{stock_cell(r)}</td>"
                  f"<td><a href='/items/{r['id']}/edit'>Edit</a></td></tr>" for r in rows) or "<tr><td colspan='6'>No saved items yet.</td></tr>"
    return layout("Items", f"""<div class='pagehead'><div><h1>Saved items</h1><div class='sub'>Saved prices fill in when you type the item name on an invoice. Turn on Track stock to count what you have.</div></div>
<div class='actions'><a class='btn alt' href='/stock'>Stock</a><a class='btn' href='/items/new'>+ Add item</a></div></div>
<div class='wrap'><table><tr><th>Item</th><th>HSN</th><th class='r'>Rate ₹</th><th class='r'>GST</th><th>In stock</th><th></th></tr>{trs}</table></div>""")


def catalog_form_page(v, error=None, item_id=None):
    g = str(v.get("gst_rate", "5"))
    try:
        g = format(Decimal(g).normalize(), "f")
    except Exception:
        pass
    opts = "".join(f"<option{' selected' if x == g else ''}>{x}</option>" for x in GST_CHOICES)
    delete = (f"<form method='post' action='/items/{item_id}/delete' onsubmit=\"return confirm('Delete this saved item? "
              f"Existing invoices are not affected.')\"><button class='warn'>Delete</button></form>" if item_id else "")
    action = f"/items/{item_id}/edit" if item_id else "/items/new"
    tracked = str(v.get("track_stock", "")) in ("1", "on", "True")
    reorder = v.get("reorder_level")
    reorder = "" if reorder is None else (format(Decimal(str(reorder)).normalize(), "f") if str(reorder).strip() else "")
    return layout("Item", f"""<h1>{'Edit' if item_id else 'Add'} item</h1><div class='card'>{_err(error)}
<form method='post' action='{action}'><div class='row'><div><label>Description *</label><input name='description' value='{e(v.get('description'))}' required></div>
<div><label>HSN</label><input name='hsn' value='{e(v.get('hsn'))}'></div>
<div><label>Rate ₹ *</label><input name='rate' value='{e(v.get('rate'))}' inputmode='decimal' required></div>
<div><label>GST %</label><select name='gst_rate'>{opts}</select></div></div>
<div class='card' style='margin:12px 0 0;padding:10px 14px'><label style='margin:0;display:flex;gap:8px;align-items:center'>
<input type='checkbox' name='track_stock' style='width:auto'{' checked' if tracked else ''}> Track stock for this item</label>
<div class='row'><div><label>Tell me when it is down to (reorder level)</label><input name='reorder_level' value='{e(reorder)}' inputmode='decimal' placeholder='e.g. 5'></div></div>
<p class='small' style='margin-bottom:0'>When on, each invoice for this item reduces stock, and you add deliveries and counts on the Stock page. Sales are matched by the item name, so keep invoice lines named exactly like the saved item.</p></div>
<p><button>Save</button> <a class='btn alt' href='/items'>Cancel</a></p></form>{delete}</div>""")


def liability_table(rows, tot):
    trs = "".join(f"<tr><td>{e(format(r['rate'].normalize(), 'f'))}%</td><td class='r'>{inr(r['taxable'])}</td><td class='r'>{inr(r['cgst'])}</td>"
                  f"<td class='r'>{inr(r['sgst'])}</td><td class='r'>{inr(r['igst'])}</td><td class='r'>{inr(r['tax'])}</td></tr>" for r in rows)
    trs += (f"<tr><th>Total</th><th class='r'>{inr(tot['taxable'])}</th><th class='r'>{inr(tot['cgst'])}</th>"
            f"<th class='r'>{inr(tot['sgst'])}</th><th class='r'>{inr(tot['igst'])}</th><th class='r'>{inr(tot['tax'])}</th></tr>")
    return (f"<div class='wrap'><table><tr><th>Rate</th><th class='r'>Taxable</th><th class='r'>CGST</th><th class='r'>SGST</th>"
            f"<th class='r'>IGST</th><th class='r'>Total tax</th></tr>{trs}</table></div>")


def invoices_page(rows, f, biz, customers=()):
    copts = "<option value=''>All customers</option>" + "".join(
        f"<option value='{c['id']}'{' selected' if str(c['id']) == str(f.get('customer_id')) else ''}>{e(c['name'])}</option>" for c in customers)
    chips = "".join(
        f"<a class='chip{' on' if (f.get('status') or '') == v else ''}' href='/invoices{_qs(f, status=v)}'>{l}</a>"
        for v, l in (("", "All"), ("unpaid", "Unpaid"), ("partly", "Partly paid"), ("overdue", "Overdue"), ("paid", "Paid"),
                     ("cancelled", "Cancelled")))
    tot = sum((r["total"] for r in rows if r["status"] == "active"), Decimal("0.00"))
    out = sum((r["outstanding"] for r in rows), Decimal("0.00"))
    return layout("Invoices", f"""<div class='pagehead'><div><h1>Invoices</h1>
<div class='sub'>{len(rows)} shown · billed ₹{inr(tot)} · outstanding ₹{inr(out)}</div></div><a class='btn' href='/invoices/new'>+ New invoice</a></div>
<div class='chips'>{chips}</div>
<form method='get' class='filters'><input type='hidden' name='status' value='{e(f.get('status'))}'>
<input type='month' name='month' value='{e(f.get('month'))}'><select name='customer_id'>{copts}</select>
<input name='q' value='{e(f.get('q'))}' placeholder='Invoice no. or customer' type='search'><button class='alt'>Filter</button>
<a class='btn alt' href='/invoices'>Reset</a></form><div style='height:12px'></div>{invoice_table(rows, True, biz)}""")


def invoice_form_page(customers, vals, error=None, today="", catalog=(), biz_state="", warnings=(), quick_text="",
                      scheme="regular", edit_id=None, edit_number="", ai_enabled=False):
    import json

    stock = getattr(_ctx, "stock_fn", lambda: {})()  # quantities in stock, for the "only 3 in stock" hint

    def _cat(c):
        d = {"hsn": c["hsn"] or "", "rate": str(c["rate"]), "gst": format(c["gst_rate"].normalize(), "f")}
        if c["track_stock"]:
            d["stock"] = format(stock.get(c["id"], Decimal("0")).normalize(), "f")
        return d

    cat_json = json.dumps({c["description"].lower(): _cat(c) for c in catalog}).replace("<", "\\u003c")
    datalist = "<datalist id='catalog'>" + "".join(f"<option value='{e(c['description'])}'>" for c in catalog) + "</datalist>"
    copts = "<option value=''>Select customer…</option>" + "".join(
        f"<option value='{c['id']}' data-state='{e(c['state'])}'{' selected' if str(c['id']) == str(vals.get('customer_id')) else ''}>"
        f"{e(c['name'])}{' · ' + e(c['phone']) if c['phone'] else ''}</option>" for c in customers)
    rows = vals.get("items") or [{}]
    stype = vals.get("supply_type") or "regular"

    def line(it):
        gr = str(it.get("gst_rate", "5"))
        g = "".join(f"<option{' selected' if x == gr else ''}>{x}</option>" for x in GST_CHOICES)
        return (f"<div class='line'><input name='description' list='catalog' value='{e(it.get('description'))}' placeholder='Item' autocomplete='off'>"
                f"<input name='hsn' value='{e(it.get('hsn'))}' placeholder='HSN'>"
                f"<input name='qty' value='{e(it.get('qty'))}' inputmode='decimal' placeholder='Qty'>"
                f"<input name='rate' value='{e(it.get('rate'))}' inputmode='decimal' placeholder='Rate ₹'>"
                f"<select name='gst_rate' title='GST %'>{g}</select><div class='amt'>₹0.00</div>"
                f"<button type='button' class='rm' title='Remove line' aria-label='Remove line'>✕</button></div>")

    warn = "".join(f"<div class='warnbox'>{e(w)}</div>" for w in warnings)
    editing = edit_id is not None
    action = f"/invoices/{edit_id}/edit" if editing else "/invoices/new"
    head = (f"<h1>Edit invoice</h1><div class='sub'>{e(edit_number)} · the number stays the same</div>" if editing else
            "<h1>New invoice</h1><div class='sub'>Tab between fields · Enter on Rate adds a line</div>")
    quick_box = "" if editing else f"""<form method='post' action='/invoices/quick' class='card' style='padding:12px 14px'><label style='margin-top:0'>Quick entry: type it like a message, then check the form below</label>
<div class='filters'><input name='text' id='qtext' value='{e(quick_text)}' placeholder='Ramesh, 3 kg barfi at 450, 2 samosa at 20' style='flex:1;min-width:240px'>
<button class='alt' name='mode' value='rules'>Fill form</button>{"<button name='mode' value='ai'>Fill with AI</button>" if ai_enabled else ""}
<button type='button' class='alt' id='mic' style='display:none' title='Speak instead of typing'>🎤 Speak</button></div>
<div class='small' id='micnote' style='display:none;margin-top:6px'>Voice uses your browser's speech service (Chrome or Edge send the audio to Google/Microsoft). Only the words are used here.
<select id='miclang' style='width:auto;display:inline;padding:2px 6px'><option value='hi-IN'>हिन्दी</option><option value='en-IN'>English</option></select></div></form>
<script>(function(){{var R=window.SpeechRecognition||window.webkitSpeechRecognition,b=document.getElementById('mic');if(!R||!b)return;b.style.display='inline-flex';
document.getElementById('micnote').style.display='block';var rec=null;b.onclick=function(){{if(rec){{rec.stop();return}}rec=new R();
rec.lang=document.getElementById('miclang').value;rec.interimResults=false;b.textContent='Listening... tap to stop';
rec.onresult=function(e){{document.getElementById('qtext').value=e.results[0][0].transcript}};
rec.onend=function(){{rec=null;b.textContent='🎤 Speak'}};rec.onerror=function(){{rec=null;b.textContent='🎤 Speak'}};rec.start()}}}})();</script>"""
    edit_note = ("<div class='warnbox'>You can edit this invoice because no payment or credit note exists yet. Every change is saved in the audit log. "
                 "Once money is recorded against it, corrections are made with a credit note.</div>") if editing else ""
    supply = "" if scheme == "composition" else f"""<div><label>Supply type</label><select name='supply_type' id='stype'>
<option value='regular'{' selected' if stype == 'regular' else ''}>Regular sale</option>
<option value='export_lut'{' selected' if stype == 'export_lut' else ''}>Export under LUT (no tax)</option>
<option value='export_igst'{' selected' if stype == 'export_igst' else ''}>Export with IGST</option></select></div>"""
    comp_note = ("<div class='warnbox'>Composition scheme: this will be a Bill of Supply with no tax.</div>" if scheme == "composition" else "")
    body = f"""<div class='pagehead'><div>{head}</div></div>{quick_box}{warn}{edit_note}{comp_note}
{_err(error)}<form method='post' action='{action}' class='invform' id='f'><div>
<div class='card'><div class='row'><div><label>Customer *</label><select name='customer_id' id='cust' required>{copts}</select>
<button type='button' class='alt sm' id='newcust' style='margin-top:8px'>+ New customer</button>
<button type='button' class='alt sm' id='lastbtn' style='margin:8px 0 0 6px;display:none'>Use items from this customer's last invoice</button></div>
<div><label>Date *</label><input type='date' name='date' value='{e(vals.get('date') or today)}' required></div>{supply}</div>
<div id='statewarn' class='warnbox' style='display:none;margin-top:10px'>This customer has no state set, so tax is treated as same-state (CGST + SGST).</div></div>
<div id='stockwarn' class='warnbox' style='display:none'></div>
<div class='card'><h2>Items (up to 10)</h2><div class='lines' id='lines'><div class='line head'><span>Description</span><span>HSN</span><span>Qty</span>
<span>Rate ₹</span><span>GST %</span><span class='r'>Amount</span><span></span></div>{''.join(line(i) for i in rows)}</div>
<p style='margin-bottom:0'><button type='button' class='alt' id='add'>+ Add line</button></p></div></div>
<aside class='card totals'><h2>Summary</h2><div class='t'><span>Taxable value</span><span id='tx'>₹0.00</span></div>
<div id='taxrows'></div><div class='t grand'><span>Total</span><span id='tt'>₹0.00</span></div>
<div class='small' id='taxkind' style='margin-top:6px'></div><button>{'Save changes' if editing else 'Save invoice'}</button></aside></form>
<dialog id='cdlg'><form id='cform'><h2 style='margin-top:0'>New customer</h2><div id='cerr' class='err' style='display:none'></div>
<label>Name *</label><input name='name' required><label>Phone</label><input name='phone' inputmode='tel'>
<label>State (decides CGST+SGST or IGST)</label>{_state_select('state', biz_state)}
<div class='actions'><button>Save customer</button><button type='button' class='alt' id='ccancel'>Cancel</button></div></form></dialog>{datalist}
<script>
(function(){{
var BIZ={json.dumps((biz_state or '').strip().lower())},COMP={json.dumps(scheme == 'composition')},CAT={cat_json},MAX=10;
var lines=document.getElementById('lines'),cust=document.getElementById('cust'),stype=document.getElementById('stype');
/*MATH*/function big(s,scale){{s=(s||'').trim();if(!/^\\d*\\.?\\d*$/.test(s)||s===''||s==='.')return null;var p=s.split('.'),f=((p[1]||'')+'000').slice(0,scale);
return BigInt((p[0]||'0')+f)}}
function money(p){{var s=p.toString().padStart(3,'0'),w=s.slice(0,-2),f=s.slice(-2),o=w.slice(-3),r=w.slice(0,-3);
while(r.length>2){{o=r.slice(-2)+','+o;r=r.slice(0,-2)}}if(r)o=r+','+o;return '₹'+o+'.'+f}}
function lineCalc(qs,rs,gs,x){{var q=big(qs,3),rt=big(rs,2);if(q===null||rt===null)return null;
var g=BigInt(gs),tx=(q*rt+500n)/1000n,tax=(tx*g+50n)/100n;if(x)return {{tx:tx,c:0n,s:0n,i:tax}};
var c=(tax+1n)/2n;return {{tx:tx,c:c,s:tax-c,i:0n}}}}/*ENDMATH*/
function sup(){{return stype?stype.value:'regular'}}
function inter(){{if(sup()!=='regular')return true;var o=cust.options[cust.selectedIndex],st=o?(o.dataset.state||'').trim().toLowerCase():'';return !!st&&!!BIZ&&st!==BIZ}}
function calc(){{var T=0n,C=0n,S=0n,I=0n,x=inter(),zero=COMP||sup()==='export_lut';
lines.querySelectorAll('.line:not(.head)').forEach(function(r){{var a=r.querySelector('.amt'),
L=lineCalc(r.querySelector('[name=qty]').value,r.querySelector('[name=rate]').value,zero?'0':(r.querySelector('[name=gst_rate]').value||'0'),x);
if(!L){{a.textContent='₹0.00';return}}a.textContent=money(L.tx);T+=L.tx;C+=L.c;S+=L.s;I+=L.i}});
document.getElementById('tx').textContent=money(T);
var sw=[];lines.querySelectorAll('.line:not(.head)').forEach(function(r){{var s=CAT[r.querySelector('[name=description]').value.trim().toLowerCase()],
q=parseFloat(r.querySelector('[name=qty]').value);if(s&&s.stock!==undefined&&q>0&&q>parseFloat(s.stock))sw.push(r.querySelector('[name=description]').value.trim()+': only '+s.stock+' in stock')}});
var sel=document.getElementById('stockwarn');sel.style.display=sw.length?'block':'none';sel.textContent=sw.join(' · ');
document.getElementById('taxrows').innerHTML=COMP?'':(x?'<div class="t"><span>IGST</span><span>'+money(I)+'</span></div>'
:'<div class="t"><span>CGST</span><span>'+money(C)+'</span></div><div class="t"><span>SGST</span><span>'+money(S)+'</span></div>');
document.getElementById('tt').textContent=money(T+C+S+I);
var k='';if(COMP)k='Bill of supply: no tax';else if(sup()==='export_lut')k='Export under LUT: no tax';else if(sup()==='export_igst')k='Export: IGST applies';
else if(cust.value)k=x?'Other state: IGST applies':'Same state: CGST + SGST';document.getElementById('taxkind').textContent=k;
var o=cust.options[cust.selectedIndex];document.getElementById('statewarn').style.display=(!COMP&&sup()==='regular'&&o&&o.value&&!(o.dataset.state||'').trim())?'block':'none'}}
function rows(){{return lines.querySelectorAll('.line:not(.head)')}}
function addLine(){{if(rows().length>=MAX)return null;var r=rows()[0].cloneNode(true);
r.querySelectorAll('input').forEach(function(i){{i.value=''}});r.querySelector('select').value='5';r.querySelector('.amt').textContent='₹0.00';
lines.appendChild(r);document.getElementById('add').disabled=rows().length>=MAX;return r}}
document.getElementById('add').onclick=function(){{var r=addLine();if(r)r.querySelector('input').focus()}};
lines.addEventListener('click',function(ev){{if(ev.target.classList.contains('rm')){{if(rows().length>1)ev.target.closest('.line').remove();
document.getElementById('add').disabled=rows().length>=MAX;calc()}}}});
lines.addEventListener('input',calc);
lines.addEventListener('change',function(ev){{if(ev.target.name==='description'){{var s=CAT[ev.target.value.trim().toLowerCase()];
if(s){{var r=ev.target.closest('.line');r.querySelector('[name=hsn]').value=s.hsn;r.querySelector('[name=rate]').value=s.rate;
r.querySelector('[name=gst_rate]').value=s.gst;var q=r.querySelector('[name=qty]');if(!q.value){{q.value='1';q.focus();q.select()}}}}}}calc()}});
lines.addEventListener('keydown',function(ev){{if(ev.key==='Enter'&&ev.target.tagName==='INPUT'){{ev.preventDefault();
var r=ev.target.closest('.line');if(ev.target.name==='rate'&&r===rows()[rows().length-1]){{var n=addLine();if(n)n.querySelector('input').focus()}}
else{{var inp=[].slice.call(r.querySelectorAll('input')),i=inp.indexOf(ev.target);(inp[i+1]||ev.target).focus()}}}}}});
function blank(){{return [].every.call(rows(),function(r){{return !r.querySelector('[name=description]').value&&!r.querySelector('[name=qty]').value&&!r.querySelector('[name=rate]').value}})}}
var last=[];
function offerLast(){{var b=document.getElementById('lastbtn');b.style.display='none';last=[];if(!cust.value||!blank())return;
fetch('/customers/'+cust.value+'/last-items').then(function(r){{return r.json()}}).then(function(j){{if(j.items&&j.items.length&&blank()){{last=j.items;b.style.display='inline-flex'}}}}).catch(function(){{}})}}
document.getElementById('lastbtn').onclick=function(){{while(rows().length>1)rows()[rows().length-1].remove();
last.slice(0,MAX).forEach(function(it,i){{var r=i===0?rows()[0]:addLine();if(!r)return;r.querySelector('[name=description]').value=it.description;
r.querySelector('[name=hsn]').value=it.hsn;r.querySelector('[name=qty]').value=it.qty;r.querySelector('[name=rate]').value=it.rate;r.querySelector('[name=gst_rate]').value=it.gst_rate}});
this.style.display='none';document.getElementById('add').disabled=rows().length>=MAX;calc()}};
cust.onchange=function(){{calc();offerLast()}};if(stype)stype.onchange=calc;
var dlg=document.getElementById('cdlg');
document.getElementById('newcust').onclick=function(){{dlg.showModal();dlg.querySelector('[name=name]').focus()}};
document.getElementById('ccancel').onclick=function(){{dlg.close()}};
document.getElementById('cform').onsubmit=function(ev){{ev.preventDefault();var fd=new URLSearchParams(new FormData(ev.target)),er=document.getElementById('cerr');
fetch('/customers/quick',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:fd}}).then(function(r){{return r.json()}}).then(function(j){{
if(j.error){{er.textContent=j.error;er.style.display='block';return}}
var o=new Option(j.label,j.id,true,true);o.dataset.state=j.state||'';cust.add(o);cust.value=j.id;dlg.close();ev.target.reset();er.style.display='none';calc();offerLast()}})}};
var pre=new URLSearchParams(location.search).get('customer_id');if(pre&&!cust.value)cust.value=pre;
calc();offerLast()}})();
</script>"""
    return layout("Edit invoice" if editing else "New invoice", body)


def invoice_view_page(inv, biz, error=None, notice=None, today="", links=(), gateway_ready=False):
    import words

    owner = getattr(_ctx, "role", "owner") == "owner"
    composition = biz["scheme"] == "composition"
    inter = bool(inv["is_interstate"])
    brk_table, totrows = _tax_tables(inv, inter, show_tax=not composition)
    totrows += f"<tr><th>Total</th><th class='r'>₹{inr(inv['total'])}</th></tr>"
    if inv["credited"] > 0:
        totrows += (f"<tr><td>Less: credit notes</td><td class='r'>-{inr(inv['credited'])}</td></tr>"
                    f"<tr><td>Net payable</td><td class='r'>{inr(inv['net_total'])}</td></tr>")
    if inv["paid"] != 0:
        totrows += f"<tr><td>Paid (net of refunds)</td><td class='r'>{inr(inv['paid'])}</td></tr>"
    if inv["status"] == "active" and (inv["paid"] != 0 or inv["credited"] > 0):
        totrows += (f"<tr><td>Outstanding</td><td class='r'>{inr(inv['outstanding'])}</td></tr>" if not inv["refund_due"] else
                    f"<tr><td>Refund due to customer</td><td class='r'>{inr(inv['refund_due'])}</td></tr>")
    cancelled = "<h2 style='color:#b3261e'>CANCELLED</h2>" if inv["status"] == "cancelled" else ""
    pays = "".join(f"<tr><td>{dmy(p['date'])}</td><td class='r'>{inr(p['amount'])}</td><td>{e(p['mode'])}</td><td>{e(p['note'])}</td>"
                   f"<td>{e(p['created_by'])}</td></tr>" for p in inv["payments"])
    modes = "".join(f"<option value='{m}'>{m.upper() if m == 'upi' else m.title()}</option>" for m in ("cash", "upi", "bank", "other"))
    active = inv["status"] == "active"
    can_pay = active and inv["outstanding"] > 0
    pay_form = f"""<form method='post' action='/invoices/{inv['id']}/payment' class='card noprint'><b>Record payment</b>
<div class='row'><div><label>Date</label><input type='date' name='date' value='{today}' required></div>
<div><label>Amount ₹ (max {inr(inv['outstanding'])})</label><input name='amount' value='{inv['outstanding']}' inputmode='decimal' required></div>
<div><label>Mode</label><select name='mode'>{modes}</select></div><div><label>Note</label><input name='note'></div></div>
<p><button>Save payment</button></p></form>""" if can_pay else ""
    refund_form = f"""<form method='post' action='/invoices/{inv['id']}/refund' class='card noprint'><b>Record refund</b>
<p class='small'>₹{inr(inv['refund_due'])} is due back to the customer after the credit note.</p>
<div class='row'><div><label>Date</label><input type='date' name='date' value='{today}' required></div>
<div><label>Amount ₹</label><input name='amount' value='{inv['refund_due']}' inputmode='decimal' required></div>
<div><label>Mode</label><select name='mode'>{modes}</select></div><div><label>Note</label><input name='note'></div></div>
<p><button class='alt'>Save refund</button></p></form>""" if owner and active and inv["refund_due"] > 0 else ""
    credit_rows = "".join(
        f"<tr><td>{n}</td><td>{e(it['description'])}</td><td class='r'>{e(format(it['qty'].normalize(), 'f'))}</td>"
        f"<td class='r'>{e(format(inv['remaining_qty'][it['id']].normalize(), 'f'))}</td>"
        f"<td><input name='qty_{it['id']}' inputmode='decimal' placeholder='0' style='width:90px'"
        f"{'' if inv['remaining_qty'][it['id']] > 0 else ' disabled'}></td></tr>" for n, it in enumerate(inv["items"], 1))
    credit_form = f"""<form method='post' action='/invoices/{inv['id']}/credit-note' class='card noprint'><b>Issue credit note</b>
<p class='small'>For returned goods or a price correction. Enter the quantity to credit on each line.</p>
<div class='wrap'><table><tr><th>#</th><th>Item</th><th class='r'>Sold</th><th class='r'>Left to credit</th><th>Credit qty</th></tr>{credit_rows}</table></div>
<div class='row'><div><label>Date</label><input type='date' name='date' value='{today}' required></div>
<div><label>Reason *</label><input name='reason' required placeholder='e.g. goods returned'></div></div>
<label style='display:flex;gap:8px;align-items:center'><input type='checkbox' name='restock' checked style='width:auto'> Put the credited goods back in stock (only for items whose stock is tracked)</label>
<p><button class='alt'>Issue credit note</button></p></form>""" if owner and active and any(v > 0 for v in inv["remaining_qty"].values()) else ""
    notes = ("<div class='card noprint'><b>Credit notes</b><table><tr><th>Number</th><th>Date</th><th>Reason</th><th class='r'>Amount</th></tr>" +
             "".join(f"<tr><td><a href='/credit-notes/{n['id']}'>{e(n['number'])}</a></td><td>{dmy(n['date'])}</td><td>{e(n['reason'])}</td>"
                     f"<td class='r'>{inr(n['total'])}</td></tr>" for n in inv["credit_notes"]) + "</table></div>") if inv["credit_notes"] else ""
    remind = (f"<a class='btn wa' target='_blank' rel='noopener' href='/invoices/{inv['id']}/remind'>WhatsApp reminder</a>" if can_pay else "")
    editable = owner and active and not inv["payments"] and not inv["credit_notes"]
    edit = f"<a class='btn alt' href='/invoices/{inv['id']}/edit'>Edit invoice</a>" if editable else ""
    dup = (f"<a class='btn alt' href='/invoices/new?copy={inv['id']}'>Duplicate</a>"
           + (f"<a class='btn alt' href='/recurring/new?invoice={inv['id']}'>Repeat this invoice</a>" if active else "")) if owner else ""
    cancel = (f"<form method='post' action='/invoices/{inv['id']}/cancel' class='actions' style='margin:0' "
              f"onsubmit=\"return confirm('Cancel this invoice? The number is kept.')\">"
              f"<input name='reason' placeholder='Reason for cancelling' required style='width:220px'>"
              f"<button class='warn'>Cancel invoice</button></form>" if editable else "")
    why = (f"<div class='warnbox'>Cancelled on {dmy((inv['cancelled_at'] or '')[:10])}: {e(inv['cancel_reason'])}</div>"
           if inv["status"] == "cancelled" and inv["cancel_reason"] else "")
    nostate = ("<div class='warnbox noprint'>Customer state is missing: tax was treated as intra-state (CGST + SGST). "
               "Edit the customer if this is wrong, then create a new invoice.</div>" if not inv["customer_state"] and not composition else "")
    pay_hist = (f"<div class='card noprint'><b>Payments</b><table><tr><th>Date</th><th class='r'>Amount</th><th>Mode</th><th>Note</th><th>By</th></tr>{pays}</table></div>"
                if pays else "")
    special = ("Composition taxable person, not eligible to collect tax on supplies." if composition else SUPPLY_NOTES.get(inv["supply_type"], ""))
    special_html = f"<p style='margin:8px 0 0'><b>{e(special)}</b></p>" if special else ""
    return layout(inv["number"], f"""{_err(error)}
<div class='actions noprint'><button onclick='window.print()'>Print / Save PDF</button>{remind}{edit}{dup}{cancel}<span>{_tag(inv)}</span></div>{why}{nostate}
{"<div class='small noprint'>Created by " + e(inv['created_by']) + "</div>" if inv.get('created_by') else ''}
<!--noxl--><div class='inv'><div class='two'><div><h1>{e(biz['name'])}</h1><div>{e(biz['address'])}</div>
{'<div>GSTIN: ' + e(biz['gstin']) + '</div>' if biz['gstin'] else ''}<div>State: {e(biz['state'])}</div></div>
<div style='text-align:right'><h2 style='margin:0'>{_doc_title(biz, inv)}</h2>{cancelled}
<div><b>{e(inv['number'])}</b></div><div>Date: {dmy(inv['date'])}</div><div>Due: {dmy(inv['due_date'])}</div></div></div>
<hr><div><b>Bill to:</b> {e(inv['customer_name'])}<br>{e(inv['customer_address'])}
{'<br>Phone: ' + e(inv['customer_phone']) if inv['customer_phone'] else ''}
{'<br>GSTIN: ' + e(inv['customer_gstin']) if inv['customer_gstin'] else ''}
{'<br>State: ' + e(inv['customer_state']) if inv['customer_state'] else ''}</div>
<div class='wrap'><table style='margin-top:10px'><tr><th>#</th><th>Description</th><th>HSN</th><th class='r'>Qty</th><th class='r'>Rate</th>
<th class='r'>GST</th><th class='r'>Taxable</th></tr>{_line_rows(inv['items'])}</table></div>
<div class='two' style='margin-top:10px'><div style='flex:1;min-width:240px'>{brk_table}</div>
<div style='min-width:240px'><table>{totrows}</table></div></div>{special_html}
<p style='margin:10px 0 0'><b>Amount in words:</b> {e(words.rupees_in_words(inv['total']))}</p>{_upi_block(biz, inv)}
<p class='small'>This is a computer-generated invoice. Tax is calculated as per GST rules for regular supplies;
please verify with your CA. Subject to local jurisdiction.</p></div><!--/noxl-->{pay_form}{_paylink_block(inv, links, gateway_ready, owner)}{refund_form}{credit_form}{notes}{pay_hist}""", notice=notice)


def staff_page(rows, error=None, notice=None):
    trs = "".join(
        f"<tr><td>{e(s['name'])}</td><td>{'Active' if s['active'] else '<b>Disabled</b>'}</td><td>"
        f"<form method='post' action='/staff/{s['id']}/active' style='display:inline'><input type='hidden' name='active' value='{0 if s['active'] else 1}'>"
        f"<button class='alt'>{'Disable' if s['active'] else 'Enable'}</button></form> "
        f"<form method='post' action='/staff/{s['id']}/passcode' style='display:inline-flex;gap:6px'><input name='passcode' type='password' "
        f"placeholder='New passcode' style='width:140px' required><button class='alt'>Reset</button></form></td></tr>"
        for s in rows) or "<tr><td colspan='3'>No staff yet.</td></tr>"
    return layout("Staff", f"""<h1>Staff</h1><p class='small'>Staff can create invoices, add customers and record payments. They cannot see the
dashboard totals, cancel invoices, or open purchases, bank, reconcile, exports, items, staff or profile.</p>{_err(error)}
<div class='card'><form method='post' action='/staff/new' class='row'><div><label>Name</label><input name='name' required></div>
<div><label>Passcode (4+ characters)</label><input name='passcode' type='password' required></div>
<div style='align-self:end'><button>Add staff</button></div></form></div>
<div class='wrap'><table><tr><th>Name</th><th>Status</th><th>Actions</th></tr>{trs}</table></div>""", notice=notice)


def forbidden_page():
    return layout("Not allowed", "<h1>Not allowed</h1><p>Your account cannot open this page. Ask the owner.</p>")


LEVEL_TEXT = {"confident": "Confident", "suggested": "Check this", "unclear": "Unclear - pick one", "none": "No match",
              "applied": "Already applied"}


def bank_page(f, error=None, entries=None, skipped=0, errors=(), summary=None):
    out = ""
    if summary:
        ok = "".join(f"<li>{e(a)}</li>" for a in summary["applied"])
        bad = "".join(f"<li>{e(a)}</li>" for a in summary["failed"])
        out += (f"<div class='ok'><b>{len(summary['applied'])} payment(s) recorded.</b><ul>{ok}</ul></div>" if summary["applied"] else "")
        out += f"<div class='err'><b>Not recorded:</b><ul>{bad}</ul></div>" if summary["failed"] else ""
    if entries is not None:
        notes = "".join(f"<div class='warnbox'>{e(x)}</div>" for x in errors)
        if skipped:
            notes += f"<div class='small'>{skipped} debit line(s) ignored.</div>"
        rows = ""
        for en in entries:
            r = en["row"]
            if en["level"] == "applied":
                pick = "<span class='small'>Already recorded earlier</span>"
            else:
                opts = "<option value=''>-- skip --</option>" + "".join(
                    f"<option value='{c['id']}'{' selected' if c['id'] == en['pick'] else ''}>{e(c['number'])} · {e(c['customer_name'])} · "
                    f"due ₹{inr(c['outstanding'])}</option>" for c in en["cands"])
                pick = f"<select name='choice_{r['line']}'>{opts}</select>"
            rows += (f"<tr><td>{dmy(r['date'])}</td><td>{e(r['desc'])}<div class='small'>{e(r['ref'])}</div></td>"
                     f"<td class='r'>{inr(r['amount'])}</td><td><span class='tag'>{e(LEVEL_TEXT[en['level']])}</span></td><td>{pick}</td></tr>")
        out += (f"<h2>Receipts found: {len(entries)}</h2>{notes}<form method='post' action='/bank'>"
                f"<textarea name='csv' style='display:none'>{e(f.get('csv'))}</textarea>"
                f"<div class='wrap'><table><tr><th>Date</th><th>Narration</th><th class='r'>Amount</th><th>Match</th><th>Apply to invoice</th></tr>{rows}</table></div>"
                f"<p class='small'>Confident matches are preselected. Check the rest yourself; leave on skip anything you are unsure of.</p>"
                f"<p><button name='action' value='apply'>Record selected payments</button></p></form>")
    return layout("Bank", f"""<h1>Bank statement</h1>{_err(error)}<form method='post' action='/bank' class='card'>
<p class='small'>Paste or load your bank statement CSV. Only money received is used. Matching is by invoice number in the narration,
customer name and the invoice balance. Nothing is recorded until you confirm. Lines already recorded are never applied twice.</p>
<label>Statement CSV <input type='file' accept='.csv,.txt' id='pick'></label>
<textarea name='csv' id='csvbox' rows='7'>{e(f.get('csv')) if entries is None else ''}</textarea>
<p><button name='action' value='preview'>Find matches</button></p></form>{out}
<script>document.getElementById('pick').onchange=function(){{var f=this.files[0];if(!f)return;var r=new FileReader();
r.onload=function(){{document.getElementById('csvbox').value=r.result}};r.readAsText(f)}}</script>""")


def purchases_page(rows, f, categories):
    copts = "<option value=''>All categories</option>" + "".join(
        f"<option{' selected' if c == f.get('category') else ''}>{e(c)}</option>" for c in categories)
    zero = Decimal("0.00")
    tot = sum((r["total"] for r in rows), zero)
    itc = sum((r["cgst"] + r["sgst"] + r["igst"] for r in rows if r["vendor_gstin"]), zero)
    trs = "".join(f"<tr><td><a href='/purchases/{r['id']}/edit'>{e(r['bill_no'])}</a></td><td>{dmy(r['date'])}</td>"
                  f"<td>{e(r['vendor_name'])}<div class='small'>{e(r['vendor_gstin'])}</div></td><td>{e(r['category'])}</td>"
                  f"<td class='r'>{inr(r['taxable'])}</td><td class='r'>{inr(r['cgst'] + r['sgst'] + r['igst'])}</td>"
                  f"<td class='r'>{inr(r['total'])}</td></tr>" for r in rows) or "<tr><td colspan='7'>No purchase bills.</td></tr>"
    month = e(f.get("month"))
    return layout("Purchases", f"""<h1>Purchase bills</h1><form method='get' class='actions'>
<input type='month' name='month' value='{month}' style='max-width:180px'><select name='category' style='max-width:200px'>{copts}</select>
<button>Filter</button><a class='btn alt' href='/purchases'>Reset</a><a class='btn' href='/purchases/scan'>Scan a bill</a><a class='btn alt' href='/purchases/new'>+ Add bill</a>
<a class='btn alt' href='/exports/purchases.csv?month={month}'>Purchase CSV</a></form>
<p class='small'>{len(rows)} bills · total ₹{inr(tot)} · input tax on bills with a vendor GSTIN ₹{inr(itc)}</p>
<div class='wrap'><table><tr><th>Bill</th><th>Date</th><th>Vendor</th><th>Category</th><th class='r'>Taxable</th><th class='r'>Tax</th>
<th class='r'>Total</th></tr>{trs}</table></div>""")


def purchase_form_page(v, categories, error=None, pid=None, warnings=(), photo_token="", photo_url=""):
    cats = "".join(f"<option{' selected' if c == (v.get('category') or 'Goods for resale') else ''}>{e(c)}</option>" for c in categories)
    delete = (f"<form method='post' action='/purchases/{pid}/delete' onsubmit=\"return confirm('Delete this purchase bill?')\">"
              f"<button class='warn'>Delete</button></form>" if pid else "")
    action = f"/purchases/{pid}/edit" if pid else "/purchases/new"
    money = "".join(f"<div class='taxin'><label>{l}</label><input name='{n}' value='{e(v.get(n))}' inputmode='decimal'></div>"
                    for n, l in (("cgst", "CGST ₹"), ("sgst", "SGST ₹"), ("igst", "IGST ₹ (other-state vendor)")))
    rcm_on = str(v.get("rcm", "")) in ("1", "on", "True")
    rates = "".join(f"<option{' selected' if str(v.get('rcm_rate')) == r else ''}>{r}</option>" for r in ("5", "12", "18", "28"))
    warn = "".join(f"<div class='warnbox'>{e(w)}</div>" for w in warnings)
    if warnings:
        warn = "<p class='sub'>Please check these against the bill before saving:</p>" + warn
    photo_html = (f"<div class='card'><b>Bill photo</b> <span class='small'>(compare it with the details below)</span><br>"
                  f"<a href='{e(photo_url)}' target='_blank' rel='noopener'><img src='{e(photo_url)}' alt='Bill photo' "
                  f"style='max-width:100%;max-height:420px;margin-top:8px;border-radius:8px'></a></div>") if photo_url else ""
    token = f"<input type='hidden' name='photo_token' value='{e(photo_token)}'>" if photo_token else ""
    return layout("Purchase bill", f"""<h1>{'Edit' if pid else 'Add'} purchase bill</h1>{warn}{photo_html}<div class='card'>{_err(error)}
<form method='post' action='{action}'>{token}<div class='row'>
<div><label>Vendor name *</label><input name='vendor_name' value='{e(v.get('vendor_name'))}' required></div>
<div><label>Vendor GSTIN (needed to claim input credit)</label><input name='vendor_gstin' value='{e(v.get('vendor_gstin'))}' maxlength='15'></div>
<div><label>Vendor phone (for follow-up)</label><input name='vendor_phone' value='{e(v.get('vendor_phone'))}' inputmode='tel'></div>
<div><label>Bill number *</label><input name='bill_no' value='{e(v.get('bill_no'))}' required></div>
<div><label>Bill date *</label><input type='date' name='date' value='{e(v.get('date'))}' required></div>
<div><label>Category</label><select name='category'>{cats}</select></div>
<div><label>Taxable value ₹ *</label><input name='taxable' value='{e(v.get('taxable'))}' inputmode='decimal'></div>{money}</div>
<div class='card' style='margin:12px 0 0;padding:10px 14px'><label style='margin:0;display:flex;gap:8px;align-items:center'>
<input type='checkbox' name='rcm' id='rcm' style='width:auto'{' checked' if rcm_on else ''}> Reverse charge (the vendor charged no tax)</label>
<div id='rcmbox' class='row' style='display:none'><div><label>GST rate to self-assess</label><select name='rcm_rate'>{rates}</select></div>
<div><label style='margin-top:30px;display:flex;gap:8px;align-items:center'><input type='checkbox' name='rcm_inter' style='width:auto'{' checked' if v.get('rcm_inter') else ''}> Vendor is in another state (IGST)</label></div></div>
<p class='small' id='rcmnote' style='display:none;margin-bottom:0'>Used for purchases from unregistered vendors where the buyer pays the tax, such as transport (GTA) or legal services. The tax is worked out from the taxable value, you pay the vendor only the taxable value, and the tax is shown as a liability. Ask your CA which of your purchases qualify.</p></div>
<label>Note</label><input name='note' value='{e(v.get('note'))}'>
<p><button>Save</button> <a class='btn alt' href='/purchases'>Cancel</a></p></form>{delete}</div>
<script>(function(){{var c=document.getElementById('rcm');function t(){{document.getElementById('rcmbox').style.display=c.checked?'grid':'none';
document.getElementById('rcmnote').style.display=c.checked?'block':'none';
document.querySelectorAll('.taxin').forEach(function(x){{x.style.display=c.checked?'none':'block'}})}}c.onchange=t;t()}})();</script>""")


def _rc_row(kind, entry):
    b, p = entry["book"], entry["portal"]
    ref = b or p
    cell = lambda x, k: inr(x[k]) if x else "-"
    return (f"<tr><td>{e(kind)}</td><td>{e(ref['name'])}<div class='small'>{e(ref['gstin'])}</div></td>"
            f"<td>{e(b['inv_raw']) if b else '-'}<div class='small'>2B: {e(p['inv_raw']) if p else '-'}</div></td>"
            f"<td class='r'>{cell(b, 'taxable')}<div class='small'>2B: {cell(p, 'taxable')}</div></td>"
            f"<td class='r'>{cell(b, 'tax')}<div class='small'>2B: {cell(p, 'tax')}</div></td><td>{e(entry['note'])}</td></tr>")


def reconcile_page(f, error=None, result=None, followups=None, notes=()):
    out = ""
    if result:
        counts = "".join(f"<div class='card'><span>{l}</span><b>{len(result[k])}</b></div>" for l, k in (
            ("Matched", "matched"), ("Amount mismatch", "mismatched"), ("Probable match", "probable"),
            ("Missing in GSTR-2B", "books_only"), ("Missing in books", "portal_only")))
        rows = "".join(_rc_row(l, x) for l, k in (("Amount mismatch", "mismatched"), ("Probable match", "probable"),
                                                    ("Missing in GSTR-2B", "books_only"), ("Missing in books", "portal_only"))
                       for x in result[k])
        exc = (f"<h2>Exceptions - only what needs a look</h2><div class='wrap'><table><tr><th>Type</th><th>Supplier</th><th>Invoice</th>"
               f"<th class='r'>Taxable</th><th class='r'>Tax</th><th>Note</th></tr>{rows}</table></div>"
               if rows else "<div class='ok'>Everything matched. No exceptions.</div>")
        fu = ""
        if followups:
            fu = ("<h2>Supplier follow-up (input credit at risk)</h2><div class='wrap'><table><tr><th>Supplier</th><th>Invoices</th>"
                  "<th class='r'>ITC at risk</th><th></th></tr>" + "".join(
                      f"<tr><td>{e(g['name'])}<div class='small'>{e(g['gstin'])}</div></td><td>{e(', '.join(g['invoices']))}</td>"
                      f"<td class='r'>{inr(g['itc_at_risk'])}</td><td><a class='btn wa' target='_blank' rel='noopener' "
                      f"href='{e(g['link'])}'>WhatsApp</a></td></tr>" for g in followups) + "</table></div>")
        note = "".join(f"<div class='warnbox'>{e(n)}</div>" for n in notes)
        out = f"{note}<div class='cards'>{counts}</div>{exc}{fu}"
    return layout("Reconcile", f"""<h1>Reconcile purchases with GSTR-2B</h1>{_err(error)}
<form method='post' action='/reconcile' class='card'>
<p class='small'>Paste or load the GSTR-2B CSV from the GST portal. Your books come from the Purchases page for the month, or paste/load
your own purchase register CSV below. Columns are recognised by name (GSTIN, invoice number, invoice date, taxable value, central/state/integrated tax).</p>
<div class='row'><div><label>Month (books from Purchases page)</label><input type='month' name='month' value='{e(f.get('month'))}'></div>
<div><label>Amount tolerance ₹</label><input name='tol' value='{e(f.get('tol') or '1.00')}' inputmode='decimal'></div></div>
<label>GSTR-2B CSV * <input type='file' accept='.csv,.txt' data-target='portal' class='pick'></label>
<textarea name='portal' id='portal' rows='6' placeholder='GSTIN of supplier,Invoice number,Invoice date,Taxable Value,...'>{e(f.get('portal'))}</textarea>
<label>Your purchase register CSV (optional, replaces the Purchases page) <input type='file' accept='.csv,.txt' data-target='books' class='pick'></label>
<textarea name='books' id='books' rows='4'>{e(f.get('books'))}</textarea>
<p class='actions'><button name='action' value='run'>Reconcile</button><button name='action' value='xlsx' class='alt'>Download Excel workbook</button>
<button name='action' value='csv' class='alt'>Download exceptions CSV</button></p></form>
{out}<script>document.querySelectorAll('.pick').forEach(function(i){{i.onchange=function(){{var f=i.files[0];if(!f)return;
var r=new FileReader();r.onload=function(){{document.getElementById(i.dataset.target).value=r.result}};r.readAsText(f)}}}})</script>""")


def exports_page(today_month, liability=None, rcm=None):
    liab = ""
    if liability:
        liab = f"<h2>GST liability · {e(today_month)}</h2>{liability_table(*liability)}"
    if rcm and rcm[0]:
        liab += (f"<h2>Reverse charge on purchases · {e(today_month)}</h2>{liability_table(*rcm)}"
                 "<p class='small'>Tax you owe on purchases from unregistered vendors. A regular dealer can claim the same amount as input credit.</p>")
    return layout("Exports", f"""<h1>Exports</h1><div class='card'><h2>GST liability summary</h2>
<form method='get' action='/exports' class='actions'><input type='month' name='month' value='{e(today_month)}' style='max-width:180px'>
<button class='alt'>Show</button><a class='btn' href='/exports/gst-liability.csv?month={e(today_month)}'>Download CSV</a>
<a class='btn alt' href='/exports/gst-liability.xlsx?month={e(today_month)}'>Download Excel</a></form>{liab}
<p class='small'>Output tax on active invoices by GST rate, net of credit notes issued in the month. Cancelled invoices are excluded.</p></div>
<div class='card'><h2>Monthly sales register (for your CA)</h2>
<form method='get' action='/exports/sales.csv' class='actions'><input type='month' name='month' value='{e(today_month)}' style='max-width:180px'>
<button>Download CSV</button><button class='alt' formaction='/exports/sales.xlsx'>Download Excel</button></form>
<p class='small'>Cancelled invoices appear with zero amounts. Credit notes appear as negative rows; the last row is the net total.</p></div>
<div class='card'><h2>Client pack for the CA</h2><p>One zip for the month: sales and purchase registers, GST liability, invoices and payments.</p>
<a class='btn' href='/exports/pack.zip?month={e(today_month)}'>Download pack for {e(today_month)}</a></div>
<div class='card'><h2>Tally export</h2><p>Ledgers plus Sales, Purchase, Receipt, Credit Note and refund Payment vouchers for the month, as Tally XML.
Import the ledgers file first. <b>Try it on a test company in Tally first</b> and have your CA check it.</p>
<a class='btn alt' href='/exports/tally.zip?month={e(today_month)}'>Download Tally files for {e(today_month)}</a></div>
<div class='card'><h2>Other reports</h2><div class='actions'><a class='btn alt' href='/exports/purchases.csv?month={e(today_month)}'>Purchase register CSV</a>
<a class='btn alt' href='/exports/invoices.csv'>Invoice list CSV</a>
<a class='btn alt' href='/exports/payments.csv'>Payment register CSV</a></div></div>
<div class='card'><h2>Full backup</h2><p>All tables as CSV plus a database snapshot, in one zip file.</p>
<a class='btn' href='/exports/all.zip'>Download full backup</a>
<p class='small'>The app also copies its database into the <code>backups</code> folder once a day.</p></div>""")
