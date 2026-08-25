# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    petty_cash_fund_ids = fields.One2many(
        'petty.cash.fund',
        'custodian_id',
        string='Petty Cash Funds',
    )
    petty_cash_fund_count = fields.Integer(
        string='Funds Count',
        compute='_compute_petty_cash_fund_count',
    )
    petty_cash_transaction_ids = fields.One2many(
        'petty.cash.transaction',
        'submitter_id',
        string='Petty Cash Transactions',
    )
    petty_cash_month_spent = fields.Monetary(
        string='Petty Cash Month-to-Date',
        currency_field='company_currency_id',
        compute='_compute_petty_cash_month_spent',
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_company_currency_id',
    )

    @api.depends('petty_cash_fund_ids')
    def _compute_petty_cash_fund_count(self):
        for emp in self:
            emp.petty_cash_fund_count = len(emp.petty_cash_fund_ids)

    @api.depends('company_id')
    def _compute_company_currency_id(self):
        for emp in self:
            emp.company_currency_id = emp.company_id.currency_id

    @api.depends('petty_cash_transaction_ids')
    def _compute_petty_cash_month_spent(self):
        from datetime import date
        today = date.today()
        month_start = today.replace(day=1)
        for emp in self:
            total = 0.0
            for tx in emp.petty_cash_transaction_ids:
                if (tx.state == 'paid' and tx.direction == 'out'
                        and tx.date and tx.date >= month_start):
                    total += tx.amount
            emp.petty_cash_month_spent = total

    def action_view_petty_cash_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Petty Cash Transactions'),
            'res_model': 'petty.cash.transaction',
            'view_mode': 'list,form',
            'domain': [('submitter_id', '=', self.id)],
            'context': {'default_submitter_id': self.id},
        }
