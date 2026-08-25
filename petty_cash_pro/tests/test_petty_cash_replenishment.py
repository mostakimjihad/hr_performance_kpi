# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestPettyCashReplenishment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].search(
            [('user_id', '=', cls.env.user.id)], limit=1) or cls.env['hr.employee'].create({
                'name': 'Test',
                'user_id': cls.env.user.id,
            })
        cls.fund = cls.env['petty.cash.fund'].create({
            'name': 'Rep Test Fund',
            'code': 'RTF',
            'custodian_id': cls.employee.id,
            'company_id': cls.company.id,
            'opening_balance': 100.0,
            'alert_threshold': 50.0,
            'transaction_limit': 25.0,
        })

    def test_replenishment_workflow(self):
        r = self.env['petty.cash.replenishment'].create({
            'fund_id': self.fund.id,
            'amount': 200.0,
            'reason': 'Balance below threshold',
        })
        self.assertEqual(r.state, 'draft')
        self.assertNotEqual(r.name, 'New')
        self.assertIn('RTF', r.name)

        r.action_submit()
        self.assertEqual(r.state, 'submitted')
        r.action_approve()
        self.assertEqual(r.state, 'approved')
        self.assertEqual(r.approved_by, self.env.user)
        self.assertTrue(r.approval_date)

        # Receiving should add the cash to the fund.
        pre_balance = self.fund.current_balance
        r.action_receive()
        self.assertEqual(r.state, 'received')
        self.fund.invalidate_recordset()
        # Allow cron-like load: recompute balance
        self.fund._compute_current_balance()
        self.assertGreater(self.fund.current_balance, pre_balance)

    def test_replenishment_reject(self):
        r = self.env['petty.cash.replenishment'].create({
            'fund_id': self.fund.id,
            'amount': 200.0,
        })
        r.action_submit()
        r.action_reject()
        self.assertEqual(r.state, 'rejected')

    def test_replenishment_cannot_receive_unapproved(self):
        r = self.env['petty.cash.replenishment'].create({
            'fund_id': self.fund.id,
            'amount': 100.0,
        })
        r.action_submit()
        with self.assertRaises(UserError):
            r.action_receive()

    def test_replenishment_cannot_cancel_after_received(self):
        r = self.env['petty.cash.replenishment'].create({
            'fund_id': self.fund.id,
            'amount': 100.0,
        })
        r.action_submit()
        r.action_approve()
        r.action_receive()
        with self.assertRaises(UserError):
            r.action_cancel()
