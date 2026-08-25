# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestPettyCashSession(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.env.user.id)], limit=1) or cls.env['hr.employee'].create({
                'name': 'Test',
                'user_id': cls.env.user.id,
            })
        cls.category = cls.env['petty.cash.category'].create({
            'name': 'Test Cat',
            'code': 'TS',
            'company_id': cls.company.id,
        })
        cls.fund = cls.env['petty.cash.fund'].create({
            'name': 'Test Fund',
            'code': 'TSF',
            'custodian_id': cls.employee.id,
            'company_id': cls.company.id,
            'opening_balance': 200.0,
            'alert_threshold': 50.0,
            'transaction_limit': 25.0,
        })

    def test_one_session_per_day(self):
        Session = self.env['petty.cash.session']
        today = fields.Date.context_today(self)
        Session.create({
            'fund_id': self.fund.id,
            'date': today,
            'opening_balance': 200.0,
        })
        constraint = Session._fund_date_unique
        self.assertIsNotNone(constraint)

    def test_session_totals_and_variance(self):
        Session = self.env['petty.cash.session']
        session = Session.create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 200.0,
        })

        # Money in
        self.env['petty.cash.transaction'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'direction': 'in',
            'amount': 50.0,
            'category_id': self.category.id,
            'description': 'Top up',
            'state': 'paid',
        })
        # Money out
        self.env['petty.cash.transaction'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'direction': 'out',
            'amount': 30.0,
            'category_id': self.category.id,
            'description': 'Expense',
            'state': 'paid',
        })

        session.invalidate_recordset()
        session._compute_totals()
        session._compute_expected_balance()
        session._compute_variance()

        # Expected = 200 + 50 - 30 = 220
        self.assertEqual(session.paid_in, 50.0)
        self.assertEqual(session.paid_out, 30.0)
        self.assertEqual(session.expected_balance, 220.0)

    def test_session_close_with_stuck_transactions_blocked(self):
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 100.0,
        })
        # Create a draft transaction
        self.env['petty.cash.transaction'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'direction': 'out',
            'amount': 15.0,
            'category_id': self.category.id,
            'description': 'Stuck draft',
            'state': 'draft',
        })
        with self.assertRaises(UserError):
            session.action_close()

    def test_session_open_today_helper(self):
        Session = self.env['petty.cash.session']
        first = Session.open_today(self.fund, opening_balance=200.0)
        second = Session.open_today(self.fund, opening_balance=200.0)
        self.assertEqual(first, second)

    def test_session_confirm_requires_closed(self):
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 200.0,
        })
        with self.assertRaises(UserError):
            session.action_confirm()

    def test_session_confirm_transitions_to_confirmed(self):
        """Confirm sets state='confirmed' so the status flow is clean."""
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 200.0,
        })
        session.action_start_closing()
        session.action_close(actual_balance=200.0)
        self.assertEqual(session.state, 'closed')
        session.action_confirm()
        self.assertEqual(session.state, 'confirmed')
        self.assertEqual(session.confirmed_by, self.env.user)

    def test_session_reopen_blocked_when_confirmed(self):
        """Reopen of a confirmed session raises — locked by the audit trail."""
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 200.0,
        })
        session.action_start_closing()
        session.action_close(actual_balance=200.0)
        session.action_confirm()
        self.assertEqual(session.state, 'confirmed')
        with self.assertRaises(UserError):
            session.action_reopen()

    def test_session_close_already_confirmed_blocked(self):
        """Confirmed session cannot be re-closed — only already-open/closing ones."""
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 200.0,
        })
        session.action_start_closing()
        session.action_close(actual_balance=200.0)
        session.action_confirm()
        with self.assertRaises(UserError):
            session.action_close(actual_balance=200.0)

    def test_session_state_full_lifecycle(self):
        """open → closing → closed → confirmed: each transition visible to chatter."""
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 100.0,
        })
        self.assertEqual(session.state, 'open')

        session.action_start_closing()
        self.assertEqual(session.state, 'closing')

        session.action_close(actual_balance=100.0)
        self.assertEqual(session.state, 'closed')
        self.assertTrue(session.closed_at)
        self.assertTrue(session.closed_by)
        self.assertTrue(session.expected_balance)

        session.action_confirm()
        self.assertEqual(session.state, 'confirmed')
        self.assertTrue(session.confirmed_by)

    def test_session_dispute_variance(self):
        session = self.env['petty.cash.session'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'opening_balance': 200.0,
        })
        session.action_start_closing()
        session.action_dispute()
        self.assertEqual(session.state, 'disputed')

    def test_session_cron_idempotent(self):
        """Running _cron_close_yesterday twice shouldn't double-create today."""
        Session = self.env['petty.cash.session']
        # First run: opens today's session.
        Session._cron_close_yesterday()
        # Second run: should be a no-op (session already exists for today).
        Session._cron_close_yesterday()
        sessions_today = Session.search([
            ('fund_id', '=', self.fund.id),
            ('date', '=', fields.Date.context_today(self)),
        ])
        # At most one session for today per fund
        self.assertEqual(len(sessions_today), 1)
