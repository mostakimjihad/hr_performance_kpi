# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    salon_appointment_ids = fields.One2many(
        'salon.appointment', 'partner_id',
        string='Salon appointments',
    )
    salon_appointment_count = fields.Integer(
        compute='_compute_salon_appointment_count',
    )

    def _compute_salon_appointment_count(self):
        counts = {
            p['partner_id'][0]: p['partner_id_count']
            for p in self.env['salon.appointment'].read_group(
                [('partner_id', 'in', self.ids)],
                ['partner_id'], ['partner_id'],
            )
        }
        for rec in self:
            rec.salon_appointment_count = counts.get(rec.id, 0)