from openerp.osv import fields, osv

class res_partner(osv.Model):
    _inherit = 'res.partner'
    _columns = {'discount': fields.float('Discount')}
