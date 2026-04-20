# -*- coding: utf-8 -*-
import json
import logging

import odoo
from odoo import http, SUPERUSER_ID, api
from odoo.http import request, Response
from odoo.addons.rss_bigseller_order_v1.models.sale_order import (
    _extract_shop_id, SHOP_ID_TO_ORDER_TYPE,
)

_logger = logging.getLogger(__name__)


def _get_registry(db_name):
    """Get database registry - compatible with Odoo 16, 17, and 18."""
    try:
        return odoo.registry(db_name)
    except (AttributeError, TypeError):
        return http.Registry(db_name)


class BigSellerWebhook(http.Controller):
    """Webhook controller that receives BigSeller order data from the
    browser auto-sync script and imports it into Odoo automatically."""

    @http.route('/bigseller/auto_import', type='http', auth='none',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def auto_import(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return Response(status=200)

        try:
            body = json.loads(request.httprequest.get_data(as_text=True))
        except Exception:
            return self._resp({'error': 'Invalid JSON body'}, 400)

        token = body.get('token', '')
        db_name = body.get('db', '')
        orders_data = body.get('orders_data')

        if not token or not db_name:
            return self._resp({'error': 'Missing token or db'}, 400)
        if not orders_data:
            return self._resp({'error': 'Missing orders_data'}, 400)

        try:
            registry = _get_registry(db_name)
        except Exception:
            return self._resp({'error': 'Database not found'}, 400)

        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            stored_token = env['ir.config_parameter'].get_param(
                'bigseller.auto_sync_token', '')
            if not stored_token or token != stored_token:
                return self._resp({'error': 'Invalid token'}, 403)

            return self._process_orders(env, orders_data)

    def _process_orders(self, env, orders_data):
        raw = json.dumps(orders_data) if isinstance(
            orders_data, (dict, list)) else str(orders_data)

        wizard = env['bigseller.json.import'].create({'json_data': raw})
        try:
            orders = wizard._extract_orders()
        except Exception as e:
            return self._resp({'error': str(e)}, 400)

        if not orders:
            return self._resp({
                'created': 0, 'updated': 0,
                'message': 'No orders in payload'})

        SaleOrder = env['sale.order']
        created = updated = 0
        errors = []

        for bs_order in orders:
            order_no = (bs_order.get('platformOrderId') or '').strip()
            if not order_no:
                continue
            shop = bs_order.get('shopName', '')
            shop_id = _extract_shop_id(shop)
            if shop_id and shop_id not in SHOP_ID_TO_ORDER_TYPE:
                continue
            try:
                existing = SaleOrder.search([
                    '|',
                    ('name', '=', order_no),
                    ('bigseller_platform_order_id', '=', order_no),
                ], limit=1)
                if existing:
                    if wizard._update_existing_order(existing, bs_order):
                        updated += 1
                else:
                    new_so = SaleOrder._bigseller_create_order(bs_order)
                    if new_so:
                        created += 1
                env.cr.commit()
            except Exception as e:
                env.cr.rollback()
                errors.append('%s: %s' % (order_no, e))
                _logger.error('Auto-import error for %s: %s', order_no, e)

        return self._resp({
            'created': created,
            'updated': updated,
            'errors': len(errors),
            'message': 'Created %d, updated %d, errors %d' % (
                created, updated, len(errors)),
        })

    @staticmethod
    def _resp(data, status=200):
        return Response(
            json.dumps(data),
            content_type='application/json',
            status=status)
