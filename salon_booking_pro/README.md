# Salon Management

Modern salon & spa management for Odoo 19.0 with a customer-facing booking
portal. Multi-branch ready. Guest booking with optional signup.

## Features

- **Back-office**: branches, service catalog (categories + services with
  duration and price), stylists with per-service skills and weekly schedule,
  full appointment lifecycle with calendar / pivot / graph views.
- **Customer portal**: multi-step booking wizard (branch → service → stylist →
  date / time → details → confirm), guest booking with email + phone, optional
  signup after confirmation, manage / cancel appointments from a secure token
  link.
- **Security**: three groups — Salon Manager (full), Salon Stylist (own
  appointments), Portal (own bookings).

## Models

- `salon.branch`
- `salon.service.category`
- `salon.service`
- `salon.stylist` (linked to `hr.employee`)
- `salon.appointment` with `salon.appointment.line`

## Portal routes

- `/salon` — home with services and branches
- `/salon/branches` — list of branches
- `/salon/branch/<id>` — branch detail
- `/salon/stylist/<id>` — stylist profile
- `/salon/book` — booking wizard
- `/salon/availability` — AJAX availability endpoint
- `/salon/appointment/<token>` — manage a booking
- `/salon/signup` — optional signup after a guest booking

## Installation

1. Add this directory to your Odoo `addons-path`.
2. Update the Apps list.
3. Install **Salon Management**.
4. Create at least one branch, some services, and one stylist before sharing
   the portal link.

## License

LGPL-3.