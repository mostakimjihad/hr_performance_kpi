# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'KPI Management',
    'version': '19.0.1.0.1',
    'category': 'Human Resources/Performance',
    'sequence': 190,
    'summary': 'Define, assign and track KPI metrics with RAG scoring and dashboards',
    'description': """
KPI Management
=============

A Key Performance Indicator (KPI) management module for Odoo that lets
organizations define metrics, assign them to employees or departments,
track periodic results with an approval workflow, and monitor performance
on a real-time dashboard.

Features
--------

- KPI Categories with hierarchical parent/child trees.
- KPI Templates with quantitative or qualitative types, configurable
  RAG (Red/Amber/Green) thresholds, periodicity (monthly/quarterly/yearly),
  and weight for roll-up scoring.
- Three calculation methods:
  * Manual Entry — the employee or manager enters the actual value.
  * ORM Query — pulls the value from any Odoo model with optional
    aggregation (sum, count, average) and a domain filter.
  * Formula — evaluates a sandboxed Python expression over the previous
    period's value (e.g. ``value * 1.1``).
- KPI Assignments to an individual employee or to an entire department,
  with a state machine (Draft → Active → Expired/Cancelled).
- KPI Results with a Draft → Submitted → Reviewed → Approved workflow,
  including a Returned state for revision.
- Real-time Dashboard with summary cards, RAG distribution and an
  overall average score gauge.
- Pivot and graph views for cross-tab analysis.
- Multi-company ready, with record rules so users see their own results
  or those of their subordinates.
""",
    'depends': [
        'hr',
        'mail',
    ],
    'data': [
        'security/kpi_security.xml',
        'security/ir.model.access.csv',
        'data/kpi_cron.xml',
        'views/kpi_category_views.xml',
        'views/kpi_template_views.xml',
        'views/kpi_assignment_views.xml',
        'views/kpi_result_views.xml',
        'views/kpi_menus.xml',
        'views/kpi_dashboard_views.xml',
    ],
    'demo': [
        'data/kpi_demo.xml',
    ],
    'installable': True,
    'application': True,
    'author': 'Mostakim Jihad',
    'license': 'LGPL-3',
}
