// ==UserScript==
// @name         BigSeller → Odoo Auto Sync
// @namespace    https://github.com/replyravi/ta-to-works-odoo-Bigseller-v1
// @version      1.0.0
// @description  Automatically fetches BigSeller orders every 1 minute and pushes them to Odoo
// @author       RSS (Ravi Singh)
// @match        https://www.bigseller.com/*
// @match        https://bigseller.com/*
// @grant        GM_xmlhttpRequest
// @connect      *
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ╔══════════════════════════════════════════════════╗
    // ║  CONFIGURATION — Edit these 3 values            ║
    // ╚══════════════════════════════════════════════════╝
    const ODOO_URL   = 'http://localhost:8069';          // Your Odoo URL (no trailing slash)
    const ODOO_DB    = 'tato';                           // Your Odoo database name
    const SYNC_TOKEN = 'PASTE_YOUR_TOKEN_HERE';          // From Odoo Settings → BigSeller → Generate Token
    // ────────────────────────────────────────────────────
    const SYNC_INTERVAL_MS = 60 * 1000; // 1 minute
    const ORDER_STATUSES   = ['new'];   // Add 'shipping','completed','canceled' if needed

    let syncInProgress = false;

    // ── Floating status badge ──────────────────────────
    const badge = document.createElement('div');
    badge.id = 'odoo-sync-badge';
    Object.assign(badge.style, {
        position: 'fixed', bottom: '20px', right: '20px', zIndex: '99999',
        background: '#2c3e50', color: '#ecf0f1',
        padding: '10px 18px', borderRadius: '10px',
        fontSize: '13px', fontFamily: 'Arial, sans-serif',
        boxShadow: '0 4px 14px rgba(0,0,0,0.35)', cursor: 'pointer',
        transition: 'background 0.3s, transform 0.15s',
        userSelect: 'none',
    });
    badge.title = 'Click to sync now';
    badge.addEventListener('mouseenter', () => { badge.style.transform = 'scale(1.05)'; });
    badge.addEventListener('mouseleave', () => { badge.style.transform = 'scale(1)'; });
    document.body.appendChild(badge);

    function ui(text, bg) {
        badge.textContent = text;
        badge.style.background = bg || '#2c3e50';
    }
    ui('\u23F3 Odoo Sync: starting\u2026');

    // ── Fetch orders from BigSeller (same-origin) ──────
    async function fetchOrders(status) {
        const resp = await fetch('/api/v1/order/' + status + '/pageList.json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'clienttype': '1' },
            body: JSON.stringify({
                status: status,
                searchType: 'orderNo',
                pageNo: 1,
                allOrder: false,
                historyOrder: false,
                packState: '0',
                desc: 0,
                orderBy: 'expireTime',
            }),
        });
        return resp.json();
    }

    // ── Send to Odoo via webhook (GM_xmlhttpRequest bypasses CORS) ──
    function pushToOdoo(ordersData) {
        return new Promise(function (resolve, reject) {
            GM_xmlhttpRequest({
                method: 'POST',
                url: ODOO_URL + '/bigseller/auto_import',
                headers: { 'Content-Type': 'application/json' },
                data: JSON.stringify({
                    token: SYNC_TOKEN,
                    db: ODOO_DB,
                    orders_data: ordersData,
                }),
                timeout: 30000,
                onload: function (r) {
                    try { resolve(JSON.parse(r.responseText)); }
                    catch (_) { reject(new Error('Bad response from Odoo (' + r.status + ')')); }
                },
                onerror: function () { reject(new Error('Cannot reach Odoo at ' + ODOO_URL)); },
                ontimeout: function () { reject(new Error('Odoo request timed out')); },
            });
        });
    }

    // ── Main sync loop ─────────────────────────────────
    async function doSync() {
        if (syncInProgress) return;
        syncInProgress = true;
        ui('\u23F3 Syncing\u2026', '#f39c12');

        try {
            let allRows = [];
            for (const status of ORDER_STATUSES) {
                const data = await fetchOrders(status);
                const rows = ((data.data || {}).page || {}).rows || [];
                allRows = allRows.concat(rows);
            }

            if (allRows.length === 0) {
                ui('\u2705 No new orders | ' + ts(), '#27ae60');
                syncInProgress = false;
                return;
            }

            const wrapper = { code: 0, data: { page: { rows: allRows, totalSize: allRows.length } } };
            const result = await pushToOdoo(wrapper);

            if (result.error) {
                ui('\u274C ' + result.error, '#e74c3c');
            } else {
                ui('\u2705 +' + (result.created || 0) + ' new, ' +
                   (result.updated || 0) + ' upd | ' + ts(), '#27ae60');
            }
        } catch (err) {
            ui('\u274C ' + err.message, '#e74c3c');
            console.error('[Odoo Sync]', err);
        }

        syncInProgress = false;
    }

    function ts() {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    badge.addEventListener('click', doSync);

    // Validate config before starting
    if (SYNC_TOKEN === 'PASTE_YOUR_TOKEN_HERE') {
        ui('\u26A0\uFE0F Set SYNC_TOKEN in Tampermonkey script!', '#e74c3c');
    } else {
        doSync();
        setInterval(doSync, SYNC_INTERVAL_MS);
    }
})();
