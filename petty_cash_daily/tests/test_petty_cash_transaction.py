# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestPettyCashTransaction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.env.user.id)], limit=1) or cls.env['hr.employee'].create({
                'name': 'Test Submitter',
                'user_id': cls.env.user.id,
            })
        cls.category = cls.env['petty.cash.category'].search(
            [('code', '=', 'TRAVEL')], limit=1)
        if not cls.category:
            cls.category = cls.env['petty.cash.category'].create({
                'name': 'Travel', 'code': 'TRAVEL',
                'company_id': cls.company.id,
            })
        cls.fund = cls.env['petty.cash.fund'].create({
            'name': 'Test Fund',
            'code': 'TF',
            'custodian_id': cls.employee.id,
            'company_id': cls.company.id,
            'opening_balance': 200.0,
            'alert_threshold': 50.0,
            'transaction_limit': 25.0,
        })

    def _create_tx(self, **kw):
        vals = {
            'fund_id': self.fund.id,
            'date': fields.Date.today(),
            'direction': 'out',
            'amount': 10.0,
            'category_id': self.category.id,
            'description': 'Test expense',
            'submitter_id': self.employee.id,
        }
        vals.update(kw)
        return self.env['petty.cash.transaction'].create(vals)

    def test_transaction_name_sequence(self):
        tx = self._create_tx()
        self.assertTrue(tx.name)
        self.assertNotEqual(tx.name, 'New')
        self.assertIn('PCOUT', tx.name)

    def test_transaction_money_in_sequence(self):
        tx = self._create_tx(direction='in', amount=50.0, description='Top up')
        self.assertIn('PCIN', tx.name)

    def test_transaction_zero_amount_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_tx(amount=0.0)

    def test_transaction_negative_amount_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_tx(amount=-5.0)

    def test_transaction_workflow(self):
        tx = self._create_tx()
        self.assertEqual(tx.state, 'draft')
        tx.action_submit()
        self.assertEqual(tx.state, 'submitted')
        tx.action_approve()
        self.assertEqual(tx.state, 'approved')
        self.assertEqual(tx.approver_id, self.env.user)
        tx.action_pay()
        self.assertEqual(tx.state, 'paid')
        self.assertTrue(tx.paid_date)

    def test_transaction_workflow_cancel(self):
        tx = self._create_tx()
        tx.action_submit()
        tx.action_cancel()
        self.assertEqual(tx.state, 'cancelled')

    def test_transaction_reset_draft_from_rejected(self):
        tx = self._create_tx(amount=30.0)
        tx.action_submit()
        tx.action_reject()
        self.assertEqual(tx.state, 'rejected')
        tx.action_reset_draft()
        self.assertEqual(tx.state, 'draft')

    def test_transaction_approval_required_above_limit(self):
        tx_small = self._create_tx(amount=20.0)
        tx_large = self._create_tx(amount=100.0)
        self.assertFalse(tx_small.approval_required)
        self.assertTrue(tx_large.approval_required)

    def test_quick_pay_under_limit(self):
        tx = self._create_tx(amount=10.0)
        tx.action_quick_pay()
        self.assertEqual(tx.state, 'paid')

    def test_quick_pay_above_limit_stops_at_submitted(self):
        tx = self._create_tx(amount=100.0)
        tx.action_quick_pay()
        self.assertEqual(tx.state, 'submitted')

    def test_quick_pay_money_in_auto_pays(self):
        tx = self._create_tx(direction='in', amount=50.0)
        tx.action_quick_pay()
        self.assertEqual(tx.state, 'paid')

    def test_transaction_pay_requires_submitted_or_approved(self):
        tx = self._create_tx()
        with self.assertRaises(UserError):
            tx.action_pay()  # draft

    def test_transaction_on_suspended_fund_rejected(self):
        self.fund.state = 'suspended'
        with self.assertRaises(ValidationError):
            self._create_tx()
