# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class KpiAssignment(models.Model):
    _name = 'kpi.assignment'
    _description = "KPI Assignment"
    _inherit = ['mail.thread']
    _order = 'template_id, employee_id'

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
        tracking=True,
        help="Leave empty to assign to an entire department.",
    )
    department_id = fields.Many2one(
        'hr.department',
        string="Department",
        tracking=True,
        help="Assign this KPI to all employees in this department.",
    )
    valid_from = fields.Date(
        string="Valid From",
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    valid_to = fields.Date(
        string="Valid To",
        tracking=True,
        help="Leave empty for ongoing assignment.",
    )
    state = fields.Selection(
        [('draft', 'Draft'),
         ('active', 'Active'),
         ('expired', 'Expired'),
         ('cancelled', 'Cancelled')],
        string="Status",
        default='draft',
        required=True,
        tracking=True,
    )
    assigned_by = fields.Many2one(
        'res.users',
        string="Assigned By",
        default=lambda self: self.env.user,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        tracking=True,
    )
    notes = fields.Text(string="Notes")
    result_ids = fields.One2many(
        'kpi.result',
        'assignment_id',
        string="KPI Results",
    )
    result_count = fields.Integer(
        string="Result Count",
        compute='_compute_result_count',
    )

    @api.depends('result_ids')
    def _compute_result_count(self):
        for assignment in self:
            assignment.result_count = len(assignment.result_ids)

    @api.constrains('employee_id', 'department_id')
    def _check_employee_or_department(self):
        for assignment in self:
            if not assignment.employee_id and not assignment.department_id:
                raise ValidationError(_(
                    'You must select either an Employee or a Department.'
                ))

    @api.constrains('valid_from', 'valid_to')
    def _check_dates(self):
        for assignment in self:
            if assignment.valid_to and assignment.valid_to <= assignment.valid_from:
                raise ValidationError(_(
                    'Valid To date must be after Valid From date.'
                ))

    @api.constrains('template_id', 'employee_id', 'state')
    def _check_unique_assignment(self):
        for assignment in self:
            if assignment.employee_id and assignment.state == 'active':
                duplicate = self.search([
                    ('id', '!=', assignment.id),
                    ('template_id', '=', assignment.template_id.id),
                    ('employee_id', '=', assignment.employee_id.id),
                    ('state', '=', 'active'),
                ])
                if duplicate:
                    raise ValidationError(_(
                        'An active assignment for template "%(template)s" already exists '
                        'for employee %(employee)s.',
                        template=assignment.template_id.name,
                        employee=assignment.employee_id.name,
                    ))

    def action_activate(self):
        """Activate the assignment and generate initial results."""
        for assignment in self:
            assignment.state = 'active'
            # Generate results for the current period
            today = date.today()
            period_start, period_end = assignment._get_period_dates(today)
            assignment._generate_results_for_period(period_start, period_end)

    def action_cancel(self):
        """Cancel the assignment."""
        for assignment in self:
            assignment.state = 'cancelled'

    def action_expire(self):
        """Mark the assignment as expired."""
        today = date.today()
        for assignment in self:
            assignment.valid_to = today
            assignment.state = 'expired'

    def action_set_draft(self):
        """Reset to draft."""
        for assignment in self:
            assignment.state = 'draft'

    def _get_employees_for_assignment(self):
        """Return recordset of hr.employee covered by this assignment."""
        self.ensure_one()
        if self.employee_id:
            return self.employee_id
        elif self.department_id:
            return self.env['hr.employee'].search([
                ('department_id', 'child_of', self.department_id.id),
                ('active', '=', True),
            ])
        return self.env['hr.employee']

    def _get_period_dates(self, reference_date=None):
        """Calculate period start and end based on template periodicity."""
        if reference_date is None:
            reference_date = date.today()
        periodicity = self.template_id.periodicity

        if periodicity == 'monthly':
            period_start = reference_date.replace(day=1)
            period_end = period_start + relativedelta(months=1, days=-1)
        elif periodicity == 'quarterly':
            quarter_month = ((reference_date.month - 1) // 3) * 3 + 1
            period_start = reference_date.replace(month=quarter_month, day=1)
            period_end = period_start + relativedelta(months=3, days=-1)
        elif periodicity == 'yearly':
            period_start = reference_date.replace(month=1, day=1)
            period_end = reference_date.replace(month=12, day=31)
        else:
            period_start = reference_date.replace(day=1)
            period_end = period_start + relativedelta(months=1, days=-1)

        return period_start, period_end

    @api.constrains('template_id', 'employee_id', 'state')
    def _check_unique_assignment(self):
        # NOTE: at most one ACTIVE assignment per (template, employee,
        # company) is allowed; multiple draft/cancelled/expired records are
        # fine.  We enforce it in Python here because PostgreSQL UNIQUE
        # indexes don't support WHERE clauses and would prevent legitimate
        # duplicates of non-active rows.
        for assignment in self:
            if not assignment.employee_id or assignment.state != 'active':
                continue
            duplicate = self.search([
                ('id', '!=', assignment.id),
                ('template_id', '=', assignment.template_id.id),
                ('employee_id', '=', assignment.employee_id.id),
                ('state', '=', 'active'),
                ('company_id', '=', assignment.company_id.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    'An active assignment for template "%(template)s" already exists '
                    'for employee %(employee)s.',
                    template=assignment.template_id.name,
                    employee=assignment.employee_id.name,
                ))

    def _generate_results_for_period(self, period_start, period_end):
        """Create kpi.result records for each employee in this assignment."""
        self.ensure_one()
        kpi_result = self.env['kpi.result']

        # Get employees - either single employee or all department members
        employees = self.employee_id
        if self.department_id and not self.employee_id:
            employees = self.env['hr.employee'].search([
                ('department_id', 'child_of', self.department_id.id),
                ('active', '=', True),
            ])

        for employee in employees:
            # Check if a result already exists for this period
            existing = kpi_result.search([
                ('template_id', '=', self.template_id.id),
                ('employee_id', '=', employee.id),
                ('period_start', '=', period_start),
                ('period_end', '=', period_end),
            ], limit=1)
            if not existing:
                kpi_result.create({
                    'template_id': self.template_id.id,
                    'employee_id': employee.id,
                    'assignment_id': self.id,
                    'period_start': period_start,
                    'period_end': period_end,
                    'target_value': self.template_id.target_value,
                    'state': 'draft',
                })

    @api.model
    def _cron_generate_results(self):
        """Cron job: Generate KPI results for active assignments at period start."""
        today = date.today()
        active_assignments = self.search([('state', '=', 'active')])
        for assignment in active_assignments:
            period_start, period_end = assignment._get_period_dates(today)
            # Only generate if we are at or past the period start
            if today >= period_start:
                assignment._generate_results_for_period(period_start, period_end)

    @api.model
    def _sync_department_members(self, employee, old_dept_id, new_dept_id):
        """Sync KPI assignments when an employee changes department.

        Called from hr.employee.write() override.
        """
        # Remove department-based assignments from old department
        if old_dept_id:
            old_assignments = self.search([
                ('department_id', 'child_of', old_dept_id),
                ('state', '=', 'active'),
            ])
            for assignment in old_assignments:
                if assignment.employee_id == employee:
                    continue  # Skip individual assignments
                # Expire any existing results for this assignment+employee
                self.env['kpi.result'].search([
                    ('assignment_id', '=', assignment.id),
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'draft'),
                ]).unlink()

        # Add department-based assignments from new department
        if new_dept_id:
            new_assignments = self.search([
                ('department_id', 'child_of', new_dept_id),
                ('state', '=', 'active'),
            ])
            for assignment in new_assignments:
                if assignment.employee_id == employee:
                    continue  # Skip individual assignments
                today = date.today()
                period_start, period_end = assignment._get_period_dates(today)
                # Check if not already assigned
                existing = self.env['kpi.result'].search([
                    ('template_id', '=', assignment.template_id.id),
                    ('employee_id', '=', employee.id),
                    ('period_start', '=', period_start),
                ])
                if not existing:
                    self.env['kpi.result'].create({
                        'template_id': assignment.template_id.id,
                        'employee_id': employee.id,
                        'assignment_id': assignment.id,
                        'period_start': period_start,
                        'period_end': period_end,
                        'target_value': assignment.template_id.target_value,
                        'state': 'draft',
                    })

    def action_view_results(self):
        """Return action to view results for this assignment."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('KPI Results'),
            'res_model': 'kpi.result',
            'view_mode': 'list,form',
            'domain': [('assignment_id', '=', self.id)],
            'context': {'default_assignment_id': self.id},
        }
