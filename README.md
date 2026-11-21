# BillSaathi

GST billing for small shops. Pure Python 3.10+ standard library, SQLite, runs on your own computer. No internet needed.

## Run it

Double-click the **BillSaathi** shortcut on your Desktop (or `BillSaathi.bat`). A small control window opens and so does your browser at http://localhost:8000. Closing the control window stops BillSaathi.

Other ways: `python gui.py` (control window), `python app.py [port]` (server only). Tests: `python -m unittest` (about 150 tests, around 25 seconds).

First run: set the owner passcode, then fill in the business profile (name, GSTIN, state, UPI ID). Data is in `billsaathi.db`.

## What it does

- **Billing:** customers, saved items, GST invoices (CGST+SGST or IGST by state), numbering per financial year, A4 print with amount in words and a UPI QR for the amount still due, quick text entry, duplicate an invoice, items from a customer's last invoice, edit an invoice until money is recorded against it.
- **Stock tracking (Items, Stock):** turn on "Track stock" for the items you want to count and set a reorder level. Invoices reduce stock by themselves (matched by item name), cancels and edits put it back, and credit notes can return goods to the shelf. Record deliveries with Receive and physical counts with Set count; every movement stays in the item's history. Selling more than you hold warns you but is allowed. The dashboard flags low and out-of-stock items.
- **Recurring invoices (Recurring):** press "Repeat this invoice" on any invoice and choose weekly, monthly, quarterly or yearly. BillSaathi never creates one by itself: when one is due it asks you to confirm (the dashboard shows a banner). If the app was not opened for a few periods, only the latest is created and the missed ones are reported, not billed back. Items and prices are copied from the invoice when you set it up.
- **Special cases:** composition scheme (Bill of Supply, no tax), exports under LUT or with IGST, reverse charge on purchases from unregistered vendors.
- **Money in:** payments, part payments, overpayment blocked, bank statement matching with confirmation, WhatsApp reminders (logged, so the dashboard shows how many payments followed one), customer statements with running balance.
- **Corrections:** cancel with a reason (number kept), credit notes with their own numbering, refunds.
- **Purchases and CA:** purchase bills, GSTR-2B reconciliation, supplier follow-up, sales/purchase registers and GST summary as CSV or Excel, a one-zip pack for your CA, Tally XML export.
- **People and safety:** owner passcode (changeable on the Account page), staff logins with limited access, login attempt limit, an audit log of who changed what.
- **Backups:** automatic daily copy kept for 60 days, "Back up now", a second backup folder (a USB drive or a OneDrive/Dropbox folder), and one-click restore. Restoring saves a "before restore" copy first, so it can be undone.
- **Language:** English or Hindi menus and screens (toggle in the sidebar). Printed invoices and credit notes stay in English.
- **Scan a supplier bill (Purchases > Scan a bill):** take or pick a photo, BillSaathi reads it and fills the purchase form for you to check and save. The photo is kept with the bill. Offline reading uses Windows' built-in text recognition (nothing leaves the computer, needs Windows 10/11). It corrects look-alike characters in GSTINs using their check digit and warns when amounts do not add up. Optional AI reading is available too.
- **AI and voice entry (optional, Integrations page):** add your own Anthropic API key to get "Fill with AI" on quick entry (Hindi, Hinglish, English) and an AI option for bill scanning. A microphone button on quick entry uses your browser's speech service. Nothing is sent unless you press an AI button; names (not phone numbers, GSTINs or amounts owed) are sent for invoice drafts, the photo for bill reading.
- **Payment links (optional, Integrations page):** with your own Razorpay account keys, create a payment link for an invoice. After the customer pays, press "Check payment" and it is recorded once. Start with Razorpay's test keys.

## Things to know

- Not for the public internet: no HTTPS. Keep it on the shop computer.
- The full-backup zip and the backup copies contain the whole database, including hashed passcodes. Keep them private. If the second folder is in OneDrive or Dropbox, your business data is stored in that account.
- Quick text entry is rule-based, not an AI model: it fills the form and lists what it guessed. Always check the form.
- The Tally export, the GSTR-2B reader and the bank statement matcher were tested on sample data, not real files. Try them on a Tally test company and a real statement first.
- Hindi covers menus, buttons, labels and headings. Sentences that contain numbers or names, and some long help texts, stay in English.
- API keys (Anthropic, Razorpay) are stored in the BillSaathi database, so backups and the full-export zip contain them. The bill photos are stored in the `bill_photos` folder and are copied to the second backup folder too.
- The AI features and payment links were built to the providers' documentation and tested against stand-in servers, not against the real services. Try each once with test data (a Razorpay test key, a small Anthropic budget) before relying on it.
- Bill scanning is a helper, not a guarantee: always compare the filled-in form with the photo. Printed bills in good light read well; handwritten, crumpled or blurred bills do not.
- Not covered: e-invoicing and e-way bills (only needed above a high turnover, and they need government portal credentials), and a hosted multi-shop version (needs servers, HTTPS and security work that does not exist yet). Have your CA review the GST logic before relying on it.

## Files

`app.py` server and routes, `db.py` schema and logic, `templates.py` pages, `i18n.py` Hindi, `gst.py` tax rules, `exports.py`, `xlsx.py`, `tally.py`, `reconcile.py`, `bank.py`, `backups.py`, `quick.py`, `qr.py`, `words.py`, `gui.py` launcher.
