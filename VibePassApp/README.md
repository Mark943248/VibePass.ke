# VibePass — Buyer and Technical Handover

VibePass is a web-based event ticketing and organizer payout application built for the Kenyan market. It lets event organizers publish events and ticket inventory, buyers discover events and purchase tickets, and organizers or assigned scanners validate QR tickets at entry. Paid ticket checkout and organizer payouts are integrated with Safaricom M-Pesa.

This guide is intended for an engineering team evaluating or taking over the codebase. It summarizes the current product, technology, architecture, end-to-end flows, external dependencies, setup, and known delivery gaps. It describes the repository as implemented; it is not a claim that the included Compose setup is production-ready or that third-party accounts, credentials, data, or services transfer with the source code. The short product summary is in the repository [README](../README.md).

## Product at a Glance

### User types and capabilities

- **Finder / buyer:** register and sign in, browse and search published events, select ticket types, book free tickets or pay through M-Pesa, view owned tickets, and present QR codes at entry.
- **Organizer:** create and manage events and ticket types, view organizer dashboards, manage scanner assignments, monitor wallet and escrow balances, and request M-Pesa withdrawals.
- **Event scanner:** validate event tickets when assigned by an organizer. Validation is scoped to the event and rejects invalid, cancelled, inactive, and already-scanned tickets.
- **Administrator:** manage application records through Django Admin, with optional two-factor authentication, login-attempt protection, moderation reporting, and flagged-event notifications.

### Main product areas

- Event discovery, event and ticket-type management, finder and organizer dashboards.
- Free bookings and paid M-Pesa STK Push checkout.
- QR ticket creation, storage, email delivery, and scanner validation.
- Organizer wallet balances, escrow holds, withdrawals, and payout reconciliation.
- Event reports, reviews, organizer verification, event cancellation, and buyer refunds.
- Google OAuth and account security features.

## Technology Stack

| Area | Current implementation |
|---|---|
| Language and runtime | Python; Django 6.0.1 (use Python 3.12 or newer for Django 6) |
| Web application | Django server-rendered templates, forms/views, and Django ORM; no separate frontend build or Node package manifest |
| Browser UI | HTML, CSS, template JavaScript, Bootstrap 5 via CDN, Font Awesome via CDN, and `html5-qrcode` via CDN for scanning |
| Database | PostgreSQL through `dj-database-url` and `psycopg2-binary`; the configured database URL requires SSL |
| Asynchronous tasks | Celery 5.6 with Redis as broker and result backend |
| Realtime | Django Channels over ASGI with `channels-redis`; Daphne is the ASGI server in the image |
| Payments | Safaricom Daraja M-Pesa STK Push (buyer collections) and B2C (organizer payouts and refunds), implemented with Python `requests` |
| Media and QR assets | Cloudinary for event flyers and generated ticket QR images |
| Email | Django SMTP backend configured for Gmail SMTP; ticket, cancellation, and admin notifications are queued with Celery |
| Static assets and edge proxy | WhiteNoise for Django static files; nginx is included in Compose |
| Authentication and security packages | Django authentication, django-allauth / Google provider, django-axes, django-otp, and django-two-factor-auth |
| Local/container tooling | Docker, Docker Compose, and a pinned Python dependency list in `requirements.txt` |

The stack and exact pinned Python packages are documented in [requirements.txt](requirements.txt). Browser libraries are loaded by templates from CDNs, so browser access to those CDNs is currently part of the UI delivery path.

## Architecture

The application is a modular Django monolith. Django owns the user-facing routes, business rules, persistence, and callbacks. Celery workers execute external network calls and background work; Celery Beat enqueues recurring maintenance/reconciliation tasks. Redis is shared by Celery and Django Channels. PostgreSQL is the relational system of record; Cloudinary stores uploaded/generated media.

