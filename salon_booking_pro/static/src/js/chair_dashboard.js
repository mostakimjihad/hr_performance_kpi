/** @odoo-module **/
/* ==========================================================================
   Salon Management — Chair Dashboard (OWL component)
   Shows a live grid of chairs per branch with booked / in-service / available
   status. Clicking a chair opens the appointment list filtered to that chair.
   ========================================================================== */

import { Component, onWillStart, useState } from "@odoo/owl";

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

// Some Odoo builds expose the underscore translation function as `_`
// globally; in any case, import-bound alias keeps the code self-contained.
const _ = _t;

// Odoo colour palette indices for kanban color picker
const KANBAN_COLORS = [
    "#c97b84", // rose (primary brand)
    "#a85964",
    "#7c8a9a",
    "#5b6f8a",
    "#7c5b8a",
    "#8a5b7c",
    "#9e7c5b",
    "#8a825b",
    "#5b8a5b",
    "#5b8a82",
];

function todayISO() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatTime(value) {
    if (!value) return "";
    // value is a string like "2026-08-15 14:30:00"
    const t = value.split(" ")[1] || value;
    return t.slice(0, 5);
}

class ChairDashboard extends Component {
    static template = "salon_booking_pro.ChairDashboard";
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        className: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            branches: [],
            branchId: null,
            branchName: "",
            selectedDate: todayISO(),
            chairs: [],
            loading: false,
            stats: { available: 0, in_service: 0, booked: 0, total: 0 },
        });

        onWillStart(() => this._load());
    }

    // ------------------------------------------------------------------
    // Helpers exposed to the template
    // ------------------------------------------------------------------
    color_for(colorIndex) {
        if (colorIndex === undefined || colorIndex === null) return KANBAN_COLORS[0];
        return KANBAN_COLORS[colorIndex % KANBAN_COLORS.length];
    }
    image_src(b64) {
        return `data:image/png;base64,${b64}`;
    }
    format_time(dt) {
        return formatTime(dt);
    }
    customer_name(appt) {
        if (!appt) return "";
        if (appt.partner_id) {
            return appt.partner_id[1];
        }
        return appt.guest_name || _("Guest");
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async _load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "salon.chair",
                "get_dashboard_data",
                [null, this.state.selectedDate],
            );
            this.state.branches = data.branches || [];
            if (this.state.branches.length) {
                this.state.branchId = this.state.branches[0].id;
                this.state.branchName = this.state.branches[0].name;
                // Initial get_dashboard_data call was for branch_id=null
                // so it only returned the branches list — fetch chairs now
                // for the auto-selected first branch.
                await this.refresh();
            }
        } catch (err) {
            console.error("Chair dashboard load failed:", err);
            const detail = (err && err.message) ? err.message : String(err);
            this.notification.add(detail, {
                title: _t("Could not load chair data"),
                type: "danger",
                sticky: true,
            });
            this.state.chairs = [];
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        if (!this.state.branchId) return;
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "salon.chair",
                "get_dashboard_data",
                [this.state.branchId, this.state.selectedDate],
            );
            if (data && data._error) {
                this.notification.add(
                    "Server error in dashboard: " + data._error,
                    { title: _t("Dashboard error"), type: "danger", sticky: true });
            }
            if (data && data._debug) {
                console.log("Chair dashboard debug:", data._debug);
                if (data.chairs.length === 0 && data._debug.chair_count_default > 0) {
                    this.notification.add(
                        `Server returned 0 chairs but DB has ${data._debug.chair_count_default}. ` +
                        `Branch arg=${data._debug.branch_id_arg}, self_ids=${data._debug.self_ids}, ` +
                        `env context=${data._debug.env_context_keys.join(",") || "none"}.`,
                        { title: _t("Chair dashboard inconsistency"), type: "warning", sticky: true });
                }
                // Always show the counts in console for diagnostics
                console.log(
                    "Chair counts: default=%s no_active_test=%s search_read=%s for branch=%s",
                    data._debug.chair_count_default,
                    data._debug.chair_count_active_false,
                    data._debug.search_read_len,
                    data._debug.branch_id_arg,
                );
            }
            this.state.chairs = data.chairs || [];
            this._recomputeStats();
            const branch = this.state.branches.find(b => b.id === this.state.branchId);
            if (branch) {
                this.state.branchName = branch.name;
            }
        } catch (err) {
            console.error("Chair dashboard refresh failed:", err);
            const detail = (err && err.message) ? err.message : String(err);
            this.notification.add(detail, {
                title: _t("Could not load chair data"),
                type: "danger",
                sticky: true,
            });
            this.state.chairs = [];
        } finally {
            this.state.loading = false;
        }
    }

    _recomputeStats() {
        const stats = { available: 0, in_service: 0, booked: 0, total: this.state.chairs.length };
        for (const c of this.state.chairs) {
            if (c.status === "in_service") stats.in_service++;
            else if (c.status === "booked") stats.booked++;
            else stats.available++;
        }
        this.state.stats = stats;
    }

    // ------------------------------------------------------------------
    // Event handlers
    // ------------------------------------------------------------------
    onBranchChange(ev) {
        const v = parseInt(ev.target.value, 10);
        if (!isNaN(v) && v !== this.state.branchId) {
            this.state.branchId = v;
            this.refresh();
        }
    }

    onDateChange(ev) {
        this.state.selectedDate = ev.target.value || todayISO();
        this.refresh();
    }

    async openChair(chairId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: _("Chair appointments"),
            res_model: "salon.appointment",
            views: [[false, "list"], [false, "form"]],
            domain: [["chair_id", "=", chairId]],
            context: { default_chair_id: chairId },
        });
    }
}

registry.category("actions").add("salon_booking_pro.chair_dashboard", ChairDashboard);