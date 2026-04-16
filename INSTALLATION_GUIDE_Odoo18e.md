# RSS BigSeller Order V1 — Installation Guide for Odoo 18.0+e (Enterprise)

**Target Server:** `https://tatov16-staging-vct-30308428.dev.odoo.com`
**Module:** `rss_bigseller_order_v1`
**Version:** 18.0.4.0.0

---

## Prerequisites

- Odoo 18.0+e (Enterprise Edition) running instance
- Admin or developer access to the Odoo server
- SSH/SFTP access to the server file system (or Odoo.sh shell access)
- The following Odoo modules must be installed:
  - `sale_management` (Sales)
  - `stock` (Inventory)
  - `delivery` (Delivery/Shipping)
  - `account` (Accounting/Invoicing)

---

## Step 1: Get the Module Code

### Option A: Clone from GitHub

```bash
cd /path/to/odoo/custom-addons/
git clone https://github.com/replyravi/ta-to-works-odoo-Bigseller-v1.git rss_bigseller_order_v1
```

### Option B: Upload via SFTP/Odoo.sh

1. Download the module folder `rss_bigseller_order_v1` from the repository
2. Upload the entire folder to your Odoo custom addons directory:
   - **Odoo.sh:** `/home/odoo/src/user/rss_bigseller_order_v1/`
   - **Self-hosted:** Your `custom-addons/` path configured in `odoo.conf`

---

## Step 2: Verify the Manifest is Set for Odoo 18

Open `__manifest__.py` and confirm:

```python
'version': '18.0.4.0.0',   # Must start with 18.0
```

And the `data` section must use `views_v18/` paths (NOT `views/`):

```python
'data': [
    'security/access_record_rule.xml',
    'security/ir.model.access.csv',
    'views_v18/bigseller_sale_wizard.xml',     # ← views_v18, NOT views
    'views_v18/sale_order_view.xml',           # ← views_v18
    'views_v18/res_config_settings_view.xml',  # ← views_v18
    'data/bigseller_cron.xml',
],
```

Also confirm `depends` does NOT include `sale_order_type` or `sale_order_type_ext` (unless they are installed on your server):

```python
'depends': [
    'base',
    'sale_management',  # NOT 'sale' — Odoo 18e uses sale_management
    'stock',
    'delivery',
    'account',
],
```

---

## Step 3: Add to Addons Path

### For Odoo.sh:
The `/home/odoo/src/user/` directory is automatically in the addons path.

### For Self-hosted:
Edit `odoo.conf` and ensure the folder containing `rss_bigseller_order_v1` is in `addons_path`:

```ini
addons_path = /path/to/odoo/addons,/path/to/custom-addons
```

Restart Odoo after changing `odoo.conf`.

---

## Step 4: Update Apps List

1. Log into Odoo as **Administrator**
2. Enable **Developer Mode**: Settings → General Settings → scroll to bottom → click "Activate the developer mode"
3. Go to **Apps** menu
4. Click **Update Apps List** (top menu) → click **Update**
5. Wait for the list to refresh

---

## Step 5: Install the Module

1. In the Apps list, search for **"BigSeller"** or **"RSS BigSeller"**
2. You should see: **RSS BigSeller Order V1**
3. Click **Install**
4. Wait for installation to complete (it will also install any missing dependencies)

### Troubleshooting Installation

| Error | Solution |
|-------|----------|
| `Module not found in apps list` | Check addons_path includes the parent folder, then Update Apps List again |
| `Module sale_order_type not found` | Remove `sale_order_type` and `sale_order_type_ext` from `depends` in `__manifest__.py` |
| `Field ... does not exist` | Make sure you're using `views_v18/` paths in manifest, NOT `views/` |
| `ParseError invisible` | You're loading Odoo 16 views on Odoo 18. Switch to `views_v18/` |

---

## Step 6: Post-Installation Verification

After installation, verify these work:

### 6.1 Check the Settings Page
1. Go to **Settings → BigSeller** (in the left sidebar)
2. You should see:
   - BigSeller API Configuration section
   - Browser Auto-Sync section with "Generate Token" button
   - Quick JSON Import section

### 6.2 Check the Menu Items
1. Go to **Sales → Orders**
2. You should see two extra menu items:
   - **Import BigSeller Sale Order V1 (XLS)** — Phase 1 XLS import
   - **Import BigSeller Orders (JSON)** — JSON import wizard

### 6.3 Check Sale Order Form
1. Open any Sale Order
2. If it has marketplace data, you should see:
   - **Marketplace** group in the header
   - **MP Status** tab in the notebook

---

## Step 7: Configure the Browser Auto-Sync

This is the recommended method to sync orders from BigSeller.

### 7.1 Generate a Token
1. Go to **Settings → BigSeller**
2. Scroll to "Browser Auto-Sync"
3. Click **"Generate Token"**
4. Copy the generated token string

### 7.2 Set Up the Console Script
1. Open **bigseller.com** in your browser (log in)
2. Press **F12** to open DevTools → **Console** tab
3. Paste the auto-sync script (see below) and press Enter

Replace `ODOO_URL`, `DB`, and `TOKEN` with your actual values:

