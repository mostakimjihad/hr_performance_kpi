# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class SalonChair(models.Model):
    _name = 'salon.chair'
    _description = 'Salon Chair'
    _order = 'sequence, name'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(help="Short code shown in the dashboard.")
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company,
    )
    branch_id = fields.Many2one(
        'salon.branch', required=True, index=True,
        domain=[('online_visible', '=', True)],
    )
    stylist_id = fields.Many2one(
        'salon.stylist', string='Dedicated Stylist',
        domain="[('branch_ids', 'in', branch_id)]",
        help="The stylist that operates this chair by default. "
             "Appointments for this stylist can be auto-assigned to this chair.",
    )
    notes = fields.Text(translate=True)

    appointment_ids = fields.One2many('salon.appointment', 'chair_id')
    appointment_count = fields.Integer(compute='_compute_appointment_count')

    _sql_constraints = [
        ('branch_name_unique',
         'unique(branch_id, name)',
         'Chair name must be unique per branch.'),
    ]

    @api.constrains('stylist_id', 'branch_id')
    def _check_stylist_branch(self):
        for chair in self:
            if chair.stylist_id and chair.branch_id not in chair.stylist_id.branch_ids:
                raise ValidationError(_(
                    'Stylist %s must be assigned to branch %s.',
                    chair.stylist_id.display_name,
                    chair.branch_id.display_name,
                ))

    def _compute_appointment_count(self):
        counts = {
            c['chair_id'][0]: c['chair_id_count']
            for c in self.env['salon.appointment'].read_group(
                [('chair_id', 'in', self.ids)],
                ['chair_id'], ['chair_id'],
            )
        }
        for chair in self:
            chair.appointment_count = counts.get(chair.id, 0)

    # ------------------------------------------------------------------
    # Dashboard helper — used by the OWL component to colour chairs
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, branch_id, date_str=None):
        """Return ``{branches, chairs}`` for the chair dashboard.

        NOTE: decorated with ``@api.model`` so that ``call_kw`` does not
        silently strip the first positional argument as a recordset id.
        Without it, ``[branch_id, date_str]`` arriving via JSON-RPC would
        become ``branch_id = date_str = <date>`` because the real branch_id
        was treated as the ids argument.
        """
        from datetime import datetime

        if not date_str:
            date_str = fields.Date.context_today(self).isoformat()

        result = {'branches': [], 'chairs': [], '_debug': {}}
        # ALWAYS work via the model class, never `self.search_*` / `self.read`.
        # When xmlrpc invokes a model method, `self` is `self.env['salon.chair']`
        # but Odoo 19 sometimes filters subsequent queries by the recordset
        # implicitly, returning zero rows even though the table has data.
        ChairModel = self.env['salon.chair']
        BranchModel = self.env['salon.branch']

        result['_debug']['model_class'] = str(type(ChairModel))
        result['_debug']['branch_id_arg'] = repr(branch_id)
        result['_debug']['branch_id_type'] = type(branch_id).__name__
        result['_debug']['date_str'] = repr(date_str)
        result['_debug']['date_str_type'] = type(date_str).__name__
        result['_debug']['self_ids'] = self.ids[:5] if self.ids else []
        result['_debug']['self_len'] = len(self)
        result['_debug']['env_context_keys'] = sorted(
            k for k in self.env.context.keys()
            if k in ('active_test', 'default_branch_id', 'lang', 'tz')
        )
        # Always log at INFO so we can see it in werkzeug default config
        _logger.info(
            "Chair dashboard debug: branch=%r date=%r self_ids=%r ctx=%r",
            branch_id, date_str, self.ids[:5],
            {k: self.env.context.get(k) for k in
             ('active_test', 'default_branch_id', 'lang', 'tz')},
        )

        try:
            # Branches for the dropdown
            result['branches'] = BranchModel.search_read(
                [('online_visible', '=', True), ('active', '=', True)],
                ['id', 'name'], order='sequence, name',
            )

            if not branch_id:
                _logger.info("Chair dashboard: no branch_id, returning branches only")
                return result

            # Two-pronged query: count and read separately so we can tell which
            # one returns nothing.
            chair_count = ChairModel.with_context(active_test=False).search_count(
                [('branch_id', '=', branch_id), ('active', '=', True)])
            result['_debug']['chair_count_active_false'] = chair_count
            chair_count2 = ChairModel.search_count(
                [('branch_id', '=', branch_id), ('active', '=', True)])
            result['_debug']['chair_count_default'] = chair_count2

            chairs = ChairModel.search_read(
                [('branch_id', '=', branch_id), ('active', '=', True)],
                ['id', 'name', 'code', 'color', 'sequence', 'stylist_id'],
                order='sequence, name',
            )
            result['_debug']['search_read_len'] = len(chairs)
            result['_debug']['first_chair_ids'] = [c['id'] for c in chairs[:3]]
            _logger.info(
                "Chair dashboard counts: default=%d no_active_test=%d search_read=%d for branch=%r",
                chair_count2, chair_count, len(chairs), branch_id,
            )

            chair_ids = [c['id'] for c in chairs]

            # Stylists for those chairs
            stylists = {}
            stylist_ids = [c['stylist_id'][0] for c in chairs if c['stylist_id']]
            if stylist_ids:
                for s in self.env['salon.stylist'].browse(stylist_ids).read(
                        ['id', 'name', 'image']):
                    stylists[s['id']] = s

            # Appointments (only if the chair_id field exists on
            # salon.appointment in this DB).
            appts = []
            try:
                if 'chair_id' in self.env['salon.appointment']._fields:
                    day_start = datetime.strptime(
                        f'{date_str} 00:00:00', '%Y-%m-%d %H:%M:%S')
                    day_end = datetime.strptime(
                        f'{date_str} 23:59:59', '%Y-%m-%d %H:%M:%S')
                    appts = self.env['salon.appointment'].search_read(
                        [
                            ('chair_id', 'in', chair_ids),
                            ('start_datetime', '>=', day_start),
                            ('start_datetime', '<=', day_end),
                            ('state', 'in', ('confirmed', 'in_progress')),
                        ],
                        ['id', 'name', 'chair_id', 'start_datetime',
                         'end_datetime', 'partner_id', 'guest_name', 'state'],
                    )
            except Exception as exc:
                _logger.warning("Chair dashboard: appointment fetch skipped: %s", exc)
                result['_debug']['appt_error'] = str(exc)

            by_chair = {}
            for a in appts:
                cid = a['chair_id'][0] if a['chair_id'] else None
                if cid is None:
                    continue
                by_chair.setdefault(cid, []).append(a)

            now = datetime.now()
            out = []
            for c in chairs:
                chair_appts = sorted(by_chair.get(c['id'], []),
                                     key=lambda a: a['start_datetime'])
                current, upcoming = None, None
                status, status_label, status_color = 'available', 'Available', 'success'
                for a in chair_appts:
                    start = (a['start_datetime'] if isinstance(a['start_datetime'], datetime)
                             else datetime.strptime(
                                 a['start_datetime'], '%Y-%m-%d %H:%M:%S'))
                    end = (a['end_datetime'] if isinstance(a['end_datetime'], datetime)
                           else datetime.strptime(
                               a['end_datetime'], '%Y-%m-%d %H:%M:%S'))
                    if start <= now <= end:
                        current = a
                        status = 'in_service'
                        status_label = (f'In service · {start.strftime("%H:%M")}'
                                        f'–{end.strftime("%H:%M")}')
                        status_color = 'warning'
                        break
                    if start > now and upcoming is None:
                        upcoming = a
                        status = 'booked'
                        status_label = f'Next {start.strftime("%H:%M")}'
                        status_color = 'info'

                stylist = (stylists.get(c['stylist_id'][0])
                           if c['stylist_id'] else None)
                out.append({
                    'id': c['id'],
                    'name': c['name'],
                    'code': c['code'],
                    'color': c['color'],
                    'sequence': c['sequence'],
                    'status': status,
                    'status_label': status_label,
                    'status_color': status_color,
                    'stylist_id': (c['stylist_id'][0] if c['stylist_id'] else None),
                    'stylist_name': (stylist['name'] if stylist else None),
                    'stylist_image': (stylist.get('image') if stylist else None),
                    'current_appointment': current,
                    'next_appointment': upcoming,
                    'appointment_count_today': len(chair_appts),
                })
            result['chairs'] = out

        except Exception as exc:
            _logger.exception("Chair dashboard: unexpected error")
            result['_error'] = str(exc)

        return result