/** @odoo-module **/
/* ==========================================================================
   Salon Management — booking wizard client-side glue
   - Running total for the multi-service picker
   - Picker-style card selection (highlight checked radio/checkbox cards)

   The availability slot refresh is wired inline in the wizard template
   (salon_portal_templates.xml, step 4) because it needs values from the
   booking session — not from the DOM.
   ========================================================================== */

(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        // --- Service picker running total -----------------------------------
        const serviceCheckboxes = document.querySelectorAll(
            '.salon-service-pick .salon-checkbox'
        );
        if (serviceCheckboxes.length) {
            const totalBox = document.createElement('div');
            totalBox.className = 'salon-running-total mt-3';
            const form = serviceCheckboxes[0].closest('form');
            if (form) {
                const submitRow = form.querySelector('.mt-4');
                if (submitRow) {
                    submitRow.parentNode.insertBefore(totalBox, submitRow);
                } else {
                    form.appendChild(totalBox);
                }
            }

            const updateTotal = () => {
                const checked = [...document.querySelectorAll(
                    '.salon-service-pick .salon-checkbox:checked'
                )];
                if (!checked.length) {
                    totalBox.innerHTML = '<em>Select one or more services to continue.</em>';
                    return;
                }
                totalBox.innerHTML = checked.length + ' service' +
                    (checked.length === 1 ? '' : 's') + ' selected.';
            };
            serviceCheckboxes.forEach((cb) => cb.addEventListener('change', updateTotal));
            updateTotal();
        }
    });
})();