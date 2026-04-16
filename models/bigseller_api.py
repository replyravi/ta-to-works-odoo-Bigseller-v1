# -*- coding: utf-8 -*-
# RSS – BigSeller Session-Based API Connector
#
# BigSeller (bigseller.com) does NOT have a public API.
# This connector reverse-engineers the internal web APIs that the BigSeller
# frontend calls via XHR. Authentication is via session cookies captured
# from the user's browser after manual login (with CAPTCHA).
#
# Discovered endpoints (2026-04-10):
#   GET  /api/v1/isLogin.json                    – session validity check
#   POST /api/v1/order/new/pageList.json         – new order list
#   POST /api/v1/order/getOrderStatusCount.json  – order counts by status
#   GET  /api/v1/shopsAndPlatforms.json          – shops & platforms
#   GET  /api/v1/order/v2/filterList.json        – order filters
#   GET  /api/v1/3pl/shipping/list.json          – 3PL shipping providers
#   GET  /api/v1/order/constant/queryLogisticsServices.json – logistics

import logging
import requests

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://www.bigseller.com'

STATUS_ENDPOINT_MAP = {
    'new':       '/api/v1/order/new/pageList.json',
    'packed':    '/api/v1/order/packed/pageList.json',
    'toShip':    '/api/v1/order/toShip/pageList.json',
    'shipping':  '/api/v1/order/shipping/pageList.json',
    'shipped':   '/api/v1/order/shipping/pageList.json',
    'done':      '/api/v1/order/done/pageList.json',
    'completed': '/api/v1/order/done/pageList.json',
    'canceled':  '/api/v1/order/cancel/pageList.json',
    'cancelled': '/api/v1/order/cancel/pageList.json',
    'voided':    '/api/v1/order/cancel/pageList.json',
}


class BigSellerClient:
    """HTTP client for BigSeller's internal web APIs.

    Usage:
        client = BigSellerClient('https://www.bigseller.com', cookie_string)
        if client.test_connection():
            orders = client.get_orders(status='new', page=1)
    """

    def __init__(self, base_url=None, cookie_string=''):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Cookie': cookie_string,
            'Content-Type': 'application/json',
            'clienttype': '1',
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/147.0.0.0 Safari/537.36'),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/web/order/index.htm?status=new',
        })

    def _url(self, path):
        return f'{self.base_url}{path}'

    def _get(self, path, params=None):
        try:
            resp = self.session.get(self._url(path), params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            _logger.error('BigSeller GET %s failed: %s', path, e)
            return {}

    def _post(self, path, data=None, json_data=None):
        try:
            resp = self.session.post(
                self._url(path), data=data, json=json_data, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            code = result.get('code')
            if code != 0:
                _logger.warning(
                    'BigSeller POST %s returned code=%s msg=%s',
                    path, code, result.get('msg', ''))
            return result
        except requests.exceptions.RequestException as e:
            _logger.error('BigSeller POST %s failed: %s', path, e)
            return {}

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def test_connection(self):
        """Verify session is valid by checking the isLogin endpoint.

        Returns True if session is active, False otherwise.
        isLogin returns code=0 with data=true when logged in,
        code=0 with data=false when session expired.
        """
        result = self._get('/api/v1/isLogin.json')
        if not result:
            return False
        if result.get('code') != 0:
            return False
        return bool(result.get('data'))

    def get_shops(self):
        """Get list of connected shops and platforms."""
        return self._get('/api/v1/shopsAndPlatforms.json')

    def get_order_status_count(self):
        """Get order counts grouped by status."""
        return self._post('/api/v1/order/getOrderStatusCount.json')

    def get_orders(self, status='new', page=1, page_size=100):
        """Fetch paginated order list for a given status.

        :param status: one of 'new', 'packed', 'shipped', 'completed', 'canceled', 'voided'
        :param page: page number (1-based)
        :param page_size: items per page (max 300)
        :return: dict with data.page.rows containing order list
        """
        endpoint = STATUS_ENDPOINT_MAP.get(status, STATUS_ENDPOINT_MAP['new'])
        payload = {
            'status': status,
            'searchType': 'orderNo',
            'pageNo': page,
            'desc': 0,
            'orderBy': 'expireTime',
            'allOrder': False,
            'historyOrder': False,
            'packState': '0',
        }
        result = self._post(endpoint, json_data=payload)
        resp_data = result.get('data') or {}
        page_data = (resp_data.get('page') or {}) if isinstance(resp_data, dict) else {}
        rows = (page_data.get('rows') or []) if isinstance(page_data, dict) else []
        _logger.info(
            'BigSeller get_orders(%s) page=%d: code=%s, totalSize=%s, '
            'rows_returned=%d, endpoint=%s',
            status, page,
            result.get('code', '?'),
            page_data.get('totalSize', '?') if isinstance(page_data, dict) else '?',
            len(rows),
            endpoint)
        return result

    def get_order_detail(self, order_id):
        """Fetch detailed information for a single order.

        Note: The exact endpoint path needs validation. BigSeller likely uses
        a path like /api/v1/order/detail.json?orderId=XXX or similar.
        Update this once the endpoint is confirmed via browser DevTools.
        """
        return self._get('/api/v1/order/detail.json', params={'orderId': order_id})

    def update_order_status(self, order_id, new_status, **kwargs):
        """Push a status update to BigSeller for an order.

        Note: The exact endpoint for status updates needs to be captured
        from BigSeller's Pack/Ship actions in the browser. Common candidates:
          POST /api/v1/order/pack.json
          POST /api/v1/order/ship.json

        Update this method once the exact endpoints are confirmed.
        """
        _logger.info(
            'BigSeller status update requested: order=%s status=%s (stub)',
            order_id, new_status)
        return {'success': False, 'message': 'Endpoint not yet configured'}

    def export_orders(self, status='new', date_from=None, date_to=None):
        """Trigger BigSeller's XLS export and download the file.

        Note: The export function in BigSeller's web UI likely triggers a
        background task and then provides a download URL. The exact endpoint
        needs to be captured from the Export button's network calls.
        """
        _logger.info(
            'BigSeller export requested: status=%s from=%s to=%s (stub)',
            status, date_from, date_to)
        return None

    def get_logistics_services(self):
        """Get available logistics service options."""
        return self._get('/api/v1/order/constant/queryLogisticsServices.json')

    def get_shipping_providers(self):
        """Get 3PL shipping provider list."""
        return self._get('/api/v1/3pl/shipping/list.json')
