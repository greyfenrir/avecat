from openerp.osv import fields, osv
import openerp.addons.decimal_precision as dp
import logging

_logger = logging.getLogger(__name__)

class sale_order(osv.Model):
    _inherit = 'sale.order'

    # create picking for new sale order (state 'progress')
    def sale_picking_create(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        partner_obj = self.pool.get('res.partner')
        move_obj = self.pool.get('stock.move')
        picking_type_id = 2 #order.picking_type_id

        _logger.error('picking_type_id: %d' % picking_type_id)
        for order in self.browse(cr, uid, ids, context=context):
            addr = order.partner_id and partner_obj.address_get(cr, uid, [order.partner_id.id], ['delivery']) or {}
            picking_id = picking_obj.create(cr, uid, {
                'origin': order.name,
                'partner_id': addr.get('delivery',False),
                'date_done' : order.date_order,
                'picking_type_id': picking_type_id,
                'company_id': order.company_id.id,
                'move_type': 'direct',
                'note': order.note or "",
            }, context=context)
            self.write(cr, uid, [order.id], {'picking_id': picking_id}, context=context)
            location_id = 12 #order.location_id.id
            destination_id = order.partner_id.property_stock_customer.id

            for line in order.order_line:
                move_obj.create(cr, uid, {
                    'name': line.name,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uos': line.product_id.uos_id.id,
                    'picking_id': picking_id,
                    'picking_type_id': picking_type_id,
                    'product_id': line.product_id.id,
                    'product_uos_qty': abs(line.product_uos_qty),
                    'product_uom_qty': abs(line.product_uom_qty),
                    'state': 'draft',
                    'location_id': location_id,
                    'location_dest_id': destination_id,
                }, context=context)

        return True

    def sale_picking_confirm(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        for order in self.browse(cr, uid, ids, context=context):
            picking_obj.action_confirm(cr, uid, [order.picking_id.id], context=context)

    def sale_picking_assign(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        for order in self.browse(cr, uid, ids, context=context):
            picking_obj.action_assign(cr, uid, [order.picking_id.id], context=context)

    # complete picking (order state became 'sent' or 'done')
    def sale_picking_done(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        for order in self.browse(cr, uid, ids, context=context):
            picking_obj.action_done(cr, uid, [order.picking_id.id], context=context)

        return True
    # to 'cancel' or 'draft'
    def sale_picking_clean(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        for order in self.browse(cr, uid, ids, context=context):
            picking_obj.action_cancel(cr, uid, [order.picking_id.id], context=context)
        return True

    def parse(self,cr, uid, ids, context=None):
        for order in self.pool.get(cr, uid, ids, context=context):
            if not self.picking_id.check(cr, uid, [order.id], order.state, context=context):
                self.action_state_cancel(cr, uid, [order.id], context=context)
                self.write(cr, uid, [order.id], {'state': 'draft'}, context=context)

    #button actions
    def action_state_cancel(self, cr, uid, ids, context=None):
        self.sale_picking_clean(cr, uid, ids, context=context)
        self.write(cr, uid, ids, {'state': 'cancel'})
        return True

    def action_state_preliminary(self, cr, uid, ids, context=None):
        for order in self.browse(cr, uid, ids, context=context):
            if order.state == 'draft':
                self.sale_picking_create(cr, uid, [order.id], context=context)
                self.sale_picking_confirm(cr, uid, [order.id], context=context)
                self.write(cr, uid, [order.id], {'state': 'preliminary'})
            if not self.pool.get("stock.picking").check_if_available(cr, uid, [order.picking_id.id], 'preliminary'):
                self.action_state_draft(cr, uid, [order.id])
        return True

    def action_state_progress(self, cr, uid, ids, context=None):
        for order in self.browse(cr, uid, ids, context=context):
            if order.state == 'draft':
                self.action_state_preliminary(cr, uid, [order.id], context=context)
            if order.state == 'preliminary':
                self.sale_picking_assign(cr, uid, [order.id])
                self.write(cr, uid, [order.id], {'state': 'progress'})
                _logger.error("before check_if_available")
                if not self.pool.get("stock.picking").check_if_available(cr, uid, [order.picking_id.id], 'progress'):
                    _logger.error("check_if_available = false")
                    self.action_state_draft(cr, uid, [order.id])
                    self.action_state_preliminary(cr, uid, [order.id])
                else:
                    _logger.error("check_if_available = true")

        return True

    def action_state_done(self, cr, uid, ids, context=None):
        self.sale_picking_done(cr, uid, ids, context=context)
        self.write(cr, uid, ids, {'state': 'done'})
        return True

    def action_state_draft(self, cr, uid, ids, context=None):
        for order in self.browse(cr, uid, ids, context=context):
            if order.state <> 'cancel':
                self.sale_picking_clean(cr, uid, [order.id], context=context)
        self.write(cr, uid, ids, {'state': 'draft'})
        return True

    def action_state_sent(self, cr, uid, ids, context=None):
        self.sale_picking_done(cr, uid, ids, context=context)
        self.write(cr, uid, ids, {'state': 'sent'})
        return True

    def action_delete(self, cr, uid, ids, context=None):
        self.unlink(cr, uid, ids, context=context)
        return True
 #----------------------

    def _get_order(self, cr, uid, ids, context=None):
        result = {}
        for line in self.pool.get('sale.order.line').browse(cr, uid, ids, context=context):
            result[line.order_id.id] = True
        return result.keys()

    def _amount_all_wrapper(self, cr, uid, ids, field_name, arg, context=None):
        """ Wrapper because of direct method passing as parameter for function fields """
        return self._amount_all(cr, uid, ids, field_name, arg, context=context)

    # modify for new value calculate
    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
        cur_obj = self.pool.get('res.currency')
        res = {}
        for order in self.browse(cr, uid, ids, context=context):
            res[order.id] = {
                'amount_untaxed': 0.0,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                'amount_discount': 0.0
            }
            val = val1 = 0.0
            cur = order.pricelist_id.currency_id
            for line in order.order_line:
                val1 += line.price_subtotal
                val += self._amount_line_tax(cr, uid, line, context=context)

            val_amount_disc = order.partner_id.discount * val1/100

            res[order.id]['amount_tax'] = cur_obj.round(cr, uid, cur, val)
            res[order.id]['amount_untaxed'] = cur_obj.round(cr, uid, cur, val1)

            res[order.id]['amount_discount'] = cur_obj.round(cr, uid, cur, val_amount_disc)

            res[order.id]['amount_total'] = res[order.id]['amount_untaxed'] - res[order.id]['amount_discount']
        return res

    _columns = {'amount_discount': fields.function(_amount_all_wrapper,    # compute method
                    digits_compute=dp.get_precision('Account'),             # (16, 2) - _amount_all_wrapper arguments?
                    string='Discount',                                      # field name
                    store={                                                 # store in DB
                    'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
                    'sale.order.line': (_get_order, ['price_unit', 'tax_id', 'discount', 'product_uom_qty'], 10),},
                    multi='sums',                           # caclulate together
                    help="The discount amount."),           # help string

                'state': fields.selection([
                    ('draft', 'Draft'),
                    ('preliminary', 'Preorder'),
                    ('progress', 'Sales Order'),
                    ('sent', 'Order Sent'),
                    ('done', 'Done'),
                    ('cancel', 'Cancel'),
                    ], 'Status', readonly=True),
                'order_line': fields.one2many('sale.order.line', 'order_id', 'Order Lines', readonly=True, states={'draft': [('readonly', False)]}, copy=True),
                'picking_id': fields.many2one('stock.picking', 'Picking', readonly=True, copy=False),}

    _defaults = {'state': 'draft'}

class sale_order_line(osv.osv):
    _inherit = 'sale.order.line'
    _columns = {'state': fields.selection([
                    ('draft', 'Draft'),
                    ('preliminary', 'Pre-order'),
                    ('progress', 'Sales Order'),
                    ('sent', 'Order Sent'),
                    ('done', 'Done'),
                    ]),}
    _defaults = {'state': 'draft'}
