# VibePass Project Documentation

VibePass is a Django-based event ticketing platform that lets organizers create and manage events, sell tickets, process M-Pesa payments, generate QR-based tickets, and allow ticket validation at the event entrance.

## 1. What this project does

The platform supports three main user roles:

- Event Organizers: create events, manage ticket types, view sales, and withdraw funds.
- Event Finders: browse events, buy tickets, and view their booked tickets.
- Authorized Scanners: validate tickets at the event entrance.

## 2. Project architecture

The app is organized into Django apps:

- [VibePassApp/Pages](VibePassApp/Pages): landing pages, about/contact/FAQ pages, and scanner management helpers.
- [VibePassApp/Events](VibePassApp/Events): event creation, listing, search, filtering, ticket types, and scanner assignments.
- [VibePassApp/Tickets](VibePassApp/Tickets): ticket creation, QR generation, display, and validation.
- [VibePassApp/Payments](VibePassApp/Payments): checkout, M-Pesa STK push, callbacks, withdrawals, and WebSocket payment updates.
- [VibePassApp/Users](VibePassApp/Users): custom user model, auth-related views, and dashboards.
- [VibePassApp/VibePassApp](VibePassApp/VibePassApp): project-level settings, routing, ASGI setup, and Django configuration.

## 3. Core data models

- User: custom Django user model with organizer flag and account balance.
- Event: event details, organizer, category, location, date, time, flyer, and active status.
- TicketType: per-event ticket categories such as VIP, Regular, or Early Bird.
- Ticket: purchased ticket record attached to a user and event, with QR and scan status.
- Payment: payment attempt record used for M-Pesa checkout and status tracking.
- Withdrawal: organizer payout request sent through M-Pesa B2C.
- EventScanner: authorized person who can validate tickets for a specific event.

## 4. Main application flow

### A. Organizer creates an event
1. Organizer logs in.
2. They open the event creation screen.
3. Event details and one or more ticket types are submitted.
4. The event is saved and becomes visible in the event list.

### B. User browses and buys tickets
1. A user opens an event details page.
2. They choose ticket quantities from the available ticket types.
3. The selected cart is stored in the session as checkout data.
4. The user proceeds to checkout.

### C. Paid ticket flow
1. The checkout view validates the request and the event state.
2. A Payment record is created.
3. M-Pesa STK push is initiated.
4. The M-Pesa callback updates the payment status.
5. A payment success signal triggers automatic ticket creation.
6. QR codes are generated and uploaded via Cloudinary.

### D. Free ticket flow
1. If the event is free, the user is routed through the free-ticket booking flow.
2. Tickets are generated immediately without a payment record.
3. QR codes are created right away.

### E. Ticket scanning flow
1. An organizer or authorized scanner opens the scanner page.
2. They scan or enter a ticket ID.
3. The backend validates permissions and ticket status.
4. The ticket is marked as scanned if valid.

### F. Organizer payout flow
1. Organizer requests a withdrawal from the dashboard.
2. The app checks available balance and M-Pesa number.
3. A B2C payment request is initiated.
4. The callback updates the withdrawal status.

## 5. Key files to understand first

- [VibePassApp/manage.py](VibePassApp/manage.py): Django entry point.
- [VibePassApp/VibePassApp/settings.py](VibePassApp/VibePassApp/settings.py): project settings, installed apps, auth, media storage, and M-Pesa-related configuration.
- [VibePassApp/VibePassApp/urls.py](VibePassApp/VibePassApp/urls.py): top-level routing.
- [VibePassApp/Events/views.py](VibePassApp/Events/views.py): event CRUD and ticket selection logic.
- [VibePassApp/Tickets/views.py](VibePassApp/Tickets/views.py): ticket booking, QR generation, and validation.
- [VibePassApp/Payments/views.py](VibePassApp/Payments/views.py): payment initiation and M-Pesa callbacks.
- [VibePassApp/Tickets/signals.py](VibePassApp/Tickets/signals.py): creates tickets after a successful payment.
- [VibePassApp/Payments/consumers.py](VibePassApp/Payments/consumers.py): WebSocket consumer for live payment updates.

## 6. Local setup

1. Open the project folder:
   - `cd VibePassApp`
2. Create and activate a virtual environment.
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Create a `.env` file with the required environment variables such as:
   - `SECRET_KEY`
   - database settings
   - Cloudinary credentials
   - Google OAuth credentials
   - M-Pesa credentials
5. Run migrations:
   - `python manage.py migrate`
6. Create a superuser if needed:
   - `python manage.py createsuperuser`
7. Start the development server:
   - `python manage.py runserver`

## 7. Installing the project from GitHub on a new machine

Follow these steps if you are cloning the repository for the first time.

### 7.1 Prerequisites

Install the following on your machine:

- Python 3.10+ or the version supported by the project
- pip
- Git
- A local database server if you are not using the default development setup

### 7.2 Clone the repository

```bash
git clone <your-github-repo-url>
cd VibePass
```

### 7.3 Create a virtual environment

On Windows:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 7.4 Install dependencies

```bash
cd VibePassApp
pip install -r requirements.txt
```

### 7.5 Configure environment variables

Create a `.env` file in the project root with values similar to this:

```env
SECRET_KEY=your-secret-key
DATABASE_ENGINE=django.db.backends.sqlite3
DATABASE_NAME=db.sqlite3
DATABASE_USER=
DATABASE_PASSWORD=
DATABASE_HOST=
DATABASE_PORT=
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

> If you are using SQLite for local development, the database settings above are usually enough. For production or shared environments, use a proper database server and secure credentials.

### 7.6 Run database migrations

```bash
python manage.py migrate
```

### 7.7 Create an admin user

```bash
python manage.py createsuperuser
```

### 7.8 Start the app

```bash
python manage.py runserver
```

Then open:

- http://127.0.0.1:8000/

### 7.9 Troubleshooting common setup issues

- If Django cannot find the settings module, confirm that you are running commands from the project root and that the package name is correct.
- If migrations fail, make sure your database environment variables are correct.
- If static or media files do not load, verify your Cloudinary credentials.
- If login or Google auth does not work, check the Google OAuth settings in the environment file.

## 8. Important notes for developers

- The project uses Django’s custom User model from [VibePassApp/Users/models.py](VibePassApp/Users/models.py).
- Media files are stored through Cloudinary.
- Payment status updates are pushed in real time using WebSockets.
- The app depends on both HTTP routes and async WebSocket routes.
- The M-Pesa integration is callback-driven, so testing locally needs careful handling of callback URLs.

## 8. Suggested first debugging path

If you are new to the codebase, follow this order:

1. Read [VibePassApp/VibePassApp/urls.py](VibePassApp/VibePassApp/urls.py).
2. Review [VibePassApp/Events/views.py](VibePassApp/Events/views.py).
3. Review [VibePassApp/Tickets/views.py](VibePassApp/Tickets/views.py).
4. Review [VibePassApp/Payments/views.py](VibePassApp/Payments/views.py).
5. Trace how the payment success signal triggers ticket creation.

## 9. Summary

VibePass is essentially an event commerce platform with four connected lifecycles:

- Event management
- Ticket sales
- Payment processing
- Ticket validation

If you understand those four pieces, you can understand most of the application.
