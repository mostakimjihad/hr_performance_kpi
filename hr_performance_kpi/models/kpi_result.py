# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class KpiResult(models.Model):
    _name = 'kpi.result'
    _description = "KPI Result"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_start desc, employee_id, template_id'
    _rec_name = 'display_name'

    template_id = fields.Many2one(
        'kpi.template',
        string="KPI Template",
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        tracking=True,
    )
    assignment_id = fields.Many2one(
        'kpi.assignment',
        string="Source Assignment",
        tracking=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string="Department",
        related='employee_id.department_id',
        store=True,
    )
    period_start = fields.Date(
        string="Period Start",
        required=True,
        tracking=True,
    )
    period_end = fields.Date(
        string="Period End",
        required=True,
        tracking=True,
    )
    target_value = fields.Float(
        string="Target Value",
        tracking=True,
    )
    actual_value = fields.Float(
        string="Actual Value",
        tracking=True,
    )
    score = fields.Float(
        string="Score (%)",
        compute='_compute_score',
        store=True,
        tracking=True,
    )
    rag_status = fields.Selection(
        [('green', 'Green'), ('amber', 'Amber'), ('red', 'Red')],
        string="RAG Status",
        compute='_compute_rag_status',
        store=True,
        tracking=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'),
         ('submitted', 'Submitted'),
         ('reviewed', 'Reviewed'),
         ('approved', 'Approved'),
         ('returned', 'Returned')],
        string="Status",
        default='draft',
        required=True,
        tracking=True,
        group_expand='_read_group_state',
    )
    reviewer_id = fields.Many2one(
        'res.users',
        string="Reviewer",
        tracking=True,
    )
    reviewed_date = fields.Datetime(
        string="Reviewed Date",
        tracking=True,
    )
    notes = fields.Text(
        string="Notes",
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='employee_id.company_id',
        store=True,
    )
    display_name = fields.Char(
        string="Display Name",
        compute='_compute_display_name',
        store=True,
    )
    period_name = fields.Char(
        string="Period",
        compute='_compute_period_name',
    )

    @api.depends('template_id', 'template_id.name',
                 'employee_id', 'employee_id.name',
                 'period_start', 'period_end')
    def _compute_display_name(self):
        for result in self:
            if result.template_id and result.employee_id and result.period_start:
                result.display_name = _(
                    '%(template)s — %(employee)s (%(period)s)'
                ) % {
                    'template': result.template_id.name,
                    'employee': result.employee_id.name,
                    'period': result.period_start.strftime('%Y-%m'),
                }
            else:
                result.display_name = 'New KPI Result'

    @api.depends('period_start', 'period_end')
    def _compute_period_name(self):
        for result in self:
            if result.period_start:
                result.period_name = result.period_start.strftime('%B %Y')
            else:
                result.period_name = ''

    @api.depends('actual_value', 'target_value',
                 'template_id.min_value', 'template_id.max_value',
                 'template_id.direction', 'template_id.kpi_type')
    def _compute_score(self):
        """Compute normalized score (0-100) based on KPI direction."""
        for result in self:
            if result.actual_value is None or result.actual_value is False:
                result.score = 0.0
                continue

            template = result.template_id
            actual = result.actual_value if result.actual_value is not None else 0.0
            min_val = template.min_value if template.min_value is not None else 0.0
            max_val = (template.max_value if template.max_value is not None
                       else (actual * 2 if actual > 0 else 100.0))
            target = template.target_value if template.target_value is not None else 0.0

            if template.kpi_type == 'qualitative':
                # For qualitative KPIs, the actual value is already a score 0-100
                result.score = min(100.0, max(0.0, actual))
                continue

            if template.direction == 'maximize':
                if max_val == min_val:
                    result.score = 100.0 if actual >= target else 0.0
                else:
                    score = ((actual - min_val) / (max_val - min_val)) * 100.0
                    result.score = min(100.0, max(0.0, score))
            elif template.direction == 'minimize':
                if max_val == min_val:
                    result.score = 100.0 if actual <= target else 0.0
                else:
                    score = ((max_val - actual) / (max_val - min_val)) * 100.0
                    result.score = min(100.0, max(0.0, score))
            elif template.direction == 'target':
                if target == 0:
                    result.score = 100.0 if actual == 0 else 0.0
                else:
                    deviation = abs(actual - target) / target
                    score = (1.0 - deviation) * 100.0
                    result.score = min(100.0, max(0.0, score))
            else:
                result.score = 0.0

    @api.depends('score', 'template_id.green_threshold', 'template_id.amber_threshold')
    def _compute_rag_status(self):
        """Determine RAG status based on score thresholds."""
        for result in self:
            if result.score is None or not result.template_id:
                result.rag_status = 'red'
                continue
            if result.score >= result.template_id.green_threshold:
                result.rag_status = 'green'
            elif result.score >= result.template_id.amber_threshold:
                result.rag_status = 'amber'
            else:
                result.rag_status = 'red'

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        for result in self:
            if result.period_start and result.period_end and result.period_end < result.period_start:
                raise ValidationError(_(
                    'Period End date must be after Period Start date.'
                ))

    @api.constrains('template_id', 'employee_id', 'period_start', 'period_end')
    def _check_unique_period(self):
        for result in self:
            if result.template_id and result.employee_id and result.period_start and result.period_end:
                duplicate = self.search([
                    ('id', '!=', result.id),
                    ('template_id', '=', result.template_id.id),
                    ('employee_id', '=', result.employee_id.id),
                    ('period_start', '=', result.period_start),
                    ('period_end', '=', result.period_end),
                ])
                if duplicate:
                    raise ValidationError(_(
                        'A result for template "%(template)s" already exists for '
                        'employee %(employee)s in this period.',
                        template=result.template_id.name,
                        employee=result.employee_id.name,
                    ))

    # ---- Approval Workflow Methods ----

    def action_submit(self):
        """Submit result for review."""
        for result in self:
            if result.state != 'draft':
                raise UserError(_('Only draft results can be submitted.'))
            if result.template_id.calculation_method == 'orm_query':
                result._compute_automated_value()
            result.state = 'submitted'
            result.message_post(body=_('KPI Result submitted for review.'))

    def action_review(self):
        """Manager reviews the result."""
        for result in self:
            if result.state != 'submitted':
                raise UserError(_('Only submitted results can be reviewed.'))
            result.state = 'reviewed'
            result.reviewer_id = self.env.user.id
            result.reviewed_date = fields.Datetime.now()
            result.message_post(body=_('KPI Result reviewed by %s.') % self.env.user.name)

    def action_approve(self):
        """Approve the result."""
        for result in self:
            if result.state not in ('submitted', 'reviewed'):
                raise UserError(_('Only submitted or reviewed results can be approved.'))
            result.state = 'approved'
            if not result.reviewer_id:
                result.reviewer_id = self.env.user.id
                result.reviewed_date = fields.Datetime.now()
            result.message_post(body=_('KPI Result approved by %s.') % self.env.user.name)

    def action_return(self):
        """Return result to draft for revision."""
        for result in self:
            if result.state in ('approved', 'draft'):
                raise UserError(_('Cannot return a result that is already approved or in draft.'))
            result.state = 'returned'
            result.message_post(body=_('KPI Result returned for revision by %s.') % self.env.user.name)

    def action_reset_draft(self):
        """Reset to draft state."""
        for result in self:
            if result.state not in ('returned',):
                raise UserError(_('Only returned results can be reset to draft.'))
            result.state = 'draft'
            result.message_post(body=_('KPI Result reset to draft.'))

    # ---- Automated Calculation ----

    def _compute_automated_value(self):
        """Compute actual value based on template's calculation method."""
        for result in self:
            template = result.template_id
            if template.calculation_method == 'manual':
                continue  # Nothing to auto-compute
            elif template.calculation_method == 'orm_query':
                result.actual_value = template._compute_actual_value_orm(
                    result.employee_id, result.period_start, result.period_end
                )
            elif template.calculation_method == 'formula':
                result.actual_value = template._compute_actual_value_formula(
                    result.employee_id, result.period_start, result.period_end
                )

    @api.model
    def _cron_calculate_automated(self):
        """Cron job: Auto-calculate values for automated (non-manual) results.

        Only submits results whose ``calculation_method`` is configured for
        automated calculation; manual results are left untouched so employees
        can fill them in.
        """
        automated_results = self.search([
            ('state', '=', 'draft'),
            ('template_id.calculation_method', 'in', ['orm_query', 'formula']),
        ])
        for result in automated_results:
            try:
                result._compute_automated_value()
                if result.actual_value is not None and result.actual_value is not False:
                    result.action_submit()
            except Exception as e:  # noqa: BLE001
                _logger.warning(
                    'Failed to auto-calculate KPI result %s: %s', result.id, e,
                )

    @api.model
    def _read_group_state(self, states, domain, order):
        """Return all states so grouped filters show all options."""
        return [
            'draft', 'submitted', 'reviewed',
            'approved', 'returned',
        ]

    # ---- Dashboard Helper Methods ----

    @api.model
    def get_dashboard_summary(self):
        """Return summary statistics for the KPI dashboard."""
        domain = self._get_dashboard_domain()
        results = self.search(domain)

        total = len(results)
        if not total:
            return {
                'total_results': 0,
                'on_track': 0,
                'at_risk': 0,
                'off_track': 0,
                'avg_score': 0.0,
                'green_pct': 0.0,
                'amber_pct': 0.0,
                'red_pct': 0.0,
            }

        # Single read_group pass for counts — avoids loading every record
        # into a Python recordset and re-filtering it.
        # With ``lazy=False`` the implicit per-group count is exposed as
        # ``__count`` (see ``models.py::read_group``), not ``rag_status_count``.
        grouped = self.read_group(
            domain, ['rag_status'], ['rag_status'], lazy=False,
        )
        counts = {g['rag_status'] or 'red': g['__count'] for g in grouped}
        green = counts.get('green', 0)
        amber = counts.get('amber', 0)
        red = counts.get('red', 0)
        avg_score = (
            sum(r.score or 0.0 for r in results) / total
        )

        return {
            'total_results': total,
            'on_track': green,
            'at_risk': amber,
            'off_track': red,
            'avg_score': round(avg_score, 1),
            'green_pct': round(green / total * 100, 1),
            'amber_pct': round(amber / total * 100, 1),
            'red_pct': round(red / total * 100, 1),
        }

    @api.model
    def get_department_performance(self):
        """Return department-wise performance data for dashboard charts."""
        domain = self._get_dashboard_domain()
        results = self.search(domain)

        dept_data = {}
        for result in results:
            dept = result.department_id
            if not dept:
                continue
            if dept.id not in dept_data:
                dept_data[dept.id] = {
                    'id': dept.id,
                    'name': dept.name,
                    'total': 0,
                    'green': 0,
                    'amber': 0,
                    'red': 0,
                    'score_sum': 0.0,
                }
            dept_data[dept.id]['total'] += 1
            dept_data[dept.id]['green'] += 1 if result.rag_status == 'green' else 0
            dept_data[dept.id]['amber'] += 1 if result.rag_status == 'amber' else 0
            dept_data[dept.id]['red'] += 1 if result.rag_status == 'red' else 0
            dept_data[dept.id]['score_sum'] += result.score or 0.0

        # Compute averages
        for dept_id in dept_data:
            d = dept_data[dept_id]
            d['avg_score'] = round(d['score_sum'] / d['total'], 1) if d['total'] > 0 else 0.0
            d['green_pct'] = round(d['green'] / d['total'] * 100, 1) if d['total'] > 0 else 0.0
            d['amber_pct'] = round(d['amber'] / d['total'] * 100, 1) if d['total'] > 0 else 0.0
            d['red_pct'] = round(d['red'] / d['total'] * 100, 1) if d['total'] > 0 else 0.0

        return sorted(dept_data.values(), key=lambda d: d['avg_score'], reverse=True)

    @api.model
    def get_employee_rankings(self, limit=10):
        """Return top employee performance rankings."""
        domain = self._get_dashboard_domain()
        results = self.search(domain)

        emp_data = {}
        for result in results:
            emp = result.employee_id
            if emp.id not in emp_data:
                emp_data[emp.id] = {
                    'id': emp.id,
                    'name': emp.name,
                    'department': emp.department_id.name or '',
                    'total': 0,
                    'score_sum': 0.0,
                    'green': 0,
                    'amber': 0,
                    'red': 0,
                }
            emp_data[emp.id]['total'] += 1
            emp_data[emp.id]['score_sum'] += result.score or 0.0
            emp_data[emp.id]['green'] += 1 if result.rag_status == 'green' else 0
            emp_data[emp.id]['amber'] += 1 if result.rag_status == 'amber' else 0
            emp_data[emp.id]['red'] += 1 if result.rag_status == 'red' else 0

        for emp_id in emp_data:
            e = emp_data[emp_id]
            e['avg_score'] = round(e['score_sum'] / e['total'], 1) if e['total'] > 0 else 0.0

        ranked = sorted(emp_data.values(), key=lambda e: e['avg_score'], reverse=True)
        return ranked[:limit]

    @api.model
    def _get_dashboard_domain(self):
        """Get default domain for dashboard queries (current user's scope)."""
        user = self.env.user
        if user.has_group('hr_performance_kpi.group_kpi_manager'):
            return [('company_id', 'in', self.env.companies.ids + [False])]
        else:
            employee = user.employee_id
            if employee:
                return [
                    '|', '|',
                    ('employee_id', '=', employee.id),
                    ('employee_id.parent_id.user_id', '=', user.id),
                    ('employee_id.department_id.manager_id.user_id', '=', user.id),
                ]
            return [('employee_id.user_id', '=', user.id)]
