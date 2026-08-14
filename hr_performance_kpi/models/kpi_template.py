# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class KpiTemplate(models.Model):
    _name = 'kpi.template'
    _description = "KPI Template"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string="KPI Name",
        required=True,
        translate=True,
        tracking=True,
    )
    code = fields.Char(
        string="Code",
        tracking=True,
    )
    description = fields.Text(
        string="Description",
        translate=True,
    )
    category_id = fields.Many2one(
        'kpi.category',
        string="Category",
        tracking=True,
    )
    kpi_type = fields.Selection(
        [('quantitative', 'Quantitative'), ('qualitative', 'Qualitative')],
        string="KPI Type",
        default='quantitative',
        required=True,
        tracking=True,
    )
    unit = fields.Char(
        string="Unit",
        default="%",
        help="Unit of measure (e.g., %, units, hours, EUR).",
    )
    direction = fields.Selection(
        [('maximize', 'Higher is Better'),
         ('minimize', 'Lower is Better'),
         ('target', 'Hit a Target')],
        string="Direction",
        default='maximize',
        required=True,
        tracking=True,
    )
    periodicity = fields.Selection(
        [('monthly', 'Monthly'),
         ('quarterly', 'Quarterly'),
         ('yearly', 'Yearly')],
        string="Evaluation Period",
        default='monthly',
        required=True,
        tracking=True,
    )
    target_value = fields.Float(
        string="Target Value",
        tracking=True,
    )
    min_value = fields.Float(
        string="Minimum Value",
        help="Minimum anticipated value for scoring calculation.",
    )
    max_value = fields.Float(
        string="Maximum Value",
        help="Maximum anticipated value for scoring calculation.",
    )
    green_threshold = fields.Float(
        string="Green Threshold (%)",
        default=80.0,
        required=True,
        help="Score percentage above which the KPI is considered 'Green' (On Track).",
    )
    amber_threshold = fields.Float(
        string="Amber Threshold (%)",
        default=50.0,
        required=True,
        help="Score percentage above which the KPI is considered 'Amber' (At Risk). "
             "Below this value is 'Red' (Off Track).",
    )
    weight = fields.Float(
        string="Weight",
        default=1.0,
        help="Relative weight (1-10) for roll-up scoring calculations.",
    )
    calculation_method = fields.Selection(
        [('manual', 'Manual Entry'),
         ('orm_query', 'Automated (Odoo Data)'),
         ('formula', 'Formula')],
        string="Calculation Method",
        default='manual',
        required=True,
        tracking=True,
    )
    model_id = fields.Many2one(
        'ir.model',
        string="Target Model",
        help="Odoo model to query for automated calculation.",
    )
    target_field_id = fields.Many2one(
        'ir.model.fields',
        string="Target Field",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['integer', 'float', 'monetary'])]",
        help="Numeric field to aggregate.",
    )
    aggregate = fields.Selection(
        [('sum', 'Sum'), ('count', 'Count'), ('avg', 'Average')],
        string="Aggregation",
    )
    domain_filter = fields.Char(
        string="Domain Filter",
        default='[]',
        help="Optional domain filter for the ORM query (e.g., [('state', '=', 'posted')]).",
    )
    expression = fields.Text(
        string="Formula",
        help="Python expression for formula-based calculation. "
             "Use 'value' for the base value. Example: value * 1.1",
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        tracking=True,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )
    assignment_ids = fields.One2many(
        'kpi.assignment',
        'template_id',
        string="Assignments",
    )
    assignment_count = fields.Integer(
        string="Assignment Count",
        compute='_compute_assignment_count',
    )
    result_ids = fields.One2many(
        'kpi.result',
        'template_id',
        string="Results",
    )
    result_count = fields.Integer(
        string="Result Count",
        compute='_compute_result_count',
    )

    @api.depends('assignment_ids')
    def _compute_assignment_count(self):
        for template in self:
            template.assignment_count = len(template.assignment_ids)

    @api.depends('result_ids')
    def _compute_result_count(self):
        for template in self:
            template.result_count = len(template.result_ids)

    @api.constrains('green_threshold', 'amber_threshold')
    def _check_rag_thresholds(self):
        for template in self:
            if template.green_threshold <= template.amber_threshold:
                raise ValidationError(_(
                    'Green threshold (%.1f%%) must be greater than Amber threshold (%.1f%%).'
                ) % (template.green_threshold, template.amber_threshold))

    @api.constrains('weight')
    def _check_weight(self):
        for template in self:
            if template.weight < 0 or template.weight > 10:
                raise ValidationError(_(
                    'Weight must be between 0 and 10.'
                ))

    @api.constrains('min_value', 'max_value')
    def _check_min_max(self):
        for template in self:
            if template.min_value is not None and template.max_value is not None and template.min_value >= template.max_value:
                raise ValidationError(_(
                    'Maximum value must be greater than Minimum value.'
                ))

    @api.constrains('target_value', 'min_value', 'max_value')
    def _check_target_in_range(self):
        for template in self:
            if (template.min_value is not None and template.max_value is not None
                    and template.target_value is not None):
                if template.target_value < template.min_value or template.target_value > template.max_value:
                    raise ValidationError(_(
                        'Target value (%.2f) must be between Min (%.2f) and Max (%.2f).'
                    ) % (template.target_value, template.min_value, template.max_value))

    @api.onchange('calculation_method')
    def _onchange_calculation_method(self):
        """Clear irrelevant fields when method changes."""
        if self.calculation_method != 'orm_query':
            self.model_id = False
            self.target_field_id = False
            self.aggregate = False
            self.domain_filter = '[]'
        if self.calculation_method != 'formula':
            self.expression = False

    def action_view_assignments(self):
        """Return action to view assignments for this template."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('KPI Assignments'),
            'res_model': 'kpi.assignment',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        }

    def action_view_results(self):
        """Return action to view results for this template."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('KPI Results'),
            'res_model': 'kpi.result',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
        }

    def _compute_actual_value_orm(self, employee, period_start, period_end):
        """Execute ORM query to compute actual value for a result."""
        self.ensure_one()
        if not self.model_id or not self.target_field_id:
            return 0.0

        model_name = self.model_id.model
        field_name = self.target_field_id.name

        # Parse domain filter
        domain = []
        if self.domain_filter:
            try:
                domain = ast.literal_eval(self.domain_filter)
                if not isinstance(domain, (list, tuple)):
                    domain = []
            except (ValueError, SyntaxError, TypeError):
                domain = []

        # Add employee-related domain if the model has employee_id field
        Model = self.env.get(model_name)
        if Model and hasattr(Model, '_fields') and 'employee_id' in Model._fields:
            domain.append(('employee_id', '=', employee.id))

        # Add date range domain if the model has date field
        date_field = self._guess_date_field(Model)
        if date_field and period_start and period_end:
            domain.append((date_field, '>=', period_start))
            domain.append((date_field, '<=', period_end))

        try:
            if self.aggregate == 'sum':
                records = self.env[model_name].search(domain)
                return sum(records.mapped(field_name))
            elif self.aggregate == 'count':
                return self.env[model_name].search_count(domain)
            elif self.aggregate == 'avg':
                records = self.env[model_name].search(domain)
                values = records.mapped(field_name)
                return sum(values) / len(values) if values else 0.0
        except Exception:
            return 0.0

        return 0.0

    def _compute_actual_value_formula(self, employee, period_start, period_end):
        """Execute formula to compute actual value for a result.

        Uses ``safe_eval`` to evaluate the expression in a restricted namespace
        that does not expose ``builtins``, the full ``env``, or arbitrary
        imports.  Only arithmetic, comparisons and a few helper names are
        available to the expression.
        """
        self.ensure_one()
        if not self.expression:
            return 0.0

        # Find the most recent result for the same template/employee so the
        # formula can reference the previous period's value if desired.
        result = self.env['kpi.result'].search([
            ('template_id', '=', self.id),
            ('employee_id', '=', employee.id),
        ], limit=1, order='period_start desc')

        local_dict = {
            'employee': employee,
            'period_start': period_start,
            'period_end': period_end,
            'result': result,
            'value': (result.actual_value if result and result.actual_value is not None else 0.0),
            'previous_value': (result.actual_value if result and result.actual_value is not None else 0.0),
        }
        try:
            computed = safe_eval(self.expression, local_dict, mode="eval")
        except Exception:
            return 0.0
        try:
            return float(computed) if computed is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _guess_date_field(self, Model):
        """Guess the most likely date field for period filtering."""
        if not Model:
            return None
        date_candidates = ['date', 'create_date', 'write_date', 'date_order',
                          'date_invoice', 'date_delivery', 'date_from', 'date_start']
        for field_name in date_candidates:
            if field_name in Model._fields:
                return field_name
        return None
