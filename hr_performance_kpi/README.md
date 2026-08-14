# KPI Management

A comprehensive Key Performance Indicator (KPI) management module for Odoo 19.0 that enables organizations to define metrics, assign them to employees or departments, track periodic results with approval workflows, and monitor performance through a real-time dashboard.

## Overview

| Model | Purpose |
|---|---|
| **KPI Categories** | Organize KPIs into hierarchical category trees (e.g., Financial, HR, Sales) |
| **KPI Templates** | Define metric definitions with targets, RAG thresholds, and calculation methods |
| **KPI Assignments** | Assign templates to individual employees or entire departments |
| **KPI Results** | Periodic performance entries with a Draft → Submitted → Reviewed → Approved workflow |
| **Dashboard** | Real-time performance overview with summary cards, RAG distribution, and trends |

## Installation

1. Copy the `hr_performance_kpi` folder into your Odoo `custom_addons` directory
2. Restart Odoo and update the apps list
3. Install the **KPI Management** module from the Apps menu

### Requirements
- Odoo 19.0
- `hr` module (Employees, Departments)
- `mail` module (messaging, tracking, activities)

## User Roles

| Group | Permissions |
|---|---|
| **KPI User** (`group_kpi_user`) | View KPIs and results; create and submit their own results |
| **KPI Manager** (`group_kpi_manager`) | Full access — create templates, manage assignments, review and approve results, configure categories |

Both groups are placed under the **Human Resources** application category.

## How to Use

### Step 1 — Set Up Categories

Navigate to **KPI Management → Configuration → KPI Categories**.

Create a hierarchy of categories to organize your KPIs. Examples:
- **Financial** — Revenue, Margin, Expenses
- **HR** — Attendance, Training, Retention
- **Sales** — Conversion Rate, Pipeline Value
- **Operations** — Delivery Time, Quality Score

Each category can have sub-categories (e.g., Financial → Revenue → Product Lines). Categories are color-coded in the kanban view for visual organization.

### Step 2 — Define KPI Templates

Navigate to **KPI Management → KPI Templates**.

Create KPI metric definitions with the following configuration:

#### Basic Information
| Field | Description |
|---|---|
| **Name** | Descriptive name (e.g., "Monthly Revenue Growth") |
| **Code** | Short identifier (e.g., `REV_GROWTH`) |
| **Category** | Assign to a KPI category |
| **KPI Type** | Quantitative (numeric) or Qualitative (rating) |
| **Unit** | Unit of measure (%, units, hours, EUR, etc.) |
| **Periodicity** | Monthly, Quarterly, or Yearly evaluation cycle |
| **Weight** | Relative importance (1–10) for roll-up scoring |
| **Direction** | Higher is Better / Lower is Better / Hit a Target |

#### RAG Thresholds

The **Red / Amber / Green** system provides instant visual status:

```
Score ≥ Green Threshold  → 🟢 Green (On Track)
Amber ≤ Score < Green    → 🟡 Amber (At Risk)
Score < Amber Threshold  → 🔴 Red (Off Track)
```

Example: Green threshold = 80%, Amber threshold = 50%. A score of 85% is Green, 65% is Amber, 35% is Red.

#### Calculation Methods

| Method | Description |
|---|---|
| **Manual Entry** | Users manually enter actual values when submitting results |
| **Automated (Odoo Data)** | Pulls values from any Odoo model using ORM queries. Select the target model, field, and optional aggregate (sum, avg, count, min, max) with a domain filter |
| **Formula** | Compute values using Python expressions referencing current or previous period values. Example: `value * 1.1` for 10% growth |

### Step 3 — Assign KPIs

Navigate to **KPI Management → Assignments**.

Create assignments to distribute KPIs:

- **Individual assignment**: Select an Employee — the KPI applies only to that person
- **Department assignment**: Select a Department — the KPI automatically applies to all current members

Set the **Valid From** date (and optionally a **Valid To** date). The assignment goes through:
1. **Draft** — initial state, results not yet generated
2. **Active** — results are generated for the current period
3. **Expired** — past the validity end date
4. **Cancelled** — manually terminated

> **Note**: When an employee changes departments, the system automatically syncs their department-based KPI assignments — removing old department KPIs and adding new ones.

### Step 4 — Submit Results

Navigate to **KPI Management → KPI Results**.

Employees and managers can:
1. Open a result record (auto-generated for active assignments each period)
2. Enter the **Actual Value** achieved
3. Click **Submit for Review**

The **Score** and **RAG Status** are calculated automatically based on the template's thresholds and direction.

#### Approval Workflow

```
Draft → Submitted → Reviewed → Approved
  ↑                      ↓
  └──── Returned ←───────┘
```

| State | Action |
|---|---|
| **Draft** | Employee enters data; can edit freely |
| **Submitted** | Locked for employee; manager reviews |
| **Reviewed** | Manager has reviewed; awaiting final approval |
| **Approved** | Final state; read-only |
| **Returned** | Manager sends back for corrections; employee can edit again |

### Step 5 — Monitor the Dashboard

Navigate to **KPI Management → Dashboard**.

The dashboard provides a real-time performance snapshot:

- **Summary Cards**: Total KPIs, On Track (Green), At Risk (Amber), Off Track (Red)
- **RAG Distribution**: Progress bars showing the percentage split across Green/Amber/Red
- **Average Score**: Overall average with a visual progress bar and status message
- **Quick Links**: Direct access to Templates, Assignments, Results, and Categories

## Automated Cron Jobs

Two scheduled actions run daily (inactive by default — activate them in Settings → Technical → Scheduled Actions):

| Cron Job | Purpose |
|---|---|
| **Generate Periodic Results** | Creates KPI result records for active assignments at the start of each period |
| **Calculate Automated Results** | Computes values for KPIs using the ORM query or formula calculation methods |

## Views & Analysis

| View Type | Available For | Purpose |
|---|---|---|
| **Dashboard** | Dashboard | Full-screen performance overview |
| **Kanban** | Categories, Templates | Visual card-based browsing |
| **List** | All models | Tabular data with multi-edit, color decorations, and progress bars |
| **Form** | All models | Detailed record editing with status bars |
| **Pivot** | Results | Cross-tab analysis (employee vs template vs score) |
| **Graph** | Results | Score trends over time |

## Demo Data

When Odoo demo data is enabled, the module creates sample records:
- 3 categories (HR, Sales, Operations)
- 4 KPI templates (Attendance Regularity, Sales Invoice Amount, Customer Satisfaction, Delivery Lead Time)
- 1 department-level assignment
- 5 individual employee assignments

## Security

- **Multi-company**: All records include a company field; multi-company rules restrict visibility to the user's allowed companies
- **Record rules**: Users see their own results or results of their subordinates; managers have broader access
- **Access rights**: Users get read access to templates/categories/assignments; managers get full CRUD; results support user-level create/submit

## Technical Notes

- The dashboard is a `TransientModel` — computed fresh on every access, never stored
- Employee-department sync is triggered via an override in `hr.employee.write()`
- KPI scores are computed with the formula: `(actual_value / target_value) × 100` (adjusted for direction)
- RAG status thresholds are configurable per template
- The `parent_path` field on categories enables hierarchical queries with `child_of`
