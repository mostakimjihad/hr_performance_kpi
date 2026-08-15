# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SalonServiceCategory(models.Model):
    _name = 'salon.service.category'
    _description = 'Salon Service Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color Index')
    image = fields.Image(max_width=1024, max_height=1024)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)
    online_visible = fields.Boolean(
        default=True,
        help="Uncheck to hide this category from the public booking portal.",
    )

    service_ids = fields.One2many('salon.service', 'category_id')
    service_count = fields.Integer(compute='_compute_service_count')

    def _compute_service_count(self):
        counts = {
            c['category_id'][0]: c['category_id_count']
            for c in self.env['salon.service'].read_group(
                [('category_id', 'in', self.ids), ('online_visible', '=', True)],
                ['category_id'], ['category_id'],
            )
        }
        for rec in self:
            rec.service_count = counts.get(rec.id, 0)