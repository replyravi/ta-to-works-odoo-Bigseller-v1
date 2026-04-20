# -*- coding: utf-8 -*-
# RSS – BigSeller JSON Import Wizard
#
# Because BigSeller's JSESSIONID expires within seconds outside a live
# browser, direct API calls from the Odoo backend are unreliable.
# This wizard lets users paste the raw JSON response they capture from
# the BigSeller browser (Network tab) and processes it into Sale Orders.

import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .sale_order import _extract_shop_id, SHOP_ID_TO_ORDER_TYPE

_logger = logging.getLogger(__name__)


class BigSellerJsonImport(models.TransientModel):
    _name = 'bigseller.json.import'
    _description = 'Import BigSeller Orders from JSON'

    json_data = fields.Text(
        string='BigSeller JSON Response',
        required=True,
        help='Paste the full JSON response from BigSeller pageList.json.\n'
             'Capture it from browser DevTools > Network tab > '
             'click pageList.json > Response tab > Select All > Copy.')
    preview_count = fields.Integer(
        string='Orders Found', readonly=True)
    preview_text = fields.Text(
        string='Preview', readonly=True)
    state = fields.Selection([
        ('paste', 'Paste JSON'),
        ('preview', 'Preview'),
    ], default='paste')

    def action_preview(self):
        """Parse the pasted JSON and show a preview of orders to import."""
        self.ensure_one()
        orders = self._extract_orders()
        if not orders:
            raise UserError(_(
                'No orders found in the pasted JSON.\n\n'
                'Make sure you copied the full response from the '
                'pageList.json request in the Network tab.'))

        new_count = 0
        update_count = 0
        skip_count = 0
        filtered_count = 0
        preview_lines = []
        SaleOrder = self.env['sale.order']

        for bs_order in orders:
            order_no = (bs_order.get('platformOrderId') or '').strip()
            if not order_no:
                skip_count += 1
                continue
            shop = bs_order.get('shopName', '')
            shop_id = _extract_shop_id(shop)
            if shop_id and shop_id not in SHOP_ID_TO_ORDER_TYPE:
                filtered_count += 1
                continue
            existing = SaleOrder.search([
                '|',
                ('name', '=', order_no),
                ('bigseller_platform_order_id', '=', order_no),
            ], limit=1)
            status = bs_order.get('state', 'new')
            items = len(bs_order.get('orderItemList', []))
            if existing:
                update_count += 1
                preview_lines.append(
                    '[UPDATE] %s  status=%s  items=%d  shop=%s' % (
                        order_no, status, items, shop))
            else:
                new_count += 1
                preview_lines.append(
                    '[NEW]    %s  status=%s  items=%d  shop=%s' % (
                        order_no, status, items, shop))

        summary = (
            'Total orders in JSON: %d\n'
            'New orders to create: %d\n'
            'Existing orders to update: %d\n'
            'Filtered (shop not in allowlist): %d\n'
            'Skipped (no order number): %d\n'
            '───────────────────────────\n%s'
        ) % (len(orders), new_count, update_count, filtered_count,
             skip_count, '\n'.join(preview_lines[:50]))
        if len(preview_lines) > 50:
            summary += '\n... and %d more' % (len(preview_lines) - 50)

        self.write({
            'preview_count': len(orders),
            'preview_text': summary,
            'state': 'preview',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        """Process the pasted JSON and create/update Sale Orders."""
        self.ensure_one()
        orders = self._extract_orders()
        if not orders:
            raise UserError(_('No orders found in the pasted JSON.'))

        SaleOrder = self.env['sale.order']
        created_ids = []
        updated_count = 0
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
                    changed = self._update_existing_order(
                        existing.sudo(), bs_order)
                    if changed:
                        updated_count += 1
                else:
                    new_order = SaleOrder.sudo()._bigseller_create_order(
                        bs_order)
                    if new_order:
                        created_ids.append(new_order.id)
                self.env.cr.commit()
            except Exception as e:
                self.env.cr.rollback()
                errors.append('%s: %s' % (order_no, str(e)))
                _logger.error('JSON import error for %s: %s', order_no, e)

        if errors and not created_ids and not updated_count:
            raise UserError(_(
                'Import failed for all orders:\n%s') % '\n'.join(errors[:20]))

        msg_parts = []
        if created_ids:
            msg_parts.append(_('%d orders created') % len(created_ids))
        if updated_count:
            msg_parts.append(_('%d orders updated') % updated_count)
        if errors:
            msg_parts.append(_('%d errors (check logs)') % len(errors))
        if not msg_parts:
            msg_parts.append(_('No new or changed orders'))

        all_ids = created_ids
        if not all_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('JSON Import Complete'),
                    'message': ' | '.join(msg_parts),
                    'type': 'success' if created_ids else 'warning',
                    'sticky': True,
                },
            }

        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported BigSeller Orders'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', all_ids)],
            'target': 'current',
        }

    def action_back(self):
        """Go back to paste step."""
        self.write({'state': 'paste', 'preview_text': '', 'preview_count': 0})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _extract_orders(self):
        """Parse the pasted JSON and extract the list of order dicts.

        Supports:
        - Full API response: {"code":0, "data":{"page":{"rows":[...]}}}
        - Just the rows array: [{"platformOrderId":"..."}, ...]
        - Multiple responses pasted together (array of responses)
        """
        raw = (self.json_data or '').strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise UserError(_(
                'Invalid JSON. Make sure you copied the complete response '
                'from the Network tab.\n\nParse error: %s') % str(e))

        if isinstance(parsed, list):
            if parsed and isinstance(parsed[0], dict):
                if 'platformOrderId' in parsed[0]:
                    return parsed
                all_orders = []
                for item in parsed:
                    all_orders.extend(self._rows_from_response(item))
                return all_orders

        if isinstance(parsed, dict):
            return self._rows_from_response(parsed)

        return []

    @staticmethod
    def _rows_from_response(resp):
        """Extract rows list from a single BigSeller API response dict."""
        if not isinstance(resp, dict):
            return []
        data = resp.get('data')
        if not data or not isinstance(data, dict):
            return []
        page = data.get('page')
        if not page or not isinstance(page, dict):
            return []
        return page.get('rows') or []

    def _update_existing_order(self, order, bs_order):
        """Update an existing order's status and BigSeller fields.

        Returns True if anything changed.
        """
        changed = False
        SaleOrder = self.env['sale.order']
        update_vals = {}

        bs_status = SaleOrder._map_bigseller_status(
            bs_order.get('state', 'new'))
        if order.mp_status != bs_status:
            order.action_update_mp_status(
                bs_status,
                notes='Updated via JSON import')
            changed = True

        bs_id = str(bs_order.get('id', ''))
        if bs_id and not order.bigseller_order_id:
            update_vals['bigseller_order_id'] = bs_id

        shop_name = bs_order.get('shopName', '')
        if shop_name and not order.bigseller_shop_name:
            update_vals['bigseller_shop_name'] = shop_name

        order_no = (bs_order.get('platformOrderId') or '').strip()
        if order_no and not order.client_order_ref:
            update_vals['client_order_ref'] = order_no

        platform = (bs_order.get('viewPlatfrom')
                    or bs_order.get('platform', ''))
        s_name = shop_name or order.bigseller_shop_name or ''
        order_type = SaleOrder._bigseller_resolve_order_type(platform, s_name)
        if order_type and (
            not getattr(order, 'type_id', None)
            or not order.type_id
            or order.type_id.id != order_type.id
        ):
            SaleOrder._bigseller_apply_order_type(update_vals, order_type)

        if 'partner_id' not in update_vals and platform and (
            not order.partner_id.is_company
            or order.partner_id.name.lower() not in (
                'lazada', 'shopee', 'tiktok', 'bigseller')
        ):
            platform_partner = SaleOrder._bigseller_get_or_create_partner(
                platform)
            update_vals['partner_id'] = platform_partner.id

        buyer_name = (
            bs_order.get('buyerUsername')
            or bs_order.get('contactPerson')
            or ''
        )
        if buyer_name and 'partner_id' in update_vals:
            partner_rec = self.env['res.partner'].browse(
                update_vals['partner_id'])
            delivery = SaleOrder._bigseller_get_or_create_delivery_address(
                buyer_name, partner_rec)
            update_vals['partner_shipping_id'] = delivery.id

        if update_vals:
            order.write(update_vals)
            changed = True

        return changed
