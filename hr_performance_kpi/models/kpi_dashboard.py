# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import api, fields, models


class KpiDashboard(models.TransientModel):
    _name = 'kpi.dashboard'
    _description = "KPI Dashboard"

    name = fields.Char(
        string="Dashboard",
        default="KPI Performance Dashboard",
    )
    total_results = fields.Integer(
        string="Total KPIs",
        compute='_compute_dashboard_data',
    )
    on_track = fields.Integer(
        string="On Track",
        compute='_compute_dashboard_data',
    )
    at_risk = fields.Integer(
        string="At Risk",
        compute='_compute_dashboard_data',
    )
    off_track = fields.Integer(
        string="Off Track",
        compute='_compute_dashboard_data',
    )
    avg_score = fields.Float(
        string="Average Score",
        compute='_compute_dashboard_data',
    )
    green_pct = fields.Float(
        string="Green %",
        compute='_compute_dashboard_data',
    )
    amber_pct = fields.Float(
        string="Amber %",
        compute='_compute_dashboard_data',
    )
    red_pct = fields.Float(
        string="Red %",
        compute='_compute_dashboard_data',
    )
    department_data = fields.Text(
        string="Department Data (JSON)",
        compute='_compute_dashboard_data',
    )
    employee_rankings = fields.Text(
        string="Employee Rankings (JSON)",
        compute='_compute_dashboard_data',
    )

    def _compute_dashboard_data(self):
        """Compute all dashboard data from kpi.result."""
        kpi_result = self.env['kpi.result']
        summary = kpi_result.get_dashboard_summary()
        dept_perf = kpi_result.get_department_performance()
        emp_rank = kpi_result.get_employee_rankings(limit=10)

        for record in self:
            record.total_results = summary.get('total_results', 0)
            record.on_track = summary.get('on_track', 0)
            record.at_risk = summary.get('at_risk', 0)
            record.off_track = summary.get('off_track', 0)
            record.avg_score = summary.get('avg_score', 0.0)
            record.green_pct = summary.get('green_pct', 0.0)
            record.amber_pct = summary.get('amber_pct', 0.0)
            record.red_pct = summary.get('red_pct', 0.0)
            record.department_data = json.dumps(dept_perf)
            record.employee_rankings = json.dumps(emp_rank)
