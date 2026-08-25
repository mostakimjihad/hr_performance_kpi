# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from datetime import date, datetime, time, timedelta

from markupsafe import Markup

from odoo import api, fields, models, tools


class PettyCashDashboard(models.TransientModel):
    _name = 'petty.cash.dashboard'
    _description = 'Petty Cash Daily Dashboard'

    name = fields.Char(
        string='Dashboard',
        default='Daily Petty Cash Dashboard',
    )

    # ---- Stat cards (visible) ----
    today_income = fields.Monetary(
        string="Today's Money In",
        currency_field='company_currency_id',
        compute='_compute_summary',
    )
    today_expenses = fields.Monetary(
        string="Today's Money Out",
        currency_field='company_currency_id',
        compute='_compute_summary',
    )
    today_net = fields.Monetary(
        string="Net Change Today",
        currency_field='company_currency_id',
        compute='_compute_summary',
    )
    today_count = fields.Integer(
        string="Transactions Today",
        compute='_compute_summary',
    )
    current_balance = fields.Monetary(
        string="Total Balance (Active Funds)",
        currency_field='company_currency_id',
        compute='_compute_summary',
    )
    opening_balance = fields.Monetary(
        string="Total Opening Balance",
        currency_field='company_currency_id',
        compute='_compute_summary',
    )
    pending_approvals = fields.Integer(
        string="Pending Approvals",
        compute='_compute_summary',
    )
    low_balance_count = fields.Integer(
        string="Low-Balance Alerts",
        compute='_compute_summary',
    )

    # ---- Chart / list HTML payloads ----
    cash_flow_html = fields.Html(
        string='Cash Flow Chart',
        compute='_compute_summary',
        sanitize=False,
    )
    top_categories_html = fields.Html(
        string='Top Categories',
        compute='_compute_summary',
        sanitize=False,
    )
    recent_transactions_html = fields.Html(
        string='Recent Transactions',
        compute='_compute_summary',
        sanitize=False,
    )
    low_balance_html = fields.Html(
        string='Low Balance Alerts',
        compute='_compute_summary',
        sanitize=False,
    )
    approval_queue_html = fields.Html(
        string='Approval Queue',
        compute='_compute_summary',
        sanitize=False,
    )
    top_custodians_html = fields.Html(
        string='Top Custodians This Month',
        compute='_compute_summary',
        sanitize=False,
    )
    budget_burn_html = fields.Html(
        string='Monthly Budget vs Actual',
        compute='_compute_summary',
        sanitize=False,
    )
    fund_snapshots_html = fields.Html(
        string='Fund Snapshots',
        compute='_compute_summary',
        sanitize=False,
    )

    company_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_summary',
    )

    # ----- Helpers ----
    @staticmethod
    def _fmt_money(amount, currency):
        # Format with thousand separators and the currency symbol.
        if amount is None or amount is False:
            amount = 0.0
        symbol = currency.symbol or ''
        return f'{currency.symbol or ""} {amount:,.2f}'

    @staticmethod
    def _fmt_day_short(d):
        # Compact weekday label without locale issues.
        return d.strftime('%a')

    def _render_cash_flow(self, series, currency):
        """Render a 7-day cash flow chart (inline SVG)."""
        if not series:
            return '<div class="text-muted small text-center py-5">No cash flow yet.</div>'

        # Layout
        width = 720
        height = 220
        pad_left = 40
        pad_right = 12
        pad_top = 16
        pad_bottom = 36
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom

        # Build value axis: max(income, expense) per day
        max_in = max((s.get('in', 0) or 0) for s in series) or 1.0
        max_out = max((s.get('out', 0) or 0) for s in series) or 1.0
        ymax = max(max_in, max_out) * 1.15

        n = len(series)
        step_x = plot_w / max(n - 1, 1)

        def x_at(i):
            return pad_left + i * step_x

        def y_at(v):
            return pad_top + plot_h - (v / ymax * plot_h)

        # Build polyline strings for income (green) and expenses (red)
        in_pts = ' '.join(f'{x_at(i):.1f},{y_at(s["in"]):.1f}' for i, s in enumerate(series))
        out_pts = ' '.join(f'{x_at(i):.1f},{y_at(s["out"]):.1f}' for i, s in enumerate(series))
        net_pts = ' '.join(f'{x_at(i):.1f},{y_at(max(0.0, s["net"])):.1f}' for i, s in enumerate(series))

        # Y-axis ticks (3 lines)
        ticks = []
        for frac in (0.0, 0.5, 1.0):
            v = ymax * frac
            y = pad_top + plot_h - (v / ymax * plot_h)
            ticks.append(
                f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" '
                f'stroke="#eef0f3" stroke-width="1"/>'
                f'<text x="{pad_left - 6}" y="{y + 3:.1f}" font-size="10" '
                f'fill="#9ba1a8" text-anchor="end">{v:,.0f}</text>'
            )

        # X-axis labels
        x_labels = []
        for i, s in enumerate(series):
            x = x_at(i)
            x_labels.append(
                f'<text x="{x:.1f}" y="{height - 12}" font-size="11" fill="#525a66" '
                f'text-anchor="middle">{s["label"]}</text>'
            )

        # Tooltip values (text beneath each series at the data point)
        circle_in = []
        circle_out = []
        for i, s in enumerate(series):
            xi, yi = x_at(i), y_at(s['in'])
            yo = y_at(s['out'])
            circle_in.append(
                f'<circle cx="{xi:.1f}" cy="{yi:.1f}" r="3" fill="#16a34a" '
                f'stroke="white" stroke-width="1.5"/>'
                f'<text x="{xi:.1f}" y="{yi - 8:.1f}" font-size="10" fill="#16a34a" '
                f'text-anchor="middle">{s["in"]:,.0f}</text>'
            )
            circle_out.append(
                f'<circle cx="{xi:.1f}" cy="{yo:.1f}" r="3" fill="#dc2626" '
                f'stroke="white" stroke-width="1.5"/>'
                f'<text x="{xi:.1f}" y="{yo + 14:.1f}" font-size="10" fill="#dc2626" '
                f'text-anchor="middle">{s["out"]:,.0f}</text>'
            )

        # Direct labels only for the first/last series to keep it clean.
        svg = (
            f'<svg viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'role="img" aria-label="7-day cash flow chart">'
            f'<style>'
            f'.pc-chart-line {{ fill: none; stroke-width: 2; stroke-linecap: round; }}'
            f'.pc-area {{ fill-opacity: 0.12; }}'
            f'</style>'
            f'{"".join(ticks)}'
            f'<polyline class="pc-chart-line pc-area" stroke="#16a34a" '
            f'fill="none" points="{in_pts}"/>'
            f'<polyline class="pc-chart-line" stroke="#16a34a" points="{in_pts}"/>'
            f'<polyline class="pc-chart-line pc-area" stroke="#dc2626" '
            f'fill="none" points="{out_pts}"/>'
            f'<polyline class="pc-chart-line" stroke="#dc2626" points="{out_pts}"/>'
            f'<polyline class="pc-chart-line" stroke="#94a3b8" '
            f'stroke-dasharray="3 3" points="{net_pts}"/>'
            f'{"".join(circle_in)}{"".join(circle_out)}'
            f'{"".join(x_labels)}'
            f'<text x="{(pad_left + width - pad_right) / 2:.1f}" y="14" '
            f'font-size="11" fill="#9ba1a8" text-anchor="middle">'
            f'Dashed line = net (income − expenses)</text>'
            f'</svg>'
        )
        return svg

    def _render_top_categories(self, cats, currency):
        """Render the top categories bar list (HTML, no SVG library needed)."""
        if not cats:
            return '<div class="text-muted small text-center py-5">No expenses this month yet.</div>'

        rows = []
        for c in cats:
            color_class = c.get('color_class') or 'secondary'
            # pct of the largest = bar width
            rows.append(f'''
                <div class="d-flex align-items-center mb-3" t-translation="off">
                    <div class="flex-grow-1 me-3">
                        <div class="d-flex justify-content-between align-items-end mb-1">
                            <span class="fw-bold">
                                <span class="badge text-bg-{color_class} me-2">
                                    <i class="fa fa-circle small"/> {c["name"]}
                                </span>
                            </span>
                            <span class="text-muted small">
                                {c["count"]} txns · {self._fmt_money(c["total"], currency)}
                            </span>
                        </div>
                        <div class="progress" style="height: 10px;">
                            <div class="progress-bar bg-{color_class}"
                                 role="progressbar"
                                 style="width: {c["pct"]}%;"
                                 aria-valuenow="{c["pct"]}"
                                 aria-valuemin="0"
                                 aria-valuemax="100">
                            </div>
                        </div>
                    </div>
                </div>''')
        return '\n'.join(rows)

    def _render_recent_transactions(self, recent, currency):
        if not recent:
            return '<div class="text-muted small text-center py-5">No transactions yet.</div>'

        state_class = {
            'draft': 'secondary',
            'submitted': 'warning',
            'approved': 'info',
            'paid': 'success',
            'rejected': 'danger',
            'cancelled': 'muted',
        }
        direction_class = {'in': 'success', 'out': 'danger'}

        rows = []
        for t in recent:
            amount_class = direction_class.get(t['direction'], 'secondary')
            state_cls = state_class.get(t['state'], 'secondary')
            dir_icon = 'fa-arrow-down' if t['direction'] == 'in' else 'fa-arrow-up'
            rows.append(f'''
                <a href="/web#id={t["id"]}&amp;model=petty.cash.transaction&amp;view_type=form"
                   class="text-decoration-none text-reset">
                    <div class="d-flex align-items-center border-bottom py-2 px-3">
                        <div class="me-3">
                            <span class="badge text-bg-{amount_class}">
                                <i class="fa {dir_icon}"/>
                            </span>
                        </div>
                        <div class="flex-grow-1">
                            <div class="fw-bold">{t["description"] or t["name"]}</div>
                            <div class="small text-muted">
                                {t["fund"]} · {t["category"]} ·
                                <i class="fa fa-user-circle"/> {t["submitter"]}
                            </div>
                        </div>
                        <div class="text-end">
                            <div class="fw-bold text-{amount_class}">
                                {("+" if t["direction"] == "in" else "-")}
                                {self._fmt_money(t["amount"], currency)}
                            </div>
                            <span class="badge text-bg-{state_cls} small">{t["state"]}</span>
                        </div>
                    </div>
                </a>''')
        return '\n'.join(rows)

    def _render_low_balance(self, funds):
        if not funds:
            return ('<div class="text-center text-success py-4">'
                    '<i class="fa fa-check-circle fa-2x mb-2"/>'
                    '<p class="mb-0 small">All funds are above their alert threshold.</p>'
                    '</div>')
        rows = []
        for f in funds:
            pct = (f['balance'] / f['threshold'] * 100) if f['threshold'] else 0
            pct = max(0, min(pct, 100))
            rows.append(f'''
                <div class="d-flex align-items-center justify-content-between border-bottom py-2">
                    <div>
                        <strong class="d-block">{f["name"]}</strong>
                        <small class="text-muted">{f["custodian"]}</small>
                    </div>
                    <div class="text-end">
                        <strong class="text-danger">{f["balance"]:,.2f}</strong>
                        <small class="text-muted d-block">/ {f["threshold"]:,.0f} threshold</small>
                        <div class="progress mt-1" style="height: 6px; width: 80px;">
                            <div class="progress-bar bg-danger" style="width: {pct:.0f}%;"></div>
                        </div>
                    </div>
                </div>
            ''')
        return '\n'.join(rows)

    def _render_approval_queue(self, pending_tx, currency):
        """Pending transactions awaiting manager approval."""
        if not pending_tx:
            return (
                '<div class="text-center text-success py-4">'
                '<i class="fa fa-check-circle fa-2x mb-2"/>'
                '<p class="mb-0 small">No transactions awaiting approval.</p>'
                '</div>'
            )
        state_class = {
            'draft': 'secondary',
            'submitted': 'warning',
            'approved': 'info',
            'paid': 'success',
        }
        rows = []
        for t in pending_tx[:8]:
            sc = state_class.get(t['state'], 'secondary')
            rows.append(
                f'<a href="/web#id={t["id"]}&amp;model=petty.cash.transaction&amp;view_type=form" '
                f'class="text-decoration-none text-reset">'
                f'<div class="d-flex align-items-center justify-content-between border-bottom py-2 px-3">'
                f'<div class="me-2 flex-grow-1 min-w-0">'
                f'<div class="fw-bold text-truncate small">{t["description"] or t["name"]}</div>'
                f'<div class="text-muted small text-truncate">'
                f'{t["submitter"]} &middot; {t["category"]} &middot; {t["fund_short"]}'
                f'</div>'
                f'</div>'
                f'<div class="text-end ps-2">'
                f'<div class="fw-bold text-danger small">{self._fmt_money(t["amount"], currency)}</div>'
                f'<span class="badge text-bg-{sc} small">{t["state"]}</span>'
                f'</div>'
                f'</div>'
                f'</a>'
            )
        if len(pending_tx) > 8:
            rows.append(
                f'<div class="text-center text-muted small py-2">'
                f'+ {len(pending_tx) - 8} more '
                f'<a href="/web#menu_id=petty_cash_pro.action_petty_cash_transaction_list&amp;'
                f'search_default_filter_pending=1">view all</a>'
                f'</div>'
            )
        return '\n'.join(rows)

    def _render_top_custodians(self, custodian_rows, currency):
        """Top custodians ranked by paid-out activity this month."""
        if not custodian_rows:
            return (
                '<div class="text-center text-muted py-4 small">'
                'No custodian activity this month yet.</div>'
            )
        items = []
        for i, c in enumerate(custodian_rows[:5], start=1):
            rank_bg = ['text-bg-primary', 'text-bg-secondary', 'text-bg-info',
                       'text-bg-light', 'text-bg-light'][min(i - 1, 4)]
            rank_text = 'text-bg-dark' if 'dark' not in rank_bg and i > 3 else ''
            items.append(
                f'<div class="d-flex align-items-center border-bottom py-2 px-3">'
                f'<div class="me-3">'
                f'<span class="badge {rank_bg} rounded-circle px-2">{i}</span>'
                f'</div>'
                f'<div class="flex-grow-1">'
                f'<div class="fw-bold">{c["name"]}</div>'
                f'<div class="text-muted small">'
                f'{c["count"]} transactions'
                f' &middot; {c["funds"]} fund{"s" if c["funds"] != 1 else ""}'
                f'</div>'
                f'</div>'
                f'<div class="text-end">'
                f'<div class="fw-bold text-danger">{self._fmt_money(c["spent"], currency)}</div>'
                f'<div class="text-muted small">spent mo</div>'
                f'</div>'
                f'</div>'
            )
        return '\n'.join(items)

    def _render_budget_burn(self, budgets, currency):
        """Category monthly budget vs actual spend bars."""
        if not budgets:
            return (
                '<div class="text-center text-muted py-4 small">'
                'No monthly budgets configured yet.</div>'
            )
        rows = []
        for b in budgets[:6]:
            # Render a horizontal progress bar, color-coded by % consumed
            pct_consumed = (b['actual'] / b['budget'] * 100) if b['budget'] > 0 else 0
            pct_consumed = min(pct_consumed, 100)
            if pct_consumed >= 100:
                bar_color = 'bg-danger'
                label_color = 'text-danger'
                exceeded = True
            elif pct_consumed >= 80:
                bar_color = 'bg-warning'
                label_color = 'text-warning'
                exceeded = False
            else:
                bar_color = 'bg-success'
                label_color = 'text-success'
                exceeded = False
            remaining = max(0.0, b['budget'] - b['actual'])
            rows.append(f'''
                <div class="mb-3">
                    <div class="d-flex justify-content-between align-items-end mb-1">
                        <span class="fw-bold small">{b["name"]}</span>
                        <span class="small">
                            <span class="{label_color} fw-bold">{b["actual"]:,.0f}</span>
                            <span class="text-muted"> / {b["budget"]:,.0f}</span>
                        </span>
                    </div>
                    <div class="progress" style="height: 10px;"
                         role="progressbar"
                         aria-valuenow="{pct_consumed:.0f}" aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar {bar_color}"
                             style="width: {pct_consumed:.1f}%;"></div>
                    </div>
                    <div class="text-muted small mt-1">
                        {"OVER" if exceeded else f"{remaining:,.0f} left this month"}
                    </div>
                </div>
            ''')
        return '\n'.join(rows)

    def _render_fund_snapshots(self, funds):
        if not funds:
            return ('<div class="text-center text-muted small py-4">'
                    'No active funds yet — '
                    '<a href="/web#action=petty_cash_pro.action_petty_cash_fund_list" '
                    'class="btn-link">create one</a> to start tracking.</div>')
        items = []
        for f in funds:
            css = f.get('color_class') or 'secondary'
            spent = f.get('spent_month', 0.0)
            items.append(f'''
                <div class="col-md-6 col-lg-4 col-xl-3 mb-3">
                    <div class="card h-100 border-{css} border-2">
                        <div class="card-body">
                            <h6 class="card-title text-uppercase small text-{css} mb-2">
                                <i class="fa fa-money"/> {f["name"]}
                            </h6>
                            <h3 class="mb-1 fw-bold">{f["current"]:,.2f}</h3>
                            <small class="text-muted">
                                of {f["opening"]:,.2f} opening
                            </small>
                            <hr class="my-2"/>
                            <div class="d-flex justify-content-between small text-muted">
                                <span><i class="fa fa-user-circle me-1"/> {f["custodian"] or "-"}</span>
                                <span class="text-danger">
                                    <i class="fa fa-arrow-up me-1"/>
                                    {spent:,.2f} spent/mo
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            ''')
        return '<div class="row">' + '\n'.join(items) + '</div>'

    # ----- Main compute -----
    def _compute_summary(self):
        Transaction = self.env['petty.cash.transaction']
        Fund = self.env['petty.cash.fund']
        today = fields.Date.context_today(self)
        company = self.env.company
        company_currency = company.currency_id

        funds = Fund.search([
            ('state', '=', 'active'),
            ('active', '=', True),
        ])

        today_txs = Transaction.search([
            ('state', '=', 'paid'),
            ('date', '=', today),
        ])
        today_income = sum(today_txs.filtered(lambda t: t.direction == 'in').mapped('amount'))
        today_expenses = sum(today_txs.filtered(lambda t: t.direction == 'out').mapped('amount'))
        today_net = today_income - today_expenses
        today_count = len(today_txs)

        pending = Transaction.search([('state', '=', 'submitted')])

        low_balance_funds = []
        total_current = 0.0
        total_opening = 0.0
        for fund in funds:
            total_current += fund.current_balance
            total_opening += fund.opening_balance
            if fund.current_balance < fund.alert_threshold:
                low_balance_funds.append({
                    'id': fund.id,
                    'name': fund.display_name,
                    'custodian': fund.custodian_id.name or '',
                    'balance': fund.current_balance,
                    'threshold': fund.alert_threshold,
                    'currency_symbol': company_currency.symbol,
                })

        # 7-day cash flow series
        cash_flow = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            txs = Transaction.search([
                ('state', '=', 'paid'),
                ('date', '=', day),
            ])
            in_amt = sum(txs.filtered(lambda t: t.direction == 'in').mapped('amount'))
            out_amt = sum(txs.filtered(lambda t: t.direction == 'out').mapped('amount'))
            cash_flow.append({
                'date': day.isoformat(),
                'label': day.strftime('%a'),
                'in': round(in_amt, 2),
                'out': round(out_amt, 2),
                'net': round(in_amt - out_amt, 2),
            })

        # Top categories this month
        month_start = today.replace(day=1)
        month_txs = Transaction.search([
            ('state', '=', 'paid'),
            ('direction', '=', 'out'),
            ('date', '>=', month_start),
        ])
        cat_totals = {}
        for t in month_txs:
            cid = t.category_id.id or 0
            cat_totals.setdefault(cid, {
                'id': cid,
                'name': t.category_id.name or 'Uncategorised',
                'color_class': t.category_id.color_class or 'secondary',
                'total': 0.0,
                'count': 0,
            })
            cat_totals[cid]['total'] += t.amount
            cat_totals[cid]['count'] += 1
        top_categories = sorted(
            cat_totals.values(), key=lambda c: c['total'], reverse=True,
        )[:7]
        max_total = max((c['total'] for c in top_categories), default=0.0)
        for c in top_categories:
            c['total'] = round(c['total'], 2)
            c['pct'] = round(c['total'] / max_total * 100, 1) if max_total else 0.0

        # Recent transactions
        recent = Transaction.search([], limit=8, order='date desc, id desc')
        recent_payload = [{
            'id': t.id,
            'name': t.name,
            'date': t.date.isoformat() if t.date else '',
            'fund': t.fund_id.display_name or '',
            'category': t.category_id.name or '',
            'amount': t.amount,
            'currency_symbol': company_currency.symbol,
            'direction': t.direction,
            'state': t.state,
            'submitter': t.submitter_id.name or '',
            'description': t.description,
        } for t in recent]

        # ---- Approval Queue -----------------------------------------------
        # Submitted transactions, with submitter + category + fund short name.
        # Manager can click to jump straight into the form view.
        pending_all = Transaction.search(
            [('state', '=', 'submitted')], order='amount desc, date desc', limit=20,
        )
        approval_payload = [{
            'id': t.id,
            'name': t.name,
            'amount': t.amount,
            'currency_symbol': company_currency.symbol,
            'state': t.state,
            'submitter': t.submitter_id.name or '—',
            'category': t.category_id.name or '—',
            'fund_short': t.fund_id.code or t.fund_id.name or '—',
            'description': t.description or '',
        } for t in pending_all]

        # ---- Top Custodians This Month ------------------------------------
        # Cashier / custodian ranked by paid-out amount this month.
        custodian_totals = {}
        for t in month_txs:
            fund_id = t.fund_id.id
            custodian = t.fund_id.custodian_id
            if not custodian:
                continue
            key = custodian.id
            entry = custodian_totals.setdefault(key, {
                'id': custodian.id,
                'name': custodian.name,
                'count': 0,
                'spent': 0.0,
                'funds': set(),
            })
            entry['count'] += 1
            entry['spent'] += t.amount
            entry['funds'].add(fund_id)
        custodian_rows = sorted(
            [
                {'id': v['id'], 'name': v['name'],
                 'count': v['count'], 'spent': v['spent'],
                 'funds': len(v['funds'])}
                for v in custodian_totals.values()
            ],
            key=lambda r: r['spent'], reverse=True,
        )

        # ---- Monthly Budget vs Actual -------------------------------------
        Category = self.env['petty.cash.category']
        budget_cats = Category.search([('monthly_budget', '>', 0)])
        budgets = []
        for cat in budget_cats:
            cat_txs = Transaction.search([
                ('state', '=', 'paid'),
                ('direction', '=', 'out'),
                ('date', '>=', month_start),
                ('category_id', '=', cat.id),
            ])
            budgets.append({
                'name': cat.name,
                'budget': cat.monthly_budget,
                'actual': sum(cat_txs.mapped('amount')),
            })
        budgets.sort(key=lambda b: b['actual'] / max(b['budget'], 1), reverse=True)

        # Fund snapshots
        fund_payload = []
        for f in funds:
            spent = sum(
                Transaction.search([
                    ('state', '=', 'paid'),
                    ('direction', '=', 'out'),
                    ('date', '>=', month_start),
                    ('fund_id', '=', f.id),
                ]).mapped('amount')
            )
            fund_payload.append({
                'id': f.id,
                'name': f.display_name,
                'custodian': f.custodian_id.name or '',
                'opening': round(f.opening_balance, 2),
                'current': round(f.current_balance, 2),
                'spent_month': round(spent, 2),
                'color_class': f.color_class or 'secondary',
            })

        # Render the SVG / HTML payloads (server-side, no JS deps).
        cash_flow_svg = Markup(self._render_cash_flow(cash_flow, company_currency))
        top_categories_html = Markup(self._render_top_categories(top_categories, company_currency))
        recent_html = Markup(self._render_recent_transactions(recent_payload, company_currency))
        low_balance_html = Markup(self._render_low_balance(low_balance_funds))
        approval_queue_html = Markup(self._render_approval_queue(approval_payload, company_currency))
        top_custodians_html = Markup(self._render_top_custodians(custodian_rows, company_currency))
        budget_burn_html = Markup(self._render_budget_burn(budgets, company_currency))
        fund_snapshots_html = Markup(self._render_fund_snapshots(fund_payload))

        today_income = round(today_income, 2)
        today_expenses = round(today_expenses, 2)
        today_net = round(today_net, 2)

        for record in self:
            record.company_currency_id = company_currency
            record.today_income = today_income
            record.today_expenses = today_expenses
            record.today_net = today_net
            record.today_count = today_count
            record.current_balance = round(total_current, 2)
            record.opening_balance = round(total_opening, 2)
            record.pending_approvals = len(pending)
            record.low_balance_count = len(low_balance_funds)
            record.cash_flow_html = cash_flow_svg
            record.top_categories_html = top_categories_html
            record.recent_transactions_html = recent_html
            record.low_balance_html = low_balance_html
            record.approval_queue_html = approval_queue_html
            record.top_custodians_html = top_custodians_html
            record.budget_burn_html = budget_burn_html
            record.fund_snapshots_html = fund_snapshots_html
