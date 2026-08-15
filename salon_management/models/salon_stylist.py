# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SalonStylist(models.Model):
    _name = 'salon.stylist'
    _description = 'Salon Stylist'
    _order = 'name'
    _inherit = ['mail.thread']

    name = fields.Char(compute='_compute_name', store=True)
    employee_id = fields.Many2one(
        'hr.employee', required=True, ondelete='restrict',
        string='Employee',
    )
    branch_ids = fields.Many2many(
        'salon.branch', 'salon_stylist_branch_rel',
        'stylist_id', 'branch_id',
        string='Branches', required=True,
    )
    service_ids = fields.Many2many(
        'salon.service', 'salon_stylist_service_rel',
        'stylist_id', 'service_id',
        string='Services',
        help="Services this stylist is qualified to perform.",
    )
    image = fields.Image(related='employee_id.image_1920', readonly=True)
    bio = fields.Html(translate=True, sanitize_attributes=False)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
    online_visible = fields.Boolean(
        default=True,
        help="Uncheck to hide this stylist from the public booking portal.",
    )
    user_id = fields.Many2one(
        'res.users', string='Portal User',
        help="Optional portal user who manages this stylist from the back-office.",
    )

    appointment_ids = fields.One2many('salon.appointment', 'stylist_id')
    appointment_count = fields.Integer(compute='_compute_appointment_count')
    chair_ids = fields.One2many('salon.chair', 'stylist_id', string='Assigned chairs')

    _sql_constraints = [
        ('employee_unique', 'unique(employee_id)', 'Each employee can be a stylist only once.'),
    ]

    @api.depends('employee_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.employee_id.name if rec.employee_id else False

    def _compute_appointment_count(self):
        counts = {
            s['stylist_id'][0]: s['stylist_id_count']
            for s in self.env['salon.appointment'].read_group(
                [('stylist_id', 'in', self.ids)],
                ['stylist_id'], ['stylist_id'],
            )
        }
        for rec in self:
            rec.appointment_count = counts.get(rec.id, 0)