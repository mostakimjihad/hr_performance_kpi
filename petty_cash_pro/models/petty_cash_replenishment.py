# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PettyCashReplenishment(models.Model):
    _name = 'petty.cash.replenishment'
    _description = 'Petty Cash Replenishment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
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
    amount = fields.Monetary(
        string='Amount Requested',
        required=True,
        tracking=True,
    )
    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user.id,
    )
    requested_employee_id = fields.Many2one(
        'hr.employee',
        string='Requester Employee',
        default=lambda self: self.env.user.employee_id.id,
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
    )
    approval_date = fields.Datetime(
        string='Approval Date',
    )
    received_by = fields.Many2one(
        'res.users',
        string='Received By',
    )
    received_date = fields.Datetime(
        string='Received Date',
    )

    reason = fields.Text(
        string='Reason',
        help='Why is this top-up needed? (e.g. "Balance below threshold" or "Project onsite expense")',
    )
    notes = fields.Text(string='Notes')

    state = fields.Selection(
        [('draft', 'Draft'),
         ('submitted', 'Submitted'),
         ('approved', 'Approved'),
         ('rejected', 'Rejected'),
         ('received', 'Received'),
         ('cancelled', 'Cancelled')],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        index=True,
        group_expand='_read_group_state',
    )

    @api.depends('name', 'amount', 'fund_id.name')
    def _compute_display_name(self):
        for r in self:
            if r.name and r.name != _('New') and r.amount:
                r.display_name = f'{r.name} · {r.amount:,.2f}'
            else:
                r.display_name = r.name or _('New Replenishment')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                fund = self.env['petty.cash.fund'].browse(vals.get('fund_id'))
                fund_code = (fund.code or 'PC') if fund else 'PC'
                seq = self.env['ir.sequence'].next_by_code(
                    'petty.cash.replenishment') or '00000'
                vals['name'] = f'{fund_code}/R/{seq}'
        return super().create(vals_list)

    # ----- State transitions -----
    def action_submit(self):
        for r in self:
            if r.state != 'draft':
                raise UserError(_('Only draft replenishments can be submitted.'))
            r.state = 'submitted'
            r.message_post(body=_('Replenishment submitted.'))

    def action_approve(self):
        for r in self:
            if r.state != 'submitted':
                raise UserError(_('Only submitted replenishments can be approved.'))
            r.state = 'approved'
            r.approved_by = self.env.user.id
            r.approval_date = fields.Datetime.now()
            r.message_post(body=_('Approved by %s.') % self.env.user.name)

    def action_reject(self):
        for r in self:
            if r.state != 'submitted':
                raise UserError(_('Only submitted replenishments can be rejected.'))
            r.state = 'rejected'
            r.approved_by = self.env.user.id
            r.message_post(body=_('Rejected by %s.') % self.env.user.name)

    def action_receive(self):
        """Mark as received and create an inbound transaction on the fund."""
        for r in self:
            if r.state != 'approved':
                raise UserError(_('Only approved replenishments can be received.'))
            # Create a paid 'in' transaction that funds the drawer today.
            self.env['petty.cash.transaction'].create({
                'fund_id': r.fund_id.id,
                'date': fields.Date.context_today(self),
                'direction': 'in',
                'amount': r.amount,
                'description': f'Replenishment {r.name}',
                'category_id': self._default_replenishment_category(r),
                'state': 'paid',
                'paid_date': fields.Date.context_today(self),
            })
            r.state = 'received'
            r.received_by = self.env.user.id
            r.received_date = fields.Datetime.now()
            r.message_post(body=_('Received by %s — cash added to drawer.') % self.env.user.name)

    def action_cancel(self):
        for r in self:
            if r.state in ('received', 'cancelled'):
                raise UserError(_('Cannot cancel a received or already cancelled replenishment.'))
            r.state = 'cancelled'
            r.message_post(body=_('Cancelled.'))

    def _default_replenishment_category(self, replenishment):
        Category = self.env['petty.cash.category']
        company = replenishment.company_id or self.env.company
        cat = Category.search([
            ('code', '=', 'REPLENISH'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not cat:
            cat = Category.create({
                'name': 'Replenishment',
                'code': 'REPLENISH',
                'company_id': company.id,
            })
        return cat.id

    @api.model
    def _read_group_state(self, states, domain, order):
        return ['draft', 'submitted', 'approved', 'received', 'rejected', 'cancelled']
