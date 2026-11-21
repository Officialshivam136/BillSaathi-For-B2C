# BillSaathi (working name): Full Build Plan

This document is the single source of truth for building the MVP. It is written so it can be handed to Claude Code as-is. Nothing in here has been built beyond Phase 0.

---

## 0. Status

| Item | State |
|---|---|
| `gst.py` (GST calculation, GSTIN check, interstate detection) | Written |
| `test_gst.py` (10 unit tests) | Written, all passing |
| `app.py` (web server, routes, templates) | Not started |
| `db.py` (schema and queries) | Not started |
| Pilot shops identified | Not yet |

---

## 1. Problem statement

Micro and small businesses waste significant administrative time creating, tracking, and reconciling invoices manually. Enterprise ERP systems are prohibitively expensive, overly complex for simple needs, and need training that small teams cannot afford.

Target segments (in order of priority):

1. Single-owner retail and food shops (sweet shops, kirana, bakeries) registered under GST or about to register.
2. Service businesses (repair shops, tailors, salons, freelancers) that bill per job.
3. CA firms that receive monthly data from these clients (secondary user, handled in later phases).

Pilot town: Bijnor, Uttar Pradesh (first 5 shops).

---

## 2. What the problem breaks down into

| # | Pain point | Who feels it | Real cost |
|---|---|---|---|
| P1 | Invoice creation is repetitive. Customer details, item prices, and tax splits are retyped every time. | Owner | About 3 minutes per invoice; errors in tax split |
| P2 | Nobody knows who owes money at a glance. | Owner | Cash flow surprises |
| P3 | Payments (cash, UPI, bank) are matched to invoices by hand. | Owner | Hours at month end |
| P4 | Chasing money is awkward, so it gets postponed. | Owner | Slower collections |
| P5 | Purchase bills are not recorded, so GST data is incomplete. | Owner, CA | Lost input tax credit |
| P6 | Month-end handoff to the CA is messy. | Owner, CA | 2 to 3 hours of cleanup per client per month |
| P7 | Supplier GST filing gaps make input tax credit at risk. | Owner | ITC denied or delayed |

---

## 3. Solution options considered

These were evaluated from cheapest to most ambitious. The MVP uses options A to D; the rest are later phases.

| Option | Description | Phase |
|---|---|---|
| A. Process fixes | One invoice series, collect GSTIN once, daily billing slot, clear payment rules | Phase 1 (guidance, not code) |
| B. Billing app | Fast invoice entry with saved customers and items, automatic GST split, printable invoice with UPI QR | Phase 1 |
| C. WhatsApp or voice entry | Owner messages "Ramesh, 3 kg barfi at 450", a model converts it to an invoice, bot replies with PDF and QR | Phase 4 |
| D. Payment tracking and reminders | Mark payments; reminders via prefilled WhatsApp links | Phase 1 (manual marking), Phase 2 (statement matching) |
| E. Photo-to-ledger | Photograph supplier bills, OCR extracts vendor, GSTIN, amounts, tax; files under categories | Phase 3 |
| F. CA handoff export | Monthly sales and purchase register, GST liability summary, unmatched items, shared as Excel or link | Phase 1 (CSV), Phase 3 (full pack) |
| G. CA reconciliation tool | Match client purchase register against GSTR-2B; output only exceptions | Phase 3 |

---

## 4. Reference: how CA firms and GST tools work today

Inferred from public material (ClearTax, ICAI AI use-case submissions by CAs, GST practice). Used to shape the later phases, not to copy.

Typical monthly pipeline:

1. **Intake.** Clients send sales and purchase data by bulk import, email, or WhatsApp.
2. **Document AI.** Invoice PDFs and images are converted into structured rows.
3. **Validation and classification.** GSTIN checks; HSN or SAC suggestions.
4. **Reconciliation.** Purchase register against GSTR-2B using fuzzy matching on invoice number, date, GSTIN, and amount. Everything unmatched goes to an exceptions queue.
5. **ITC decision.** Matched records become claimable input tax credit.
6. **Supplier follow-up.** If a supplier has not filed GSTR-1, flag their invoices, quantify at-risk ITC, and trigger a reminder to the supplier.
7. **Filing.** GSTR-1, GSTR-3B, e-invoicing via IRP, e-way bills. Out of scope for BillSaathi.
8. **Review and sign-off.** The CA reviews the exceptions queue and signs off.

Design lessons carried into the plan:

- The exceptions queue is the product. The user should only look at what did not match.
- Supplier follow-up is a high-value feature because it protects the owner's input tax credit.
- ICAI submissions report manual reconciliation at 2 to 3 hours per client per month, and automated runs taking under 2 minutes. These are self-reported and should be measured in the pilot, not assumed.
- Some CA firms want zero-subscription, Excel-compatible tools. Excel export is a must-have from the start.