```text
Browser (finder / organizer / scanner / admin)
                  |
          HTTPS reverse proxy
                  |
        Django views + templates
          |       |       |
          |       |       +---- WebSockets (Django Channels / Redis)
          |       +------------ PostgreSQL (Django ORM)
          +-------------------- Redis (Celery queue)
                                     |
                     +---------------+---------------+
                     |                               |
               Celery worker                    Celery Beat
                     |                         periodic schedules
           +---------+----------+
           |         |          |
        M-Pesa   Cloudinary    SMTP
     callbacks/API  media      email
```

The diagram represents logical dependencies. In the checked-in Compose file, nginx/ngrok and the Django web container are included, but PostgreSQL and Redis must be provisioned separately.

### Django app boundaries

- `Pages`: public pages and scanner-management helpers.
- `Users`: custom user model, authentication, organizer profiles, wallets, and dashboards.
- `Events`: events, ticket types, event reports, reviews, organizer verification, and scanner assignments.
- `Tickets`: ticket records, QR ticket generation/display, email dispatch, and validation.
- `Payments`: payments, escrow, withdrawals, platform revenue/refunds, M-Pesa callbacks, WebSocket consumers, and payment tasks.
- `VibePassApp`: settings, root URL routing, ASGI/WSGI, and Celery application setup.

### Main domain records

- `Users.User` is the custom Django user; `is_organiser` distinguishes organizer accounts from finder accounts.
- `Users.OrganizerProfile` stores organizer verification state; `Users.OrganizerWallet` separates available withdrawal funds from pending escrow.
- `Events.Event` belongs to an organizer and has publication/cancellation state. `Events.TicketType` stores per-event pricing and inventory.
- `Events.EventScanner` grants event-specific scanning access. `Events.ReportEvent` and `Events.ReviewEvent` support moderation and buyer feedback.
- `Payments.Payment` represents one checkout/payment attempt. Multiple `Tickets.Ticket` records from that checkout refer to the same payment.
- `Payments.EscrowModel` tracks funds held for the organizer and their payout state.
- `Payments.Withdrawal` tracks organizer B2C payout requests and provider identifiers.
- `Payments.PlatformRefunds` tracks refund attempts and provider identifiers. A conditional unique constraint allows at most one in-progress or completed refund per payment.
- `Payments.PlatformRevenue` records platform fees collected through organizer payout flows.

## End-to-End Flows

### Buyer registration and event discovery

1. A visitor registers with a finder account or authenticates using an enabled sign-in option.
2. The buyer browses published events and views event details, ticket types, and availability.
3. Ticket selections are collected into session checkout data. The buyer's account dashboard exposes owned tickets and activity.

### Free ticket booking

1. The buyer selects a free ticket and submits the booking.
2. The ticket-creation path checks inventory and creates ticket records.
3. QR assets are generated/stored, and email delivery is queued for the buyer.

### Paid ticket checkout

1. The buyer selects ticket types and quantities; checkout data is retained for the payment callback flow.
2. The checkout validates the M-Pesa phone number and terms acceptance, checks the event and ticket availability, and creates a pending `Payment`.
3. A Celery task requests an M-Pesa STK Push. A status-check task is also scheduled in case the callback is delayed.
4. M-Pesa calls the application callback. The callback queues processing rather than performing the payment work inline.
5. On confirmed payment, the payment state is updated and the success flow creates tickets/QR assets and an escrow hold. Payment status can be surfaced to the browser through the Channels/WebSocket layer.

### Event entry and QR validation

1. The organizer assigns a scanner to the event.
2. The organizer or authorized scanner opens the scanner UI and submits a QR value or ticket identifier.
3. The server checks event authorization and ticket state, then marks a valid ticket as scanned atomically to prevent duplicate entry.

### Organizer balances and payouts

1. Successful paid checkouts create escrow records and increase the organizer's pending escrow balance.
2. Matured holds are eligible for scheduled release unless the event is under a report/dispute freeze.
3. The organizer requests a withdrawal to an M-Pesa number. A Celery task sends the B2C request.
4. Provider callbacks update the withdrawal and wallet. Missing or inconsistent callbacks are reconciled through transaction-status queries rather than assumed successful.
5. Platform fees are recorded in `PlatformRevenue`. Review the payout implementation and business rules before changing fee percentages or enabling live transactions.

### Event cancellation and buyer refunds

