# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import datetime, timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request, route
from odoo.tools import format_datetime

_logger = logging.getLogger(__name__)


class SalonPortal(http.Controller):

    # ------------------------------------------------------------------
    # Static pages
    # ------------------------------------------------------------------
    @route(['/salon', '/salon/home'], type='http', auth='public', website=True, sitemap=True)
    def home(self, **kw):
        Branch = request.env['salon.branch'].sudo()
        Category = request.env['salon.service.category'].sudo()
        branches = Branch.search([('online_visible', '=', True), ('active', '=', True)], order='sequence, name')
        categories = Category.search([('online_visible', '=', True), ('active', '=', True)], order='sequence')
        return request.render('salon_booking_pro.portal_home', {
            'branches': branches,
            'categories': categories,
            'main_object': branches[:1],
        })

    @route(['/salon/branches'], type='http', auth='public', website=True, sitemap=True)
    def branches(self, **kw):
        branches = request.env['salon.branch'].sudo().search([
            ('online_visible', '=', True), ('active', '=', True),
        ], order='sequence, name')
        return request.render('salon_booking_pro.portal_branches', {'branches': branches})

    @route(['/salon/branch/<int:branch_id>'], type='http', auth='public', website=True, sitemap=True)
    def branch_detail(self, branch_id, **kw):
        branch = request.env['salon.branch'].sudo().browse(branch_id)
        if not branch.exists() or not branch.online_visible:
            return request.not_found()
        services = request.env['salon.service'].sudo().search([
            ('online_visible', '=', True),
            ('active', '=', True),
            '|', ('branch_ids', '=', False), ('branch_ids', 'in', branch.id),
        ], order='category_id, sequence, name')
        stylists = request.env['salon.stylist'].sudo().search([
            ('branch_ids', 'in', branch.id),
            ('online_visible', '=', True),
            ('active', '=', True),
        ], order='name')
        return request.render('salon_booking_pro.portal_branch_detail', {
            'branch': branch,
            'services': services,
            'stylists': stylists,
        })

    @route(['/salon/stylist/<int:stylist_id>'], type='http', auth='public', website=True, sitemap=True)
    def stylist_detail(self, stylist_id, **kw):
        stylist = request.env['salon.stylist'].sudo().browse(stylist_id)
        if not stylist.exists() or not stylist.online_visible:
            return request.not_found()
        services = stylist.service_ids.filtered(lambda s: s.online_visible and s.active)
        return request.render('salon_booking_pro.portal_stylist_detail', {
            'stylist': stylist,
            'services': services,
        })

    # ------------------------------------------------------------------
    # Booking flow
    # ------------------------------------------------------------------
    @route(['/salon/book'], type='http', auth='public', website=True, sitemap=False)
    def book(self, **kw):
        """Multi-step booking wizard — state is held in a signed cookie session."""
        Booking = request.env['salon.appointment']
        session = request.session

        # Reset stale data older than 1 hour
        last = session.get('salon_booking_timestamp')
        if last and (datetime.now() - datetime.fromisoformat(last)) > timedelta(hours=1):
            for k in list(session.keys()):
                if k.startswith('salon_booking_'):
                    session.pop(k, None)

        booking = {
            'branch_id': session.get('salon_booking_branch_id'),
            'stylist_id': session.get('salon_booking_stylist_id'),
            'service_ids': session.get('salon_booking_service_ids', []),
            'date': session.get('salon_booking_date'),
            'start': session.get('salon_booking_start'),
            'guest_name': session.get('salon_booking_guest_name'),
            'guest_email': session.get('salon_booking_guest_email'),
            'guest_phone': session.get('salon_booking_guest_phone'),
            'guest_notes': session.get('salon_booking_guest_notes'),
        }

        step = int(kw.get('step', 1))
        if step not in (1, 2, 3, 4, 5):
            step = 1

        values = {
            'step': step,
            'booking': booking,
            'branches': request.env['salon.branch'].sudo().search([
                ('online_visible', '=', True), ('active', '=', True),
            ], order='sequence, name'),
            'errors': {},
            'Booking': Booking,
        }
        return request.render('salon_booking_pro.portal_book', values)

    @route(['/salon/book/select'], type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def book_select(self, **post):
        """Persist a wizard step into the session and redirect to the next step."""
        session = request.session
        step = int(post.get('step', 1))

        # Always refresh the timestamp
        session['salon_booking_timestamp'] = datetime.now().isoformat()

        if step == 1:
            branch_id = int(post.get('branch_id') or 0)
            branch = request.env['salon.branch'].sudo().browse(branch_id)
            if not branch.exists() or not branch.online_visible:
                return request.redirect('/salon/book?step=1')
            session['salon_booking_branch_id'] = branch_id
            session.pop('salon_booking_stylist_id', None)
            session.pop('salon_booking_service_ids', None)
            session.pop('salon_booking_date', None)
            session.pop('salon_booking_start', None)
            return request.redirect('/salon/book?step=2')

        if step == 2:
            service_ids = [int(x) for x in request.httprequest.form.getlist('service_ids') if x.isdigit()]
            session['salon_booking_service_ids'] = service_ids
            return request.redirect('/salon/book?step=3')

        if step == 3:
            stylist_id = int(post.get('stylist_id') or 0)
            branch_id = session.get('salon_booking_branch_id')
            stylist = request.env['salon.stylist'].sudo().browse(stylist_id)
            if not stylist.exists() or branch_id not in stylist.branch_ids.ids:
                stylist_id = 0
            session['salon_booking_stylist_id'] = stylist_id
            return request.redirect('/salon/book?step=4')

        if step == 4:
            date_str = post.get('date')
            start_str = post.get('start')
            if not date_str or not start_str:
                return request.redirect('/salon/book?step=4')
            try:
                datetime.fromisoformat(date_str)
                datetime.fromisoformat(start_str)
            except ValueError:
                return request.redirect('/salon/book?step=4')
            session['salon_booking_date'] = date_str
            session['salon_booking_start'] = start_str
            return request.redirect('/salon/book?step=5')

        return request.redirect('/salon/book?step=1')

    @route(['/salon/book/confirm'], type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def book_confirm(self, **post):
        """Create the appointment from the wizard session."""
        session = request.session
        branch_id = session.get('salon_booking_branch_id')
        service_ids = session.get('salon_booking_service_ids', [])
        stylist_id = session.get('salon_booking_stylist_id')
        date_str = session.get('salon_booking_date')
        start_str = session.get('salon_booking_start')

        errors = {}
        guest_name = (post.get('guest_name') or '').strip()
        guest_email = (post.get('guest_email') or '').strip()
        guest_phone = (post.get('guest_phone') or '').strip()
        guest_notes = (post.get('guest_notes') or '').strip()

        if not guest_name:
            errors['guest_name'] = _('Please enter your name.')
        if '@' not in guest_email or '.' not in guest_email:
            errors['guest_email'] = _('Please enter a valid email.')
        if not guest_phone:
            errors['guest_phone'] = _('Please enter a phone number.')

        if not (branch_id and service_ids and stylist_id and date_str and start_str):
            errors['step'] = _('Your booking session has expired. Please start over.')

        if errors:
            values = {
                'step': 5,
                'booking': {
                    'branch_id': branch_id,
                    'stylist_id': stylist_id,
                    'service_ids': service_ids,
                    'date': date_str,
                    'start': start_str,
                    'guest_name': guest_name,
                    'guest_email': guest_email,
                    'guest_phone': guest_phone,
                    'guest_notes': guest_notes,
                },
                'branches': request.env['salon.branch'].sudo().search([
                    ('online_visible', '=', True), ('active', '=', True),
                ]),
                'errors': errors,
            }
            return request.render('salon_booking_pro.portal_book', values)

        try:
            start_dt = datetime.fromisoformat(start_str)
            duration_minutes = sum(
                request.env['salon.service'].sudo().browse(service_ids).mapped('duration_minutes')
            )
            branch = request.env['salon.branch'].sudo().browse(branch_id)
            if start_dt not in branch.get_available_slots(
                start_dt.date(), duration_minutes,
                stylist_id=stylist_id,
            ):
                raise ValidationError(_('The selected slot is no longer available.'))

            appt = request.env['salon.appointment'].sudo().create({
                'branch_id': branch_id,
                'stylist_id': stylist_id,
                'start_datetime': fields.Datetime.to_string(start_dt),
                'guest_name': guest_name,
                'guest_email': guest_email,
                'guest_phone': guest_phone,
                'guest_notes': guest_notes,
                'line_ids': [(0, 0, {'service_id': sid}) for sid in service_ids],
                'partner_id': request.env.user.partner_id.id if not request.env.user._is_public() else False,
                'state': 'confirmed',
            })
        except ValidationError as exc:
            values = {
                'step': 5,
                'booking': {
                    'branch_id': branch_id,
                    'stylist_id': stylist_id,
                    'service_ids': service_ids,
                    'date': date_str,
                    'start': start_str,
                    'guest_name': guest_name,
                    'guest_email': guest_email,
                    'guest_phone': guest_phone,
                    'guest_notes': guest_notes,
                },
                'branches': request.env['salon.branch'].sudo().search([
                    ('online_visible', '=', True), ('active', '=', True),
                ]),
                'errors': {'slot': str(exc)},
            }
            return request.render('salon_booking_pro.portal_book', values)

        # Clear session
        for k in list(session.keys()):
            if k.startswith('salon_booking_'):
                session.pop(k, None)
        return request.redirect(f'/salon/appointment/{appt.id}?access_token={appt.access_token}')

    # ------------------------------------------------------------------
    # AJAX: availability
    # ------------------------------------------------------------------
    @route(['/salon/availability'], type='json', auth='public', methods=['POST'])
    def availability(self, branch_id, date, stylist_id=None, service_ids=None, exclude_id=None, **kw):
        if not branch_id or not date:
            return {'error': _('Missing branch or date')}
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError:
            return {'error': _('Invalid date')}

        service_ids = service_ids or []
        Service = request.env['salon.service'].sudo()
        duration = sum(Service.browse(service_ids).mapped('duration_minutes')) or 30

        branch = request.env['salon.branch'].sudo().browse(int(branch_id))
        if not branch.exists() or not branch.online_visible:
            return {'error': _('Branch not found')}

        slots = branch.get_available_slots(
            target_date, duration,
            stylist_id=int(stylist_id) if stylist_id else False,
            exclude_appointment_id=int(exclude_id) if exclude_id else False,
        )
        return {
            'slots': [
                {
                    'iso': s.isoformat(),
                    'label': s.strftime('%H:%M'),
                }
                for s in slots
            ],
            'duration_minutes': duration,
        }

    # ------------------------------------------------------------------
    # Manage an appointment
    # ------------------------------------------------------------------
    def _get_appointment(self, appointment_id, access_token):
        appt = request.env['salon.appointment'].sudo().browse(appointment_id)
        if not appt.exists() or not appt.access_token:
            raise AccessError(_('Invalid appointment'))
        if access_token and access_token != appt.access_token:
            raise AccessError(_('Invalid token'))
        return appt

    @route(['/salon/appointment/<int:appointment_id>'], type='http', auth='public', website=True)
    def appointment_detail(self, appointment_id, access_token=None, **kw):
        try:
            appt = self._get_appointment(appointment_id, access_token)
        except AccessError:
            return request.not_found()
        return request.render('salon_booking_pro.portal_appointment_detail', {
            'appointment': appt,
            'token': access_token,
            'format_datetime': lambda dt: format_datetime(
                request.env, dt,
                tz=request.env.user.tz or request.env.company.partner_id.tz,
            ),
        })

    @route(['/salon/appointment/<int:appointment_id>/cancel'], type='http', auth='public',
           website=True, methods=['POST'], csrf=True)
    def appointment_cancel(self, appointment_id, access_token=None, **kw):
        try:
            appt = self._get_appointment(appointment_id, access_token)
        except AccessError:
            return request.not_found()
        if appt.state in ('done', 'cancelled', 'no_show'):
            return request.redirect(f'/salon/appointment/{appointment_id}?access_token={access_token}')
        appt.sudo().action_cancel()
        return request.redirect(f'/salon/appointment/{appointment_id}?access_token={access_token}')

    # ------------------------------------------------------------------
    # Signup (after guest booking)
    # ------------------------------------------------------------------
    @route(['/salon/signup'], type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def signup(self, **post):
        email = (post.get('email') or '').strip().lower()
        name = (post.get('name') or '').strip()
        access_token = post.get('access_token')
        appointment_id = int(post.get('appointment_id') or 0)
        if not email or not name or not access_token:
            return request.redirect('/salon')

        appt = self._get_appointment(appointment_id, access_token)
        if appt.partner_id:
            return request.redirect(f'/salon/appointment/{appointment_id}?access_token={access_token}')

        Partner = request.env['res.partner'].sudo()
        existing = Partner.search([('email', '=ilike', email)], limit=1)
        if existing:
            appt.sudo().write({'partner_id': existing.id})
            return request.redirect(f'/salon/appointment/{appointment_id}?access_token={access_token}')

        # Hand off to the standard Odoo signup flow
        return request.redirect(f'/web/signup?email={email}&name={name}&redirect=/salon/appointment/{appointment_id}?access_token={access_token}')

    # ------------------------------------------------------------------
    # Portal: customer's appointments
    # ------------------------------------------------------------------
    @route(['/salon/my-appointments'], type='http', auth='user', website=True)
    def my_appointments(self, **kw):
        partner = request.env.user.partner_id
        if not partner:
            return request.not_found()
        appointments = request.env['salon.appointment'].sudo().search([
            '|',
            ('partner_id', '=', partner.id),
            ('guest_email', '=ilike', partner.email or ''),
        ], order='start_datetime desc')
        return request.render('salon_booking_pro.portal_my_appointments', {
            'appointments': appointments,
            'partner': partner,
            'format_datetime': lambda dt: format_datetime(
                request.env, dt,
                tz=request.env.user.tz or request.env.company.partner_id.tz,
            ),
        })