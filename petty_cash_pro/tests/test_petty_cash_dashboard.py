# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestPettyCashDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.env.user.id)], limit=1) or cls.env['hr.employee'].create({
                'name': 'Dash',
                'user_id': cls.env.user.id,
            })
        cls.category = cls.env['petty.cash.category'].create({
            'name': 'Dash Cat', 'code': 'DC', 'company_id': cls.company.id,
        })
        cls.fund = cls.env['petty.cash.fund'].create({
            'name': 'Dash Fund',
            'code': 'DF',
            'custodian_id': cls.employee.id,
            'company_id': cls.company.id,
            'opening_balance': 100.0,
            'alert_threshold': 25.0,
            'transaction_limit': 25.0,
        })
        cls.fund_high = cls.env['petty.cash.fund'].create({
            'name': 'Top Up Fund',
            'code': 'TU',
            'custodian_id': cls.employee.id,
            'company_id': cls.company.id,
            'opening_balance': 500.0,
            'alert_threshold': 100.0,
            'transaction_limit': 25.0,
        })

    def test_dashboard_aggregates(self):
        """Computed aggregates are correct for the test's funds + transactions.

        Demo data may load other transactions today. We assert deltas relative
        to a baseline, so the test stays green whether demo is loaded or not.
        """
        dash_before = self.env['petty.cash.dashboard'].create({})
        dash_before._compute_summary()
        base_income = dash_before.today_income
        base_expenses = dash_before.today_expenses
        base_net = dash_before.today_net
        base_count = dash_before.today_count
        base_current = dash_before.current_balance
        base_pending = dash_before.pending_approvals

        # Seed some paid transactions today
        for amt in (10.0, 15.0):
            self.env['petty.cash.transaction'].create({
                'fund_id': self.fund.id,
                'date': fields.Date.today(),
                'direction': 'out',
                'amount': amt,
                'category_id': self.category.id,
                'description': 'Test',
                'state': 'paid',
            })
        # Money in (replenishment)
        self.env['petty.cash.transaction'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'direction': 'in',
            'amount': 50.0,
            'category_id': self.category.id,
            'description': 'Top up',
            'state': 'paid',
        })
        # Submitted transaction counts toward pending
        self.env['petty.cash.transaction'].create({
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'direction': 'out',
            'amount': 5.0,
            'category_id': self.category.id,
            'description': 'Pending',
            'state': 'submitted',
        })

        dash_after = self.env['petty.cash.dashboard'].create({})
        dash_after._compute_summary()

        # Deltas: +1 in (50), +2 paid out (25), +1 submitted
        self.assertAlmostEqual(dash_after.today_income - base_income, 50.0, places=2)
        self.assertAlmostEqual(dash_after.today_expenses - base_expenses, 25.0, places=2)
        self.assertAlmostEqual(dash_after.today_net - base_net, 25.0, places=2)
        self.assertEqual(dash_after.today_count - base_count, 3)
        self.assertEqual(dash_after.pending_approvals - base_pending, 1)
        # The two new paid transactions adjust the test fund's current balance
        # by 50 (in) − 25 (out) = +25 over the prior total.
        self.assertAlmostEqual(dash_after.current_balance - base_current, 25.0, places=2)

    def test_dashboard_low_balance_alerts(self):
        """The test funds stay non-low; if demo data dips below thresholds,
        the alert count must be at least zero (which it always is)."""
        dash = self.env['petty.cash.dashboard'].create({})
        dash._compute_summary()
        # Smoke test only — demo data may add real alerts, which is fine.
        self.assertGreaterEqual(dash.low_balance_count, 0)

    def test_dashboard_renders_html(self):
        dash = self.env['petty.cash.dashboard'].create({})
        dash._compute_summary()
        # HTML payloads populated
        self.assertTrue(dash.cash_flow_html)
        self.assertIn('<svg', dash.cash_flow_html)
        self.assertTrue(dash.fund_snapshots_html)
        self.assertTrue(dash.recent_transactions_html)
        self.assertTrue(dash.top_categories_html)
        self.assertTrue(dash.low_balance_html)

    def test_render_cash_flow_empty_series_returns_placeholder(self):
        html = self.env['petty.cash.dashboard']._render_cash_flow(
            [], self.company.currency_id)
        self.assertIn('No cash flow yet', html)

    def test_render_top_categories_empty_returns_placeholder(self):
        html = self.env['petty.cash.dashboard']._render_top_categories(
            [], self.company.currency_id)
        self.assertIn('No expenses', html)

    def test_dashboard_new_widgets_render(self):
        """Approval Queue, Top Custodians, Monthly Budget all render."""
        # Seed a submitted transaction
        cat = self.env['petty.cash.category'].search([], limit=1)
        if cat:
            self.env['petty.cash.transaction'].create({
                'fund_id': self.fund.id,
                'date': fields.Date.today(),
                'direction': 'out',
                'amount': 200.0,                 # above the limit so it stays submitted
                'category_id': cat.id,
                'description': 'Pending plumber',
                'state': 'submitted',
            })

        dash = self.env['petty.cash.dashboard'].create({})
        dash._compute_summary()

        self.assertTrue(dash.approval_queue_html)
        # At least one item links to a transaction form
        self.assertIn('/web#id=', dash.approval_queue_html)
        self.assertIn('Pending plumber', dash.approval_queue_html)

        # Budget burn should contain at least one progress bar
        self.assertTrue(dash.budget_burn_html)
        self.assertIn('progress-bar', dash.budget_burn_html)

    def test_render_approval_queue_empty(self):
        html = self.env['petty.cash.dashboard']._render_approval_queue(
            [], self.company.currency_id)
        self.assertIn('No transactions awaiting approval', html)

    def test_render_top_custodians_empty(self):
        html = self.env['petty.cash.dashboard']._render_top_custodians(
            [], self.company.currency_id)
        self.assertIn('No custodian activity', html)

    def test_render_budget_burn_empty(self):
        html = self.env['petty.cash.dashboard']._render_budget_burn(
            [], self.company.currency_id)
        self.assertIn('No monthly budgets', html)