1. An organizer cancels an event. The transaction marks active tickets cancelled, freezes escrow holds for that event, and records the event cancellation.
2. After commit, Celery queues cancellation notifications and a refund task.
3. The refund task processes cancelled tickets tied to completed paid checkouts. Tickets from the same checkout share one payment, so the task reserves one refund for the full payment amount, not one refund per ticket.
4. A `PlatformRefunds` row is created before calling M-Pesa. The payment is locked, and the conditional uniqueness constraint prevents duplicate active refunds.
5. The worker requests an M-Pesa B2C payment to the original payer's number. Provider callback success marks the refund complete and the linked escrow refunded.
6. Delayed/time-out outcomes remain unresolved and are queried by scheduled reconciliation. Failed refunds can be retried.

This is a platform-managed workflow, not an automatic reversal by the card/payment provider: it depends on available M-Pesa credentials, worker/broker availability, public HTTPS callbacks, and operational reconciliation.

## Background Workers and Schedules

The Docker Compose configuration declares separate `celery` and `celery-beat` services:

- **Worker (`celery`)** consumes the Redis task queue: STK Push work, payment and withdrawal processing, refund initiation/reconciliation, ticket QR emails, cancellation notices, and admin alerts.
- **Scheduler (`celery-beat`)** periodically enqueues past-event/ticket cleanup, matured escrow release, B2C withdrawal callback checks, and refund status checks.
- **Redis** is required by both Celery and Django Channels, but is not a service in the current Compose file.

Run one Beat scheduler for a deployment environment; multiple Beat instances can enqueue duplicate periodic tasks unless deployment is coordinated.

## Repository Map

```text
VibePassApp/
  Events/          event, ticket-type, moderation, and scanner domain
  Pages/           public pages and scanner-management helpers
  Payments/        checkout, M-Pesa, escrow, withdrawals, and refunds
  Tickets/         ticket records, QR/email work, and validation
  Users/           accounts, profiles, wallets, and dashboards
  VibePassApp/     Django settings, root routes, ASGI/WSGI, Celery
  manage.py        Django command entry point
  Dockerfile       Python application image
  docker-compose.yaml
  requirements.txt pinned Python dependencies
```

## Important Entry Points

- [manage.py](manage.py): Django command entry point.
- [settings.py](VibePassApp/settings.py): installed apps, authentication, database, media, Channels, and security settings.
- [urls.py](VibePassApp/urls.py): top-level HTTP routes.
- [celery.py](VibePassApp/celery.py): Celery application and periodic task discovery.
- [Payments/routing.py](Payments/routing.py): WebSocket routes.
- [Payments/tasks.py](Payments/tasks.py): asynchronous payment, withdrawal, escrow, refund, and scheduled jobs.
- [Payments/models.py](Payments/models.py): payment, escrow, withdrawal, revenue, and refund records.
- [docker-compose.yaml](docker-compose.yaml): local web, worker, scheduler, nginx, and ngrok services.

## Request and Domain Flows

### Event and ticket types

`Events.views.CreateEvent` handles both creation and editing. In edit mode it verifies ownership, updates existing ticket types by ID, creates new types, and deletes removed types. Event flyers use Cloudinary storage and have a 2 MB validator. Event slugs are generated on save and made unique when titles collide.

`TicketType` stores price, capacity, group size, sold count, description, and active state. The event details page exposes active ticket types to the browser and stores selected quantities in the session for checkout.

### Tickets

Free and paid ticket creation eventually use the ticket creation logic in `Tickets`. Ticket creation locks inventory with `select_for_update()`, supports group-size quantities, generates QR codes, uploads QR images to Cloudinary, and sends ticket email asynchronously.

The scanner accepts a ticket ID or QR value. Validation checks that the user is the event organizer or an assigned scanner, rejects inactive, cancelled, or already-scanned tickets, and marks a valid ticket as scanned atomically.

### Payments and escrow

Paid checkout validates the Kenyan M-Pesa number and terms acceptance, creates a `Payment`, and dispatches an STK Push task. STK callbacks and status polling update payment state. A successful payment signal creates tickets and the escrow flow updates the organizer wallet.