---

## 5. MVP scope (Phase 1)

Goal: one shop owner can create GST-correct invoices, track payments, send reminders, and export a monthly summary for their CA, in under 1 minute per invoice.

### In scope
- Business profile
- Customer list
- Invoice creation with automatic numbering and GST split
- Printable invoice with UPI ID and QR
- Payments (full or partial) and outstanding balance
- Dashboard
- WhatsApp reminder links
- Monthly CSV export for the CA

### Out of scope
- Payroll
- Inventory costing or stock deduction
- Multi-user roles and logins beyond a single owner passcode
- Bank feed or UPI API integration
- GSTR filing, e-invoicing, e-way bills
- Composition scheme, reverse charge, exports (LUT), credit notes (may be added in Phase 2)
- Offline mode
- Native mobile app (the web app must be mobile-responsive)
- Paid WhatsApp Business API

---

## 6. Features and acceptance criteria (Phase 1)

### F1. Business profile
- Fields: business name, address, GSTIN, state, UPI ID, invoice prefix, financial year start month (default April).
- Acceptance: profile appears on every invoice; GSTIN is validated (15 characters, correct pattern); app redirects to profile setup on first run.

### F2. Customer list
- Fields: name, phone, GSTIN (optional), state, address.
- Acceptance: add, edit, search by name or phone; customer selectable on invoice creation; customer state decides tax type.

### F3. Create invoice
- Select customer, date, and up to 10 line items (description, HSN optional, quantity, rate, GST rate).
- GST rate choices: 0, 5, 12, 18, 28.
- Acceptance: at least one line item required; quantity and rate validated; totals match `gst.py`; invoice number assigned in a database transaction.

### F4. Invoice numbering
- Format: `<prefix>/<FY>/<sequence>`, for example `BS/2026-27/0001`.
- Sequence resets per financial year and per prefix.
- Acceptance: no gaps and no reuse; invoices are never hard-deleted (cancel instead, which keeps the number).

### F5. GST calculation
- Already implemented in `gst.py`, covered by `test_gst.py`.
- Intra-state: CGST and SGST, each half of the rate; SGST = tax minus CGST so the two always sum to the tax.
- Inter-state: IGST for the full rate.
- Missing customer state is treated as intra-state and flagged on screen.
- Acceptance: all tests pass; invoice shows the tax breakup per GST rate.

### F6. Invoice view and print
- Printable A4 page with business header, GSTIN, customer details, item table, tax summary, total in words (optional), UPI ID and QR, and a footer disclaimer.
- Acceptance: browser print dialog produces a clean, one-page invoice for up to 10 items.

### F7. Payments
- Record payment: date, amount, mode (cash, UPI, bank, other), note.
- Status: Unpaid, Partly paid, Paid, Cancelled.
- Acceptance: outstanding = total minus sum of payments; status updates on every change; overpayment is blocked.

### F8. Dashboard
- Cards: invoiced this month, collected this month, total outstanding, overdue count and amount.
- Overdue = outstanding and older than the due window (default 15 days, configurable).
- Acceptance: numbers match the invoice list when filtered to the same period.

### F9. Reminders
- For each unpaid or partly paid invoice, a button opens a prefilled WhatsApp message (`https://wa.me/91XXXXXXXXXX?text=...`).
- Default message: polite, includes invoice number, outstanding amount, and UPI ID.
- Phone numbers normalized: 10-digit numbers get the 91 prefix.
- Acceptance: one tap opens WhatsApp with the text filled in; no API keys needed.

### F10. Monthly CA export (CSV)
- Columns: invoice number, invoice date, customer name, customer GSTIN, customer state, taxable value, CGST, SGST, IGST, total, status, amount paid.
- Choose month and financial year.
- Acceptance: opens in Excel without formatting; UTF-8 with BOM so Hindi names display correctly; totals row included.

### F11. Data safety
- Daily automatic SQLite backup copy into a `backups/` folder.
- Full data export (all tables as CSV) on demand.
- Acceptance: restoring a backup on a fresh install reproduces the same invoices and totals.

### F12. Access
- Single owner passcode, set on first run, required to open the app.
- Acceptance: unauthenticated requests redirect to the login page.

---

## 7. Exports

| Export | Format | Purpose | Phase |
|---|---|---|---|
| Invoice | Printable HTML (print to PDF) | Send to customer | 1 |
| Invoice list | CSV | Owner records | 1 |
| Monthly sales register | CSV (Excel-ready) | CA handoff | 1 |
| Payment register | CSV | Cash and bank tracking | 1 |
| Full data backup | CSV set and SQLite file | Disaster recovery | 1 |
| Purchase register | CSV, with photo-entered bills | CA handoff, ITC | 3 |
| GST liability summary (CGST, SGST, IGST totals per month) | CSV or Excel | CA handoff | 2 |
| Reconciliation exceptions | Excel | CA review | 3 |
| Client pack for CA | Zipped folder with all above | Monthly handoff | 3 |

