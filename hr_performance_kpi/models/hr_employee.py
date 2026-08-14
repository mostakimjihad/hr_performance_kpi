# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    kpi_result_ids = fields.One2many(
        'kpi.result',
        'employee_id',
        string="KPI Results",
    )
    kpi_result_count = fields.Integer(
        string="KPI Results Count",
        compute='_compute_kpi_result_count',
    )
    kpi_avg_score = fields.Float(
        string="KPI Average Score",
        compute='_compute_kpi_avg_score',
    )

    @api.depends('kpi_result_ids')
    def _compute_kpi_result_count(self):
        for employee in self:
            employee.kpi_result_count = len(employee.kpi_result_ids)

    @api.depends('kpi_result_ids', 'kpi_result_ids.score')
    def _compute_kpi_avg_score(self):
        for employee in self:
            results = employee.kpi_result_ids.filtered(
                lambda r: r.state == 'approved'
            )
            scores = results.mapped('score')
            employee.kpi_avg_score = sum(scores) / len(scores) if scores else 0.0

    def write(self, vals):
        """Track department changes to sync KPI assignments."""
        old_depts = {}
        if 'department_id' in vals:
            old_depts = {emp.id: emp.department_id.id for emp in self}

        result = super().write(vals)

        if 'department_id' in vals:
            new_dept_id = vals.get('department_id', False)
            for employee in self:
                old_dept_id = old_depts.get(employee.id, False)
                # Compare to the freshly written value to handle records with
                # no prior department (``False`` -> ``new_dept_id``).
                if employee.department_id.id != old_dept_id:
                    try:
                        self.env['kpi.assignment']._sync_department_members(
                            employee, old_dept_id, new_dept_id
                        )
                    except Exception as e:
                        _logger.warning(
                            'Failed to sync KPI assignments for employee %s: %s',
                            employee.name, str(e)
                        )
        return result

    def action_view_kpi_results(self):
        """Return action to view KPI results for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('KPI Results'),
            'res_model': 'kpi.result',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
