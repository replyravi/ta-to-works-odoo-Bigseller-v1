# -*- coding: utf-8 -*-
from odoo import models, fields

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
    _order = 'update_date desc, id desc'

    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order',
        required=True, ondelete='cascade', index=True)
    marketplace = fields.Char(string='Marketplace')
    bigseller_status = fields.Selection(
        BIGSELLER_STATUS_SELECTION, string='BigSeller Status')
    mp_status = fields.Char(string='MP Status')
    odoo_action = fields.Char(string='Odoo Action')
    update_date = fields.Datetime(
        string='Update Date', default=fields.Datetime.now)
    notes = fields.Text(string='Notes')