`OrganizerWallet` separates `available_withdraw_balance` from `pending_escrow_balance`. `EscrowModel` tracks held, frozen, refunded, and released funds. Matured holds are released by Celery unless the event has active reports. A successful B2C callback deducts the wallet amount; an inconsistent callback that would produce a negative wallet is moved to reconciliation instead.

`PlatformRefunds` is the ledger for platform-initiated buyer refunds. When an organizer cancels an event, the cancellation transaction cancels its active tickets and freezes that event's escrow holds. After commit, it queues buyer notifications and the refund task. The worker processes cancelled tickets linked to completed payments, creates one refund for the full payment amount (multiple tickets from a checkout share one payment), then sends M-Pesa B2C funds to the original payer's phone number.

Each refund record stores the user and payment links, amount, status (`in_progress`, `completed`, or `failed`), reason, and M-Pesa conversation/transaction identifiers. The worker locks the payment and a conditional unique constraint prevents duplicate in-progress or completed refunds for the same payment. Failed refunds may be retried. A successful M-Pesa result marks the refund completed and the associated escrow refunded. Timeouts and uncertain responses remain in progress and are reconciled by querying M-Pesa; they are not treated as successful refunds.

### Signals and asynchronous work

Signals connect payment success, ticket generation, event reports, and organizer verification scheduling. Celery handles:

- STK Push requests and retries.
- STK status polling and callbacks.
- B2C initiation, callbacks, and missing-callback reconciliation.
- Matured escrow release.
- Past-event deactivation.
- QR ticket email.
- Event-cancellation email to affected buyers.
- M-Pesa refunds for cancelled tickets, refund result callbacks, and status-query reconciliation for delayed or timed-out callbacks.
- Administrator notification for flagged events.

Redis is used by Celery and Django Channels. Daphne serves the ASGI application in the Docker image.

Docker Compose runs `celery` as the queued-task worker and `celery-beat` as the periodic scheduler. Beat schedules hourly past-event cleanup and escrow release, and runs withdrawal/refund reconciliation every ten minutes. Compose does not start Redis; `CELERY_BROKER_URL` must point to a reachable broker for workers and scheduled jobs to run.

## Local Development Setup

### Prerequisites

- Python 3.12 or newer.
- PostgreSQL with a reachable SSL-enabled `DATABASE_URL`.
- Redis reachable through `CELERY_BROKER_URL`.
- Cloudinary credentials for flyer and QR media storage.
- M-Pesa Daraja sandbox credentials and a public HTTPS callback URL to test payment flows.
- SMTP credentials for email delivery.

### Clone and install

From a directory where you want the repository cloned:

```powershell
git clone https://github.com/Mark943248/VibePass.ke.git
cd VibePass.ke\VibePassApp
py -m venv ..\venv
..\venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

Create an untracked `VibePassApp\.env` with the required values described in [Configuration](#configuration), then run:

```powershell
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

Run the worker and scheduler in separate terminals for async and scheduled features:

```powershell
celery -A VibePassApp worker --loglevel=info
```

```powershell
celery -A VibePassApp beat --loglevel=info
```

### Docker Compose workflow

From `VibePassApp`, create `.env`, ensure external PostgreSQL and Redis are available, then:

