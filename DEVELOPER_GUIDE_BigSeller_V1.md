# RSS – BigSeller Order V1: Developer Guide (Phase 2)

> **Author:** RSS  
> **Module name:** `rss_bigseller_order_v1`  
> **Odoo version:** 16.0 (also compatible with Odoo 18)  
> **Purpose:** Import BigSeller marketplace orders from XLS, track marketplace status on Sale Orders, auto-trigger Odoo actions based on status changes, and sync with BigSeller via session-based API.  
> **Audience:** Junior/fresher developers with basic Python knowledge. No prior Odoo experience required.  
> **Previous Phase:** This module builds on Phase 1 (`rss_import_bigseller_order`). Read `DEVELOPER_GUIDE_BigSeller.md` first for Odoo fundamentals.

---

## Table of Contents

1. [What Does This Module Do?](#1-what-does-this-module-do)
2. [What's New in V1 (Phase 2) vs Phase 1?](#2-whats-new-in-v1-phase-2-vs-phase-1)
3. [Folder Structure](#3-folder-structure)
4. [File-by-File Explanation](#4-file-by-file-explanation)
   - [4.1 `__manifest__.py` — Module Identity](#41-__manifestpy--module-identity)
   - [4.2 `__init__.py` Files — Package Loaders](#42-__initpy-files--package-loaders)
   - [4.3 `compat.py` — Odoo Version Detection](#43-compatpy--odoo-version-detection)
   - [4.4 `models/mp_status_history.py` — Status History Model](#44-modelsmp_status_historypy--status-history-model)
   - [4.5 `models/sale_order.py` — Sale Order Extensions](#45-modelssale_orderpy--sale-order-extensions)
   - [4.6 `models/bigseller_sale.py` — XLS Import Wizard](#46-modelsbigseller_salepy--xls-import-wizard)
   - [4.7 `models/bigseller_api.py` — BigSeller API Connector](#47-modelsbigseller_apipy--bigseller-api-connector)
   - [4.8 `models/res_config_settings.py` — Settings UI](#48-modelsres_config_settingspy--settings-ui)
   - [4.9 Security Files](#49-security-files)
   - [4.10 Views (Odoo 16)](#410-views-odoo-16)
   - [4.11 Views (Odoo 18)](#411-views-odoo-18)
   - [4.12 `data/bigseller_cron.xml` — Scheduled Sync Job](#412-databigseller_cronxml--scheduled-sync-job)
5. [Status Mapping — BigSeller to Odoo Actions](#5-status-mapping--bigseller-to-odoo-actions)
6. [Cancellation Scenarios](#6-cancellation-scenarios)
7. [BigSeller API Integration](#7-bigseller-api-integration)
8. [Order Flow (End to End)](#8-order-flow-end-to-end)
9. [Odoo 16 / 18 Compatibility](#9-odoo-16--18-compatibility)
10. [How to Install / Update / Uninstall](#10-how-to-install--update--uninstall)
11. [Common Changes You Might Need to Make](#11-common-changes-you-might-need-to-make)
12. [Database Tables Created by This Module](#12-database-tables-created-by-this-module)
13. [Common Errors and Fixes](#13-common-errors-and-fixes)
14. [Glossary of Odoo Terms](#14-glossary-of-odoo-terms)

---

## 1. What Does This Module Do?

This module manages the **full lifecycle** of marketplace orders from BigSeller into Odoo:

```
BigSeller (Shopee/Lazada/TikTok)
        │
        ▼
┌─────────────────────────────┐
│  Method 1: XLS Import       │  ← Upload .xls file exported from BigSeller
│  Method 2: API Sync         │  ← Automatic sync via BigSeller internal API
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Odoo Sale Order (Quotation)│  ← Created with marketplace fields
│  + MP Status tracking       │  ← History of every status change
│  + Auto Odoo actions        │  ← Confirm SO, create invoice, cancel, etc.
└─────────────────────────────┘
```

**In Odoo, the module adds:**

| Where | What |
|---|---|
| Sales > Orders > **Import BigSeller Sale Order V1** | XLS import wizard (popup) |
| Sale Order form > **Marketplace** group | Shows MP name, status, last update |
| Sale Order form > **MP Status** tab | Full history of all status changes |
| Settings > Sales > **BigSeller** section | API config: session cookie, sync toggle, test connection |
| Scheduled Actions | **BigSeller: Sync Orders** — auto-sync every 30 minutes |

---

## 2. What's New in V1 (Phase 2) vs Phase 1?

| Feature | Phase 1 (`rss_import_bigseller_order`) | Phase 2 (`rss_bigseller_order_v1`) |
|---|---|---|
| XLS Import | Yes | Yes (cloned + enhanced) |
| Marketplace field on SO | No | `mp_marketplace` (Shopee / Lazada / TikTok) |
| MP Status tracking | No | `mp_status` Selection field with 9 statuses |
| Status history tab | No | `mp.status.history` One2many model |
| Auto Confirm SO | No | Yes, when status = Shipped / To Pickup |
| Auto Create Invoice | No | Yes, when status = Completed |
| 3 Cancellation scenarios | No | Yes (not picked / picked / shipped) |
| BigSeller API connector | No | Yes (session cookie based) |
| Settings UI | No | Yes (under Sales > BigSeller) |
| Cron job for sync | No | Yes (every 30 min, disabled by default) |
| Odoo 18 compatible | No | Yes (separate `views_v18/` directory) |

---

## 3. Folder Structure

```
rss_bigseller_order_v1/
│
├── __init__.py                  ← Root package loader
├── __manifest__.py              ← Module identity + dependencies + data files
├── compat.py                    ← Odoo version detection helper
│
├── models/
│   ├── __init__.py              ← Imports all Python model files
│   ├── mp_status_history.py     ← NEW: Marketplace status history model
│   ├── sale_order.py            ← NEW: Sale order extensions + status logic + cancel logic
│   ├── bigseller_sale.py        ← CLONED: XLS import wizard (enhanced for Phase 2)
│   ├── bigseller_api.py         ← NEW: BigSeller session-based API client
│   └── res_config_settings.py   ← NEW: Settings page for BigSeller config
│
├── security/
│   ├── access_record_rule.xml   ← Security group definition
│   └── ir.model.access.csv      ← Database access permissions
│
├── views/                       ← Odoo 16 XML views (default)
│   ├── bigseller_sale_wizard.xml      ← Import wizard popup + menu item
│   ├── sale_order_view.xml            ← SO form: Marketplace group + MP Status tab
│   └── res_config_settings_view.xml   ← Settings page UI
│
├── views_v18/                   ← Odoo 18 XML views (alternative)
│   ├── bigseller_sale_wizard.xml
│   ├── sale_order_view.xml
│   └── res_config_settings_view.xml
│
└── data/
    └── bigseller_cron.xml       ← Scheduled action for auto-sync
```

**Total: 18 files** (6 Python + 3 XML views + 3 XML views v18 + 2 security + 1 data + 3 config)

---

## 4. File-by-File Explanation

### 4.1 `__manifest__.py` — Module Identity

```python
{
    'name': 'RSS BigSeller Order V1',
    'version': '16.0.1.0.0',
    'category': 'Sales',
    'depends': [
        'base',                # Core Odoo (always required)
        'sale',                # Sale orders
        'sale_order_type',     # OCA addon for Order Types
        'sale_order_type_ext', # TA-TO helper (tracking_reference, cancel_reason_id, etc.)
        'stock',               # Inventory/warehouse (needed for picking operations)
        'delivery',            # Delivery carriers
        'account',             # Invoicing (needed for auto-create invoice)
    ],
    'data': [
        'security/access_record_rule.xml',   # ← MUST come before ir.model.access.csv
        'security/ir.model.access.csv',
        'views/bigseller_sale_wizard.xml',
        'views/sale_order_view.xml',
        'views/res_config_settings_view.xml',
        'data/bigseller_cron.xml',
    ],
}
```

**Important rules:**
- `security/access_record_rule.xml` MUST come **before** `ir.model.access.csv` in the `data` list. The XML creates the security group, and the CSV references it. If reversed, you get: `No matching record found for external id`.
- `stock`, `delivery`, `account` are new dependencies (not in Phase 1). They are needed because Phase 2 manages picking operations and invoicing.
- For **Odoo 18**: change the three `views/` paths to `views_v18/` paths. See [Section 9](#9-odoo-16--18-compatibility).

---

### 4.2 `__init__.py` Files — Package Loaders

**Root `__init__.py`:**
```python
from . import models
```

**`models/__init__.py`:**
```python
from . import mp_status_history    # Must come before sale_order (it defines the Selection)
from . import sale_order
from . import bigseller_sale
from . import bigseller_api
from . import res_config_settings
```

**Load order matters!** `mp_status_history` must be imported first because `sale_order.py` imports `BIGSELLER_STATUS_SELECTION` from it.

---

### 4.3 `compat.py` — Odoo Version Detection

```python
import odoo
ODOO_VERSION = int(odoo.release.version_info[0])   # 16, 17, or 18
IS_V16 = ODOO_VERSION < 17
IS_V18 = ODOO_VERSION >= 17
```

Use this in Python code if you ever need version-specific behavior:
```python
from ..compat import IS_V16
if IS_V16:
    # Odoo 16 specific code
else:
    # Odoo 17/18 specific code
```

---

### 4.4 `models/mp_status_history.py` — Status History Model

This is a **brand new database table** that stores every marketplace status change for a sale order.

```python
BIGSELLER_STATUS_SELECTION = [
    ('new', 'New'),
    ('in_process', 'In Process'),
    ('platform_processing', 'Platform Processing'),
    ('to_pickup', 'To Pickup'),
    ('retry_ship', 'Retry Ship'),
    ('shipped', 'Shipped'),
    ('completed', 'Completed'),
    ('canceled', 'Canceled'),
    ('voided', 'Voided'),
]

class MpStatusHistory(models.Model):
    _name = 'mp.status.history'
    _description = 'Marketplace Status History'
    _order = 'update_date desc, id desc'    # Newest first

    sale_order_id   = fields.Many2one('sale.order', required=True, ondelete='cascade')
    marketplace     = fields.Char()          # "Shopee", "Lazada", "TikTok"
    bigseller_status = fields.Selection(BIGSELLER_STATUS_SELECTION)
    mp_status       = fields.Char()          # Freeform marketplace-specific text
    odoo_action     = fields.Char()          # What Odoo did: "Created Quotation", etc.
    update_date     = fields.Datetime(default=fields.Datetime.now)
    notes           = fields.Text()
```

**Key concepts for beginners:**

| Concept | Explanation |
|---|---|
| `models.Model` | Permanent database table (unlike `TransientModel` which auto-deletes) |
| `_name = 'mp.status.history'` | Creates a table called `mp_status_history` in PostgreSQL |
| `_order = 'update_date desc'` | Default sort order when records are displayed |
| `Many2one('sale.order')` | Foreign key — each history record belongs to one sale order |
| `ondelete='cascade'` | If the sale order is deleted, all its history records are deleted too |
| `BIGSELLER_STATUS_SELECTION` | A Python list defined as a constant so it can be reused in `sale_order.py` |

**Database table created:**

| Column | Type | Description |
|---|---|---|
| `id` | Integer (auto) | Primary key |
| `sale_order_id` | Integer (FK) | Links to `sale_order.id` |
| `marketplace` | VARCHAR | "Shopee" / "Lazada" / "TikTok" |
| `bigseller_status` | VARCHAR | Selection key like "shipped", "completed" |
| `mp_status` | VARCHAR | Freeform status text |
| `odoo_action` | VARCHAR | What Odoo did when this status was set |
| `update_date` | TIMESTAMP | When this status change happened |
| `notes` | TEXT | Optional notes |
| `create_uid` | Integer (FK) | User who created the record |
| `write_uid` | Integer (FK) | User who last modified the record |
| `create_date` | TIMESTAMP | Auto-set when record is created |
| `write_date` | TIMESTAMP | Auto-set when record is modified |

---

### 4.5 `models/sale_order.py` — Sale Order Extensions

This file does three things:
1. **Adds new fields** to the existing `sale.order` table
2. **Implements status mapping logic** (BigSeller status -> Odoo action)
3. **Implements cancellation scenarios**

#### New Fields on sale.order

```python
class SaleOrderBigSellerV1(models.Model):
    _inherit = 'sale.order'     # ← Extends the EXISTING sale.order table

    buyer_designed_logistics = fields.Char()      # From Phase 1
    mp_marketplace = fields.Char(tracking=True)   # "Shopee", "Lazada", "TikTok"
    mp_status = fields.Selection(BIGSELLER_STATUS_SELECTION, tracking=True)
    mp_last_update = fields.Datetime(tracking=True)
    mp_status_history_ids = fields.One2many('mp.status.history', 'sale_order_id')
```

**Key points:**
- `_inherit = 'sale.order'` means we are NOT creating a new table. We are adding columns to the existing `sale_order` table.
- `tracking=True` means Odoo will log changes to this field in the chatter (the message feed at the bottom of the form).
- `One2many('mp.status.history', 'sale_order_id')` creates a link: "one sale order has many history records". This is the reverse of the `Many2one` defined in `mp_status_history.py`.

#### Status Mapping Logic

The `STATUS_ACTION_MAP` dictionary defines what Odoo should do when a BigSeller status changes:

```python
STATUS_ACTION_MAP = {
    'new':                  'Created Quotation',         # Import creates QTN
    'in_process':            None,                       # No action needed
    'platform_processing':   None,                       # Shopee payment verification
    'to_pickup':            'Confirmed SO + Confirm Delivery',
    'retry_ship':            None,                       # Shopee pickup failed
    'shipped':              'Confirmed SO + Confirm Delivery',
    'completed':            'Created Invoice + Posted',
    'canceled':             'Cancelled SO',
    'voided':                None,                       # Manual hold, no action
}
```

The main method is `action_update_mp_status()`:

```python
def action_update_mp_status(self, new_status, mp_status_text='', notes=''):
    # 1. Create a history record
    # 2. Update mp_status and mp_last_update on the SO
    # 3. Trigger the corresponding Odoo action:
    #    - to_pickup / shipped  → _mp_confirm_and_deliver()
    #    - completed            → _mp_create_invoice()
    #    - canceled             → action_cancel_mp_order()
```

**What each Odoo action does:**

| Method | What it does |
|---|---|
| `_mp_confirm_and_deliver()` | If SO is draft, confirms it. Then validates all pending delivery pickings. |
| `_mp_create_invoice()` | Confirms + delivers (if needed), then creates and posts an invoice. |
| `action_cancel_mp_order()` | Handles 3 cancellation scenarios (see [Section 6](#6-cancellation-scenarios)). |

#### Important: `self.ensure_one()`

You will see `self.ensure_one()` at the start of many methods. This is an Odoo safety check:
- In Odoo, `self` can contain **multiple records** (a recordset).
- `ensure_one()` raises an error if `self` contains 0 or more than 1 record.
- It guarantees the method operates on exactly one sale order.

---

### 4.6 `models/bigseller_sale.py` — XLS Import Wizard

This is a **clone** of Phase 1's `bigseller_sale.py` with these enhancements:

| What Changed | Phase 1 | Phase 2 (V1) |
|---|---|---|
| Model name | `gen.bigseller.sale` | `gen.bigseller.sale.v1` |
| `make_sale()` creates SO with... | Basic fields only | + `mp_marketplace`, `mp_status`, `mp_last_update` |
| Status history | Not tracked | Creates first `mp.status.history` record on import |
| Status mapping | None | Maps XLS "Order Status" to `mp_status` Selection key |

**The key change in `make_sale()`:**

```python
# Phase 2: map XLS status text to selection key
mp_status_key = XLS_STATUS_MAP.get(order_status, 'new')

sale_id = sale_obj.create({
    # ... all Phase 1 fields ...
    # Phase 2 additions:
    'mp_marketplace':  values.get('marketplace', ''),
    'mp_status':       mp_status_key,
    'mp_last_update':  fields.Datetime.now(),
})

# Phase 2: create initial status history entry
self.env['mp.status.history'].create({
    'sale_order_id':    sale_id.id,
    'marketplace':      values.get('marketplace', ''),
    'bigseller_status': mp_status_key,
    'mp_status':        order_status,
    'odoo_action':      'Created Quotation',
    'notes':            'Initial import via XLS',
})
```

**All finder methods** (`find_partner`, `find_order_type`, `find_product`, etc.) are identical to Phase 1. See `DEVELOPER_GUIDE_BigSeller.md` Section 4.5 for detailed explanations.

---

### 4.7 `models/bigseller_api.py` — BigSeller API Connector

**Background:** BigSeller does NOT have a public API. This connector calls BigSeller's **internal web APIs** (the same ones their website's JavaScript calls) using a session cookie captured from the user's browser.

#### How Session Authentication Works

```
1. User logs into bigseller.com in their browser (solves CAPTCHA manually)
2. User opens browser DevTools > Application > Cookies
3. User copies the full cookie string
4. User pastes it into Odoo: Settings > Sales > BigSeller > Session Cookie
5. Odoo uses this cookie to call BigSeller's APIs
6. When session expires (~24h), user repeats steps 1-4
```

#### The BigSellerClient Class

```python
class BigSellerClient:
    def __init__(self, base_url, cookie_string):
        self.session = requests.Session()
        self.session.headers.update({
            'Cookie': cookie_string,           # This is how we authenticate
            'User-Agent': 'Mozilla/5.0 ...',   # Pretend to be a browser
            'X-Requested-With': 'XMLHttpRequest',  # Required by BigSeller
        })
```

#### Discovered API Endpoints

These were captured on 2026-04-10 by monitoring BigSeller's network traffic:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/isLogin.json` | Check if session is valid |
| `POST` | `/api/v1/order/new/pageList.json` | List new orders |
| `POST` | `/api/v1/order/packed/pageList.json` | List packed orders |
| `POST` | `/api/v1/order/shipped/pageList.json` | List shipped orders |
| `POST` | `/api/v1/order/completed/pageList.json` | List completed orders |
| `POST` | `/api/v1/order/canceled/pageList.json` | List canceled orders |
| `POST` | `/api/v1/order/getOrderStatusCount.json` | Order counts by status |
| `GET` | `/api/v1/shopsAndPlatforms.json` | Connected shops list |
| `GET` | `/api/v1/3pl/shipping/list.json` | 3PL shipping providers |

#### Methods Available

| Method | Status | Description |
|---|---|---|
| `test_connection()` | Working | Checks if session cookie is valid |
| `get_orders(status, page, page_size)` | Working | Fetches paginated order list |
| `get_shops()` | Working | Lists connected marketplace shops |
| `get_order_detail(order_id)` | Stub | Endpoint needs confirmation |
| `update_order_status(order_id, status)` | Stub | Endpoint needs confirmation |
| `export_orders(status, date_from, date_to)` | Stub | Endpoint needs confirmation |

**Stub methods** are placeholders that log a message but don't actually call the API. They need the exact endpoint URL to be discovered from BigSeller's browser DevTools (see [Section 7](#7-bigseller-api-integration)).

---

### 4.8 `models/res_config_settings.py` — Settings UI

This extends Odoo's Settings page to add a "BigSeller" configuration section.

```python
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bigseller_session_cookie = fields.Char(config_parameter='bigseller.session_cookie')
    bigseller_base_url       = fields.Char(config_parameter='bigseller.base_url')
    bigseller_sync_enabled   = fields.Boolean(config_parameter='bigseller.sync_enabled')
    bigseller_sync_interval  = fields.Integer(config_parameter='bigseller.sync_interval')
    bigseller_last_sync      = fields.Datetime(config_parameter='bigseller.last_sync')
    bigseller_last_sync_error = fields.Char(config_parameter='bigseller.last_sync_error')
```

**Key concept: `config_parameter`**

When you add `config_parameter='bigseller.session_cookie'` to a field, Odoo automatically:
- **Saves** the field value to the `ir.config_parameter` table (a key-value store)
- **Loads** it back when the Settings page is opened

This is Odoo's standard way to store module configuration. You can read these values anywhere in code:

```python
ICP = self.env['ir.config_parameter'].sudo()
cookie = ICP.get_param('bigseller.session_cookie', '')
```

**Important rule:** `config_parameter` fields on `res.config.settings` must be one of these types only: `Boolean`, `Integer`, `Float`, `Char`, `Selection`, `Many2one`, `Datetime`. Using `Text` will crash with: `Field must have type 'boolean', 'integer', 'float', 'char'...`

#### Action Buttons

```python
def action_bigseller_test_connection(self):
    # Creates a BigSellerClient and calls test_connection()
    # Shows success notification or raises UserError

def action_bigseller_sync_now(self):
    # Calls sale.order._bigseller_sync_orders() immediately
    # Same logic as the cron job but triggered manually
```

---

### 4.9 Security Files

#### `security/access_record_rule.xml`

```xml
<record id="group_import_bigseller_order_v1" model="res.groups">
    <field name="name">BigSeller Order V1</field>
    <field name="implied_ids" eval="[(4,ref('base.group_user'))]"/>
</record>
```

Creates a security group. Users must be in this group to see the BigSeller menu items.

**To assign users:** Settings > Users & Companies > Users > select user > scroll to "Other" section > check "BigSeller Order V1".

#### `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_gen_bigseller_sale_v1,...,model_gen_bigseller_sale_v1,,1,1,1,1
access_mp_status_history_user,...,model_mp_status_history,base.group_user,1,0,0,0
access_mp_status_history_manager,...,model_mp_status_history,rss_bigseller_order_v1.group_import_bigseller_order_v1,1,1,1,1
```

| Rule | Who | Can read | Can write | Can create | Can delete |
|---|---|---|---|---|---|
| Wizard | Everyone | Yes | Yes | Yes | Yes |
| MP History (user) | All internal users | Yes | No | No | No |
| MP History (manager) | BigSeller V1 group | Yes | Yes | Yes | Yes |

---

### 4.10 Views (Odoo 16)

#### `views/bigseller_sale_wizard.xml`

Three records:
1. **Form view** — the popup layout with file upload field and Import button
2. **Window action** — tells Odoo "open this form as a popup" (`target="new"`)
3. **Menu item** — placed under Sales > Orders at sequence 63

#### `views/sale_order_view.xml`

Two `xpath` modifications to the standard sale order form:

**1. Marketplace group (header area):**

```xml
<xpath expr="//group[@name='sale_header']" position="after">
    <group string="Marketplace" attrs="{'invisible': [('mp_marketplace', '=', False)]}">
        <field name="mp_marketplace" readonly="1"/>
        <field name="mp_status" readonly="1"/>
        <field name="mp_last_update" readonly="1"/>
    </group>
</xpath>
```

- `position="after"` = insert this XML **after** the matched element
- `attrs="{'invisible': [...]}"` = hide this group when `mp_marketplace` is empty (Odoo 16 syntax)
- `readonly="1"` = users can't edit these fields directly (they're set by code)

**2. MP Status History tab (notebook area):**

```xml
<xpath expr="//notebook" position="inside">
    <page string="MP Status" name="mp_status_tab" attrs="{'invisible': [...]}">
        <field name="mp_status_history_ids">
            <tree create="0" delete="0">
                <field name="update_date"/>
                <field name="bigseller_status"/>
                <field name="odoo_action"/>
                ...
            </tree>
        </field>
    </page>
</xpath>
```

- `position="inside"` = add this page **inside** the existing notebook
- `create="0" delete="0"` = users can't manually add or delete history rows (only code does that)

#### `views/res_config_settings_view.xml`

Inherits `sale.res_config_settings_view_form` and adds a "BigSeller" section with:
- Enable Auto Sync toggle
- Sync interval field
- Base URL field
- Session cookie text input
- Test Connection button
- Sync Now button
- Last sync timestamp and error display

---

### 4.11 Views (Odoo 18)

The `views_v18/` folder contains the same UI but with Odoo 18 syntax:

| Odoo 16 Syntax | Odoo 18 Syntax |
|---|---|
| `<tree>` | `<list>` |
| `attrs="{'invisible': [('field', '=', False)]}"` | `invisible="not field"` |
| `attrs="{'readonly': [...]}"` | `readonly="expression"` |
| `states="draft"` | `invisible="state != 'draft'"` |

**To switch:** Edit `__manifest__.py` and replace `views/` with `views_v18/` in the `data` list.

---

### 4.12 `data/bigseller_cron.xml` — Scheduled Sync Job

```xml
<record id="ir_cron_bigseller_sync" model="ir.cron">
    <field name="name">BigSeller: Sync Orders</field>
    <field name="model_id" ref="sale.model_sale_order"/>
    <field name="code">model._bigseller_sync_orders()</field>
    <field name="interval_number">30</field>
    <field name="interval_type">minutes</field>
    <field name="active" eval="False"/>   ← Disabled by default
</record>
```

This creates a **scheduled action** that runs `_bigseller_sync_orders()` on `sale.order` every 30 minutes.

**To enable:** Go to Settings > Technical > Automation > Scheduled Actions > find "BigSeller: Sync Orders" > check "Active". Or use the Settings > Sales > BigSeller > "Enable Auto Sync" toggle.

---

## 5. Status Mapping — BigSeller to Odoo Actions

This is the heart of Phase 2. When a BigSeller status changes, Odoo automatically takes action:

| BigSeller Status | Lazada Status | Shopee Status | Odoo Action |
|---|---|---|---|
| **New** | Pending | To Ship (Unprocessed) | Create Quotation (via import wizard) |
| **In Process** | Ready to Ship | To Ship (Processed) | No action |
| **Platform Processing** | — | Payment Verifying | No action |
| **To Pickup** | Ready to Ship | To Ship (Processed) | Confirm QTN → SO + Confirm Delivery |
| **Retry Ship** | — | Pickup Failed | No action |
| **Shipped** | Shipped | Shipping | Confirm QTN → SO + Confirm Delivery |
| **Completed** | Delivered | Completed | Create Invoice + Post |
| **Canceled** | Cancelled | Cancelled | Cancel SO (see scenarios below) |
| **Voided** | Manual Hold | Manual Hold | No action |

**Where is this defined in code?** `models/sale_order.py` → `STATUS_ACTION_MAP` dictionary.

---

## 6. Cancellation Scenarios

When a marketplace cancels an order, the response depends on how far the order has progressed in the warehouse:

```
┌─────────────────────────────────────────┐
│ Marketplace sends cancellation request  │
└─────────────────────┬───────────────────┘
                      │
            ┌─────────▼─────────┐
            │ Check picking state│
            └──┬───────┬────────┘
               │       │        │
     ┌─────────▼──┐ ┌──▼──────┐ ┌▼──────────────┐
     │ Scenario 1  │ │Scenario 2│ │ Scenario 3    │
     │ Not picked  │ │ Picked   │ │ Already shipped│
     │             │ │ not sent │ │               │
     └──────┬──────┘ └──┬──────┘ └──────┬────────┘
            │           │               │
            ▼           ▼               ▼
     Cancel SO +   Cancel pickings   Log as "Return
     Cancel all    + Cancel SO       flow — manual
     deliveries                      credit note"
```

**Where is this defined in code?** `models/sale_order.py` → `action_cancel_mp_order()` method.

---

## 7. BigSeller API Integration

### How to Capture New API Endpoints

If you need to discover additional BigSeller API endpoints (e.g., for status updates or order details):

1. Open Chrome and log into `bigseller.com`
2. Press **F12** to open DevTools
3. Go to **Network** tab
4. Check **"Preserve log"** checkbox
5. Filter by **"Fetch/XHR"**
6. Navigate to the page whose API you want to capture (e.g., click on an order)
7. Look for requests to `bigseller.com/api/v1/...`
8. Click on a request to see:
   - **URL** — the endpoint path
   - **Method** — GET or POST
   - **Headers** — especially `Cookie` and `Content-Type`
   - **Payload** — request body (for POST)
   - **Response** — the JSON data structure
9. Right-click the request > **"Copy as cURL"** to test from terminal

### How to Add a New Endpoint

Open `models/bigseller_api.py` and add a new method:

```python
def get_order_detail(self, order_id):
    """Fetch single order details."""
    return self._get('/api/v1/order/detail.json', params={'orderId': order_id})
    # Change the URL to the actual endpoint you discovered
```

For POST endpoints:
```python
def update_order_status(self, order_id, new_status):
    return self._post('/api/v1/order/updateStatus.json', data={
        'orderId': order_id,
        'status': new_status,
    })
```

---

## 8. Order Flow (End to End)

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 0: Marketplace (Shopee/Lazada) receives customer order      │
│         BigSeller picks it up automatically (Status: New)        │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: Import to Odoo                                           │
│   Method A: Upload XLS via wizard (Sales > Orders > Import V1)   │
│   Method B: Auto-sync via cron (every 30 min, if enabled)        │
│   → Creates Quotation (draft) with mp_marketplace + mp_status    │
│   → Creates first mp.status.history record                       │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 2: Staff checks price manually (QTN stays in draft)         │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 3: Status changes to "Shipped" or "To Pickup"               │
│   (detected via next XLS import or API sync)                     │
│   → action_update_mp_status('shipped')                           │
│   → _mp_confirm_and_deliver():                                   │
│       1. Confirms QTN → Sale Order                               │
│       2. Assigns + validates delivery picking                    │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 4: Status changes to "Completed"                            │
│   → action_update_mp_status('completed')                         │
│   → _mp_create_invoice():                                        │
│       1. Creates invoice from SO                                 │
│       2. Posts (validates) the invoice                            │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 5: Staff pays invoice to marketplace account (manual)       │
│         MP Status → Completed                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 9. Odoo 16 / 18 Compatibility

The Python code works on both Odoo 16 and 18. Only the XML views need to change.

### Switching to Odoo 18

1. Open `__manifest__.py`
2. Change:

```python
# FROM (Odoo 16):
'views/bigseller_sale_wizard.xml',
'views/sale_order_view.xml',
'views/res_config_settings_view.xml',

# TO (Odoo 18):
'views_v18/bigseller_sale_wizard.xml',
'views_v18/sale_order_view.xml',
'views_v18/res_config_settings_view.xml',
```

3. Change version:
```python
'version': '18.0.1.0.0',
```

4. Reinstall or update the module.

### XML Syntax Differences Cheat Sheet

| Feature | Odoo 16 | Odoo 18 |
|---|---|---|
| List view tag | `<tree>` | `<list>` |
| Conditional visibility | `attrs="{'invisible': [('field', '=', False)]}"` | `invisible="not field"` |
| Conditional readonly | `attrs="{'readonly': [('state', '!=', 'draft')]}"` | `readonly="state != 'draft'"` |
| State-based visibility | `states="draft,sent"` | `invisible="state not in ('draft', 'sent')"` |

---

## 10. How to Install / Update / Uninstall

### Prerequisites
- Odoo is stopped
- Module folder is inside `custom-addons/`
- `custom-addons` path is in `odoo.conf` under `addons_path`

### Install (first time)
```bash
cd /Users/ravishankersingh/Downloads/TA-TO-Works-Mar-26/odoo-16
source venv/bin/activate
python odoo-source/odoo-bin -d tato -i rss_bigseller_order_v1 --stop-after-init
```

### Update (after code changes)
```bash
python odoo-source/odoo-bin -d tato -u rss_bigseller_order_v1 --stop-after-init
```

### Restart Odoo
```bash
bash start-odoo.sh
```

### Stop Odoo
```bash
bash stop-odoo.sh
```

### Verify Installation
```bash
# Check module state in database:
PGPASSWORD=odoo16 psql -h localhost -U odoo16 -d tato \
  -c "SELECT name, state FROM ir_module_module WHERE name = 'rss_bigseller_order_v1';"

# Expected output:
#           name          |   state
# ------------------------+-----------
#  rss_bigseller_order_v1 | installed
```

Or in the browser: **Settings > Apps > search "BigSeller"** → should show "Installed".

---

## 11. Common Changes You Might Need to Make

### Change 1: Add a new BigSeller status

1. Edit `models/mp_status_history.py` → add to `BIGSELLER_STATUS_SELECTION`:
```python
('new_status_key', 'Display Name'),
```

2. Edit `models/sale_order.py` → add to `STATUS_ACTION_MAP`:
```python
'new_status_key': 'Description of Odoo action',  # or None if no action
```

3. If the new status should trigger an Odoo action, add the logic in `action_update_mp_status()`.

4. Run module update: `python odoo-bin -d tato -u rss_bigseller_order_v1 --stop-after-init`

---

### Change 2: Add a new field to the Sale Order form

1. Edit `models/sale_order.py` → add the field:
```python
my_new_field = fields.Char(string='My New Field')
```

2. Edit `views/sale_order_view.xml` → add an xpath to show it:
```xml
<xpath expr="//field[@name='mp_status']" position="after">
    <field name="my_new_field"/>
</xpath>
```

3. Also edit `views_v18/sale_order_view.xml` with the same change (Odoo 18 syntax).

4. Run module update.

---

### Change 3: Change XLS column positions

If BigSeller changes their export format:

1. Open a new export file in Excel
2. Count column positions (A=0, B=1, C=2...)
3. Edit `models/bigseller_sale.py` → update the `COL_*` constants:
```python
COL_ORDER_NO     = 0   # Update these numbers
COL_ORDER_STATUS = 7
COL_MARKETPLACE  = 9
# ... etc
```

4. NO other changes needed — the rest of the code uses these constants.

---

### Change 4: Add a new API endpoint

1. Capture the endpoint from BigSeller's browser DevTools (see [Section 7](#7-bigseller-api-integration))
2. Edit `models/bigseller_api.py` → add a new method:
```python
def my_new_endpoint(self, params):
    return self._post('/api/v1/path/to/endpoint.json', data=params)
```

---

### Change 5: Change the cron schedule

1. Edit `data/bigseller_cron.xml`:
```xml
<field name="interval_number">15</field>   <!-- Change from 30 to 15 -->
<field name="interval_type">minutes</field>
```

2. Run module update.

Or change it in the UI: Settings > Technical > Scheduled Actions > "BigSeller: Sync Orders".

---

### Change 6: Add a new field to the Settings page

1. Edit `models/res_config_settings.py` → add field:
```python
bigseller_my_setting = fields.Char(
    string='My Setting',
    config_parameter='bigseller.my_setting')
```

2. Edit `views/res_config_settings_view.xml` → add inside the BigSeller block:
```xml
<div class="col-12 o_setting_box">
    <div class="o_setting_right_pane">
        <label for="bigseller_my_setting"/>
        <field name="bigseller_my_setting"/>
    </div>
</div>
```

3. Remember: only `Char`, `Boolean`, `Integer`, `Float`, `Selection`, `Many2one`, `Datetime` types are allowed for `config_parameter` fields.

---

## 12. Database Tables Created by This Module

### New table: `mp_status_history`

```sql
SELECT * FROM mp_status_history LIMIT 5;
```

### New columns on `sale_order`

```sql
SELECT id, name, mp_marketplace, mp_status, mp_last_update, buyer_designed_logistics
FROM sale_order
WHERE mp_marketplace IS NOT NULL;
```

### Configuration values in `ir_config_parameter`

```sql
SELECT key, value FROM ir_config_parameter WHERE key LIKE 'bigseller.%';
```

| Key | Description |
|---|---|
| `bigseller.session_cookie` | BigSeller browser session cookie |
| `bigseller.base_url` | BigSeller base URL |
| `bigseller.sync_enabled` | "True" or "False" |
| `bigseller.sync_interval` | Minutes between syncs |
| `bigseller.last_sync` | Timestamp of last successful sync |
| `bigseller.last_sync_error` | Error message from last failed sync |

---

## 13. Common Errors and Fixes

### `No matching record found for external id 'rss_bigseller_order_v1.group_import_bigseller_order_v1'`
**Cause:** `ir.model.access.csv` is loaded before `access_record_rule.xml` in `__manifest__.py`.  
**Fix:** Make sure `access_record_rule.xml` comes BEFORE `ir.model.access.csv` in the `data` list.

### `Field res.config.settings.bigseller_session_cookie must have type 'boolean', 'integer', 'float', 'char'...`
**Cause:** A `config_parameter` field is using `fields.Text` instead of `fields.Char`.  
**Fix:** Change `fields.Text` to `fields.Char` in `res_config_settings.py`.

### `AttributeError: 'NoneType' object has no attribute 'id'`
**Cause:** A finder method returned `None` or empty recordset, and code tries to access `.id`.  
**Fix:** Check the finder method — it should either return a record or raise `ValidationError`.

### `"<SKU>" product is not found.`
**Cause:** Product with that default_code doesn't exist in Odoo.  
**Fix:** Create the product in Inventory > Products first, with matching Internal Reference (SKU).

### BigSeller API returns empty results
**Cause:** Session cookie expired or is invalid.  
**Fix:** Log into bigseller.com again, copy fresh cookies, paste in Settings > BigSeller.

### `KeyError` when accessing BigSeller API response fields
**Cause:** BigSeller changed their API response format.  
**Fix:** Use browser DevTools to capture the current response structure and update the code in `_bigseller_sync_status()`.

---

## 14. Glossary of Odoo Terms

| Term | Simple Explanation |
|---|---|
| `self.env['model.name']` | Access any database table |
| `.search([domain])` | SQL SELECT with WHERE conditions |
| `.create({vals})` | SQL INSERT |
| `.write({vals})` | SQL UPDATE |
| `record.id` | Primary key (integer) |
| `_inherit = 'sale.order'` | Add fields/methods to existing model (no new table) |
| `_name = 'mp.status.history'` | Create a brand new model (new table) |
| `Many2one` | Foreign key (one record points to one parent) |
| `One2many` | Reverse of Many2one (one parent has many children) |
| `Selection` | Dropdown with fixed options |
| `TransientModel` | Temporary wizard (auto-deleted after ~24h) |
| `models.Model` | Permanent database table |
| `config_parameter` | Stores setting value in `ir.config_parameter` table |
| `ir.cron` | Scheduled action (runs periodically) |
| `xpath` | XML path expression to locate elements in inherited views |
| `attrs` | Odoo 16 way to conditionally show/hide/readonly fields |
| `invisible="expr"` | Odoo 18 way to conditionally hide fields |
| `tracking=True` | Log field changes in the chatter message feed |
| `ensure_one()` | Assert that recordset contains exactly 1 record |

---

*Document prepared by RSS for TA-TO project. Last updated: April 2026.*
