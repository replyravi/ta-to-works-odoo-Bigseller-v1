# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
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

        platform_partner = self._bigseller_get_or_create_partner(
            platform or 'BigSeller')
        delivery_contact = self._bigseller_get_or_create_delivery_address(
            buyer_name, platform_partner)
        currency = self.env['res.currency'].search(
            [('name', '=ilike', currency_code)], limit=1)

        order_date = self._bigseller_parse_order_date(bs_order)

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
            'partner_id': platform_partner.id,
            'partner_shipping_id': delivery_contact.id,
            'mp_marketplace': platform,
            'mp_status': self._map_bigseller_status(state),
            'mp_last_update': fields.Datetime.now(),
            'buyer_designed_logistics': bs_order.get('buyerShippingCarrier', ''),
            'bigseller_order_id': str(bs_order.get('id', '')),
            'bigseller_shop_name': shop_name,
            'bigseller_platform_order_id': order_no,
        }
        if order_date:
            vals['date_order'] = order_date
        if currency:
            vals['currency_id'] = currency.id
        if order_lines:
            vals['order_line'] = order_lines

        order_type = self._bigseller_resolve_order_type(platform, shop_name)
        if order_type:
            self._bigseller_apply_order_type(vals, order_type)

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

    def _bigseller_resolve_order_type(self, platform, shop_name):
        """Match BigSeller platform/shop to a sale.order.type record.

        The production system has types like 'MP: Lazada', 'MP: Lazada 2',
        'MP: Shopee', 'MP: TikTok'.  We search by checking if the type name
        contains the platform keyword.  When multiple matches exist (e.g.
        Lazada vs Lazada 2), we use the shop_name to pick the right one.

        Returns a sale.order.type recordset (possibly empty).
        """
        if 'sale.order.type' not in self.env:
            return False

        OrderType = self.env['sale.order.type']
        platform_lower = (platform or '').lower()
        shop_lower = (shop_name or '').lower()

        keyword = ''
        if 'lazada' in platform_lower or 'lazada' in shop_lower:
            keyword = 'Lazada'
        elif 'shopee' in platform_lower or 'shopee' in shop_lower:
            keyword = 'Shopee'
        elif 'tiktok' in platform_lower or 'tiktok' in shop_lower:
            keyword = 'TikTok'
        elif platform_lower:
            keyword = platform

        if not keyword:
            return OrderType.browse()

        types = OrderType.search([('name', 'ilike', keyword)])
        if not types:
            _logger.warning(
                'No sale.order.type found matching platform "%s" / shop "%s"',
                platform, shop_name)
            return OrderType.browse()

        if len(types) == 1:
            return types

        # Multiple matches — disambiguate using shop_name.
        # Check longest suffix first so "Lazada 2" beats "Lazada"
        # when the shop name contains "lazada 2".
        for ot in types.sorted(key=lambda t: len(t.name), reverse=True):
            type_suffix = ot.name.replace('MP:', '').strip().lower()
            if type_suffix and type_suffix in shop_lower:
                return ot

        # Fallback: shortest (most generic) match
        return types.sorted(key=lambda t: len(t.name))[0]

    @staticmethod
    def _bigseller_apply_order_type(vals, order_type):
        """Merge fields from a sale.order.type into the SO vals dict."""
        if not order_type:
            return
        vals['type_id'] = order_type.id
        if order_type.warehouse_id:
            vals['warehouse_id'] = order_type.warehouse_id.id
        if order_type.pricelist_id:
            vals['pricelist_id'] = order_type.pricelist_id.id
        if order_type.fiscal_position_id:
            vals['fiscal_position_id'] = order_type.fiscal_position_id.id
        if hasattr(order_type, 'sale_team_id') and order_type.sale_team_id:
            vals['team_id'] = order_type.sale_team_id.id
        if order_type.user_id:
            vals['user_id'] = order_type.user_id.id
        if hasattr(order_type, 'utm_source_id') and order_type.utm_source_id:
            vals['source_id'] = order_type.utm_source_id.id
        if hasattr(order_type, 'company_id') and order_type.company_id:
            vals['company_id'] = order_type.company_id.id

        deadline_days = 0
        if hasattr(order_type, 'delivery_deadline_days'):
            deadline_days = order_type.delivery_deadline_days or 0
        if deadline_days > 0:
            base_date = vals.get('date_order') or fields.Datetime.now()
            if isinstance(base_date, str):
                base_date = fields.Datetime.from_string(base_date)
            vals['commitment_date'] = base_date + timedelta(days=deadline_days)

    def _bigseller_get_or_create_partner(self, name):
        """Find or create a company-type partner for the platform name.

        The partner_id on the SO represents the marketplace company
        (e.g. "Lazada", "Shopee", "TikTok").
        """
        Partner = self.env['res.partner']
        partner = Partner.search([
            ('name', '=ilike', name),
            ('is_company', '=', True),
        ], limit=1)
        if not partner:
            partner = Partner.search([('name', '=ilike', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'is_company': True,
                'customer_rank': 1,
                'comment': 'Auto-created by BigSeller import',
            })
            _logger.info('Created company partner: %s', name)
        return partner

    def _bigseller_get_or_create_delivery_address(self, buyer_name, parent_partner):
        """Find or create a delivery-type child contact under the platform partner.

        The buyer name from BigSeller becomes the delivery address contact,
        parented under the marketplace company (Lazada / Shopee / TikTok).
        """
        Partner = self.env['res.partner']
        if not buyer_name or buyer_name == parent_partner.name:
            return parent_partner

        existing = Partner.search([
            ('name', '=ilike', buyer_name),
            ('type', '=', 'delivery'),
            ('parent_id', '=', parent_partner.id),
        ], limit=1)
        if existing:
            return existing

        delivery = Partner.create({
            'name': buyer_name,
            'parent_id': parent_partner.id,
            'type': 'delivery',
            'comment': 'Delivery address from BigSeller import',
        })
        _logger.info('Created delivery contact: %s (under %s)',
                      buyer_name, parent_partner.name)
        return delivery

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

    @staticmethod
    def _bigseller_parse_order_date(bs_order):
        """Extract the real order date from BigSeller JSON.

        BigSeller provides dates as epoch-millisecond timestamps in fields
        like paidTime, orderCreateTime, createTime.  Returns a datetime
        or None if no usable date is found.
        """
        from datetime import datetime
        for key in ('paidTime', 'orderCreateTime', 'createTime', 'payTime'):
            val = bs_order.get(key)
            if val:
                try:
                    ts = int(val)
                    if ts > 1e12:
                        ts = ts / 1000
                    return datetime.utcfromtimestamp(ts)
                except (ValueError, TypeError, OSError):
                    continue
        date_str = bs_order.get('orderDate') or bs_order.get('createDate')
        if date_str and isinstance(date_str, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S'):
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        return None

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
