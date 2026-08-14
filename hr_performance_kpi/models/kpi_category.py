# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class KpiCategory(models.Model):
    _name = 'kpi.category'
    _description = "KPI Category"
    _inherit = ['mail.thread']
    _order = 'name'
    _parent_store = True

    name = fields.Char(
        string="Category Name",
        required=True,
        translate=True,
        tracking=True,
    )
    description = fields.Text(
        string="Description",
        translate=True,
    )
    parent_id = fields.Many2one(
        'kpi.category',
        string="Parent Category",
        index=True,
        ondelete='cascade',
    )
    child_ids = fields.One2many(
        'kpi.category',
        'parent_id',
        string="Child Categories",
    )
    parent_path = fields.Char(index=True)
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        tracking=True,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
    )
    color = fields.Integer(
        string="Color Index",
        default=0,
    )
    color_class = fields.Char(
        string="Color CSS Class",
        compute='_compute_color_class',
        help="Bootstrap text-bg-* class derived from ``color`` for the kanban view.",
    )
    template_ids = fields.One2many(
        'kpi.template',
        'category_id',
        string="KPI Templates",
    )
    template_count = fields.Integer(
        string="Template Count",
        compute='_compute_template_count',
    )

    @api.depends('color')
    def _compute_color_class(self):
        # Map color index 0..9 to a fixed palette so the kanban view does not
        # need to compute classes via fragile string interpolation.
        palette = [
            'primary', 'success', 'info', 'warning', 'danger',
            'secondary', 'dark', 'primary', 'success', 'info',
        ]
        for category in self:
            category.color_class = palette[category.color % len(palette)]

    @api.depends('template_ids')
    def _compute_template_count(self):
        for category in self:
            category.template_count = len(category.template_ids)

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if not self._check_recursion():
            raise ValidationError(_('You cannot create recursive categories.'))

    def action_view_templates(self):
        """Return action to view templates in this category."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('KPI Templates'),
            'res_model': 'kpi.template',
            'view_mode': 'list,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }
