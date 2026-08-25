# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Petty Cash Daily',
    'version': '19.0.1.0.0',
    'category': 'Finance/Accounting',
    'sequence': 192,
    'summary': 'Daily cash box management with a beautiful expense dashboard',
    'description': """
Petty Cash Daily
================

A daily-first petty cash management module for Odoo 19.0 with a beautiful
real-time expense dashboard.

What it does
------------

- Define one or more **cash boxes** (funds), each with a custodian,
  opening balance and currency.
- Record every transaction as **money in** (replenishment, hand-in) or
  **money out** (expense) with a receipt attachment, category and notes.
- A configurable per-fund **approval limit** auto-routes small expenses
  to be paid instantly and larger ones to a manager for approval.
- Open and close a **daily session** for each fund; the dashboard
  compares the expected closing balance (computed from the day's
  transactions) to the **actual** count, surfacing variances.
- Request a **replenishment** when the balance drops below a configurable
  threshold; manager approves and the funds are added to the next session.
- View the **Daily Expense Dashboard** — today's income, today's
  expenses, net change, current balance and pending approvals at a
  glance; seven-day cash-flow trend; top expense categories for the
  month; recent transactions; low-balance alerts.

Back-office
-----------

- Funds (kanban cards with color-coded custodian) and categories
  (tree hierarchy with budgets) under Configuration.
- Transactions with a Draft → Submitted → Approved/Rejected → Paid
  workflow, chatter messages on every transition.
- Daily Sessions with start/end times, expected vs actual balance,
  variance alert and manager confirmation.
- Replenishments with a Draft → Submitted → Approved → Received
  workflow.

Security
--------

Three groups live under *Petty Cash Daily*:

- **Petty Cash User** — view funds and own transactions; open own
  sessions; submit expenses.
- **Petty Cash Manager** — full access; approve transactions and
  replenishments; close sessions; configure funds and categories.
- **Petty Cash Auditor** — read-only across all funds with access to
  the audit log.

Integration
------------

- ``account`` module: each transaction can post to a default expense
  account and analytic distribution, so approved expenses flow through
  to vendor bills and analytic reports.
- ``hr`` module: custodian is an ``hr.employee`` so the dashboard can
  break spend down by department and manager.
- ``mail`` module: full chatter on every stateful model.

Differentiators
---------------

Petty Cash Daily is built around the **daily** experience: opening the
cash drawer, recording every transaction through the day, closing the
drawer at end-of-day and seeing the variance the moment it matters.
The dashboard is the home screen — a single page that an office
manager opens every morning before any other view.
""",
    'depends': [
        'account',
        'hr',
        'mail',
    ],
    'data': [
        'security/petty_cash_security.xml',
        'security/ir.model.access.csv',
        'data/petty_cash_cron.xml',
        'data/petty_cash_sequence.xml',
        'data/petty_cash_data.xml',
        'views/petty_cash_fund_views.xml',
        'views/petty_cash_category_views.xml',
        'views/petty_cash_transaction_views.xml',
        'views/petty_cash_session_views.xml',
        'views/petty_cash_replenishment_views.xml',
        'views/petty_cash_menus.xml',
        'views/petty_cash_dashboard_views.xml',
    ],
    'demo': [
        'data/petty_cash_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'petty_cash_daily/static/src/css/petty_cash_dashboard.css',
        ],
    },
    'installable': True,
    'application': True,
    'author': 'Mostakim Jihad',
    'license': 'LGPL-3',
    'images': ['static/description/banner.svg'],
}