---

## 8. Data model

```
business
  id                integer, primary key (single row, id = 1)
  name              text
  gstin             text, nullable
  state             text
  address           text
  upi_id            text
  invoice_prefix    text, default "BS"
  fy_start_month    integer, default 4

customer
  id                integer, primary key
  name              text, required
  phone             text
  gstin             text, nullable
  state             text
  address           text
  created_at        datetime

invoice
  id                integer, primary key
  number            text, unique
  fy                text (for example "2026-27")
  seq               integer
  date              date
  due_date          date
  customer_id       integer, foreign key
  is_interstate     boolean
  taxable           decimal(12,2)
  cgst              decimal(12,2)
  sgst              decimal(12,2)
  igst              decimal(12,2)
  total             decimal(12,2)
  status            text (active, cancelled)
  created_at        datetime

invoice_item
  id                integer, primary key
  invoice_id        integer, foreign key
  line_no           integer
  description       text
  hsn               text, nullable
  qty               decimal(12,3)
  rate              decimal(12,2)
  gst_rate          decimal(5,2)
  taxable           decimal(12,2)
  tax               decimal(12,2)

payment
  id                integer, primary key
  invoice_id        integer, foreign key
  date              date
  amount            decimal(12,2)
  mode              text (cash, upi, bank, other)
  note              text, nullable
  created_at        datetime
```

Indexes: `invoice(number)` unique; `invoice(date)`; `payment(invoice_id)`; `customer(phone)`.

---

## 9. Tech stack

- **Language:** Python 3.10 or newer.
- **Dependencies:** none. Standard library only (`http.server`, `sqlite3`, `csv`, `decimal`, `unittest`, `hashlib`, `html`).
- **Storage:** SQLite, single file `billsaathi.db`.
- **UI:** server-rendered HTML, minimal inline CSS, vanilla JavaScript for adding and removing invoice line items.
- **QR code:** generated for the UPI deep link. If no QR library is allowed, show the UPI ID as text and link the UPI URI.
- **Testing:** `unittest` for `gst.py` and the database layer; a smoke test script that runs the server, creates a business, a customer, an invoice, a payment, and downloads the CSV.
- **Run command:** `python3 app.py` opens the app on `http://localhost:8000`.
- **Packaging:** none for the MVP. A later phase may add a single-file executable or a small cloud deployment.

### File layout

```
billsaathi/
  plan.md              this document
  gst.py               GST calculation (done)
  test_gst.py          tests for gst.py (done)
  db.py                schema, migrations, queries
  app.py               HTTP server, routes, HTML templates
  templates.py         HTML template strings (optional split from app.py)
  test_db.py           database tests
  test_smoke.py        end-to-end smoke test
  backups/             automatic database backups
  billsaathi.db        created on first run
```

### Coding conventions
- All money as `Decimal`, never `float`.
- Dates as ISO strings in storage (`YYYY-MM-DD`), formatted as `DD-MM-YYYY` in the UI.
- Every write that touches invoice numbers runs inside `BEGIN IMMEDIATE`.
- HTML output escapes all user input.
- No external network calls in the MVP.

---

## 10. Phases and milestones

### Phase 0: Foundation (done)
- GST calculation module and unit tests.

### Phase 1: MVP core (about 4 weeks)
Week 1: database schema, business profile, customers, first-run setup and passcode.
Week 2: invoice creation, numbering, GST wiring, printable invoice view with UPI ID and QR.
Week 3: payments, status, outstanding balance, dashboard.
Week 4: WhatsApp reminder links, monthly CSV export, daily backup, full data export, smoke test.

Exit criteria for Phase 1:
- All tests pass.
- One full workflow (profile, customer, invoice, print, payment, reminder link, CSV) works end to end on a laptop.
- Invoice creation takes under 60 seconds in a timed run by someone who is not the developer.

### Phase 2: Pilot and refinement (about 3 weeks)
- Pilot with 2 shops in Bijnor, then 5 shops.
- Measure per invoice time, late payments, and month-end hours before and after.
- Add: credit notes (cancel with reason), invoice search and filters, due-date setting per customer, GST liability summary CSV, item catalog with saved prices.
- CA reviews GST logic and the export format.

Exit criteria:
- 5 shops using it for at least 2 weeks each.
- Owners create at least 10 invoices in their second week.
- CA confirms the export needs no cleanup, or lists the changes needed.

