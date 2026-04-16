# -*- coding: utf-8 -*-
# RSS – BigSeller Order Import V1 for TA-TO (Phase 2)

import logging
import tempfile
import binascii
import xlrd
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError
from odoo import models, fields, exceptions, api, _

_logger = logging.getLogger(__name__)

try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')

# ── BigSeller XLS column indices ──────────────────────────────────────────────
COL_ORDER_NO        = 0
COL_ORDER_STATUS    = 7
COL_MARKETPLACE     = 9
COL_STORE_NICK      = 11
COL_BUYER           = 13
COL_SKU             = 24
COL_QUANTITY        = 31
COL_PRICE           = 32
COL_ORIG_PRICE      = 34
COL_BUYER_LOGISTICS = 52
COL_SHIP_OPTION     = 53
COL_TRACKING        = 55
COL_ORDER_TIME      = 69
COL_SHIPPED_TIME    = 75
COL_CANCEL_REASON   = 79

PROCESS_STATUSES = ('Shipped', 'Canceled', 'Completed')
CANCEL_STATUS    = 'Canceled'

# Map XLS "Order Status" text → mp_status selection key
XLS_STATUS_MAP = {
    'Shipped':   'shipped',
    'Completed': 'completed',
    'Canceled':  'canceled',
    'Cancelled': 'canceled',
    'New':       'new',
    'In Process': 'in_process',
    'Platform Processing': 'platform_processing',
    'To Pickup': 'to_pickup',
    'Retry Ship': 'retry_ship',
    'Voided':    'voided',
}


class GenBigsellerSaleV1(models.TransientModel):
    _name = "gen.bigseller.sale.v1"
    _description = "Import BigSeller Sale Order V1"

    file      = fields.Binary('File')
    file_name = fields.Char('File Name')

    # ── helpers ───────────────────────────────────────────────────────────────

    def _cell(self, row, idx):
        val = row[idx].value
        if isinstance(val, float):
            return str(int(val)) if val == int(val) else str(val)
        return str(val).strip() if val else ''

    def _parse_date(self, raw):
        if not raw:
            return False
        raw = raw.strip()
        try:
            dt = datetime.strptime(raw, "%d %b %Y %H:%M") - timedelta(hours=7)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            raise ValidationError(
                _('Wrong date format "%s". Expected "DD Mon YYYY HH:MM".') % raw)

    # ── finder methods ────────────────────────────────────────────────────────

    def find_company(self, name):
        obj = self.env['res.company']
        rec = obj.search([('name', '=', name)], limit=1)
        return rec if rec else obj.create({'name': name})

    def find_partner(self, name):
        obj = self.env['res.partner']
        rec = obj.search([('name', '=', name), ('is_company', '=', True)], limit=1)
        return rec if rec else obj.create({'name': name, 'is_company': True})

    def find_delivery_address(self, buyer_name, parent_partner):
        obj = self.env['res.partner']
        rec = obj.search([
            ('name', '=', buyer_name),
            ('type', '=', 'delivery'),
            ('parent_id', '=', parent_partner.id),
        ], limit=1)
        if rec:
            return rec
        return obj.create({
            'name': buyer_name,
            'parent_id': parent_partner.id,
            'type': 'delivery',
        })

    def find_delivery_method(self, name):
        if not name:
            return self.env['delivery.carrier'].browse()
        obj = self.env['delivery.carrier']
        return obj.search([('name', '=', name)], limit=1)

    def find_sale_team(self, name):
        obj = self.env['crm.team']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" Sale Team is not available.') % name)

    def find_user(self, name):
        obj = self.env['res.users']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" User is not available.') % name)

    def find_fiscal_position(self, name):
        obj = self.env['account.fiscal.position']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" Fiscal Position is not available.') % name)

    def find_currency(self, name):
        obj = self.env['product.pricelist']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" Pricelist are not available.') % name)

    def find_payment_term(self, name):
        obj = self.env['account.payment.term']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" Payment Term is not available.') % name)

    def find_source(self, name):
        obj = self.env['utm.source']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" Source is not available.') % name)

    def find_warehouse(self, name):
        obj = self.env['stock.warehouse']
        rec = obj.search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_(' "%s" Warehouse is not available.') % name)

    def find_route(self, name):
        if not name:
            return self.env['stock.route'].browse()
        obj = self.env['stock.route']
        return obj.search([('name', '=', name)], limit=1)

    def find_cancel_reason(self, name):
        if not name:
            return False
        if 'sale.order.reason' not in self.env:
            return False
        obj = self.env['sale.order.reason']
        rec = obj.search([('name', '=', name)], limit=1)
        return rec if rec else obj.create({'name': name})

    def find_order_type(self, name):
        if 'sale.order.type' not in self.env:
            _logger.warning(
                'sale_order_type module not installed — skipping order type "%s"', name)
            return False
        obj = self.env['sale.order.type']
        rec = obj.search([('name', '=', name)], limit=1)
        if not rec:
            raise ValidationError(
                _('Sale Order Type "%s" is not configured in Odoo.\n'
                  'Please create it under Sales → Configuration → Order Types '
                  'and fill in: Sales Team, Salesperson, Fiscal Position, Pricelist, '
                  'UTM Source, and Warehouse.') % name)
        required = {
            'sale_team_id':       'Sales Team',
            'user_id':            'Salesperson',
            'fiscal_position_id': 'Fiscal Position',
            'pricelist_id':       'Pricelist',
            'utm_source_id':      'Source',
            'warehouse_id':       'Warehouse',
        }
        missing = [label for field, label in required.items() if not rec[field]]
        if missing:
            raise ValidationError(
                _('Order Type "%s" is missing required fields:\n- %s')
                % (name, '\n- '.join(missing)))
        return rec

    def find_product(self, value):
        obj = self.env['product.product']
        value = str(value).strip()
        rec = obj.search([('default_code', '=', value)], limit=1)
        if not rec:
            raise ValidationError(_('"%s" product is not found.') % value)
        return rec[0]

    # ── order / line creation ─────────────────────────────────────────────────

    def make_order_line(self, values, sale_id):
        product  = self.find_product(values['product'])
        route_id = self.find_route("TATO 21 (MP): Deliver in 1-Step")

        line_vals = {
            'order_id':        sale_id.id,
            'product_id':      product.id,
            'product_uom_qty': float(values.get('quantity') or 1.0),
            'price_unit':      float(values.get('price') or 0.0),
        }
        if route_id:
            line_vals['route_id'] = route_id.id
        disc = float(values.get('discount') or 0.0)
        if disc:
            line_vals['discount'] = disc
        self.env['sale.order.line'].create(line_vals)

    def make_sale(self, values):
        order_name   = values.get('order', '').strip()
        order_status = values.get('state', '')
        is_cancel    = (order_status == CANCEL_STATUS)
        state        = 'cancel' if is_cancel else 'draft'

        if not order_name:
            raise ValidationError(_("Order number is missing in the import file."))

        sale_obj      = self.env['sale.order']
        cancel_reason = self.find_cancel_reason(values.get('cancel_reason'))

        # Phase 2: map XLS status to mp_status selection key
        mp_status_key = XLS_STATUS_MAP.get(order_status, 'new')

        existing = sale_obj.search([('name', '=', order_name)], limit=1)
        if existing:
            if is_cancel and existing.state != 'cancel':
                existing.state = 'cancel'
                if cancel_reason:
                    existing.cancel_reason_id = cancel_reason.id
            # Update MP status if changed
            if existing.mp_status != mp_status_key:
                existing.action_update_mp_status(
                    mp_status_key,
                    mp_status_text=order_status,
                    notes='Updated via XLS import')
            sku = str(values.get('product', '')).strip()
            already_has_sku = any(
                (l.product_id.default_code or '') == sku
                for l in existing.order_line
            )
            if not already_has_sku:
                self.make_order_line(values, existing)
            return existing

        # ── resolve config from col L (store nickname → order type) ──────────
        order_type       = self.find_order_type(values['store_nickname'])
        company_id       = self.find_company(order_type.company_id.name)
        partner_id       = self.find_partner(values['marketplace'])
        partner_shipping = self.find_delivery_address(
            values.get('buyer', 'Unknown'), partner_id)

        team_id          = self.find_sale_team(order_type.sale_team_id.name)
        user_id          = self.find_user(order_type.user_id.name)
        fiscal_id        = self.find_fiscal_position(order_type.fiscal_position_id.name)
        pricelist_id     = self.find_currency(order_type.pricelist_id.name)
        payment_term_id  = self.find_payment_term("BIGSELLER Payment")
        source_id        = self.find_source(order_type.utm_source_id.name)
        warehouse_id     = self.find_warehouse(order_type.warehouse_id.name)
        carrier_id       = (self.find_delivery_method(values.get('carrier_id'))
                            if not is_cancel else self.env['delivery.carrier'].browse())

        sale_id = sale_obj.create({
            'name':                     order_name,
            'company_id':               company_id.id,
            'partner_id':               partner_id.id,
            'partner_shipping_id':      partner_shipping.id,
            'team_id':                  team_id.id,
            'user_id':                  user_id.id,
            'fiscal_position_id':       fiscal_id.id,
            'pricelist_id':             pricelist_id.id,
            'payment_term_id':          payment_term_id.id,
            'source_id':                source_id.id,
            'warehouse_id':             warehouse_id.id,
            'type_id':                  order_type.id,
            'carrier_id':               carrier_id.id if carrier_id else False,
            'date_order':               values.get('date') or False,
            'commitment_date':          values.get('commitment_date') if not is_cancel else False,
            'tracking_reference':       values.get('tracking_reference', ''),
            'cancel_reason_id':         cancel_reason.id if cancel_reason else False,
            'state':                    state,
            'buyer_designed_logistics': values.get('buyer_logistics', ''),
            # Phase 2 fields
            'mp_marketplace':           values.get('marketplace', ''),
            'mp_status':                mp_status_key,
            'mp_last_update':           fields.Datetime.now(),
        })

        # Phase 2: create initial MP status history entry
        self.env['mp.status.history'].create({
            'sale_order_id':   sale_id.id,
            'marketplace':     values.get('marketplace', ''),
            'bigseller_status': mp_status_key,
            'mp_status':       order_status,
            'odoo_action':     'Created Quotation' if not is_cancel else 'Cancelled SO',
            'notes':           'Initial import via XLS',
        })

        self.make_order_line(values, sale_id)
        return sale_id

    # ── main import action ────────────────────────────────────────────────────

    def import_sale(self):
        if not self.file:
            raise UserError(_("Please upload a BigSeller XLS file."))

        try:
            fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xls")
            fp.write(binascii.a2b_base64(self.file))
            fp.seek(0)
            wb = xlrd.open_workbook(fp.name)
            ws = wb.sheet_by_index(0)
        except Exception as e:
            raise exceptions.ValidationError(_("Invalid XLS file: %s") % str(e))

        sale_ids        = []
        return_sale_ids = []

        for row_no in range(1, ws.nrows):
            row    = ws.row(row_no)
            status = self._cell(row, COL_ORDER_STATUS)

            if not status or status == 'Order Status':
                continue
            if status not in PROCESS_STATUSES:
                continue

            order_no        = self._cell(row, COL_ORDER_NO)
            marketplace     = self._cell(row, COL_MARKETPLACE)
            store_nickname  = self._cell(row, COL_STORE_NICK)
            buyer           = self._cell(row, COL_BUYER)
            sku             = self._cell(row, COL_SKU)
            qty_raw         = self._cell(row, COL_QUANTITY)
            price_raw       = self._cell(row, COL_PRICE)
            orig_raw        = self._cell(row, COL_ORIG_PRICE)
            buyer_logistics = self._cell(row, COL_BUYER_LOGISTICS)
            carrier         = self._cell(row, COL_SHIP_OPTION)
            tracking        = self._cell(row, COL_TRACKING)
            order_time      = self._cell(row, COL_ORDER_TIME)
            shipped_time    = self._cell(row, COL_SHIPPED_TIME)
            cancel_rsn      = self._cell(row, COL_CANCEL_REASON)

            order_date = self._parse_date(order_time)
            if not order_date:
                raise ValidationError(
                    _('Order date is missing for order %s') % order_no)
            commitment_date = (self._parse_date(shipped_time)
                               if status != CANCEL_STATUS else False)

            try:
                price      = float(price_raw) if price_raw else 0.0
                orig_price = float(orig_raw)  if orig_raw  else 0.0
                discount   = (round((orig_price - price) / orig_price * 100, 2)
                              if orig_price > 0 else 0.0)
            except Exception:
                price    = 0.0
                discount = 0.0

            values = {
                'order':              order_no,
                'state':              status,
                'marketplace':        marketplace,
                'store_nickname':     store_nickname,
                'buyer':              buyer,
                'product':            sku,
                'quantity':           float(qty_raw) if qty_raw else 1.0,
                'price':              price,
                'discount':           discount,
                'buyer_logistics':    buyer_logistics,
                'carrier_id':         carrier or False,
                'tracking_reference': tracking,
                'date':               order_date,
                'commitment_date':    commitment_date,
                'cancel_reason':      cancel_rsn,
            }

            try:
                sale_id = self.make_sale(values)
                if sale_id and sale_id.id not in return_sale_ids:
                    sale_ids.append(sale_id)
                    return_sale_ids.append(sale_id.id)
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(
                    _('Error processing order %s: %s') % (order_no, str(e)))

        return {
            'type':      'ir.actions.act_window',
            'name':      'Sale Orders',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain':    [('id', 'in', return_sale_ids)],
            'target':    'current',
        }
