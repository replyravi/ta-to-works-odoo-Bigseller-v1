# -*- coding: utf-8 -*-
#
# DEPLOYMENT SWITCH:
#   Odoo 16: set version to '16.0.x.x.x' and use 'views/' paths below.
#   Odoo 18: set version to '18.0.x.x.x' and use 'views_v18/' paths below.
#
# Current: Odoo 18 (views_v18/ — uses invisible="expr" and <list>)
#
{
    'name': 'RSS BigSeller Order V1',
    'version': '18.0.6.0.0',
    'sequence': 5,
    'category': 'Sales',
    'summary': 'BigSeller marketplace order management with API sync and status tracking',
    'description': """
RSS developed this module for TA-TO (Phase 2).

Features:
- Import BigSeller marketplace orders from XLS (Phase 1)
- Marketplace status tracking on Sale Orders
- Status history tab (One2many)
- BigSeller status mapping (New -> QTN, Shipped -> SO, Completed -> Invoice)
- 3 cancellation scenarios
- BigSeller session-based API connector for bidirectional sync
- Auto-create Sale Orders from BigSeller API (auto-sync every 2 minutes)
- JSON Import Wizard: paste BigSeller API response to create orders instantly
- Browser Auto-Sync: Tampermonkey script pushes orders to Odoo every 1 minute
- Odoo 16 / 18 dual compatibility (swap views/ with views_v18/ for Odoo 18)
    """,
    'author': 'RSS',
    'website': 'https://github.com/replyravi/ta-to-works-odoo-Bigseller-v1',
    'depends': [
        'base',
        'sale_management',
        'stock',
        'delivery',
        'account',
    ],
    'data': [
        'security/access_record_rule.xml',
        'security/ir.model.access.csv',
        'views_v18/bigseller_sale_wizard.xml',
        'views_v18/sale_order_view.xml',
        'views_v18/res_config_settings_view.xml',
        'data/bigseller_cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': True,
}
