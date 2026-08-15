# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, datetime, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSalonBooking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['salon.branch'].create({
            'name': 'Test Branch',
            'code': 'TB',
        })
        # Opening hours: Mon-Fri 09:00-18:00
        for d in range(0, 5):
            cls.env['salon.branch.hour'].create({
                'branch_id': cls.branch.id,
                'dayofweek': str(d),
                'hour_from': 9.0,
                'hour_to': 18.0,
            })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Stylist',
        })
        cls.stylist = cls.env['salon.stylist'].create({
            'employee_id': cls.employee.id,
            'branch_ids': [(6, 0, [cls.branch.id])],
        })
        cls.service = cls.env['salon.service'].create({
            'name': 'Test Cut',
            'category_id': cls.env['salon.service.category'].create({
                'name': 'Hair',
            }).id,
            'duration': 1.0,
            'list_price': 50.0,
        })
        cls.stylist.service_ids = [(6, 0, [cls.service.id])]

    def test_slot_returns_open_hours(self):
        # Monday next week
        target = date(2026, 1, 5)
        slots = self.branch.get_available_slots(target, 60)
        self.assertGreater(len(slots), 0, 'Expected open slots for Monday 09:00-18:00')

    def test_appointment_creates_with_lines(self):
        start = datetime(2026, 1, 5, 10, 0)
        appt = self.env['salon.appointment'].create({
            'branch_id': self.branch.id,
            'stylist_id': self.stylist.id,
            'start_datetime': start,
            'guest_name': 'Jane Doe',
            'guest_email': 'jane@example.com',
            'guest_phone': '+15555550100',
            'line_ids': [(0, 0, {'service_id': self.service.id})],
        })
        self.assertEqual(appt.state, 'draft')
        self.assertEqual(appt.duration, 1.0)
        self.assertEqual(appt.end_datetime - appt.start_datetime, timedelta(hours=1))
        self.assertEqual(appt.total_price, 50.0)

    def test_overlap_raises(self):
        start = datetime(2026, 1, 5, 10, 0)
        self.env['salon.appointment'].create({
            'branch_id': self.branch.id,
            'stylist_id': self.stylist.id,
            'start_datetime': start,
            'guest_name': 'A',
            'guest_email': 'a@example.com',
            'guest_phone': '1',
            'line_ids': [(0, 0, {'service_id': self.service.id})],
            'state': 'confirmed',
        })
        with self.assertRaises(ValidationError):
            self.env['salon.appointment'].create({
                'branch_id': self.branch.id,
                'stylist_id': self.stylist.id,
                'start_datetime': start + timedelta(minutes=30),
                'guest_name': 'B',
                'guest_email': 'b@example.com',
                'guest_phone': '2',
                'line_ids': [(0, 0, {'service_id': self.service.id})],
                'state': 'confirmed',
            })

    def test_lifecycle(self):
        start = datetime(2026, 1, 5, 10, 0)
        appt = self.env['salon.appointment'].create({
            'branch_id': self.branch.id,
            'stylist_id': self.stylist.id,
            'start_datetime': start,
            'guest_name': 'L',
            'guest_email': 'l@example.com',
            'guest_phone': '3',
            'line_ids': [(0, 0, {'service_id': self.service.id})],
        })
        appt.action_confirm()
        self.assertEqual(appt.state, 'confirmed')
        appt.action_start()
        self.assertEqual(appt.state, 'in_progress')
        appt.action_done()
        self.assertEqual(appt.state, 'done')

    def test_token_unique(self):
        start = datetime(2026, 1, 5, 11, 0)
        a1 = self.env['salon.appointment'].create({
            'branch_id': self.branch.id,
            'stylist_id': self.stylist.id,
            'start_datetime': start,
            'guest_name': 'T',
            'guest_email': 't@example.com',
            'guest_phone': '4',
            'line_ids': [(0, 0, {'service_id': self.service.id})],
        })
        a2 = self.env['salon.appointment'].create({
            'branch_id': self.branch.id,
            'stylist_id': self.stylist.id,
            'start_datetime': start + timedelta(hours=2),
            'guest_name': 'U',
            'guest_email': 'u@example.com',
            'guest_phone': '5',
            'line_ids': [(0, 0, {'service_id': self.service.id})],
        })
        self.assertNotEqual(a1.access_token, a2.access_token)
        self.assertTrue(a1.access_token)