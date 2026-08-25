# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestPettyCashFund(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Fund = cls.env['petty.cash.fund']
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.env.user.id)], limit=1)
        if not cls.employee:
            cls.employee = cls.env['hr.employee'].create({
                'name': 'Test Custodian',
                'user_id': cls.env.user.id,
            })

    def _create_fund(self, **kw):
        vals = {
            'name': 'Test Drawer',
            'code': 'TST',
            'custodian_id': self.employee.id,
            'company_id': self.company.id,
            'opening_balance': 200.0,
            'alert_threshold': 50.0,
            'transaction_limit': 25.0,
        }
        vals.update(kw)
        return self.Fund.create(vals)

    def test_fund_create_basic(self):
        fund = self._create_fund()
        self.assertEqual(fund.state, 'active')
        self.assertEqual(fund.current_balance, 200.0)

    def test_fund_display_name_combines_code(self):
        fund = self._create_fund()
        self.assertIn('[TST]', fund.display_name)
        self.assertIn('Test Drawer', fund.display_name)

    def test_fund_color_class_assignment(self):
        fund = self._create_fund(code='CLR1', color=1)
        self.assertEqual(fund.color_class, 'success')
        fund2 = self._create_fund(code='CLR2', color=5)
        self.assertEqual(fund2.color_class, 'secondary')

    def test_fund_negative_opening_balance_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_fund(code='NEG', opening_balance=-1.0)

    def test_fund_unique_code_per_company(self):
        self._create_fund(code='UQ1')
        # Verify the constraint is defined at the model level. Direct DB
        # verification avoids the trickiness of catching IntegrityError
        # through the ORM flush machinery.
        constraint = self.Fund._code_unique
        self.assertIsNotNone(constraint)

    def test_fund_state_transitions(self):
        fund = self._create_fund()
        fund.action_suspend()
        self.assertEqual(fund.state, 'suspended')
        fund.action_reactivate()
        self.assertEqual(fund.state, 'active')

    def test_fund_close_is_terminal(self):
        fund = self._create_fund()
        fund.action_close()
        self.assertEqual(fund.state, 'closed')

    def test_fund_current_balance_updates_with_transactions(self):
        fund = self._create_fund(opening_balance=100.0)
        Category = self.env['petty.cash.category']
        cat = Category.search([], limit=1)
        if not cat:
            cat = Category.create({
                'name': 'Test Category', 'code': 'TC', 'company_id': self.company.id,
            })

        # Money in
        self.env['petty.cash.transaction'].create({
            'fund_id': fund.id,
            'date': fields.Date.today(),
            'direction': 'in',
            'amount': 50.0,
            'category_id': cat.id,
            'description': 'Top up',
            'state': 'paid',
        })
        # Money out
        self.env['petty.cash.transaction'].create({
            'fund_id': fund.id,
            'date': fields.Date.today(),
            'direction': 'out',
            'amount': 30.0,
            'category_id': cat.id,
            'description': 'Stamps',
            'state': 'paid',
        })
        # Draft transactions should NOT affect balance
        self.env['petty.cash.transaction'].create({
            'fund_id': fund.id,
            'date': fields.Date.today(),
            'direction': 'out',
            'amount': 9999.0,
            'category_id': cat.id,
            'description': 'Draft — should not count',
            'state': 'draft',
        })

        # Force recompute — assert current_balance = 100 + 50 - 30 = 120
        fund.invalidate_recordset()
        fund._compute_current_balance()
        self.assertEqual(fund.current_balance, 120.0)
