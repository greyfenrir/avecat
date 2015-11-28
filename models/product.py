from openerp.tools.float_utils import float_round
import openerp.addons.decimal_precision as dp
from openerp.osv import fields, osv
from _low_level import get_grayscale
import logging

_logger = logging.getLogger(__name__)

class product_template(osv.Model):
    _inherit = 'product.template'
    _columns = {'new_field': fields.text('new_field_text')}

class product_product(osv.osv):
    _inherit = "product.product"

    # for some fields
    def _search_product_quantity(self, cr, uid, obj, name, domain, context):
        res = []
        for field, operator, value in domain:
            #to prevent sql injections
            assert field in ('qty_available', 'virtual_available', 'incoming_qty', 'outgoing_qty'), 'Invalid domain left operand'
            assert operator in ('<', '>', '=', '!=', '<=', '>='), 'Invalid domain operator'
            assert isinstance(value, (float, int)), 'Invalid domain right operand'

            if operator == '=':
                operator = '=='

            ids = []
            if name == 'qty_available' and (value != 0.0 or operator not in  ('==', '>=', '<=')):
                res.append(('id', 'in', self._search_qty_available(cr, uid, operator, value, context)))
            else:
                product_ids = self.search(cr, uid, [], context=context)
                if product_ids:
                    #TODO: Still optimization possible when searching virtual quantities
                    for element in self.browse(cr, uid, product_ids, context=context):
                        if eval(str(element[field]) + operator + str(value)):
                            ids.append(element.id)
                    res.append(('id', 'in', ids))
        return res

    # research product rest calculation
    def _product_available(self, cr, uid, ids, field_names=None, arg=False, context=None):
        context = context or {}
        field_names = field_names or []
        _logger.error('_product_available()')
        domain_products = [('product_id', 'in', ids)]
        domain_quant, domain_move_in, domain_move_out = [], [], []
        domain_quant_loc, domain_move_in_loc, domain_move_out_loc = self._get_domain_locations(cr, uid, ids, context=context)
        domain_move_in += self._get_domain_dates(cr, uid, ids, context=context) + [('state', 'not in', ('done', 'cancel', 'draft'))] + domain_products

        domain_move_out += self._get_domain_dates(cr, uid, ids, context=context) + domain_products

        domain_quant += domain_products

        if context.get('lot_id'):
            domain_quant.append(('lot_id', '=', context['lot_id']))
        if context.get('owner_id'):
            domain_quant.append(('owner_id', '=', context['owner_id']))
            owner_domain = ('restrict_partner_id', '=', context['owner_id'])
            domain_move_in.append(owner_domain)
            domain_move_out.append(owner_domain)
        if context.get('package_id'):
            domain_quant.append(('package_id', '=', context['package_id']))

        domain_move_in += domain_move_in_loc
        domain_move_out += domain_move_out_loc

        domain_move_out_pre = domain_move_out + [('state', '=', 'confirmed')]
        domain_move_out_sale = domain_move_out + [('state', '=', 'assigned')]

        moves_in = self.pool.get('stock.move').read_group(cr, uid, domain_move_in, ['product_id', 'product_qty'], ['product_id'], context=context)

        moves_out_pre = self.pool.get('stock.move').read_group(cr, uid, domain_move_out_pre, ['product_id', 'product_qty'], ['product_id'], context=context)
        moves_out_sale = self.pool.get('stock.move').read_group(cr, uid, domain_move_out_sale, ['product_id', 'product_qty'], ['product_id'], context=context)

        domain_quant += domain_quant_loc
        quants = self.pool.get('stock.quant').read_group(cr, uid, domain_quant, ['product_id', 'qty'], ['product_id'], context=context)
        quants = dict(map(lambda x: (x['product_id'][0], x['qty']), quants))

        moves_in = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_in))
        # moves_out = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_out))
        moves_out_pre = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_out_pre))
        moves_out_sale = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_out_sale))
        res = {}
        for product in self.browse(cr, uid, ids, context=context):
            id = product.id
            qty_available = float_round(quants.get(id, 0.0), precision_rounding=product.uom_id.rounding)
            incoming_qty = float_round(moves_in.get(id, 0.0), precision_rounding=product.uom_id.rounding)
            outgoing_qty = float_round(moves_out_sale.get(id, 0.0), precision_rounding=product.uom_id.rounding)
            virtual_available = float_round(
                                            quants.get(id, 0.0) +
                                            moves_in.get(id, 0.0) -
                                            moves_out_sale.get(id, 0.0) -
                                            moves_out_pre.get(id, 0.0),
                                                precision_rounding=product.uom_id.rounding)
            sale_available = float_round(
                                            quants.get(id, 0.0) -
                                            moves_out_sale.get(id, 0.0) -
                                            ((moves_out_pre.get(id, 0.0) - moves_in.get(id, 0.0)) if moves_out_pre.get(id, 0.0) > moves_in.get(id, 0.0) else 0),
                                                precision_rounding=product.uom_id.rounding)

            res[id] = {
                'qty_available': qty_available,
                'incoming_qty': incoming_qty,
                'outgoing_qty': outgoing_qty,
                'virtual_available': virtual_available,
                'sale_available': sale_available,
            }
        return res

    def _get_image_variant(self, cr, uid, ids, name, args, context=None):
        result = dict.fromkeys(ids, False)

        for obj in self.browse(cr, uid, ids, context=context):
            if obj.sale_available > 0:
                result[obj.id] = obj.image_variant or getattr(obj.product_tmpl_id, name)
            else :
                result[obj.id] = get_grayscale(obj.image_variant)

        return result

    def _set_image_variant(self, cr, uid, id, name, value, args, context=None):
        image = tools.image_resize_image_big(value)
        res = self.write(cr, uid, [id], {'image_variant': image}, context=context)
        product = self.browse(cr, uid, id, context=context)
        if not product.product_tmpl_id.image:
            product.write({'image_variant': None})
            product.product_tmpl_id.write({'image': image})
        return res
    _columns = {'image': fields.function(_get_image_variant, fnct_inv=_set_image_variant,
                string="Big-sized image", type="binary",
                help="Image of the product variant (Big-sized image of product template if false). It is automatically "\
                     "resized as a 1024x1024px image, with aspect ratio preserved."),
        'qty_available': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Quantity On Hand',
            fnct_search=_search_product_quantity,
            help="Current quantity of products.\n"
                 "In a context with a single Stock Location, this includes "
                 "goods stored at this Location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods stored in the Stock Location of this Warehouse, or any "
                 "of its children.\n"
                 "stored in the Stock Location of the Warehouse of this Shop, "
                 "or any of its children.\n"
                 "Otherwise, this includes goods stored in any Stock Location "
                 "with 'internal' type."),
        'virtual_available': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Forecast Quantity',
            fnct_search=_search_product_quantity,
            help="Forecast quantity (computed as Quantity On Hand "
                 "- Outgoing + Incoming)\n"
                 "In a context with a single Stock Location, this includes "
                 "goods stored in this location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods stored in the Stock Location of this Warehouse, or any "
                 "of its children.\n"
                 "Otherwise, this includes goods stored in any Stock Location "
                 "with 'internal' type."),
        'incoming_qty': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Incoming',
            fnct_search=_search_product_quantity,
            help="Quantity of products that are planned to arrive.\n"
                 "In a context with a single Stock Location, this includes "
                 "goods arriving to this Location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods arriving to the Stock Location of this Warehouse, or "
                 "any of its children.\n"
                 "Otherwise, this includes goods arriving to any Stock "
                 "Location with 'internal' type."),
        'outgoing_qty': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Outgoing',
            fnct_search=_search_product_quantity,
            help="Quantity of products that are planned to leave.\n"
                 "In a context with a single Stock Location, this includes "
                 "goods leaving this Location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods leaving the Stock Location of this Warehouse, or "
                 "any of its children.\n"
                 "Otherwise, this includes goods leaving any Stock "
                 "Location with 'internal' type."),
        'sale_available':fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Available for Sale')
                }
