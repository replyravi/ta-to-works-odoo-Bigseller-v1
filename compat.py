# -*- coding: utf-8 -*-
import odoo

ODOO_VERSION = int(odoo.release.version_info[0])
IS_V16 = ODOO_VERSION < 17
IS_V18 = ODOO_VERSION >= 17
