"""Hindi interface. Translates the visible text of a finished HTML page using a phrase table.

- Only text between tags and the placeholder / title / aria-label attributes are translated.
- <script>, <style> and anything between <!--noxl--> and <!--/noxl--> are left alone. The printed invoice and credit note are
  marked noxl: they are legal documents and stay in English.
- Text that is not in the table (customer names, amounts, long sentences with numbers in them) stays as it is, so the page
  is never broken, only partly in English.
"""
import re

HI = {
    # navigation
    "Dashboard": "डैशबोर्ड", "New invoice": "नया बिल", "Invoices": "बिल", "Credit notes": "क्रेडिट नोट", "Customers": "ग्राहक",
    "Items": "सामान", "Purchases": "खरीद", "Bank": "बैंक", "Reconcile": "मिलान", "Exports": "एक्सपोर्ट", "Staff": "स्टाफ",
    "Profile": "प्रोफ़ाइल", "Logout": "लॉग आउट", "Backups": "बैकअप", "Account": "खाता सेटिंग", "Audit log": "गतिविधि लॉग",
    # sign in / setup
    "Sign in": "साइन इन", "Welcome": "स्वागत है", "Open": "खोलें", "Passcode": "पासकोड", "Save passcode": "पासकोड सेव करें",
    "User (leave blank for owner)": "यूज़र (मालिक के लिए खाली छोड़ें)", "Repeat passcode": "पासकोड दोबारा लिखें",
    "New passcode (4+ characters)": "नया पासकोड (कम से कम 4 अक्षर)",
    "Set an owner passcode. You will need it every time you open the app.": "मालिक का पासकोड बनाएँ। ऐप खोलने पर हर बार यह चाहिए होगा।",
    # dashboard
    "Invoiced this month": "इस महीने का बिल", "billed to customers": "ग्राहकों को बिल किया", "Collected this month": "इस महीने की वसूली",
    "payments received": "मिले हुए भुगतान", "Outstanding": "बाकी रकम", "yet to be received": "अभी मिलना बाकी", "Overdue": "देर से",
    "Last 6 months": "पिछले 6 महीने", "Invoiced": "बिल किया", "Collected": "वसूला", "Who owes you": "किसका कितना बाकी है",
    "Not yet due": "अभी देय नहीं", "1-15 days late": "1-15 दिन देर", "16-30 days late": "16-30 दिन देर",
    "31-60 days late": "31-60 दिन देर", "Over 60 days": "60 दिन से ज़्यादा", "Needs attention": "ध्यान दें",
    "Remind": "याद दिलाएँ", "Recent invoices": "हाल के बिल", "+ New invoice": "+ नया बिल", "Reminders": "रिमाइंडर",
    "Nothing is overdue. Nice work.": "कुछ भी बकाया नहीं है। बहुत बढ़िया!", "overdue": "देर से",
    # statuses and table headers
    "Paid": "चुकाया", "Unpaid": "बाकी", "Partly paid": "आंशिक भुगतान", "Cancelled": "रद्द", "Credited": "क्रेडिट हुआ",
    "Refund due": "रिफंड देना है", "Number": "नंबर", "Date": "तारीख", "Customer": "ग्राहक", "Total": "कुल", "Status": "स्थिति",
    "Name": "नाम", "Phone": "फ़ोन", "State": "राज्य", "GSTIN": "GSTIN", "Amount": "रकम", "Mode": "तरीका", "Note": "टिप्पणी",
    "By": "किसने", "Reason": "कारण", "Invoice": "बिल", "Description": "विवरण", "HSN": "HSN", "Qty": "मात्रा", "Rate": "दर",
    "Rate ₹": "दर ₹", "GST %": "GST %", "Taxable": "कर योग्य", "Taxable value": "कर योग्य मूल्य", "Total tax": "कुल कर",
    "Item": "सामान", "Vendor": "विक्रेता", "Category": "श्रेणी", "Bill": "बिल", "Tax": "कर", "Type": "प्रकार", "Narration": "विवरण",
    "Match": "मिलान", "Debit": "डेबिट", "Credit": "क्रेडिट", "Balance": "बैलेंस", "Actions": "कार्रवाई", "Action": "कार्रवाई",
    # buttons / common
    "Save": "सेव करें", "Cancel": "रद्द करें", "Edit": "बदलें", "Delete": "हटाएँ", "Search": "खोजें", "Filter": "छाँटें",
    "Reset": "रीसेट", "Show": "दिखाएँ", "Download": "डाउनलोड", "Download CSV": "CSV डाउनलोड करें",
    "Download Excel": "Excel डाउनलोड करें", "Print / Save PDF": "प्रिंट / PDF सेव करें", "Back to invoice": "बिल पर वापस",
    "Yes": "हाँ", "No": "नहीं", "None": "कोई नहीं", "Disable": "बंद करें", "Enable": "चालू करें", "Active": "चालू",
    "Disabled": "बंद", "Add": "जोड़ें", "Remove line": "लाइन हटाएँ", "Select customer…": "ग्राहक चुनें…", "-- select --": "-- चुनें --",
    "-- skip --": "-- छोड़ें --", "All": "सभी", "All customers": "सभी ग्राहक", "All categories": "सभी श्रेणियाँ",
    # invoice form
    "Customer *": "ग्राहक *", "Date *": "तारीख *", "Items (up to 10)": "सामान (अधिकतम 10)", "Summary": "सारांश",
    "+ Add line": "+ लाइन जोड़ें", "+ New customer": "+ नया ग्राहक", "Save invoice": "बिल सेव करें", "Save customer": "ग्राहक सेव करें",
    "New customer": "नया ग्राहक", "Fill form": "फ़ॉर्म भरें", "Supply type": "सप्लाई का प्रकार", "Regular sale": "सामान्य बिक्री",
    "Export under LUT (no tax)": "LUT के तहत एक्सपोर्ट (बिना कर)", "Export with IGST": "IGST के साथ एक्सपोर्ट",
    "Tab between fields · Enter on Rate adds a line": "फ़ील्ड बदलने के लिए Tab · दर पर Enter दबाने से नई लाइन जुड़ेगी",
    "Quick entry: type it like a message, then check the form below": "तेज़ एंट्री: संदेश की तरह लिखें, फिर नीचे का फ़ॉर्म जाँच लें",
    "Use items from this customer's last invoice": "इस ग्राहक के पिछले बिल का सामान लगाएँ",
    "Name *": "नाम *", "Phone": "फ़ोन", "State (decides CGST+SGST or IGST)": "राज्य (इसी से CGST+SGST या IGST तय होता है)",
    # invoice page
    "WhatsApp reminder": "व्हाट्सऐप रिमाइंडर", "Record payment": "भुगतान दर्ज करें", "Save payment": "भुगतान सेव करें",
    "Payments": "भुगतान", "Cash": "नकद", "UPI": "UPI", "Other": "अन्य", "Issue credit note": "क्रेडिट नोट जारी करें",
    "Record refund": "रिफंड दर्ज करें", "Save refund": "रिफंड सेव करें", "Cancel invoice": "बिल रद्द करें",
    "Reason for cancelling": "रद्द करने का कारण", "Edit invoice": "बिल सुधारें", "Duplicate": "इसी जैसा नया बिल",
    "Credit qty": "क्रेडिट मात्रा", "Sold": "बिका", "Left to credit": "क्रेडिट बाकी", "Credit notes": "क्रेडिट नोट",
    "Created by": "बनाने वाला", "Pay by UPI": "UPI से भुगतान", "Open UPI app": "UPI ऐप खोलें",
    # customers / lists
    "+ Add customer": "+ ग्राहक जोड़ें", "Add customer": "ग्राहक जोड़ें", "Edit customer": "ग्राहक बदलें", "Statement": "खाता विवरण",
    "Search name or phone": "नाम या फ़ोन से खोजें", "Invoice no. or customer": "बिल नंबर या ग्राहक", "Customer statement": "ग्राहक खाता विवरण",
    "Unpaid": "बाकी", "Partly paid": "आंशिक भुगतान", "Overdue": "देर से",
    "No customers yet. Add your first customer to start billing.": "अभी कोई ग्राहक नहीं है। बिल बनाने के लिए पहला ग्राहक जोड़ें।",
    "No invoices.": "कोई बिल नहीं।", "No credit notes yet.": "अभी कोई क्रेडिट नोट नहीं।",
    # profile
    "Business profile": "व्यापार की जानकारी", "Business name *": "व्यापार का नाम *", "State *": "राज्य *", "UPI ID": "UPI आईडी",
    "Invoice prefix": "बिल का प्रीफ़िक्स", "Financial year starts in": "वित्त वर्ष शुरू होता है", "Payment due after (days)": "भुगतान की अवधि (दिन)",
    "Address": "पता", "Save profile": "प्रोफ़ाइल सेव करें", "GST scheme": "GST योजना", "Regular": "सामान्य (Regular)",
    "Composition scheme": "कंपोज़िशन योजना", "GSTIN (leave blank if not registered)": "GSTIN (रजिस्टर्ड न हों तो खाली छोड़ें)",
    # exports
    "GST liability summary": "GST देनदारी सारांश", "Monthly sales register (for your CA)": "मासिक बिक्री रजिस्टर (आपके CA के लिए)",
    "Client pack for the CA": "CA के लिए पूरा पैक", "Tally export": "Tally एक्सपोर्ट", "Other reports": "अन्य रिपोर्ट",
    "Full backup": "पूरा बैकअप", "Download full backup": "पूरा बैकअप डाउनलोड करें", "Purchase register CSV": "खरीद रजिस्टर CSV",
    "Invoice list CSV": "बिलों की सूची CSV", "Payment register CSV": "भुगतान रजिस्टर CSV",
    # purchases
    "Purchase bills": "खरीद के बिल", "+ Add bill": "+ बिल जोड़ें", "Add purchase bill": "खरीद का बिल जोड़ें",
    "Edit purchase bill": "खरीद का बिल बदलें", "Vendor name *": "विक्रेता का नाम *", "Bill number *": "बिल नंबर *",
    "Bill date *": "बिल की तारीख *", "Taxable value ₹ *": "कर योग्य मूल्य ₹ *", "Purchase CSV": "खरीद CSV",
    "Reverse charge (the vendor charged no tax)": "रिवर्स चार्ज (विक्रेता ने कर नहीं लगाया)",
    # bank / reconcile
    "Bank statement": "बैंक स्टेटमेंट", "Find matches": "मिलान खोजें", "Record selected payments": "चुने हुए भुगतान दर्ज करें",
    "Apply to invoice": "किस बिल में लगाएँ", "Confident": "पक्का", "Check this": "जाँच लें", "Unclear - pick one": "साफ़ नहीं - एक चुनें",
    "No match": "कोई मेल नहीं", "Already applied": "पहले ही दर्ज", "Reconcile purchases with GSTR-2B": "खरीद का GSTR-2B से मिलान",
    "Reconcile": "मिलान करें", "Download Excel workbook": "Excel वर्कबुक डाउनलोड करें", "Download exceptions CSV": "अपवाद CSV डाउनलोड करें",
    "Supplier follow-up (input credit at risk)": "सप्लायर से पूछताछ (इनपुट क्रेडिट खतरे में)", "Matched": "मिला हुआ",
    # items / staff
    "Saved items": "सेव किया सामान", "+ Add item": "+ सामान जोड़ें", "Add item": "सामान जोड़ें", "Edit item": "सामान बदलें",
    "Add staff": "स्टाफ जोड़ें", "Reset passcode": "पासकोड रीसेट", "Not allowed": "अनुमति नहीं है",
    # backups / account / audit
    "Back up now": "अभी बैकअप लें", "Restore": "वापस लाएँ", "Restore this backup": "यह बैकअप वापस लाएँ", "Where": "कहाँ",
    "Second backup folder": "दूसरा बैकअप फ़ोल्डर", "Save folder": "फ़ोल्डर सेव करें", "Copy now": "अभी कॉपी करें",
    "Change passcode": "पासकोड बदलें", "Current passcode": "मौजूदा पासकोड", "New passcode": "नया पासकोड",
    "Daily": "रोज़ाना", "Manual": "हाथ से", "Before restore": "वापसी से पहले का", "Size": "साइज़", "File": "फ़ाइल",
    "Who": "किसने", "When": "कब", "What": "क्या", "Details": "विवरण",
    # statement
    "Opening balance": "शुरुआती बैलेंस", "Closing balance": "अंतिम बैलेंस", "From": "से", "To": "तक", "Refund": "रिफंड",
    "Payment": "भुगतान", "They owe you": "ग्राहक पर बाकी", "You owe them": "ग्राहक का आपके पास जमा",
}
HI.update({
    "Owner ·": "मालिक ·", "Owner": "मालिक",
    "No reminders sent yet. Use Remind on an overdue invoice and BillSaathi will track what it brings in.":
        "अभी तक कोई रिमाइंडर नहीं भेजा। देर से चल रहे बिल पर 'याद दिलाएँ' दबाएँ, BillSaathi देखेगा कि उससे कितना पैसा आया।",
    "A copy is saved automatically once a day and kept for 60 days.": "रोज़ एक कॉपी अपने आप सेव होती है और 60 दिन रखी जाती है।",
    "Back up now": "अभी बैकअप लें", "Copy now": "अभी कॉपी करें", "Available backups": "उपलब्ध बैकअप",
    "Audit log": "गतिविधि लॉग", "Nothing recorded yet.": "अभी कुछ दर्ज नहीं है।", "Opening balance": "शुरुआती बैलेंस",
    "Closing balance": "अंतिम बैलेंस", "Print / Save PDF": "प्रिंट / PDF सेव करें", "WhatsApp the balance": "व्हाट्सऐप पर बैलेंस भेजें",
    "Back": "वापस", "Details": "विवरण", "Type": "प्रकार", "Credit note": "क्रेडिट नोट",
    "Quick entry": "तेज़ एंट्री", "Invoice number": "बिल नंबर", "Bill number": "बिल नंबर",
})
HI.update({
    "Integrations": "इंटीग्रेशन", "Scan a bill": "बिल स्कैन करें", "Scan a purchase bill": "खरीद का बिल स्कैन करें",
    "Read the bill": "बिल पढ़ें", "Enter by hand instead": "हाथ से भरें", "Reading method": "पढ़ने का तरीका",
    "Fill with AI": "AI से भरें", "Bill photo": "बिल की फ़ोटो", "Payment link": "पेमेंट लिंक",
    "Check payment": "पेमेंट जाँचें", "Link": "लिंक", "Created": "बनाया गया",
    "Bill scanning (offline)": "बिल स्कैनिंग (ऑफ़लाइन)", "AI (Claude)": "AI (Claude)", "Model": "मॉडल",
    "Payment links (Razorpay)": "पेमेंट लिंक (Razorpay)", "Key id": "की आईडी", "Remove the saved key": "सेव की हुई की हटाएँ",
    "Remove the saved keys": "सेव की हुई की हटाएँ", "Save and test AI": "सेव करें और AI जाँचें", "Save and test": "सेव करें और जाँचें",
    "Please check these against the bill before saving:": "सेव करने से पहले इन्हें बिल से मिलाकर जाँच लें:",
    "🎤 Speak": "🎤 बोलें",
})
HI.update({
    "Stock": "स्टॉक", "Recurring": "बार-बार वाले बिल", "Receive": "माल आया", "Set count": "गिनती दर्ज करें",
    "In stock": "स्टॉक में", "Reorder at": "दोबारा मँगाएँ", "Low": "कम", "OK": "ठीक", "Out": "ख़त्म", "Below zero": "शून्य से नीचे",
    "Due": "देय", "Scheduled": "निर्धारित", "Pause": "रोकें", "Resume": "चालू करें", "Repeat this invoice": "इस बिल को दोहराएँ",
    "Recurring invoices": "बार-बार वाले बिल", "Due recurring invoices": "देय बार-बार वाले बिल", "Save schedule": "शेड्यूल सेव करें",
    "Create the selected invoices": "चुने हुए बिल बनाएँ", "Review and create": "देखें और बनाएँ", "See stock": "स्टॉक देखें",
    "Needs attention": "ध्यान दें", "Goods received": "आया हुआ माल", "Physical count": "गिनती", "Track stock for this item": "इस सामान का स्टॉक गिनें",
    "How often": "कितनी बार", "Every week": "हर हफ़्ते", "Every month": "हर महीने", "Every 3 months": "हर 3 महीने", "Every year": "हर साल",
    "Stock history": "स्टॉक का इतिहास", "Back to stock": "स्टॉक पर वापस", "Opening": "शुरुआती", "Received": "आया", "Sold": "बिका",
    "Returned": "वापस आया", "Count adjustment": "गिनती सुधार", "Invoice edited": "बिल सुधारा गया", "Invoice cancelled": "बिल रद्द हुआ",
})
_MONTHS = {"January": "जनवरी", "February": "फ़रवरी", "March": "मार्च", "April": "अप्रैल", "May": "मई", "June": "जून", "July": "जुलाई",
           "August": "अगस्त", "September": "सितंबर", "October": "अक्टूबर", "November": "नवंबर", "December": "दिसंबर"}
