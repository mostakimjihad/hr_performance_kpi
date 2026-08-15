# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SalonBranch(models.Model):
    _name = 'salon.branch'
    _description = 'Salon Branch'
    _order = 'sequence, name'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help="Short code used in the appointment reference.")
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='company_id.currency_id',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Address',
        help="Postal address shown on the portal branch page.",
    )
    phone = fields.Char()
    email = fields.Char()
    image = fields.Image(max_width=1920, max_height=1920)
    manager_id = fields.Many2one(
        'hr.employee', string='Branch Manager',
    )
    active = fields.Boolean(default=True)
    online_visible = fields.Boolean(
        default=True,
        help="Uncheck to hide this branch from the public booking portal.",
    )

    # Working hours stored as a JSON list of dicts:
    # [{'dayofweek': '0', 'hour_from': 9.0, 'hour_to': 19.5, 'break_from': 13.0, 'break_to': 14.0}]
    hour_ids = fields.One2many(
        'salon.branch.hour', 'branch_id', string='Opening Hours',
    )

    # Stylists at this branch — reverse direction of salon.stylist.branch_ids
    stylist_ids = fields.Many2many(
        'salon.stylist',
        'salon_stylist_branch_rel',
        'branch_id', 'stylist_id',
        string='Stylists',
    )
    # Services offered at this branch — through stylists.service_ids ∪ services.branch_ids
    service_ids = fields.Many2many(
        'salon.service',
        compute='_compute_service_ids',
        string='Available services',
    )
    appointment_ids = fields.One2many('salon.appointment', 'branch_id')
    appointment_count = fields.Integer(compute='_compute_appointment_count')
    chair_ids = fields.One2many('salon.chair', 'branch_id', string='Chairs')

    def _compute_service_ids(self):
        for branch in self:
            stylist_services = branch.stylist_ids.service_ids
            branch_services = self.env['salon.service'].sudo().search([
                '|',
                ('branch_ids', '=', False),
                ('branch_ids', 'in', branch.id),
            ])
            branch.service_ids = (stylist_services & branch_services) | branch_services

    def _compute_appointment_count(self):
        counts = {
            b['branch_id'][0] if isinstance(b['branch_id'], (list, tuple)) else b['branch_id']:
                b['branch_id_count']
            for b in self.env['salon.appointment'].read_group(
                [('branch_id', 'in', self.ids)],
                ['branch_id'], ['branch_id'],
            )
        }
        for branch in self:
            branch.appointment_count = counts.get(branch.id, 0)

    def _slot_step_minutes(self):
        return 15

    def _open_hours_for(self, weekday):
        """Return the list of hour records for a given weekday int (0=Mon)."""
        self.ensure_one()
        return self.hour_ids.filtered(lambda h: int(h.dayofweek) == weekday)

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def get_available_slots(self, date, duration_minutes, stylist_id=False, exclude_appointment_id=False):
        """Return a list of UTC datetimes for slots that can fit *duration_minutes*.

        :param date: ``datetime.date`` (or ISO string) to search.
        :param duration_minutes: total duration the customer wants to book.
        :param stylist_id: optional stylist to filter by. ``False`` means *any*
            stylist at this branch who can perform all services.
        :param exclude_appointment_id: appointment id to ignore (for reschedule).
        :returns: list of ``datetime`` in the branch's timezone.
        """
        self.ensure_one()
        from datetime import datetime, time, timedelta

        # Tolerate either a date object or an ISO string.
        if isinstance(date, str):
            date = datetime.fromisoformat(date).date()

        slots = []
        step = timedelta(minutes=self._slot_step_minutes())

        if not self.hour_ids:
            return slots

        hours = self._open_hours_for(date.weekday())
        if not hours:
            return slots

        # Stylists eligible for the slot: at the branch, with the service
        # (caller has already filtered services). stylist_id narrows it.
        domain = [('branch_ids', 'in', self.id)]
        if stylist_id:
            domain.append(('id', '=', stylist_id))
        stylists = self.env['salon.stylist'].search(domain)
        if not stylists:
            return slots

        # Existing appointments of the day for these stylists
        day_start = datetime.combine(date, time.min)
        day_end = datetime.combine(date, time.max)
        appt_domain = [
            ('branch_id', '=', self.id),
            ('start_datetime', '>=', day_start),
            ('start_datetime', '<=', day_end),
            ('state', 'in', ('confirmed', 'in_progress')),
        ]
        if exclude_appointment_id:
            appt_domain.append(('id', '!=', exclude_appointment_id))
        existing = self.env['salon.appointment'].search(appt_domain)

        needed = timedelta(minutes=duration_minutes)
        for hour in hours:
            start_dt = datetime.combine(date, time()) + timedelta(hours=hour.hour_from)
            end_dt = datetime.combine(date, time()) + timedelta(hours=hour.hour_to)
            break_start = datetime.combine(date, time()) + timedelta(hours=hour.break_from) if hour.break_from else None
            break_end = datetime.combine(date, time()) + timedelta(hours=hour.break_to) if hour.break_to else None

            cursor = start_dt
            while cursor + needed <= end_dt:
                if break_start and break_end and cursor < break_end and cursor + needed > break_start:
                    cursor += step
                    continue
                slot_end = cursor + needed
                if slot_end <= datetime.now():
                    cursor += step
                    continue
                # check at least one stylist is free
                if any(self._stylist_free(s, cursor, slot_end, existing) for s in stylists):
                    slots.append(cursor)
                cursor += step
        return slots

    def _stylist_free(self, stylist, start, end, existing):
        for appt in existing:
            if appt.stylist_id == stylist:
                if appt.start_datetime < end and appt.end_datetime > start:
                    return False
        return True


class SalonBranchHour(models.Model):
    _name = 'salon.branch.hour'
    _description = 'Salon Branch Opening Hour'
    _order = 'dayofweek, hour_from'

    branch_id = fields.Many2one('salon.branch', required=True, ondelete='cascade')
    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], required=True)
    hour_from = fields.Float(string='Opening', required=True)
    hour_to = fields.Float(string='Closing', required=True)
    break_from = fields.Float(string='Break start')
    break_to = fields.Float(string='Break end')

    @api.constrains('hour_to', 'break_to', 'break_from')
    def _check_hours(self):
        for rec in self:
            if rec.hour_to <= rec.hour_from:
                raise ValidationError(_('Closing time must be after opening time.'))
            if rec.break_from and rec.break_to:
                if not (rec.hour_from <= rec.break_from < rec.break_to <= rec.hour_to):
                    raise ValidationError(_('Break must be inside opening hours.'))

    @api.constrains('dayofweek', 'branch_id')
    def _check_unique_day(self):
        for rec in self:
            if rec.search_count([
                ('branch_id', '=', rec.branch_id.id),
                ('dayofweek', '=', rec.dayofweek),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(_('Only one opening-hours row per day per branch.'))