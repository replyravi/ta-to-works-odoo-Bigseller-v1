# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .mp_status_history import BIGSELLER_STATUS_SELECTION

_logger = logging.getLogger(__name__)

STATUS_ACTION_MAP = {
    'new': 'Created Quotation',
    'in_process': None,
    'platform_processing': None,
    'to_pickup': 'Confirmed SO + Confirm Delivery',
    'retry_ship': None,
    'shipped': 'Confirmed SO + Confirm Delivery',
    'completed': 'Created Invoice + Posted',
    'canceled': 'Cancelled SO',
    'voided': None,
}


class SaleOrderBigSellerV1(models.Model):
    _inherit = 'sale.order'

    buyer_designed_logistics = fields.Char(string='Buyer Designed Logistics')
    mp_marketplace = fields.Char(string='Marketplace', tracking=True)
    mp_status = fields.Selection(
        BIGSELLER_STATUS_SELECTION, string='MP Status',
        tracking=True, copy=False)
    mp_last_update = fields.Datetime(
        string='MP Last Update', copy=False, tracking=True)
    mp_status_history_ids = fields.One2many(
        'mp.status.history', 'sale_order_id',
        string='MP Status History')
    bigseller_order_id = fields.Char(
        string='BigSeller ID', copy=False, index=True,
        help='Internal BigSeller order ID for API linking')
    bigseller_shop_name = fields.Char(
        string='BigSeller Shop', copy=False)
    bigseller_platform_order_id = fields.Char(
        string='Platform Order ID', copy=False, index=True)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def action_update_mp_status(self, new_status, mp_status_text='', notes=''):
        """Update marketplace status and trigger the corresponding ODOO action.

        :param new_status: selection key from BIGSELLER_STATUS_SELECTION
        :param mp_status_text: freeform marketplace-specific status text
        :param notes: optional notes for the history record
        """
        self.ensure_one()
        odoo_action = STATUS_ACTION_MAP.get(new_status)

        self.env['mp.status.history'].create({
            'sale_order_id': self.id,
            'marketplace': self.mp_marketplace or '',
            'bigseller_status': new_status,
            'mp_status': mp_status_text or dict(BIGSELLER_STATUS_SELECTION).get(new_status, ''),
            'odoo_action': odoo_action or 'No action',
            'notes': notes,
        })

        self.write({
            'mp_status': new_status,
            'mp_last_update': fields.Datetime.now(),
        })

        if new_status in ('to_pickup', 'shipped'):
            self._mp_confirm_and_deliver()
        elif new_status == 'completed':
            self._mp_create_invoice()
        elif new_status == 'canceled':
            self.action_cancel_mp_order()

    def _mp_confirm_and_deliver(self):
        """Confirm quotation → SO and validate deliveries if possible."""
        self.ensure_one()
        if self.state == 'draft':
            try:
                self.action_confirm()
            except Exception as e:
                _logger.warning('Could not confirm SO %s: %s', self.name, e)
                return
        for picking in self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
            try:
                picking.action_assign()
                for move_line in picking.move_line_ids:
                    move_line.qty_done = move_line.reserved_uom_qty
                picking.button_validate()
            except Exception as e:
                _logger.warning('Could not validate picking %s: %s', picking.name, e)

    def _mp_create_invoice(self):
        """Create and post invoice when status reaches Completed."""
        self.ensure_one()
        if self.state == 'draft':
            self._mp_confirm_and_deliver()
        if self.invoice_status != 'to invoice':
            return
        try:
            invoice = self._create_invoices()
            for inv in invoice:
                inv.action_post()
        except Exception as e:
            _logger.warning('Could not create invoice for SO %s: %s', self.name, e)

    # ------------------------------------------------------------------
    # Cancellation scenarios (Issue-101)
    # ------------------------------------------------------------------

    def action_cancel_mp_order(self):
        """Handle 3 cancellation scenarios based on picking state.

        Scenario 1: Not yet picked → Cancel SO + deliveries
        Scenario 2: Picked, not shipped → Reverse pick step 1, then cancel
        Scenario 3: Already shipped → Mark as return flow (manual credit note)
        """
        self.ensure_one()
        pickings = self.picking_ids

        done_pickings = pickings.filtered(lambda p: p.state == 'done')
        assigned_pickings = pickings.filtered(lambda p: p.state == 'assigned')

        if done_pickings:
            # Scenario 3: goods already shipped
            self._mp_log_history(
                'canceled',
                'Return flow – manual credit note required',
                'Goods already shipped. Return/refund handled manually.')
            return

        if assigned_pickings:
            # Scenario 2: picked but not shipped – reverse
            for picking in assigned_pickings:
                try:
                    picking.action_cancel()
                except Exception as e:
                    _logger.warning('Could not cancel picking %s: %s', picking.name, e)
            self._mp_log_history(
                'canceled',
                'Reversed picking + Cancelled SO',
                'Picked goods returned to stock, SO cancelled.')

        else:
            # Scenario 1: nothing picked
            self._mp_log_history(
                'canceled',
                'Cancelled SO + Deliveries',
                'No picking done yet, clean cancel.')

        # Cancel remaining non-done pickings
        for picking in pickings.filtered(lambda p: p.state not in ('done', 'cancel')):
            try:
                picking.action_cancel()
            except Exception:
                pass

        if self.state not in ('cancel', 'done'):
            try:
                self.action_cancel()
            except Exception as e:
                _logger.warning('Could not cancel SO %s: %s', self.name, e)

    def _mp_log_history(self, status, action_text, notes=''):
        """Convenience to create a status history entry."""
        self.env['mp.status.history'].create({
            'sale_order_id': self.id,
            'marketplace': self.mp_marketplace or '',
            'bigseller_status': status,
            'mp_status': dict(BIGSELLER_STATUS_SELECTION).get(status, ''),
            'odoo_action': action_text,
            'notes': notes,
        })

    # ------------------------------------------------------------------
    # BigSeller API sync helpers
    # ------------------------------------------------------------------

    def _bigseller_sync_orders(self, manual=False):
        """Cron entry point: sync orders from BigSeller API.

        :param manual: if True, bypass sync_enabled check (Sync Now button)
        :return: dict with 'created' and 'updated' counts
        """
        self = self.sudo()
        ICP = self.env['ir.config_parameter'].sudo()

        if not manual and ICP.get_param('bigseller.sync_enabled', 'False') != 'True':
            return {'created': 0, 'updated': 0}

        cookie = ICP.get_param('bigseller.session_cookie', '')
        base_url = ICP.get_param('bigseller.base_url', 'https://www.bigseller.com')
        if not cookie:
            ICP.set_param('bigseller.last_sync_error',
                          'No session cookie configured. Go to Settings > '
                          'BigSeller and paste your cookie.')
            return {'created': 0, 'updated': 0}

        from .bigseller_api import BigSellerClient
        client = BigSellerClient(base_url, cookie)

        if not client.test_connection():
            _logger.error('BigSeller sync: session expired or invalid.')
            ICP.set_param('bigseller.last_sync_error',
                          'Session expired or invalid. Please paste a fresh cookie.')
            return {'created': 0, 'updated': 0}

        created_count = 0
        updated_count = 0
        errors = []
        for status in ('new', 'shipped', 'completed', 'canceled'):
            try:
                c, u = self._bigseller_sync_status(client, status)
                created_count += c
                updated_count += u
            except Exception as e:
                _logger.error('BigSeller sync error for status %s: %s', status, e)
                errors.append('%s: %s' % (status, e))

        ICP.set_param('bigseller.last_sync', fields.Datetime.now())
        if errors:
            ICP.set_param('bigseller.last_sync_error', '; '.join(errors))
        else:
            ICP.set_param('bigseller.last_sync_error', '')
        _logger.info(
            'BigSeller sync complete: %d created, %d updated',
            created_count, updated_count)
        return {'created': created_count, 'updated': updated_count}

    def _bigseller_sync_status(self, client, status):
        """Fetch orders with given status from BigSeller and sync to Odoo.

        Returns (created_count, updated_count) tuple.
        """
        page = 1
        created = 0
        updated = 0
        auto_create = self.env['ir.config_parameter'].sudo().get_param(
            'bigseller.auto_create_orders', 'True') == 'True'

        while True:
            data = client.get_orders(status=status, page=page, page_size=100)

            api_code = data.get('code')
            if api_code is not None and api_code != 0:
                _logger.error(
                    'BigSeller API error for status %s: code=%s msg=%s',
                    status, api_code, data.get('msg', ''))
                break

            resp_data = data.get('data') or {}
            page_data = (resp_data.get('page') or {}) if isinstance(resp_data, dict) else {}
            orders = (page_data.get('rows') or []) if isinstance(page_data, dict) else []
            if not orders:
                _logger.info(
                    'BigSeller sync status=%s: no orders returned (page=%d)',
                    status, page)
                break

            _logger.info(
                'BigSeller sync status=%s: processing %d orders (page %d)',
                status, len(orders), page)

            for bs_order in orders:
                order_no = (bs_order.get('platformOrderId') or '').strip()
                if not order_no:
                    continue

                existing = self.search([
                    '|',
                    ('name', '=', order_no),
                    ('bigseller_platform_order_id', '=', order_no),
                ], limit=1)

                if existing:
                    bs_status = self._map_bigseller_status(
                        bs_order.get('state', status))
                    changed = False
                    if existing.mp_status != bs_status:
                        existing.action_update_mp_status(
                            bs_status,
                            notes='Auto-synced from BigSeller API')
                        changed = True
                    bs_id = str(bs_order.get('id', ''))
                    if bs_id and not existing.bigseller_order_id:
                        existing.write({'bigseller_order_id': bs_id})
                        changed = True
                    if changed:
                        updated += 1
                elif auto_create:
                    try:
                        self._bigseller_create_order(bs_order)
                        created += 1
                        self.env.cr.commit()
                    except Exception as e:
                        self.env.cr.rollback()
                        _logger.error(
                            'Failed to create order %s: %s', order_no, e)

            total = page_data.get('totalSize', 0) if isinstance(page_data, dict) else 0
            if page * 100 >= total:
                break
            page += 1

        return created, updated

    # ------------------------------------------------------------------
    # Auto-create Sale Orders from BigSeller API data
    # ------------------------------------------------------------------

    def _bigseller_create_order(self, bs_order):
        """Create a new Sale Order from a BigSeller API order dict."""
        order_no = bs_order.get('platformOrderId', '')
        buyer_name = (
            bs_order.get('buyerUsername')
            or bs_order.get('contactPerson')
            or 'BigSeller Customer'
        )
        platform = bs_order.get('viewPlatfrom') or bs_order.get('platform', '')
        shop_name = bs_order.get('shopName', '')
        state = bs_order.get('state', 'new')
        currency_code = bs_order.get('amountUnit', 'THB')

        partner = self._bigseller_get_or_create_partner(buyer_name)
        currency = self.env['res.currency'].search(
            [('name', '=ilike', currency_code)], limit=1)

        order_lines = []
        for item in bs_order.get('orderItemList', []):
            sku = (item.get('varSku') or '').strip()
            qty = item.get('quantity', 1)
            price = self._bigseller_parse_price(item)
            product = self._bigseller_get_or_create_product(sku, item)
            line_name = product.display_name
            attr = (item.get('varAttr') or '').strip()
            if attr:
                line_name = f'{line_name} ({attr})'
            order_lines.append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'price_unit': price,
                'name': line_name,
            }))

        vals = {
            'name': order_no,
            'partner_id': partner.id,
            'mp_marketplace': platform,
            'mp_status': self._map_bigseller_status(state),
            'mp_last_update': fields.Datetime.now(),
            'buyer_designed_logistics': bs_order.get('buyerShippingCarrier', ''),
            'bigseller_order_id': str(bs_order.get('id', '')),
            'bigseller_shop_name': shop_name,
            'bigseller_platform_order_id': order_no,
        }
        if currency:
            vals['currency_id'] = currency.id
        if order_lines:
            vals['order_line'] = order_lines

        order = self.create(vals)

        order._mp_log_history(
            vals['mp_status'],
            'Auto-created from BigSeller API',
            'Shop: %s | Platform: %s | BS-ID: %s' % (
                shop_name, platform, bs_order.get('id', '')))

        bs_status = self._map_bigseller_status(state)
        if bs_status in ('to_pickup', 'shipped'):
            order._mp_confirm_and_deliver()
        elif bs_status == 'completed':
            order._mp_confirm_and_deliver()
            order._mp_create_invoice()
        elif bs_status == 'canceled':
            order.action_cancel_mp_order()

        _logger.info(
            'Created SO %s from BigSeller (platform=%s, status=%s)',
            order.name, platform, state)
        return order

    def _bigseller_get_or_create_partner(self, name):
        """Find an existing partner by name or create a new one."""
        Partner = self.env['res.partner']
        partner = Partner.search([('name', '=ilike', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'customer_rank': 1,
                'comment': 'Auto-created by BigSeller API sync',
            })
            _logger.info('Created partner: %s', name)
        return partner

    def _bigseller_get_or_create_product(self, sku, item_data):
        """Find product by SKU (default_code) or create a placeholder."""
        Product = self.env['product.product']
        if sku:
            product = Product.search(
                [('default_code', '=', sku)], limit=1)
            if product:
                return product

        product_name = (
            item_data.get('itemName')
            or item_data.get('vName')
            or sku
            or 'BigSeller Product'
        )
        vals = {
            'name': product_name,
            'default_code': sku or False,
            'type': 'consu',
            'sale_ok': True,
        }
        attr = (item_data.get('varAttr') or '').strip()
        if attr:
            vals['name'] = f'{product_name} [{attr}]'

        image_url = item_data.get('image')
        if image_url:
            vals['description_sale'] = image_url

        product = Product.create(vals)
        _logger.info('Created product: %s (SKU: %s)', product.name, sku)
        return product

    @staticmethod
    def _bigseller_parse_price(item):
        """Extract the best price from an order item dict."""
        for key in ('varDiscountedPrice', 'varOriginalPrice', 'amount'):
            val = item.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return 0.0

    @api.model
    def _map_bigseller_status(self, raw_status):
        """Map BigSeller web status string to our selection key."""
        mapping = {
            'new': 'new',
            'in_process': 'in_process',
            'inprocess': 'in_process',
            'platform_processing': 'platform_processing',
            'to_pickup': 'to_pickup',
            'topickup': 'to_pickup',
            'retry_ship': 'retry_ship',
            'retryship': 'retry_ship',
            'shipped': 'shipped',
            'completed': 'completed',
            'canceled': 'canceled',
            'cancelled': 'canceled',
            'voided': 'voided',
        }
        return mapping.get(raw_status.lower().replace(' ', '_'), 'new')