# text that mixes words and numbers: pattern -> replacement
_RULES = (
    (re.compile(r"^(\d+) invoice\(s\) past due$"), r"\1 बिल देर से"),
    (re.compile(r"^(\d+) inv\.$"), r"\1 बिल"),
    (re.compile(r"^(\d+) shown$"), r"\1 दिख रहे"),
    (re.compile(r"^billed (₹[\d,.]+)$"), r"बिल किया \1"),
    (re.compile(r"^outstanding (₹[\d,.]+)$"), r"बाकी \1"),
    (re.compile(r"^(\d+) in your list$"), r"आपकी सूची में \1"),
    (re.compile(r"^(\d+) issued$"), r"\1 जारी"),
    (re.compile(r"^net of (₹[\d,.]+) credit notes$"), r"\1 के क्रेडिट नोट घटाकर"),
    (re.compile(r"^Customer statement$"), "ग्राहक खाता विवरण"),
    (re.compile(r"^They owe you (₹[\d,.]+)$"), r"ग्राहक पर बाकी \1"),
    (re.compile(r"^You owe them (₹[\d,.]+)$"), r"ग्राहक का आपके पास जमा \1"),
    (re.compile(r"^Settled: nothing owed$"), "हिसाब बराबर: कुछ बाकी नहीं"),
    (re.compile(r"^(\d+) of (\d+)$"), r"\2 में से \1"),
    (re.compile(r"^The newest (\d+) entries\.$"), r"सबसे नए \1 रिकॉर्ड।"),
)
_MONTH_YEAR = re.compile(r"^(" + "|".join(_MONTHS) + r") (\d{4})$")
# phrases that read better with the number kept in place are handled by splitting on " · "
_SKIP = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>|<!--noxl-->.*?<!--/noxl-->)", re.S | re.I)
_TEXT = re.compile(r">([^<>]+)<")
_ATTR = re.compile(r"\b(placeholder|title|aria-label)='([^']*)'")