```javascript
(function(){
  var ODOO='https://tatov16-staging-vct-30308428.dev.odoo.com',
      DB='tatov16-staging-vct-30308428',
      TOKEN='PASTE_YOUR_TOKEN_HERE';
  var b=document.getElementById('odoo-sync')||document.createElement('div');
  b.id='odoo-sync';
  b.style.cssText='position:fixed;bottom:20px;right:20px;z-index:999999;background:#2c3e50;color:#ecf0f1;padding:12px 20px;border-radius:10px;font:bold 14px Arial;box-shadow:0 4px 15px rgba(0,0,0,0.4);cursor:pointer';
  if(!b.parentNode)document.body.appendChild(b);
  function ui(t,c){b.textContent=t;b.style.background=c||'#2c3e50'}
  ui('Odoo Sync: Starting...');
  async function fetchPage(status,page){
    var r=await fetch('/api/v1/order/'+status+'/pageList.json',{
      method:'POST',headers:{'Content-Type':'application/json',clienttype:'1'},
      body:JSON.stringify({status:status,searchType:'orderNo',pageNo:page,allOrder:false,historyOrder:false,packState:'0',desc:0,orderBy:'expireTime'})
    });return r.json()
  }
  async function fetchAll(status){
    var d=await fetchPage(status,1);var rows=((d.data||{}).page||{}).rows||[];
    var total=((d.data||{}).page||{}).totalSize||0;
    if(!rows.length)return[];
    var pages=Math.ceil(total/rows.length);
    for(var p=2;p<=Math.min(pages,10);p++){var d2=await fetchPage(status,p);rows=rows.concat(((d2.data||{}).page||{}).rows||[])}
    return rows
  }
  function push(rows){
    return new Promise(function(ok,fail){
      var x=new XMLHttpRequest();x.open('POST',ODOO+'/bigseller/auto_import');
      x.setRequestHeader('Content-Type','application/json');
      x.onload=function(){try{ok(JSON.parse(x.responseText))}catch(e){fail(e)}};
      x.onerror=function(){fail(new Error('Cannot reach Odoo'))};
      x.send(JSON.stringify({token:TOKEN,db:DB,orders_data:{code:0,data:{page:{rows:rows,totalSize:rows.length}}}}))
    })
  }
  async function sync(){
    ui('Syncing...','#f39c12');
    try{
      var all=await fetchAll('new');
      if(!all.length){ui('No new orders | '+new Date().toLocaleTimeString().slice(0,5),'#27ae60');return}
      var r=await push(all);
      if(r.error){ui('Error: '+r.error,'#e74c3c')}
      else{ui('+'+r.created+' new, '+r.updated+' upd (of '+all.length+') | '+new Date().toLocaleTimeString().slice(0,5),'#27ae60')}
    }catch(e){ui('Error: '+e.message,'#e74c3c')}
  }
  b.onclick=sync;sync();setInterval(sync,60000);
  console.log('Auto-Sync started! Badge at bottom-right.')
})()
```

### 7.3 What to Expect
- A **dark badge** appears at the bottom-right of BigSeller
- It syncs orders every **1 minute** automatically
- Click the badge to sync immediately
- Shows: `+5 new, 0 upd (of 89) | 22:15`

---

## Step 8: Switching Back to Odoo 16

If you need to deploy on Odoo 16 instead:

1. Edit `__manifest__.py`:
   - Change `version` to `'16.0.4.0.0'`
   - Change `'sale_management'` to `'sale'` in depends
   - Replace all `views_v18/` with `views/` in the data section
   - Optionally add `'sale_order_type'` and `'sale_order_type_ext'` to depends

2. Restart Odoo and upgrade the module

---

## File Structure Reference

```
rss_bigseller_order_v1/
├── __init__.py
├── __manifest__.py              ← Edit this for v16/v18 switch
├── compat.py                    ← Version detection helper
├── controllers/
│   ├── __init__.py
│   └── bigseller_webhook.py     ← Auto-sync webhook endpoint
├── data/
│   └── bigseller_cron.xml       ← Scheduled sync job (disabled by default)
├── models/
│   ├── __init__.py
│   ├── bigseller_api.py         ← BigSeller API client
│   ├── bigseller_json_import.py ← JSON import wizard logic
│   ├── bigseller_sale.py        ← XLS import wizard (Phase 1)
│   ├── mp_status_history.py     ← Status history model
│   ├── res_config_settings.py   ← Settings page fields
│   └── sale_order.py            ← Sale Order extensions + sync
├── security/
│   ├── access_record_rule.xml   ← Security group definition
│   └── ir.model.access.csv      ← Model access rights
├── static/
│   └── src/tampermonkey/
│       └── bigseller_odoo_sync.user.js  ← Tampermonkey script
├── views/                       ← Odoo 16 views (attrs syntax)
│   ├── bigseller_sale_wizard.xml
│   ├── res_config_settings_view.xml
│   └── sale_order_view.xml
└── views_v18/                   ← Odoo 18 views (invisible= syntax)
    ├── bigseller_sale_wizard.xml
    ├── res_config_settings_view.xml
    └── sale_order_view.xml
```
