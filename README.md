# VibePass

VibePass is a Django event-ticketing platform for publishing events, selling free and paid tickets, issuing QR tickets, validating entry, and paying organizers through M-Pesa.

## Product Features

### Accounts and roles

- Custom Django user model with finder and organizer accounts.
- Registration, login, logout, profile updates, and Google OAuth.
- Promotion from finder to organizer after M-Pesa number validation.
- Organizer dashboards with event, attendance, revenue, wallet, verification, and flagged-event information.
- Finder dashboards with upcoming events, purchased tickets, and scanned-ticket history.
- Organizer verification based on completed events, reviews, ratings, and report state.
- Admin two-factor authentication, django-axes login protection, and an admin honeypot route.

### Event management

- Organizer-only event creation, editing, and deletion.
- Event flyers stored through Cloudinary with a 2 MB validation limit.
- Automatic unique slug generation.
- Multiple ticket types per event, including name, description, price, capacity, group size, active state, and sold count.
- Event browsing with pagination, search, and category filters.
- Event detail pages with ticket availability and organizer ratings.
- Event reporting with duplicate prevention and automatic flagging after three unique reports.
- One review per user per event.
- Assignment and removal of event scanners.

### Tickets and entry validation

- Free-ticket booking without a payment record.
- Paid checkout for one or more ticket types.
- Capacity locking during ticket creation.
- Group-size ticket creation.
- QR code generation and Cloudinary storage.
- Ticket display restricted to the ticket owner.
- QR ticket email delivery through Celery.
- Browser scanner UI using `html5-qrcode`.
- Ticket validation restricted to the event organizer or an assigned scanner.
- Atomic prevention of duplicate scans and cancelled-ticket scans.

### Payments, wallets, and escrow

- Kenyan M-Pesa phone formatting and validation.
- Terms acceptance during paid checkout.
- Safaricom sandbox STK Push initiation and callback processing.
- Payment status polling when a callback is delayed.
- Payment-success signal that creates tickets and QR codes.
- Organizer wallet with available and pending escrow balances.
- Escrow holds created after successful payment and released after the configured maturity time.
- Reported events can freeze escrow holds.
- Organizer withdrawals through M-Pesa B2C.
- B2C callback processing, timeout reconciliation, duplicate-callback protection, and insufficient-balance reconciliation.
- Ten percent platform fee calculation.
- WebSocket updates for payment and organizer balance changes.

### Public pages

- Homepage with recent events.
- About, contact, and FAQ pages.
- Event finder and organizer dashboards.
- Admin interface for managing application data.

## Architecture

The project is split into Django apps:

- [Pages](VibePassApp/Pages): public pages and scanner-management helpers.
- [Users](VibePassApp/Users): custom user model, authentication views, wallets, profiles, and dashboards.
- [Events](VibePassApp/Events): events, ticket types, reports, reviews, verification, and scanner assignments.
- [Tickets](VibePassApp/Tickets): ticket issuance, QR generation, email delivery, and validation.
- [Payments](VibePassApp/Payments): checkout, M-Pesa STK/B2C integration, escrow, withdrawals, and WebSockets.
- [VibePassApp](VibePassApp/VibePassApp): settings, top-level URLs, ASGI, WSGI, and Celery configuration.

Important entry points:

- [manage.py](VibePassApp/manage.py)
- [settings.py](VibePassApp/VibePassApp/settings.py)
- [project URLs](VibePassApp/VibePassApp/urls.py)
- [Celery configuration](VibePassApp/VibePassApp/celery.py)
- [WebSocket routing](VibePassApp/Payments/routing.py)

## Core Models

- `Users.User`: custom `AbstractUser`, organizer flag, and M-Pesa number.
- `Users.OrganizerProfile`: organizer verification state.
- `Users.OrganizerWallet`: available withdrawal balance and pending escrow balance.
- `Events.Event`: event details, organizer, status, reports, and reviews.
- `Events.TicketType`: per-event pricing and inventory.
- `Events.EventScanner`: event-specific scanner authorization.
- `Events.ReportEvent`: moderation reports and status.
- `Events.ReviewEvent`: event reviews and ratings.
- `Tickets.Ticket`: user ticket, ticket type, QR image, payment, and scan state.
- `Payments.Payment`: checkout and M-Pesa payment state.
- `Payments.EscrowModel`: held, frozen, refunded, or released organizer funds.
- `Payments.Withdrawal`: organizer payout state and M-Pesa transaction identifiers.

## Main Workflows

### Create or edit an event

1. An organizer signs in and opens the event form.
2. The organizer enters event details and one or more ticket types.
3. The event becomes available in the event listing.
4. Editing uses the same form and supports updating, adding, and removing ticket types.
5. Ownership is checked before edits or deletion are allowed.

### Buy a ticket

1. A finder selects ticket quantities on the event detail page.
2. The cart is stored in the session and passed to checkout.
3. Free events create tickets immediately.
4. Paid events create a payment and start an M-Pesa STK Push.
5. A successful payment creates tickets, QR codes, and an escrow hold.

### Validate entry

1. The organizer or assigned scanner opens the scanner workflow.
2. A QR code or ticket ID is submitted.
3. The backend checks event authorization, ownership, ticket status, and duplicate scans.
4. A valid active ticket is marked as scanned.

### Withdraw organizer funds

1. The organizer requests the available wallet balance.
2. The app validates the M-Pesa number and blocks duplicate open withdrawals.
3. A B2C request is sent asynchronously.
4. The callback completes or reconciles the withdrawal and updates the wallet.

## Setup

### Prerequisites

- Python 3.10 or newer.
- Docker Desktop for the container workflow.
- PostgreSQL and Redis, either managed externally or provided by your own local setup.
- Cloudinary account for media storage.
- Safaricom Daraja sandbox credentials for payment testing.

### Docker workflow

The Compose file starts the web app, Celery worker, Celery Beat, nginx, and ngrok. It does **not** provision PostgreSQL or Redis, so `DATABASE_URL` and `CELERY_BROKER_URL` must point to reachable services.

```bash
cd VibePassApp
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Open `http://127.0.0.1:8000/`.

### Python workflow

```powershell
cd VibePassApp
py -m venv ..\venv
..\venv\Scripts\Activate.ps1
pip install -r requirements.txt
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

Run asynchronous services separately when not using Compose:

```bash
celery -A VibePassApp worker --loglevel=info
celery -A VibePassApp beat --loglevel=info
```

Without Celery and Redis, payment callbacks, ticket email, withdrawals, and scheduled jobs will not complete.

### Admin two-factor authentication

After creating an admin user, visit `/account/two-factor/setup/`, authenticate, scan the generated QR code, and store the generated backup codes securely.

## Environment Variables

Create an untracked `.env` file. Names used by the application include:

```env
SECRET_KEY=replace-me
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgresql://user:password@host:5432/database
CELERY_BROKER_URL=redis://host:6379/0
CLOUDINARY_CLOUD_NAME=replace-me
CLOUDINARY_API_KEY=replace-me
CLOUDINARY_API_SECRET=replace-me
GOOGLE_CLIENT_ID=replace-me
GOOGLE_CLIENT_SECRET=replace-me
MPESA_CONSUMER_KEY=replace-me
MPESA_CONSUMER_SECRET=replace-me
MPESA_SHORT_CODE=replace-me
MPESA_PASSKEY=replace-me
MPESA_CALLBACK_URL=https://public-host.example
MPESA_INITIATOR_NAME=replace-me
MPESA_INITIATOR_PASSWORD=replace-me
MPESA_B2C_SHORT_CODE=replace-me
EMAIL_HOST_USER=replace-me
EMAIL_HOST_PASSWORD=replace-me
DEFAULT_EMAIL=replace-me
NGROK_AUTHTOKEN=replace-me
PORT=8000
```

M-Pesa callbacks require a public HTTPS URL. Never commit `.env`, API keys, OAuth secrets, M-Pesa credentials, backup codes, or certificate private keys.

## Background Jobs

Celery tasks currently cover:

- Hourly deactivation of past events.
- Hourly release of matured escrow holds.
- STK Push initiation and retries.
- STK status checks and callbacks.
- B2C withdrawal initiation and callbacks.
- Withdrawal timeout reconciliation.
- QR ticket email delivery.
- Flagged-event administrator notifications.

## Tests and Checks

Run the full Django test suite from `VibePassApp`:

```powershell
py manage.py test
```

Useful checks:

```powershell
py manage.py check
py manage.py makemigrations --check --dry-run
py manage.py showmigrations
```

## Known Gaps and Follow-Up Work

These items should be addressed or verified before treating the application as production-ready:

1. Compose does not define PostgreSQL or Redis services; deployment must provide them separately.
2. Database configuration is driven by `DATABASE_URL` and currently enables SSL unconditionally, which may require adjustment for local non-SSL databases.
3. Assigned scanners can validate tickets but should be verified against the scanner page authorization flow.
4. Escrow release and report moderation should have dedicated tests for active reports, frozen holds, and already-released holds.
5. Ticket inventory should be reserved or revalidated consistently across pending payments to prevent overselling under concurrency.
6. STK callback and polling paths should have an explicit idempotency test proving that tickets and escrow are created only once.
7. Group-size capacity and sold-count units should be made consistent and tested.
8. Ticket-type sales reporting is not currently documented as a complete feature.
9. Review string rendering and moderation workflows should have regression tests.
10. Production deployment needs a security review for HTTPS, trusted origins, admin routes, callback exposure, credentials, backup codes, and certificate handling.

## Further Reading

- [Developer guide](VibePassApp/README.md)
- [Docker Compose](VibePassApp/docker-compose.yaml)
- [Dependency list](VibePassApp/requirements.txt)
- [Event models](VibePassApp/Events/models.py)
- [Payment tasks](VibePassApp/Payments/tasks.py)
