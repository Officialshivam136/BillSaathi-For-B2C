"""Quick entry: turn a short message like "Ramesh, 3 kg barfi at 450, 2 samosa at 20" into a DRAFT invoice.

Rule-based (no language model, no network). It only ever fills the invoice form; the owner reviews and saves.
"""
import difflib
import re

UNITS = ("kg", "kgs", "g", "gm", "gms", "gram", "grams", "pcs", "pc", "piece", "pieces", "nos", "no", "box", "boxes", "dozen",
         "doz", "ltr", "ltrs", "litre", "litres", "l", "plate", "plates", "packet", "packets", "pkt", "pkts", "unit", "units")
GRAMS = ("g", "gm", "gms", "gram", "grams")
FILLER = {"bill", "invoice", "for", "to", "make", "create", "new", "a", "an", "the", "sold", "sell", "of"}
NUM = r"\d+(?:\.\d+)?"
UNIT_RE = r"(?:" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")"
AT = r"(?:\b(?:at|rate|for|x)\b|\brs\.?|@|₹)"  # word boundaries: "dates" must not be read as "d" + "at" + "es"
MONEY = r"(?:rs\.?\s*|₹\s*)?"
# qty [unit] item AT rate    e.g. "3 kg barfi at 450"
P_QTY_FIRST = re.compile(rf"(?P<qty>{NUM})\s*(?P<unit>{UNIT_RE}\b)?\s*(?P<item>[^\d@₹%][^\d@₹%]*?)\s*{AT}\s*{MONEY}(?P<rate>{NUM})", re.I)
# item qty [unit] AT rate    e.g. "barfi 3kg at 450"
P_ITEM_FIRST = re.compile(rf"(?P<item>[^\d@₹%]+?)\s+(?P<qty>{NUM})\s*(?P<unit>{UNIT_RE}\b)?\s*{AT}\s*{MONEY}(?P<rate>{NUM})", re.I)
# qty [unit] item (rate comes from the saved item)
P_NO_RATE = re.compile(rf"(?P<qty>{NUM})\s*(?P<unit>{UNIT_RE}\b)?\s*(?P<item>[^\d@₹%]+)$", re.I)
GST_RE = re.compile(r"(?:gst\s*)?(\d{1,2})\s*%|gst\s*(\d{1,2})", re.I)


def _clean_name(s):
    words = [w for w in re.split(r"\s+", s.strip(" :-,;")) if w]
    while words and words[0].lower() in FILLER:
        words.pop(0)
    return " ".join(words)


def _real_item(raw):
    """An item name must contain letters and not be just a unit or a filler word ('kg', 'at', 'for' ...)."""
    name = _clean_name(raw).lower()
    return len(name) >= 2 and any(ch.isalpha() for ch in name) and name not in UNITS and name not in ("at", "rate", "rs", "x")


def _match(name, choices, cutoff=0.6):
    """Best fuzzy match of name among choices (dict lower-name -> value), or None."""
    name = name.lower().strip()
    if not name:
        return None
    if name in choices:
        return choices[name]
    hit = difflib.get_close_matches(name, list(choices), n=1, cutoff=cutoff)
    if hit:
        return choices[hit[0]]
    for key, val in choices.items():  # a single word of the typed name matches a word of a saved name
        if name in key.split() or key in name.split():
            return val
    return None


def _num(s):
    from decimal import Decimal

    return Decimal(s)


def parse(text, customers, catalog):
    """customers: rows with id,name; catalog: rows with description,hsn,rate,gst_rate.
    Returns {'customer_id', 'customer_text', 'items': [...], 'warnings': [...]}."""
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text or "")  # 1,200 -> 1200
    segments = [s.strip() for s in re.split(r"[\n;,]+|\band\b", text, flags=re.I) if s.strip()]
    cust_by_name = {c["name"].lower(): c["id"] for c in customers}
    cat = {c["description"].lower(): c for c in catalog}
    result = {"customer_id": None, "customer_text": "", "items": [], "warnings": []}
    customer_text = ""
    for n, seg in enumerate(segments):
        gst = None
        g = GST_RE.search(seg)
        if g:
            gst = g.group(1) or g.group(2)
            seg = (seg[:g.start()] + " " + seg[g.end():]).strip()
        m = next((x for pat in (P_QTY_FIRST, P_ITEM_FIRST) for x in pat.finditer(seg) if _real_item(x.group("item"))), None)
        rate_from_catalog = False
        if not m:
            m = P_NO_RATE.search(seg)
            rate_from_catalog = bool(m and _real_item(m.group("item")))
            m = m if rate_from_catalog else None
        if not m:
            if not re.search(r"\d", seg) and not customer_text:
                customer_text = _clean_name(seg)  # a segment with no numbers is the customer
            else:
                result["warnings"].append(f"Could not read: \"{seg}\"")
            continue
        if n == 0 or not customer_text:
            before = _clean_name(seg[:m.start()])
            if before and not customer_text:
                customer_text = before
        item_name = _clean_name(m.group("item"))
        if not item_name:
            result["warnings"].append(f"No item name in: \"{seg}\"")
            continue
        qty = _num(m.group("qty"))
        unit = (m.group("unit") or "").lower()
        if unit in GRAMS:
            qty = qty / 1000
            result["warnings"].append(f"{m.group('qty')} {unit} of {item_name} read as {qty.normalize():f} kg (rate taken per kg)")
        saved = _match(item_name, cat)
        if rate_from_catalog:
            if not saved:
                result["warnings"].append(f"No price given for \"{item_name}\" and it is not in your saved items")
                continue
            rate = saved["rate"]
        else:
            rate = _num(m.group("rate"))
        gst_rate = gst or (format(saved["gst_rate"].normalize(), "f") if saved else "5")
        if gst_rate not in ("0", "5", "12", "18", "28"):
            result["warnings"].append(f"GST {gst_rate}% is not a valid rate; used 5%")
            gst_rate = "5"
        if not saved and not gst:
            result["warnings"].append(f"\"{item_name}\" is not in your saved items: GST assumed 5%, please check")
        result["items"].append({"description": saved["description"] if saved else item_name.title(),
                                "hsn": (saved["hsn"] or "") if saved else "", "qty": format(qty.normalize(), "f"),
                                "rate": str(rate), "gst_rate": gst_rate})
    result["customer_text"] = customer_text
    if customer_text:
        cid = _match(customer_text, cust_by_name)
        if cid:
            result["customer_id"] = cid
        else:
            result["warnings"].append(f"No customer matches \"{customer_text}\": choose one or add a new customer")
    else:
        result["warnings"].append("No customer name found: choose one")
    if not result["items"]:
        result["warnings"].append("No items found. Try: Ramesh, 3 kg barfi at 450, 2 samosa at 20")
    return result
