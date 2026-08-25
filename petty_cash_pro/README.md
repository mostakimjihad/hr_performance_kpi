# Petty Cash Pro

A daily-first petty cash management module for Odoo 19 with a beautiful
real-time expense dashboard.

## Overview

| Model | Purpose |
|---|---|
| **Cash Boxes** (`petty.cash.fund`) | Each physical drawer — custodian, opening balance, alert threshold, auto-approve limit |
| **Categories** (`petty.cash.category`) | Expense categories with budgets and default accounts |
| **Transactions** (`petty.cash.transaction`) | Every receipt and disbursement, with quick-pay, receipt attachments, and the full Draft → Submitted → Approved → Paid workflow |
| **Daily Sessions** (`petty.cash.session`) | One session per cash box per day — opening balance, expected vs actual reconciliation, variance |
| **Replenishments** (`petty.cash.replenishment`) | Top-up requests with manager approval |
| **Dashboard** (`petty.cash.dashboard`) | The daily overview: today's income / expenses / net / balance / pending, 7-day cash flow, top categories, low-balance alerts |

## Why Petty Cash Pro

Most cash-management apps focus on cards (Ramp, Brex, Spendesk) but a real
office still has a physical drawer that someone has to count at the end of the
day. Petty Cash Pro is built around that daily experience:

- **Open once.** A daily cron opens today's session at midnight, gives the
  cashier the opening balance, and starts recording transactions.
- **Capture every penny.** Money in (replenishment, return) or money out
  (expense). Under the auto-approve cap = instant. Over the cap = manager
  approval.
- **Reconcile at the end.** The session forces the cashier to enter the
  actual counted cash, then surfaces the variance in green / red. The
  manager confirms the close.
- **Replenish gracefully.** When the balance drops below the alert
  threshold, a one-click replenishment request creates a Draft replenishment;
  on approval and receipt, the cash lands back in the drawer as a paid
  Money-In transaction.

## Installation

1. Drop `petty_cash_pro` into your Odoo addons path.
2. Restart Odoo and update the apps list.
3. Install **Petty Cash Pro** from the Apps menu.
4. (Optional) In Settings → Technical → Scheduled Actions, enable
   *Petty Cash: Open / Close Daily Sessions* to have the system auto-open
   and close sessions for you.

### Requirements

- Odoo **19.0**
- `account` (Accounting) — for default accounts and analytic distribution
- `hr` (Human Resources) — for custodians and submitter identity
- `mail` (Discuss / Chatter) — for state tracking and approvals

## Security

Three groups live under *Petty Cash Pro* in Settings → Users & Companies:

| Group | Permissions |
|---|---|
| **Petty Cash User** | View own funds, open sessions, submit expenses and replenishments |
| **Petty Cash Manager** | Full access — approve transactions, close sessions, configure funds |
| **Petty Cash Auditor** | Read-only across all funds with full audit trail visibility |

Record rules scope users to their own submissions plus their department
manager and direct reports.

## How to Use

### Step 1 — Create Cash Boxes

Navigate to **Petty Cash → Cash Boxes → Create**.

For each box:
- A short **Code** (`FRONT`, `CAFE`)
- A **Custodian** (the employee who holds the cash)
- An **Opening Balance** — the cash physically placed in the drawer
- An **Alert Threshold** — when balance drops below this, the dashboard surfaces an alert
- A **Transaction Limit** — auto-approve cap

### Step 2 — Define Categories (Optional)

Navigate to **Petty Cash → Configuration → Categories**.

The module ships with seven defaults — Travel, Meals & Entertainment, Office
Supplies, Fuel & Tolls, Utilities, Postage, Replenishment — each with a
monthly budget. Add more or override the default account as needed.

### Step 3 — Record Transactions

From the Dashboard or **Petty Cash → Transactions**:

1. Click **Create** on the Transactions list.
2. Pick the cash box, choose direction (in/out), enter amount.
3. Pick a category and write a short description.
4. **Quick Pay** if under the limit — submits and pays in one click.
5. Over the limit — Submit, then a manager approves and pays.

Receipts attach via the form's *Receipt* field. The chatter logs every
transition.

### Step 4 — Close the Daily Session

The daily session is automatically created at midnight. To close manually:

1. Open the session record (today's row in **Daily Sessions**).
2. Click **Start Closing**.
3. Enter the **Actual Cash Counted**.
4. The **Variance** row shows the overage/shortage against expected.
5. Click **Close Session** and have a manager **Confirm**.

### Step 5 — Replenishments

When a box drops below its alert threshold:

1. From the fund form, click **Request Replenishment**.
2. Enter the requested amount and a reason.
3. Manager **Approves** → when cash arrives, **Mark Received** — an inbound
   transaction is automatically created.

## Daily Dashboard

The dashboard is the **first menu item** and opens by default. It shows:

| Tile | What it shows |
|---|---|
| Income (green) | Money in today across all active funds |
| Expenses (red) | Money out today, with transaction count |
| Net Change (blue) | Income − Expenses |
| In Drawers (yellow) | Total cash across all active funds |
| Pending (cyan) | Submitted transactions awaiting approval |

Below the tiles:
- **7-Day Cash Flow** — SVG line chart with income, expenses, and a dashed net line
- **Top Categories This Month** — horizontal bar chart, color-coded per category
- **Recent Transactions** — last 8 transactions with submitter and status badge
- **Low Balance Alerts** — funds whose balance is below their threshold
- **Fund Snapshots** — color-coded card grid of every active fund

## Technical Notes

- All stateful models use `mail.thread` and `mail.activity.mixin`. Every
  transition posts to chatter.
- The dashboard is a `TransientModel` rendered server-side. Charts are
  pure SVG / Bootstrap — no JS chart library.
- The 7-day cash-flow series auto-aggregates `petty.cash.transaction`
  grouped by date.
- `_sql_constraints` are declared via the new Odoo 19 `models.Constraint`
  API; Odoo 19 removed the `tree` view alias (we use `list`), the
  `_sql_constraints` class attribute, the `numbercall` field on `ir.cron`,
  and the `account.module_category_accounting` XML ID — the module is
  hardened against these.
- `mailto:partner_alias@yourcompany.example` style emails are not used;
  receipts are stored as `ir.attachment` records.

## License

LGPL-3.
