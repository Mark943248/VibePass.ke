# VibePass App Developer Guide

This document explains how the Django app works and how the different modules connect together.

## Overview

VibePass is a web application for organizing and attending events. It allows organizers to publish events, define ticket types, accept payments, issue tickets, and validate them at entry.

## App structure

- Pages: public pages and helper views for organizers.
- Events: event management, search, filters, ticket type management, and scanner assignment.
- Tickets: ticket issuance, QR generation, and ticket validation.
- Payments: checkout flow, M-Pesa integration, withdrawals, and WebSocket updates.
- Users: authentication and custom user details.

## Entry points

- Start the project through [manage.py](manage.py).
- Main URL routing is defined in [VibePassApp/urls.py](VibePassApp/urls.py).
- Project settings are in [VibePassApp/settings.py](VibePassApp/settings.py).
- WebSocket routing is defined in [Payments/routing.py](Payments/routing.py) and [VibePassApp/asgi.py](VibePassApp/asgi.py).
- Docker Compose is defined in [docker-compose.yaml](docker-compose.yaml) and starts PostgreSQL, Redis, the web process, Celery, ngrok, and nginx.

## Request flow

### 1. Event creation

The organizer uses the event creation view in [Events/views.py](Events/views.py). The flow is:

1. The organizer submits event data.
2. The event is created or updated.
3. Ticket types are created or updated for that event.
4. The organizer is redirected to the event list.

The same view supports event editing when called with an event slug. Editing is restricted to the event organizer; existing ticket types are updated by ID, new types are created, and removed types are deleted.

### 2. Ticket purchase

The user browses an event and selects tickets on the event details page.

1. The selected ticket quantities are submitted as checkout data from the browser.
2. The user moves to checkout.
3. If the event is free, the free-ticket booking logic is used.
4. If the event is paid, the payment flow begins.

### 3. Paid payment flow

The payment flow is handled in [Payments/views.py](Payments/views.py):

1. Checkout form is submitted.
2. Phone number and terms are validated.
3. A Payment model instance is created.
4. A Celery worker sends and processes the M-Pesa request through Redis.
5. The public callback updates the payment status.
6. A payment-success signal triggers ticket creation.

### 4. Ticket creation and QR generation

The signal in [Tickets/signals.py](Tickets/signals.py) calls the ticket creation flow in [Tickets/views.py](Tickets/views.py).

1. Ticket records are created for each selected ticket type.
2. QR codes are generated.
3. QR images are uploaded to Cloudinary.
4. The user can later view their tickets.

### 5. Ticket validation

Authorized users use the scanner page in [Tickets/views.py](Tickets/views.py).

1. The scanner submits a ticket ID.
2. The app checks whether the user is the organizer or an authorized scanner.
3. If valid, the ticket is marked as scanned.
4. The state changes from active to scanned.

### 6. Withdrawal flow

Organizers can request payouts in [Payments/views.py](Payments/views.py).

1. The system checks the organizer balance and phone number.
2. A Withdrawal record is created.
3. A B2C request is sent to M-Pesa.
4. The callback updates the payout status.

## Important models

- [Events/models.py](Events/models.py): Event, TicketType, EventScanner
- [Tickets/models.py](Tickets/models.py): Ticket
- [Payments/models.py](Payments/models.py): Payment, Withdrawal
- [Users/models.py](Users/models.py): User

## Environment and dependencies

The app depends on Django, Channels, Cloudinary, django-allauth, django-otp, and M-Pesa integration helpers. See [requirements.txt](requirements.txt) for the dependency list.

The application reads configuration from an untracked `.env` file. Configure Django and database settings, Cloudinary credentials, Google OAuth credentials, Celery/Redis settings, and M-Pesa STK/B2C credentials. `MPESA_CALLBACK_URL` must point to a public HTTPS base URL because the callbacks are received at the payment routes. Never commit secrets, backup codes, or certificate keys.

## Running locally

From this directory:

```bash
docker compose up --build
docker compose exec VibePass_web python manage.py migrate
docker compose exec VibePass_web python manage.py createsuperuser
```

Open `http://127.0.0.1:8000/`. For a Python-only workflow, create a virtual environment, install `requirements.txt`, and run Django with PostgreSQL and Redis available separately. Start a Celery worker with:

```bash
celery -A VibePassApp worker --loglevel=info
```

Without the worker, M-Pesa STK and withdrawal tasks will not be processed.

## Developer onboarding checklist

1. Read the URL config and core views.
2. Review the event and ticket creation flow.
3. Follow the payment callback path.
4. Understand the signal-based ticket generation flow.
5. Test the scanner validation path.

## Notes

The app uses a custom user model, Cloudinary for images, and WebSockets for live payment updates. These choices affect how you debug and extend the platform.

M-Pesa integrations currently target Safaricom sandbox endpoints. STK and B2C requests retry transient HTTP failures up to three times, and B2C withdrawals deduct the platform fee before sending the payout request.