### Phase 3: Purchases and CA tools (about 4 weeks)
- Purchase bill entry: manual first, then photo upload with OCR (vendor, GSTIN, date, amounts, tax).
- Category tagging for expenses.
- Purchase register and purchase CSV.
- CA reconciliation tool: upload client purchase register and GSTR-2B export (both CSV from the GST portal), output matched and exceptions sheets using invoice number, date, GSTIN, and amount tolerance.
- Supplier follow-up list: suppliers whose invoices are missing from GSTR-2B, with a prefilled WhatsApp reminder.
- Client pack export (zipped).

### Phase 4: Assisted entry and payments (about 4 weeks)
- WhatsApp or voice invoice entry: owner sends a short message, a language model parses it into a draft invoice that the owner confirms before saving.
- Bank statement CSV import and automatic payment matching by amount and reference, with owner confirmation for unclear matches.
- Payment gateway link on invoices (evaluate options first).
- Multi-user access for staff with limited roles.

### Phase 5: Scale (later, based on pilot results)
- Hosted version with per-shop accounts.
- Pricing and billing for the SaaS offering.
- Integration with Tally or other accounting software.
- E-invoicing and e-way bill support, if the target users need it.

---

## 11. Success metrics

| Metric | Target | How measured |
|---|---|---|
| Time per invoice | Under 1 minute, down from about 3 | Timed runs and owner survey in pilot |
| Payment status updated within 2 days | At least 80 percent of payments | Audit of payment dates in the app |
| Owners creating 10+ invoices in week 2 | At least 4 of 5 pilot shops | App logs |
| Month-end hours for CA cleanup | Measured drop | CA time log before and after |
| CA export needs no cleanup | Yes | CA sign-off |
| Reminder-driven payments | Track share of payments received within 3 days of a reminder | Payment dates vs reminder log |

---

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| GST rules are complex and easy to get wrong | Wrong invoices, owner penalties | Keep to regular supplies; CA reviews logic before pilot; disclaimer on invoice; tests for each rule |
| Owners do not adopt a new tool | No usage | Fewest possible fields; prefill from last invoice; start with the shop owner's real workflow; test with real shops early |
| Data loss on a laptop | Owner loses records | Daily backups; full CSV export; restore test in Phase 1 |
| Invoice numbering gaps | Tax compliance issue | Transactional numbering; never hard-delete; cancel keeps number |
| Competition from existing apps (Vyapar, myBillBook, Tally, ClearTax) | Low differentiation | Differentiate on speed, WhatsApp-native reminders, and CA handoff; validate in pilot |
| Connectivity in small shops | Failed saves | Phase 1 runs locally, no network needed; offline sync is a Phase 5 item |
| Privacy of customer and financial data | Trust loss | Local storage in Phase 1; passcode; no third-party data sharing; clear data policy before hosting |
| WhatsApp reminder misuse (spam) | Account risk | Owner taps to send; no bulk automated messages in MVP |
| Scope creep into a full ERP | Delay | Out-of-scope list is binding for Phase 1 |

---

## 13. Open questions

1. Which GST rates and HSN codes do the pilot shops use most?
2. Does any pilot shop need a fiscal year other than April to March?
3. Who reviews the GST logic before the pilot: the CA we know, or a paid reviewer?
4. Which pilot shops are willing to test in weeks 2 to 4, and who is the contact at each?
5. Hosting for the pilot: laptop only, or a small cloud server from Week 4?
6. Is the target product a standalone app, or part of the agency offering?
7. Pricing expectation for shops (free pilot, low monthly fee, or per-invoice).

---

## 14. Handoff notes for Claude Code

Build in this order, one phase at a time, and stop at each exit criteria check:

1. Read `plan.md` and `gst.py` first. Do not change the GST rules without updating `test_gst.py`.
2. Phase 1, week 1: write `db.py` with the schema above and migration on first run. Add tests in `test_db.py`.
3. Phase 1, week 2: write `app.py` with routes for profile, customers, invoices, and invoice view. Use only the standard library.
4. Phase 1, week 3: payments and dashboard routes; status calculation in `db.py`.
5. Phase 1, week 4: reminder links, CSV export, backups, passcode, smoke test.
6. Run `python3 -m unittest` after each step. Keep all tests passing before moving on.
7. Do not add dependencies. Do not add a paid API. Do not start Phase 2 features until Phase 1 exit criteria are met.

Known decisions already made:
- Pure Python, standard library, SQLite.
- Money as `Decimal`.
- Intra-state uses CGST and SGST, with SGST as the remainder.
- Invoices are never hard-deleted.
- Reminders are opened by the owner, not sent automatically.
- The app runs locally in Phase 1.
