# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PettyCashCategory(models.Model):
    _name = 'petty.cash.category'
    _description = 'Petty Cash Category'
    _inherit = ['mail.thread']
    _order = 'sequence, name'
    _parent_store = True

    name = fields.Char(
        string='Category Name',
        required=True,
        translate=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        help='Optional short identifier (e.g. "TRAVEL", "MEALS").',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    color = fields.Integer(
        string='Color Index',
        default=0,
    )
    color_class = fields.Char(
        string='Color CSS Class',
        compute='_compute_color_class',
    )
    description = fields.Text(
        string='Description',
        translate=True,
    )
    parent_id = fields.Many2one(
        'petty.cash.category',
        string='Parent Category',
        index=True,
        ondelete='cascade',
    )
    child_ids = fields.One2many(
        'petty.cash.category',
        'parent_id',
        string='Child Categories',
    )
    parent_path = fields.Char(index=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    # ---- Money -----------------------------------------------------
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    default_account_id = fields.Many2one(
        'account.account',
        string='Default Expense Account',
        help='Posted on transactions when no explicit account is chosen.',
    )
    monthly_budget = fields.Monetary(
        string='Monthly Budget',
        help='Soft budget surfaced on the dashboard; no hard block is enforced.',
    )

    transaction_ids = fields.One2many(
        'petty.cash.transaction',
        'category_id',
        string='Transactions',
    )
    transaction_count = fields.Integer(
        compute='_compute_transaction_count',
    )

    @api.depends('color')
    def _compute_color_class(self):
        palette = [
            'primary', 'success', 'info', 'warning', 'danger',
            'secondary', 'dark', 'primary', 'success', 'info',
        ]
        for cat in self:
            cat.color_class = palette[cat.color % len(palette)]

    @api.depends('transaction_ids')
    def _compute_transaction_count(self):
        for cat in self:
            cat.transaction_count = len(cat.transaction_ids)

    @api.constrains('parent_id')
    def _check_parent_id(self):
        for cat in self:
            if not cat._check_recursion():
                raise ValidationError(_('You cannot create recursive categories.'))

    def action_view_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Petty Cash Transactions'),
            'res_model': 'petty.cash.transaction',
            'view_mode': 'list,form,kanban',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }
