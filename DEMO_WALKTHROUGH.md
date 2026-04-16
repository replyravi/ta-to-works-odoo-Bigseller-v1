# RSS BigSeller Order V1 — Demo Walkthrough

Use this guide to demonstrate all features of the module to the client.

---

## Demo Preparation

1. Module is installed on `https://tatov16-staging-vct-30308428.dev.odoo.com`
2. You are logged in as Admin
3. BigSeller is open in another browser tab (`bigseller.com`)
4. Developer mode is enabled (Settings → Activate developer mode)

---

## Demo 1: Settings Page — BigSeller Configuration

### Steps:
1. Go to **Settings** → scroll left sidebar to find **BigSeller**
2. Show the sections:
   - **BigSeller API Configuration** — Enable sync, cookie, base URL
   - **Browser Auto-Sync** — Token generation, setup instructions
   - **Quick JSON Import** — Manual fallback with console script

### Key Points to Highlight:
- "Generate Token" creates a secure key for auto-sync
- Auto-sync works via browser — no server-side cookie issues
- Three sync methods: Auto (browser), JSON import, Cookie-based API

---

## Demo 2: Browser Auto-Sync (Main Feature)

### Steps:
1. In Odoo Settings → BigSeller, click **"Generate Token"**
2. Copy the token
3. Switch to the **BigSeller browser tab**
4. Press **F12** → Console tab
5. Paste the auto-sync console script (from the installation guide)
   - Replace `ODOO_URL` with: `https://tatov16-staging-vct-30308428.dev.odoo.com`
   - Replace `DB` with: `tatov16-staging-vct-30308428`
   - Replace `TOKEN` with: the token you just generated
6. Press Enter
7. Show the **dark badge** at bottom-right: "Syncing..."
8. Wait for result: `+X new, Y upd | HH:MM`
9. Switch to **Odoo → Sales → Orders** → refresh
10. Show the newly imported orders

### Key Points:
- "Orders sync automatically every 1 minute"
- "Click the badge for instant sync"
- "No manual copy-paste needed — just keep BigSeller open"
- "Duplicate detection: same order won't be imported twice"

---

## Demo 3: JSON Import Wizard (Manual Fallback)

### Steps:
1. Go to **Sales → Orders → Import BigSeller Orders (JSON)**
2. On BigSeller tab, press F12 → Console
3. Run the quick copy script from the Settings page
4. Go back to Odoo → paste the JSON data in the wizard
5. Click **"Preview"** → show the order count and preview
6. Click **"Import Orders"**
7. Show the imported orders in the list

### Key Points:
- "Useful when auto-sync isn't set up yet"
- "Preview before import — see what will be created/updated"
- "Handles all order statuses: New, Shipped, Completed, Cancelled"

---

## Demo 4: Order Details — Marketplace Fields

### Steps:
1. Open any imported order (e.g., from the list click on one)
2. Show the **Marketplace** group in the header:
   - Marketplace (e.g., "Shopee", "Lazada")
   - MP Status (e.g., "New", "Shipped")
   - BigSeller Shop name
   - BigSeller Order ID
   - Platform Order ID
3. Scroll down to the **MP Status** tab
4. Show the status history records

### Key Points:
- "Every status change is tracked with timestamp and action"
- "The platform order ID links back to BigSeller"
- "Shop name helps identify which store the order came from"

---

## Demo 5: Status Change Automation

### Steps:
1. Find an order with status "New"
2. Explain: "When BigSeller status changes to Shipped, Odoo automatically:"
   - Confirms the Quotation → Sale Order
   - Validates the Delivery (picking)
3. Explain: "When status changes to Completed, Odoo also:"
   - Creates an Invoice
   - Posts the Invoice
4. Explain: "When status changes to Cancelled, Odoo handles 3 scenarios:"
   - Not picked → Clean cancel
   - Picked not shipped → Reverse pick + cancel
   - Already shipped → Mark for manual return/credit note

### Key Points:
- "No manual intervention for status updates"
- "Delivery and invoicing are automated"
- "3 cancellation scenarios handle all cases"

---

## Demo 6: XLS Import (Phase 1 — Legacy)

### Steps:
1. Go to **Sales → Orders → Import BigSeller Sale Order V1 (XLS)**
2. Show the upload form
3. Explain: "This was the Phase 1 method — export from BigSeller, import XLS"
4. (Optional: upload a sample XLS to demonstrate)

### Key Points:
- "Still available as a backup method"
- "API sync and JSON import are now the preferred methods"

---

## Demo 7: Re-import Safety

### Key Points to Address (Peter's Questions):
1. **"Can we install on staging and later re-import in production?"**
   - "Yes! The module uses platform order ID as the unique key"
   - "If an order already exists in production, it will be updated, not duplicated"
   - "Safe to install on staging first, test, then deploy to production"

2. **"Does Odoo close delivery when BigSeller status changes?"**
   - "Yes — Shipped status confirms SO + validates delivery"
   - "Completed status also creates and posts the invoice"
   - "All automated, no manual steps needed"

---

## Common Questions During Demo

| Question | Answer |
|----------|--------|
| How often does it sync? | Every 1 minute (configurable) |
| What if BigSeller is closed? | Sync pauses, resumes when reopened |
| What if Odoo is down? | Badge shows error, retries next minute |
| Can we sync old orders? | Yes, JSON import can handle any orders |
| Is the token secure? | Yes, random 32-char hex, only you have it |
| What about duplicates? | Orders are matched by platform order ID |
| Does it work with multiple shops? | Yes, shop name is captured per order |
