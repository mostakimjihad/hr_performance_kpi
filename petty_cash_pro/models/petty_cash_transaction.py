# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PettyCashTransaction(models.Model):
    _name = 'petty.cash.transaction'
    _description = 'Petty Cash Transaction'
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

    # ---- What / when / how much ------------------------------------
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    fund_id = fields.Many2one(
        'petty.cash.fund',
        string='Cash Box',
        required=True,
        index=True,
        tracking=True,
    )
    direction = fields.Selection(
        [('in', 'Money In'),
         ('out', 'Money Out')],
        string='Direction',
        required=True,
        tracking=True,
        help='In = replenishment / cash returned. Out = expense.',
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
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
    category_id = fields.Many2one(
        'petty.cash.category',
        string='Category',
        required=True,
        tracking=True,
    )
    description = fields.Char(
        string='Description',
        required=True,
        tracking=True,
        help='Short text describing the transaction, e.g. "Taxi to client — Acme Inc."',
    )
    notes = fields.Text(
        string='Notes',
    )

    # ---- People ----------------------------------------------------
    submitter_id = fields.Many2one(
        'hr.employee',
        string='Submitter',
        default=lambda self: self.env.user.employee_id,
        tracking=True,
    )
    submitter_user_id = fields.Many2one(
        'res.users',
        string='Submitter User',
        related='submitter_id.user_id',
        store=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        tracking=True,
    )
    approval_required = fields.Boolean(
        string='Manager Approval Required',
        compute='_compute_approval_required',
        store=True,
    )

    # ---- Receipt / accounting --------------------------------------
    receipt_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Receipt',
        help='Upload the receipt photo/PDF here (will be stored in the chatter too).',
    )
    receipt_preview = fields.Binary(
        string='Receipt Preview',
        related='receipt_attachment_id.datas',
        readonly=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        help='Defaults from the chosen category. Override here if needed.',
    )
    analytic_distribution = fields.Json(
        string='Analytic Distribution',
        help='Odoo analytic-account distribution for the expense.',
    )

    # ---- State ----------------------------------------------------
    state = fields.Selection(
        [('draft', 'Draft'),
         ('submitted', 'Submitted'),
         ('approved', 'Approved'),
         ('rejected', 'Rejected'),
         ('paid', 'Paid'),
         ('cancelled', 'Cancelled')],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        index=True,
        group_expand='_read_group_state',
    )
    paid_date = fields.Date(
        string='Paid Date',
        readonly=True,
    )

    # ---- Computed / smart buttons ----------------------------------
    session_id = fields.Many2one(
        'petty.cash.session',
        string='Session',
        compute='_compute_session',
        store=True,
    )

    @api.depends('name', 'fund_id.code', 'date', 'amount')
    def _compute_display_name(self):
        for tx in self:
            if tx.name and tx.name != _('New') and tx.fund_id and tx.amount:
                tx.display_name = f'{tx.name} · {tx.amount:,.2f} {tx.currency_id.name or ""}'
            else:
                tx.display_name = tx.name or _('New Transaction')

    @api.depends('amount', 'fund_id.transaction_limit')
    def _compute_approval_required(self):
        for tx in self:
            tx.approval_required = (
                tx.amount and tx.fund_id.transaction_limit
                and tx.amount > tx.fund_id.transaction_limit
            )

    @api.depends('fund_id', 'date', 'state')
    def _compute_session(self):
        Session = self.env['petty.cash.session']
        for tx in self:
            session = Session.search([
                ('fund_id', '=', tx.fund_id.id),
                ('date', '=', tx.date),
            ], limit=1)
            tx.session_id = session

    # ---- CRUD -----------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self._next_name(vals)
            # Default account from category if not set
            if vals.get('category_id') and not vals.get('account_id'):
                cat = self.env['petty.cash.category'].browse(vals['category_id'])
                if cat.default_account_id:
                    vals['account_id'] = cat.default_account_id.id
        return super().create(vals_list)

    def _next_name(self, vals):
        fund = self.env['petty.cash.fund'].browse(vals.get('fund_id'))
        direction = vals.get('direction', 'in').upper()
        fund_code = (fund.code or 'PC') if fund else 'PC'
        # Use direction-specific sequences (PC-IN-..., PC-OUT-...)
        seq_code = f'petty.cash.transaction.{direction.lower()}'
        n = self.env['ir.sequence'].next_by_code(seq_code) or '00000'
        return f'{fund_code}/{direction}/{n}'

    # ---- Constraints ----------------------------------------------
    @api.constrains('amount')
    def _check_amount(self):
        for tx in self:
            if tx.amount is None or tx.amount <= 0:
                raise ValidationError(_('Transaction amount must be greater than zero.'))

    @api.constrains('fund_id', 'state')
    def _check_fund_active(self):
        for tx in self:
            if tx.fund_id.state != 'active' and tx.state not in ('cancelled', 'rejected'):
                raise ValidationError(_(
                    'You cannot create transactions on a fund that is %s.',
                    tx.fund_id.state,
                ))

    # ---- State transitions ----------------------------------------
    def action_submit(self):
        for tx in self:
            if tx.state != 'draft':
                raise UserError(_('Only draft transactions can be submitted.'))
            tx.state = 'submitted'
            tx.message_post(body=_('Transaction submitted.'))

    def action_approve(self):
        for tx in self:
            if tx.state != 'submitted':
                raise UserError(_('Only submitted transactions can be approved.'))
            tx.state = 'approved'
            tx.approver_id = self.env.user.id
            tx.message_post(body=_('Approved by %s.') % self.env.user.name)

    def action_reject(self):
        for tx in self:
            if tx.state != 'submitted':
                raise UserError(_('Only submitted transactions can be rejected.'))
            tx.state = 'rejected'
            tx.approver_id = self.env.user.id
            tx.message_post(body=_('Rejected by %s.') % self.env.user.name)

    def action_pay(self):
        for tx in self:
            # Money-in can skip the approval step (e.g. cash returned);
            # but we still require submitted at minimum.
            if tx.state == 'draft':
                raise UserError(_('Submit the transaction before paying.'))
            if tx.state in ('paid', 'cancelled', 'rejected'):
                raise UserError(_('This transaction is already finalized (%s).') % tx.state)
            tx.state = 'paid'
            tx.paid_date = fields.Date.context_today(self)
            tx.message_post(body=_('Transaction paid.'))

    def action_cancel(self):
        for tx in self:
            if tx.state in ('paid', 'cancelled'):
                raise UserError(_('Cannot cancel a paid or already-cancelled transaction.'))
            tx.state = 'cancelled'
            tx.message_post(body=_('Cancelled.'))

    def action_reset_draft(self):
        for tx in self:
            if tx.state not in ('rejected', 'cancelled'):
                raise UserError(_('Only rejected or cancelled transactions can be reset.'))
            tx.state = 'draft'
            tx.message_post(body=_('Reset to draft.'))

    def action_quick_pay(self):
        """Submit and (auto-)approve + pay in one click if under the fund's limit.

        Money-in (replenishment, return) auto-skips approval. Money-out below
        the fund's ``transaction_limit`` auto-approves. Above the limit, the
        transaction stops at ``submitted`` so a manager must approve.
        """
        for tx in self:
            if tx.state != 'draft':
                continue
            tx.action_submit()
            if tx.direction == 'in':
                tx.action_pay()
            elif not tx.approval_required:
                tx.action_approve()
                tx.action_pay()

    # ---- Attachment helpers ----------------------------------------
    def action_attach_receipt(self, attachment_data, attachment_name):
        """Attach a receipt file (binary data) to this transaction."""
        self.ensure_one()
        Attachment = self.env['ir.attachment']
        attachment = Attachment.create({
            'name': attachment_name,
            'datas': attachment_data,
            'res_model': 'petty.cash.transaction',
            'res_id': self.id,
            'type': 'binary',
        })
        self.write({'receipt_attachment_id': attachment.id})
        self.message_post(body=_('Receipt attached: %s') % attachment_name)

    # ---- Misc -----------------------------------------------------
    @api.model
    def _read_group_state(self, states, domain, order):
        return ['draft', 'submitted', 'approved', 'paid', 'rejected', 'cancelled']
