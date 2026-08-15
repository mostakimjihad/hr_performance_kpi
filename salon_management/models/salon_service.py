# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SalonService(models.Model):
    _name = 'salon.service'
    _description = 'Salon Service'
    _order = 'category_id, sequence, name'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one(
        'salon.service.category', required=True,
        ondelete='restrict',
    )
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='company_id.currency_id',
    )
    duration = fields.Float(
        string='Duration (hours)', required=True, default=0.5,
        help="Service duration in hours. Stored as float so 30 min = 0.5.",
    )
    duration_minutes = fields.Integer(
        compute='_compute_duration_minutes', store=True,
    )
    list_price = fields.Monetary(required=True)
    description = fields.Html(translate=True, sanitize_attributes=False)
    image = fields.Image(max_width=1920, max_height=1920)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
    online_visible = fields.Boolean(
        default=True,
        help="Uncheck to hide this service from the public booking portal.",
    )
    branch_ids = fields.Many2many(
        'salon.branch',
        'salon_branch_service_rel', 'service_id', 'branch_id',
        string='Available at branches',
        help="Branches where this service can be booked. Empty = available everywhere.",
    )
    stylist_ids = fields.Many2many(
        'salon.stylist',
        compute='_compute_stylist_ids',
        string='Eligible stylists',
    )

    @api.depends('duration')
    def _compute_duration_minutes(self):
        for rec in self:
            rec.duration_minutes = int(round(rec.duration * 60))

    @api.depends('branch_ids')
    def _compute_stylist_ids(self):
        Stylist = self.env['salon.stylist']
        for rec in self:
            domain = []
            if rec.branch_ids:
                domain.append(('branch_ids', 'in', rec.branch_ids.ids))
            rec.stylist_ids = Stylist.search(domain)

    @api.onchange('duration')
    def _onchange_duration(self):
        # Helpful nudge when user enters minutes in error
        if self.duration and self.duration > 8:
            return {
                'warning': {
                    'title': self.env._('Duration looks long'),
                    'message': self.env._(
                        'Duration is in hours. Did you mean %.1f (%.0f minutes)?',
                        self.duration / 60, self.duration,
                    ),
                },
            }