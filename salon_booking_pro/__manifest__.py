# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Salon Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Salon',
    'sequence': 195,
    'summary': 'Modern salon & spa booking portal with multi-branch support',
    'description': """
Salon Management
================

A complete salon & spa management module for Odoo 19.0 with a modern
customer-facing booking portal.

Back-office
-----------

- **Branches** — multiple locations, each with its own address, opening hours,
  manager and team.
- **Service catalog** — categories (Hair, Spa, Nails, Massage, Makeup, ...) and
  individual services with duration, price and per-branch availability.
- **Stylists** — staff members with the services they can perform, branch
  assignment, weekly work schedule and a public bio.
- **Appointments** — full booking lifecycle: draft → confirmed → in progress →
  done, with cancel and no-show states. Calendar view per branch / stylist.
- **Analytics** — pivot and graph views by branch, service, stylist, status.

Customer portal
---------------

- Modern, responsive booking portal with hero, category browse and stylist
  profiles.
- Multi-step booking wizard:
    1. Pick a branch
    2. Pick services (one or several, total price and duration recalculated)
    3. Pick a stylist (or "any available")
    4. Pick a date and time slot (live availability check)
    5. Enter contact details (guest booking — name, email, phone, notes)
    6. Review and confirm
- Guest booking with **optional signup** after confirmation, so the customer
  can manage / cancel their appointments later.
- Customer appointment history and cancellation through a secure token link.

Security
--------

Two employee groups and one portal group live under the *Salon Management*
application category:

- **Salon Manager** — full access to all branches, services, stylists and
  appointments.
- **Salon Stylist** — read access to the catalog, full access only to
  appointments assigned to them.
- **Portal** — customers can book services and manage their own appointments.
""",
    'depends': [
        'auth_signup',
        'hr',
        'mail',
        'portal',
    ],
    'data': [
        'security/salon_security.xml',
        'security/ir.model.access.csv',
        'data/salon_data.xml',
        'data/mail_templates.xml',
        # Actions must be defined before any view that references them via %(...)d
        'views/salon_appointment_views.xml',
        'views/salon_chair_views.xml',
        'views/salon_branch_views.xml',
        'views/salon_service_category_views.xml',
        'views/salon_service_views.xml',
        'views/salon_stylist_views.xml',
        'views/salon_menus.xml',
        'views/salon_portal_templates.xml',
    ],
    'demo': [
        'data/salon_demo.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'salon_booking_pro/static/src/css/portal.css',
            'salon_booking_pro/static/src/js/portal.js',
        ],
        'web.assets_backend': [
            'salon_booking_pro/static/src/css/chair_dashboard.css',
            'salon_booking_pro/static/src/xml/chair_dashboard.xml',
            'salon_booking_pro/static/src/js/chair_dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
    'author': 'Mostakim Jihad',
    'license': 'LGPL-3',
}