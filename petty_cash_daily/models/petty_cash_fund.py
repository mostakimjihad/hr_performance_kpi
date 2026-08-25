# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PettyCashFund(models.Model):
    _name = 'petty.cash.fund'
    _description = 'Petty Cash Fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Fund Name',
        required=True,
        translate=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        help='Short identifier used in sequence prefixes.',
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
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
        help='Bootstrap text-bg-* class derived from ``color`` for the kanban view.',
    )

    # ---- People & scope --------------------------------------------
    custodian_id = fields.Many2one(
        'hr.employee',
        string='Custodian',
        tracking=True,
        help='Person who physically holds the cash box.',
    )
    custodian_user_id = fields.Many2one(
        'res.users',
        string='Custodian User',
        related='custodian_id.user_id',
        store=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        related='company_id.currency_id',
    )
    branch_name = fields.Char(
        string='Location',
        help='Free-text physical location, e.g. "Reception Desk — Floor 2".',
    )

    # ---- Money -----------------------------------------------------
    opening_balance = fields.Monetary(
        string='Opening Balance',
        required=True,
        tracking=True,
        help='Initial cash placed in the drawer when the fund is created.',
    )
    current_balance = fields.Monetary(
        string='Current Balance',
        compute='_compute_current_balance',
        store=True,
        help='Opening balance + money in − money out (paid transactions only).',
    )
    alert_threshold = fields.Monetary(
        string='Low-Balance Alert',
        default=50.0,
        required=True,
        help='When current balance drops below this amount, the dashboard surfaces a low-balance alert.',
    )
    transaction_limit = fields.Monetary(
        string='Auto-Approve Limit',
        default=25.0,
        required=True,
        tracking=True,
        help='Transactions at or below this amount are auto-approved; above this amount need a manager.',
    )
    monthly_budget = fields.Monetary(
        string='Monthly Budget',
        help='Soft budget for monthly outflow; surfaced on the dashboard.',
    )

    # ---- Operations ------------------------------------------------
    auto_open_daily_session = fields.Boolean(
        string='Open One Session per Day',
        default=True,
        tracking=True,
        help='If enabled, the daily cron closes any open sessions and starts the next-day session.',
    )
    state = fields.Selection(
        [('active', 'Active'),
         ('suspended', 'Suspended'),
         ('closed', 'Closed')],
        string='Status',
        default='active',
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )

    # ---- Counts (for smart buttons) --------------------------------
    transaction_ids = fields.One2many(
        'petty.cash.transaction',
        'fund_id',
        string='Transactions',
    )
    transaction_count = fields.Integer(
        compute='_compute_transaction_count',
    )
    paid_out_count = fields.Integer(
        compute='_compute_paid_out_count',
    )
    session_ids = fields.One2many(
        'petty.cash.session',
        'fund_id',
        string='Sessions',
    )
    session_count = fields.Integer(
        compute='_compute_session_count',
    )
    replenishment_ids = fields.One2many(
        'petty.cash.replenishment',
        'fund_id',
        string='Replenishments',
    )
    pending_approval_count = fields.Integer(
        compute='_compute_pending_approval_count',
    )

    # ---- Computes --------------------------------------------------
    @api.depends('name', 'code')
    def _compute_display_name(self):
        for fund in self:
            if fund.name and fund.code:
                fund.display_name = f'[{fund.code}] {fund.name}'
            else:
                fund.display_name = fund.name or ''

    @api.depends('color')
    def _compute_color_class(self):
        # Map color index 0..9 to a fixed palette so the kanban view does not
        # need to compute classes via fragile string interpolation.
        palette = [
            'primary', 'success', 'info', 'warning', 'danger',
            'secondary', 'dark', 'primary', 'success', 'info',
        ]
        for fund in self:
            fund.color_class = palette[fund.color % len(palette)]

    @api.depends('opening_balance',
                 'transaction_ids.amount', 'transaction_ids.direction',
                 'transaction_ids.state')
    def _compute_current_balance(self):
        # NOTE: we re-read ``transaction_ids`` here to ensure freshly-cached
        # balances after a multi-record compute. Relying on the One2many
        # cache alone could leave a stale balance when several funds share
        # the same transaction set across the same transaction.
        Transaction = self.env['petty.cash.transaction']
        for fund in self:
            tx = Transaction.search([
                ('fund_id', '=', fund.id),
                ('state', '=', 'paid'),
            ])
            money_in = sum(tx.filtered(lambda t: t.direction == 'in').mapped('amount'))
            money_out = sum(tx.filtered(lambda t: t.direction == 'out').mapped('amount'))
            fund.current_balance = fund.opening_balance + money_in - money_out

    @api.depends('transaction_ids')
    def _compute_transaction_count(self):
        for fund in self:
            fund.transaction_count = len(fund.transaction_ids)

    @api.depends('transaction_ids')
    def _compute_paid_out_count(self):
        for fund in self:
            fund.paid_out_count = len(fund.transaction_ids.filtered(
                lambda t: t.state == 'paid' and t.direction == 'out'))

    @api.depends('session_ids')
    def _compute_session_count(self):
        for fund in self:
            fund.session_count = len(fund.session_ids)

    @api.depends('transaction_ids')
    def _compute_pending_approval_count(self):
        for fund in self:
            fund.pending_approval_count = len(fund.transaction_ids.filtered(
                lambda t: t.state == 'submitted'))

    # ---- Constraints -----------------------------------------------
    _code_unique = models.Constraint(
        'unique(code, company_id)',
        'Fund code must be unique per company.',
    )

    @api.constrains('opening_balance', 'alert_threshold',
                    'transaction_limit', 'monthly_budget')
    def _check_amounts(self):
        for fund in self:
            if fund.opening_balance and fund.opening_balance < 0:
                raise ValidationError(_('Opening balance cannot be negative.'))
            if fund.alert_threshold and fund.alert_threshold < 0:
                raise ValidationError(_('Low-balance alert threshold cannot be negative.'))
            if fund.transaction_limit and fund.transaction_limit < 0:
                raise ValidationError(_('Auto-approve limit cannot be negative.'))

    @api.constrains('state')
    def _check_state_change(self):
        """Closed is terminal — never silently reopen it via constraints."""
        # NOTE: transitions are enforced by the action_* methods (state setters
        # require explicit calls), not by DB constraints, so this hook stays
        # a no-op for now. Kept as a hook for future custom behavior.

    # ---- Actions ---------------------------------------------------
    def action_suspend(self):
        for fund in self:
            if fund.state == 'closed':
                raise UserError(_('A closed fund cannot be suspended.'))
            fund.state = 'suspended'

    def action_reactivate(self):
        for fund in self:
            fund.state = 'active'

    def action_close(self):
        for fund in self:
            fund.state = 'closed'

    def action_open_session(self):
        """Open today's session for this fund (used from the form view)."""
        self.ensure_one()
        Session = self.env['petty.cash.session']
        return Session.open_today(self, opening_balance=self.current_balance)

    def action_view_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Petty Cash Transactions'),
            'res_model': 'petty.cash.transaction',
            'view_mode': 'list,form',
            'domain': [('fund_id', '=', self.id)],
            'context': {'default_fund_id': self.id},
        }

    def action_view_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Daily Sessions'),
            'res_model': 'petty.cash.session',
            'view_mode': 'list,form',
            'domain': [('fund_id', '=', self.id)],
            'context': {'default_fund_id': self.id},
        }

    def action_request_replenishment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Request Replenishment'),
            'res_model': 'petty.cash.replenishment',
            'view_mode': 'form',
            'context': {
                'default_fund_id': self.id,
                'default_amount': max(0.0, self.opening_balance - self.current_balance),
            },
            'target': 'new',
        }
