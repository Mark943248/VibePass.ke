# VibePass Developer Guide

This document describes the implementation boundaries, local development workflow, and known engineering risks of the Django application. The product-level feature overview is in the repository [README](../README.md).

## Application Structure

- `Pages`: public pages and scanner-management helpers.
- `Users`: custom user model, organizer profiles, wallets, authentication views, and dashboards.
- `Events`: events, ticket types, reports, reviews, organizer verification, and scanner assignments.
- `Tickets`: ticket creation, QR generation, email delivery, and validation.
- `Payments`: checkout, STK/B2C M-Pesa integration, escrow, withdrawals, and WebSockets.
- `VibePassApp`: settings, top-level URL routing, ASGI, WSGI, and Celery configuration.

## Important Entry Points

- [manage.py](manage.py): Django command entry point.
- [settings.py](VibePassApp/settings.py): installed apps, authentication, database, media, Channels, and security settings.
- [urls.py](VibePassApp/urls.py): top-level HTTP routes.
- [celery.py](VibePassApp/celery.py): Celery application and periodic task discovery.
- [Payments/routing.py](Payments/routing.py): WebSocket routes.
- [Payments/tasks.py](Payments/tasks.py): asynchronous payment, withdrawal, escrow, and scheduled jobs.

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

### Signals and asynchronous work

Signals connect payment success, ticket generation, event reports, and organizer verification scheduling. Celery handles:

- STK Push requests and retries.
- STK status polling and callbacks.
- B2C initiation, callbacks, and missing-callback reconciliation.
- Matured escrow release.
- Past-event deactivation.
- QR ticket email.
- Administrator notification for flagged events.

Redis is used by Celery and Django Channels. Daphne serves the ASGI application in the Docker image.

## Clone Repositry
- git clone https://github.com/Mark943248/VibePass.ke.git

## Local Development

From this directory:

```powershell
py -m venv ..\venv
..\venv\Scripts\Activate.ps1
pip install -r requirements.txt
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

Run a worker and scheduler in separate terminals:

```bash
celery -A VibePassApp worker --loglevel=info
celery -A VibePassApp beat --loglevel=info
```

The Docker workflow is:

```bash
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Compose starts web, Celery, Celery Beat, nginx, and ngrok. It does not start PostgreSQL or Redis; provide those services separately and set `DATABASE_URL` and `CELERY_BROKER_URL` accordingly.

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

## Suggested Debugging Order

1. Confirm migrations and run `python manage.py check`.
2. Read the relevant app models and URL file.
3. Trace the owning view or Celery task.
4. Follow signals and transaction boundaries.
5. Run the focused app test before the full suite.
6. For M-Pesa issues, inspect callback payloads, task logs, Redis/Celery state, and the matching payment or withdrawal row.