```powershell
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

The web Compose command uses Django's development `runserver`; the Docker image default uses Daphne. Treat the current Compose file as a development/demo configuration, not a production deployment recipe. It also starts nginx and ngrok, which require their own configuration and a valid ngrok token.

## Configuration

The application reads an untracked `.env` file. Important variables include:

- Django: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `ADMIN_URL`, `DECOY_ADMIN`.
- Database and queue: `DATABASE_URL`, `CELERY_BROKER_URL`.
- Media: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.
- OAuth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- M-Pesa: `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORT_CODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`, `MPESA_INITIATOR_NAME`, `MPESA_INITIATOR_PASSWORD`, `MPESA_B2C_SHORT_CODE`.
- Email: `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_EMAIL`.
- Tunnel/container: `NGROK_AUTHTOKEN`, `PORT`.

M-Pesa callbacks require a public HTTPS URL. Use sandbox credentials during development. Do not commit credentials, backup codes, or certificate keys.

Third-party accounts and production credentials are not supplied by the repository. A new operator needs to provision and own its database, Redis, Cloudinary, Google OAuth, SMTP, domain/TLS, and Safaricom Daraja accounts, then configure callback URLs and allowed hosts for its environment.

## Testing and Validation

```powershell
py manage.py check
py manage.py makemigrations --check --dry-run
py manage.py test
```

Focus on the app owning the change while developing:

```powershell
py manage.py test Payments.tests
py manage.py test Events.tests
py manage.py test Tickets.tests
py manage.py test Users.tests
```

## Migration Notes

The current model state uses `OrganizerWallet` rather than `User.account_balance`, and organizer M-Pesa numbers live on `User.mpesa_number` rather than `Event.Event_mpesa_number`. Do not reintroduce those removed fields just to satisfy stale fixtures; update code and tests to the current schema.

Recent schema additions include:

- `Users.0009_organizerwallet`: organizer wallet balances.
- `Payments.0009_escrowmodel`: escrow records.
- `Payments.0010_escrowmodel_release_dates`: escrow release and completion timestamps.

## Known Engineering Gaps

- PostgreSQL and Redis are external dependencies even in the Compose workflow.
- SSL is enabled unconditionally in the database URL helper and may need a local-development setting.
- Scanner-page authorization should be tested for assigned scanners, not only organizers.
- Escrow release needs regression coverage for active reports, frozen holds, and idempotent reruns.
- Pending paid checkouts do not visibly reserve inventory for their entire payment lifetime.
- STK callback and polling paths need an explicit test proving ticket and escrow creation is idempotent.
- Group-size capacity and sold-count units should be made consistent and tested.
- Ticket-type sales reporting is not currently implemented/documented as complete.
- `ReviewEvent.__str__` and other model string methods should be covered by model tests.
- Production security requires a review of HTTPS redirects, trusted origins, admin paths, callback exposure, secrets, backup codes, and certificate handling.

### Acquisition and production-readiness checklist

Before operating the code for real customers or accepting live money, the acquiring team should:

1. Confirm code ownership, license/third-party asset terms, domain and brand rights, data/privacy obligations, and transfer of any required vendor accounts separately from the repository.
2. Provision production PostgreSQL and Redis, configure backups/restore tests, and plan migration execution and rollback.
3. Review and configure secrets, allowed hosts, trusted origins, admin routes, HTTPS/proxy behavior, logging, monitoring, and alerting for the target host.
4. Confirm Safaricom production Daraja access, callback URLs, settlement/funds availability, refund and payout reconciliation procedures, and test all callback states in a controlled environment. Payment endpoints currently reference the Safaricom sandbox in task code; live enablement requires an explicit implementation/configuration review.
5. Review fee, escrow maturity, cancellation, refund, reporting, verification, and dispute policies with the business owner; code behavior is not a substitute for customer-facing terms or legal review.
6. Load-test checkout, inventory contention, scanners, asynchronous task throughput, and callback delivery; add operational dashboards and a manual recovery procedure for stuck payments/refunds.
7. Replace the demo-oriented Compose setup with a production deployment: ASGI server, managed secrets, secure reverse proxy, dedicated worker and single scheduler, health checks, process supervision, static/media strategy, and no development bind mounts/runserver.
8. Complete focused and end-to-end tests for callbacks, idempotency, payment/refund failure paths, wallet accounting, event cancellation, and permissions before launch.

The repository provides an application foundation and working integration paths, but production readiness depends on that diligence and environment-specific work.

## Suggested Debugging Order

1. Confirm migrations and run `python manage.py check`.
2. Read the relevant app models and URL file.
3. Trace the owning view or Celery task.
4. Follow signals and transaction boundaries.
5. Run the focused app test before the full suite.
6. For M-Pesa issues, inspect callback payloads, task logs, Redis/Celery state, and the matching payment or withdrawal row.