def _one(core):
    """A whole phrase: table first, then the number patterns, then month names. Unknown text comes back unchanged."""
    if core in HI:
        return HI[core]
    for pat, rep in _RULES:
        if pat.match(core):
            return pat.sub(rep, core)
    m = _MONTH_YEAR.match(core)
    if m:
        return f"{_MONTHS[m.group(1)]} {m.group(2)}"
    return core


def _word(s):
    core = s.strip()
    whole = _one(core)
    if whole != core:
        return whole
    if " · " in core:
        parts = core.split(" · ")
        done = [_one(p.strip()) for p in parts]
        return " · ".join(done) if done != parts else core
    if core.endswith(" - BillSaathi") and core[: -len(" - BillSaathi")] in HI:
        return HI[core[: -len(" - BillSaathi")]] + " - BillSaathi"
    return core


def _text(m):
    raw = m.group(1)
    lead = raw[: len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    return ">" + lead + _word(raw) + trail + "<"


def _chunk(html):
    html = _TEXT.sub(_text, html)
    return _ATTR.sub(lambda m: f"{m.group(1)}='{_word(m.group(2))}'", html)


def translate(html, lang):
    if lang != "hi" or not html:
        return html
    parts = _SKIP.split(html)
    for i in range(0, len(parts), 2):  # even indexes are ordinary markup; odd ones are the protected blocks
        parts[i] = _chunk(parts[i])
    return "".join(parts).replace("<html lang='en'>", "<html lang='hi'>", 1)
