# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def _gen_token(record=None):
    """Generate a per-appointment access token.

    Odoo calls defaults with the model record as the first positional arg,
    so we accept (and ignore) it.
    """
    return secrets.token_urlsafe(24)


class SalonAppointment(models.Model):
    _name = 'salon.appointment'
    _description = 'Salon Appointment'
    _order = 'start_datetime desc'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _rec_name = 'name'
    _mail_post_access = 'read'

    name = fields.Char(
        string='Reference', required=True, readonly=True,
        default=lambda self: _('New'),
    )
    active = fields.Boolean(
        default=True,
        help="Uncheck to archive the appointment instead of deleting it.",
    )

    # ---- Customer --------------------------------------------------
    partner_id = fields.Many2one(
        'res.partner', string='Customer',
        index=True, ondelete='set null',
        help="Linked portal user. Empty for guest bookings.",
    )
    guest_name = fields.Char(string='Guest name')
    guest_email = fields.Char(string='Guest email')
    guest_phone = fields.Char(string='Guest phone')
    guest_notes = fields.Text(string='Customer notes')

    # ---- What & where ----------------------------------------------
    branch_id = fields.Many2one(
        'salon.branch', required=True, index=True,
        domain=[('online_visible', '=', True)],
    )
    stylist_id = fields.Many2one(
        'salon.stylist', required=True, index=True,
        domain="[('branch_ids', 'in', branch_id)]",
    )
    chair_id = fields.Many2one(
        'salon.chair', string='Chair', index=True,
        domain="[('branch_id', '=', branch_id)]",
        help="The physical chair this appointment will be served at.",
    )
    line_ids = fields.One2many(
        'salon.appointment.line', 'appointment_id',
        string='Services', required=True,
    )

    # ---- Time ------------------------------------------------------
    start_datetime = fields.Datetime(required=True, index=True)
    end_datetime = fields.Datetime(compute='_compute_end_datetime', store=True)
    duration = fields.Float(
        compute='_compute_duration', store=True,
        string='Total duration (hours)',
    )

    # ---- Money -----------------------------------------------------
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
    )
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company,
    )
    total_price = fields.Monetary(compute='_compute_total_price', store=True)
    service_summary = fields.Char(
        compute='_compute_service_summary',
        string='Services',
    )

    # ---- State -----------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No show'),
    ], default='draft', required=True, tracking=True, index=True)

    # ---- Portal token ---------------------------------------------
    access_token = fields.Char(
        required=True, default=_gen_token,
        copy=False,
        help="Per-appointment token used by the portal link to view/cancel "
             "without needing the customer to log in.",
    )

    # ---- Computed --------------------------------------------------
    @api.depends('line_ids.duration')
    def _compute_duration(self):
        for appt in self:
            appt.duration = sum(appt.line_ids.mapped('duration'))

    @api.depends('start_datetime', 'duration')
    def _compute_end_datetime(self):
        for appt in self:
            if appt.start_datetime and appt.duration:
                appt.end_datetime = appt.start_datetime + timedelta(hours=appt.duration)
            else:
                appt.end_datetime = appt.start_datetime

    @api.depends('line_ids.price_subtotal')
    def _compute_total_price(self):
        for appt in self:
            appt.total_price = sum(appt.line_ids.mapped('price_subtotal'))

    @api.depends('line_ids.service_id')
    def _compute_service_summary(self):
        for appt in self:
            names = appt.line_ids.service_id.mapped('name')
            appt.service_summary = ', '.join(names) if names else ''

    # ---- Onchange -------------------------------------------------
    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        if self.stylist_id and self.branch_id not in self.stylist_id.branch_ids:
            self.stylist_id = False

    @api.onchange('stylist_id')
    def _onchange_stylist_id(self):
        if self.stylist_id and self.stylist_id.service_ids:
            services = self.stylist_id.service_ids
            lines = self.line_ids.filtered(lambda l: l.service_id in services)
            removed = self.line_ids - lines
            if removed:
                self.line_ids = [(6, 0, lines.ids)]
            if not lines:
                self.line_ids = [(0, 0, {'service_id': False})]

    @api.onchange('line_ids')
    def _onchange_line_ids(self):
        # recompute start_datetime to be earlier of the suggested slots
        pass

    @api.onchange('stylist_id', 'branch_id')
    def _onchange_stylist_pick_chair(self):
        """Form-view auto-fill: pick the stylist's chair when missing."""
        for appt in self:
            if appt.chair_id or not (appt.stylist_id and appt.branch_id):
                continue
            chair = self.env['salon.chair'].search([
                ('stylist_id', '=', appt.stylist_id.id),
                ('branch_id', '=', appt.branch_id.id),
                ('active', '=', True),
            ], limit=1)
            if chair:
                appt.chair_id = chair

    # ---- CRUD ------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # Inject a default name + auto-pick a chair if none was set.
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                branch = self.env['salon.branch'].browse(vals.get('branch_id'))
                vals['name'] = self._next_name(branch)
            if not vals.get('chair_id') and vals.get('stylist_id') and vals.get('branch_id'):
                chair = self.env['salon.chair'].search([
                    ('stylist_id', '=', vals['stylist_id']),
                    ('branch_id', '=', vals['branch_id']),
                    ('active', '=', True),
                ], limit=1)
                if chair:
                    vals['chair_id'] = chair.id
        return super().create(vals_list)

    def write(self, vals):
        # If a chair is missing on an existing appointment but a stylist is
        # set, try to assign the stylist's dedicated chair.
        if ('chair_id' not in vals or not vals.get('chair_id')) and \
                ('stylist_id' in vals or 'branch_id' in vals):
            for appt in self:
                if appt.chair_id:
                    continue
                stylist_id = vals.get('stylist_id') or appt.stylist_id.id
                branch_id = vals.get('branch_id') or appt.branch_id.id
                if not (stylist_id and branch_id):
                    continue
                chair = self.env['salon.chair'].search([
                    ('stylist_id', '=', stylist_id),
                    ('branch_id', '=', branch_id),
                    ('active', '=', True),
                ], limit=1)
                if chair:
                    vals = {**vals, 'chair_id': chair.id}
                    break
        return super().write(vals)

    @api.model
    def action_backfill_chairs(self):
        """One-shot helper: assign chairs to existing appointments that
        have no chair_id but have a stylist_id and branch_id.
        """
        appts = self.search([
            ('chair_id', '=', False),
            ('stylist_id', '!=', False),
            ('branch_id', '!=', False),
        ])
        count = 0
        for appt in appts:
            chair = self.env['salon.chair'].search([
                ('stylist_id', '=', appt.stylist_id.id),
                ('branch_id', '=', appt.branch_id.id),
                ('active', '=', True),
            ], limit=1)
            if chair:
                appt.chair_id = chair
                count += 1
        return count

    def _next_name(self, branch):
        seq = self.env['ir.sequence'].next_by_code('salon.appointment') or '00000'
        code = (branch.code or 'SAL') if branch else 'SAL'
        return f'{code}/{seq}'

    # ---- Constraints ----------------------------------------------
    @api.constrains('line_ids')
    def _check_at_least_one_line(self):
        for appt in self:
            if not appt.line_ids:
                raise ValidationError(_('An appointment needs at least one service.'))

    @api.constrains('start_datetime', 'branch_id', 'stylist_id', 'line_ids')
    def _check_no_overlap(self):
        for appt in self:
            if not (appt.start_datetime and appt.end_datetime and appt.stylist_id):
                continue
            overlapping = self.search([
                ('id', '!=', appt.id),
                ('stylist_id', '=', appt.stylist_id.id),
                ('state', 'in', ('confirmed', 'in_progress')),
                ('start_datetime', '<', appt.end_datetime),
                ('end_datetime', '>', appt.start_datetime),
            ])
            if overlapping:
                raise ValidationError(_(
                    'This slot conflicts with appointment %s for the same stylist.',
                    overlapping[0].name,
                ))

    # ---- State transitions ----------------------------------------
    def action_confirm(self):
        for appt in self:
            if appt.state != 'draft':
                continue
            appt.state = 'confirmed'
            appt.message_post(body=_('Appointment confirmed.'))

    def action_start(self):
        for appt in self:
            if appt.state == 'confirmed':
                appt.state = 'in_progress'
                appt.message_post(body=_('Service started.'))

    def action_done(self):
        for appt in self:
            if appt.state in ('confirmed', 'in_progress'):
                appt.state = 'done'
                appt.message_post(body=_('Service completed.'))

    def action_cancel(self):
        for appt in self:
            if appt.state in ('done', 'cancelled', 'no_show'):
                continue
            appt.state = 'cancelled'
            appt.message_post(body=_('Appointment cancelled.'))

    def action_no_show(self):
        for appt in self:
            if appt.state in ('done', 'cancelled', 'no_show'):
                continue
            appt.state = 'no_show'
            appt.message_post(body=_('Marked as no-show.'))

    def action_reset_draft(self):
        for appt in self:
            appt.state = 'draft'

    # ------------------------------------------------------------------
    # Demo data helper — invoked from salon_demo.xml via <function>
    # ------------------------------------------------------------------
    @api.model
    def action_create_demo_appointments(self, spec):
        """Create demo appointments for the chair dashboard.

        :param spec: list of tuples
            (branch_xmlid, chair_xmlid, stylist_xmlid,
             partner_xmlid_or_False, [service_xmlids], state)

        Times are computed relative to today so the demo always shows fresh
        appointments when the database is created.
        """
        from datetime import datetime, timedelta

        now = datetime.now()
        # Two "in_service" appointments starting ~30 min ago (in progress),
        # four "confirmed" appointments spread over today.
        in_progress_offset = -30   # started 30 min ago
        confirmed_offsets = [-120, 60, 180, 240]  # -2h, +1h, +3h, +4h

        def _resolve(xmlid_or_id):
            if not xmlid_or_id:
                return self.env['res.partner']
            if isinstance(xmlid_or_id, str) and '.' in xmlid_or_id:
                return self.env.ref(xmlid_or_id, raise_if_not_found=False)
            return self.env['res.partner'].browse(xmlid_or_id)

        # Walk the spec and assign offsets in the order appointments appear
        confirmed_index = 0
        for branch_xid, chair_xid, stylist_xid, partner_xid, service_xids, state in spec:
            branch = self.env.ref(branch_xid, raise_if_not_found=False)
            chair = self.env.ref(chair_xid, raise_if_not_found=False)
            stylist = self.env.ref(stylist_xid, raise_if_not_found=False)
            partner = _resolve(partner_xid)
            if not branch or not chair or not stylist:
                continue
            services = []
            for xid in service_xids:
                svc = self.env.ref(xid, raise_if_not_found=False)
                if svc:
                    services.append(svc.id)
            if not services:
                continue

            if state == 'in_progress':
                offset = in_progress_offset
            else:
                offset = confirmed_offsets[confirmed_index % len(confirmed_offsets)]
                confirmed_index += 1
            start = now + timedelta(minutes=offset)

            vals = {
                'branch_id': branch.id,
                'chair_id': chair.id,
                'stylist_id': stylist.id,
                'start_datetime': start,
                'state': state,
                'line_ids': [(0, 0, {'service_id': sid}) for sid in services],
                'access_token': _gen_token(),
            }
            if partner:
                vals['partner_id'] = partner.id
                vals['guest_name'] = partner.name
                vals['guest_email'] = partner.email
                vals['guest_phone'] = partner.phone
            else:
                vals['guest_name'] = 'Walk-in'
                vals['guest_email'] = 'walkin@example.com'
                vals['guest_phone'] = '+1 555 000 0000'

            try:
                self.create(vals)
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Skipped demo appointment: %s (%s)", vals, exc)

    def action_open_portal_url(self):
        """Open the customer's portal URL in a new tab/window."""
        self.ensure_one()
        if not self.access_token:
            raise UserError(_('This appointment has no portal link yet.'))
        url = f'/salon/appointment/{self.id}?access_token={self.access_token}'
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    # ---- Portal helpers -------------------------------------------
    def _get_portal_return_action(self):
        self.ensure_one()
        return self.env['ir.actions.act_window']._for_xml_id(
            'salon_booking_pro.action_salon_appointment_portal_list'
        )

    def _get_share_url(self, redirect=True):
        self.ensure_one()
        return self.access_token and self._portal_share_url() or False

    def _portal_share_url(self):
        self.ensure_one()
        return f'/salon/appointment/{self.id}?access_token={self.access_token}'

    # ---- Customer display ------------------------------------------
    def _customer_display(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id.display_name
        return self.guest_name or _('Guest')


class SalonAppointmentLine(models.Model):
    _name = 'salon.appointment.line'
    _description = 'Salon Appointment Service Line'
    _order = 'sequence, id'

    appointment_id = fields.Many2one(
        'salon.appointment', required=True, ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    service_id = fields.Many2one(
        'salon.service', required=True,
        domain=[('online_visible', '=', True)],
    )
    stylist_id = fields.Many2one(
        'salon.stylist', related='appointment_id.stylist_id',
        string='Stylist',
    )
    duration = fields.Float(
        related='service_id.duration', store=True,
        string='Duration (hours)',
    )
    currency_id = fields.Many2one(
        'res.currency', related='appointment_id.currency_id',
    )
    price_unit = fields.Monetary(related='service_id.list_price')
    price_subtotal = fields.Monetary(compute='_compute_price_subtotal', store=True)

    @api.depends('price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.price_unit