# -*- coding: utf-8 -*-
import logging
import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bigseller_session_cookie = fields.Char(
        string='BigSeller Session Cookie',
        config_parameter='bigseller.session_cookie',
        help='Paste the full cookie string from your browser after logging '
             'into bigseller.com. Open DevTools > Application > Cookies to copy it.')
    bigseller_base_url = fields.Char(
        string='BigSeller Base URL',
        config_parameter='bigseller.base_url',
        default='https://www.bigseller.com',
        help='Base URL for BigSeller. Default: https://www.bigseller.com')
    bigseller_sync_enabled = fields.Boolean(
        string='Enable Auto Sync',
        config_parameter='bigseller.sync_enabled',
        help='Enable automatic order sync via BigSeller API.')
    bigseller_auto_create_orders = fields.Boolean(
        string='Auto-Create New Orders',
        config_parameter='bigseller.auto_create_orders',
        default=True,
        help='Automatically create Sale Orders in Odoo when new orders '
             'are found in BigSeller. If disabled, sync only updates '
             'existing orders.')
    bigseller_sync_interval = fields.Integer(
        string='Sync Interval (minutes)',
        config_parameter='bigseller.sync_interval',
        default=2,
        help='How often to sync orders from BigSeller (in minutes).')
    bigseller_last_sync = fields.Datetime(
        string='Last Sync', readonly=True,
        config_parameter='bigseller.last_sync')
    bigseller_last_sync_error = fields.Char(
        string='Last Sync Error', readonly=True,
        config_parameter='bigseller.last_sync_error')
    bigseller_auto_sync_token = fields.Char(
        string='Auto-Sync Token', readonly=True,
        config_parameter='bigseller.auto_sync_token')

    def action_generate_auto_sync_token(self):
        """Generate a new random token for the browser auto-sync script."""
        new_token = uuid.uuid4().hex
        self.env['ir.config_parameter'].sudo().set_param(
            'bigseller.auto_sync_token', new_token)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Token Generated'),
                'message': _('New auto-sync token created. '
                             'Copy it into your Tampermonkey script.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_bigseller_test_connection(self):
        """Test the BigSeller session cookie by calling isLogin endpoint."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        cookie = ICP.get_param('bigseller.session_cookie', '')
        base_url = ICP.get_param('bigseller.base_url', 'https://www.bigseller.com')

        if not cookie:
            raise UserError(_('Please save a session cookie first.'))

        from .bigseller_api import BigSellerClient
        client = BigSellerClient(base_url, cookie)
        if client.test_connection():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('BigSeller session is active and valid.'),
                    'type': 'success',
                    'sticky': False,
                },
            }
        raise UserError(
            _('Connection failed. The session cookie may be expired or invalid.\n'
              'Please log into bigseller.com again and paste a fresh cookie.'))

    def action_bigseller_sync_now(self):
        """Manually trigger a BigSeller order sync (bypasses sync_enabled check)."""
        result = self.env['sale.order']._bigseller_sync_orders(manual=True)
        ICP = self.env['ir.config_parameter'].sudo()
        last_error = ICP.get_param('bigseller.last_sync_error', '')
        if last_error:
            raise UserError(
                _('Sync encountered an error:\n%s') % last_error)
        created = result.get('created', 0) if result else 0
        updated = result.get('updated', 0) if result else 0
        msg = _('Created: %d orders, Updated: %d orders') % (created, updated)
        if not created and not updated:
            msg = _('No new or changed orders found in BigSeller.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Complete'),
                'message': msg,
                'type': 'success' if (created or updated) else 'warning',
                'sticky': True,
            },
        }
