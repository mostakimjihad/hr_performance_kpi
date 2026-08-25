# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date, datetime, time, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PettyCashSession(models.Model):
    _name = 'petty.cash.session'
    _description = 'Petty Cash Daily Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        default=lambda self: _('New'),
    )
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )
    fund_id = fields.Many2one(
        'petty.cash.fund',
        string='Cash Box',
        required=True,
        index=True,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
    )
    custodian_id = fields.Many2one(
        'hr.employee',
        string='Custodian',
        related='fund_id.custodian_id',
        store=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='fund_id.currency_id',
    )
    company_id = fields.Many2one(
        'res.company',
        related='fund_id.company_id',
        store=True,
    )

    opened_at = fields.Datetime(
        string='Opened At',
        default=fields.Datetime.now,
    )
    closed_at = fields.Datetime(
        string='Closed At',
        readonly=True,
    )
    opened_by = fields.Many2one(
        'res.users',
        string='Opened By',
        default=lambda self: self.env.user.id,
    )
    closed_by = fields.Many2one(
        'res.users',
        string='Closed By',
    )
    confirmed_by = fields.Many2one(
        'res.users',
        string='Confirmed By',
    )

    opening_balance = fields.Monetary(
        string='Opening Balance',
        required=True,
        help='Cash physically present when the session opened.',
    )
    actual_balance = fields.Monetary(
        string='Actual Cash Counted',
        help='Cash physically present when the session closed.',
    )
    expected_balance = fields.Monetary(
        string='Expected Closing Balance',
        compute='_compute_expected_balance',
        store=True,
    )
    variance = fields.Monetary(
        string='Variance (Over/Short)',
        compute='_compute_variance',
        store=True,
    )

    notes = fields.Text(
        string='Closing Notes',
    )

    state = fields.Selection(
        [('open', 'Open'),
         ('closing', 'Closing'),
         ('closed', 'Closed'),
         ('confirmed', 'Confirmed'),
         ('disputed', 'Disputed')],
        string='Status',
        default='open',
        required=True,
        tracking=True,
        index=True,
    )

    transaction_ids = fields.One2many(
        'petty.cash.transaction',
        'session_id',
        string='Transactions',
    )
    transaction_count = fields.Integer(
        compute='_compute_transaction_count',
    )
    paid_in = fields.Monetary(
        string='Cash In',
        compute='_compute_totals',
        store=True,
    )
    paid_out = fields.Monetary(
        string='Cash Out',
        compute='_compute_totals',
        store=True,
    )

    # ----- Display ----
    @api.depends('name', 'fund_id.name', 'date')
    def _compute_display_name(self):
        for s in self:
            if s.name and s.name != _('New') and s.fund_id and s.date:
                s.display_name = f'{s.name} · {s.fund_id.name} · {s.date}'
            else:
                s.display_name = s.name or _('New Session')

    # ----- Totals -----
    @api.depends('transaction_ids.amount', 'transaction_ids.direction',
                 'transaction_ids.state', 'transaction_ids.session_id')
    def _compute_totals(self):
        for s in self:
            in_amt = 0.0
            out_amt = 0.0
            # Only count paid transactions that belong to this session
            txs = s.transaction_ids.filtered(
                lambda t: t.state == 'paid' and t.session_id == s)
            for t in txs:
                if t.direction == 'in':
                    in_amt += t.amount
                else:
                    out_amt += t.amount
            s.paid_in = in_amt
            s.paid_out = out_amt

    @api.depends('opening_balance', 'paid_in', 'paid_out')
    def _compute_expected_balance(self):
        for s in self:
            s.expected_balance = s.opening_balance + s.paid_in - s.paid_out

    @api.depends('expected_balance', 'actual_balance')
    def _compute_variance(self):
        for s in self:
            if s.expected_balance and s.actual_balance is not False:
                s.variance = s.actual_balance - s.expected_balance
            else:
                s.variance = 0.0

    @api.depends('transaction_ids')
    def _compute_transaction_count(self):
        for s in self:
            s.transaction_count = len(s.transaction_ids)

    # ----- SQL / constraints -----
    _fund_date_unique = models.Constraint(
        'unique(fund_id, date)',
        'Only one session per cash box per date.',
    )

    @api.constrains('opening_balance')
    def _check_opening(self):
        for s in self:
            if s.opening_balance < 0:
                raise ValidationError(_('Opening balance cannot be negative.'))

    # ----- Lifecycle -----
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                fund = self.env['petty.cash.fund'].browse(vals.get('fund_id'))
                fund_code = (fund.code or 'PC') if fund else 'PC'
                seq = self.env['ir.sequence'].next_by_code(
                    'petty.cash.session') or '00000'
                vals['name'] = f'{fund_code}/S/{seq}'
        return super().create(vals_list)

    def action_start_closing(self):
        for s in self:
            if s.state != 'open':
                raise UserError(_('Only open sessions can move to closing.'))
            s.state = 'closing'

    def action_close(self, actual_balance=None):
        for s in self:
            if s.state not in ('open', 'closing'):
                raise UserError(_('Only open or closing-in-progress sessions can be closed.'))
            # Block close if any transaction is still mid-flow.
            stuck = s.transaction_ids.filtered(
                lambda t: t.state in ('draft', 'submitted'))
            if stuck:
                raise UserError(_(
                    'All transactions must be paid before closing. '
                    '%d transaction(s) are still pending.'
                ) % len(stuck))
            if actual_balance is not None:
                s.actual_balance = actual_balance
            s.state = 'closed'
            s.closed_at = fields.Datetime.now()
            s.closed_by = self.env.user.id
            s.message_post(body=_('Session closed by %s.') % self.env.user.name)

    def action_dispute(self):
        for s in self:
            if s.state == 'closed':
                raise UserError(_('A confirmed session cannot be disputed.'))
            s.state = 'disputed'
            s.message_post(body=_('Variance disputed.'))

    def action_confirm(self):
        for s in self:
            if s.state != 'closed':
                raise UserError(_('Only closed sessions can be confirmed.'))
            s.confirmed_by = self.env.user.id
            s.state = 'confirmed'
            s.message_post(body=_('Session confirmed by %s.') % self.env.user.name)

    def action_reopen(self):
        for s in self:
            # Reopen is forbidden once the session is confirmed — the manager
            # has signed off and the variance is recorded for the books.
            if s.state == 'confirmed':
                raise UserError(_(
                    'A confirmed session cannot be reopened. '
                    'If the figures are wrong, dispute and create a '
                    'correcting replacement instead.'
                ))
            if s.confirmed_by:
                raise UserError(_(
                    'This session has been confirmed by %s. '
                    'Dispute before re-opening.'
                ) % s.confirmed_by.name)
            s.state = 'open'
            s.closed_at = False
            s.confirmed_by = False
            s.message_post(body=_('Session reopened.'))

    # ----- Helpers -----
    @api.model
    def open_today(self, fund, opening_balance=None):
        """Open today's session for ``fund``.

        If a session already exists for today, return it; otherwise create one.
        """
        if not fund:
            raise UserError(_('A fund is required to open a session.'))
        today = fields.Date.context_today(self)
        existing = self.search([
            ('fund_id', '=', fund.id),
            ('date', '=', today),
        ], limit=1)
        if existing:
            return existing
        opening = opening_balance if opening_balance is not None else (
            fund.current_balance if fund.current_balance is not False
            else fund.opening_balance
        )
        session = self.create({
            'fund_id': fund.id,
            'date': today,
            'opening_balance': opening,
            'opened_by': self.env.user.id,
        })
        session.message_post(body=_('Session opened by %s.') % self.env.user.name)
        return session

    @api.model
    def _cron_close_yesterday(self):
        """Cron entry — close any open sessions from yesterday, open today's.

        Active by default at module install; switches off via the standard
        scheduled-actions UI.
        """
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)

        # Close any open session for yesterday that hasn't been touched today.
        stale = self.search([
            ('state', 'in', ('open', 'closing')),
            ('date', '<', today),
        ])
        for s in stale:
            # If there are no transactions and no actual_balance set, close at expected
            if s.actual_balance is False:
                s.actual_balance = s.expected_balance
            try:
                s.action_close()
                s.message_post(body=_('Cron closed stale session.'))
            except UserError as exc:
                _logger.warning(
                    'Petty cash session %s left open by cron: %s', s.name, exc)

        # Open a session for today on every active fund that uses auto-open.
        Fund = self.env['petty.cash.fund']
        funds = Fund.search([
            ('state', '=', 'active'),
            ('auto_open_daily_session', '=', True),
        ])
        for fund in funds:
            self.open_today(fund)

    # ----- Misc -----
    @api.model
    def _read_group_state(self, states, domain, order):
        return ['open', 'closing', 'closed', 'confirmed', 'disputed']
