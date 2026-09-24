from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import Group
from Payments.models import Withdrawal
from Events.models import Event
from Tickets.models import Ticket
from .models import OrganizerWallet
from django.db.models import Sum
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import date
from .models import OrganizerProfile, User
from Payments.utils import format_phone_number


# view for user registration
def RegisterView(request):
    """Handle user registration by creating a new user account and assigning them to the appropriate group."""
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        password = request.POST["password"]
        # ensure fields are filled
        if not all([username, email, password]):
            messages.error(request, "Please fill in all fields!")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken! Please choose another.")
        elif User.objects.filter(email=email).exists():
            messages.error(
                request, "Email already registered! Please use another email."
            )
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            user.save()
            messages.success(
                request,
                "Account Created Succesfully, Login to verify your credentials!.",
            )
            return redirect("login")
    return render(request, "users/register.html")


# view for user login
def LoginView(request):
    """Handle user login by authenticating credentials and redirecting to the appropriate dashboard."""
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {username}!")
            return redirect("finders_dashboard")
        else:
            messages.error(request, "Invalid login credentials. Please try again.")
    return render(request, "users/login.html")


# make user an event organiser
@login_required
@require_POST
def make_event_organiser(request):
    """Make the logged-in user an event organiser and add them to the 'Event Organizers' group.
    This view updates the user's role to an event organiser and adds them to the appropriate group.
    """
    user = request.user
    mpesa_number = request.POST.get("mpesa_number", "").strip()
    formatted_mpesa_number = format_phone_number(mpesa_number)
    if not formatted_mpesa_number.startswith("254") or len(formatted_mpesa_number) != 12:
        messages.error(request, "Please enter a valid M-PESA number.")
        return redirect("finders_dashboard")

    user.mpesa_number = formatted_mpesa_number
    user.is_organiser = True
    user.save(update_fields=["mpesa_number", "is_organiser"])
    group = Group.objects.get(name="Event Organizers")
    user.groups.add(group)
    messages.success(request, "Create your events here.")
    return redirect("organizers_dashboard")


# view for user logout
def LogoutView(request):
    """Log out the user and redirect to the login page with a success message."""
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")


# view for user dashboards
# 1. Event Finders Dashboard
@login_required
def EventFindersDashboard(request):
    """Render the Event Finders dashboard with relevant events and tickets."""
    user = request.user
    today_date = timezone.now().date()
    upcoming_events = Event.objects.filter(Event_date__gt=today_date)
    tickets = Ticket.objects.filter(user=user).order_by("-created_at")
    past_events = Event.objects.filter(
        tickets__user=user,
        tickets__status="scanned",
        Event_date__lte=today_date,
    ).distinct()
    bought_tickets_events = (
        Event.objects.filter(tickets__user=user)
       .prefetch_related('tickets')
       .distinct()
    )
    context = {
        "user": user,
        "upcoming_events": upcoming_events,
        "tickets": tickets,
        "past_events": past_events,
        "bought_tickets_events": bought_tickets_events,
        "today": today_date,
    }
    return render(request, "users/Event_finder.html", context)


# 2. Event Organizers Dashboard
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url="login")
def EventOrganizersDashboard(request):
    """Render the Event Organizers dashboard with relevant statistics and event information.
    This view retrieves all events organized by the logged-in user, calculates revenue, ticket sales,
    """
    user = request.user

    # Get all events organized by the user
    events = Event.objects.filter(Event_organiser=user).order_by("-Event_created_at")
    
    # Calculate revenue for each event
    total_revenue = 0
    total_tickets_sold = 0
    total_attendees = 0

    for event in events:
        event_revenue = (
            event.payments.filter(payment_status="Completed").aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        event.revenue = event_revenue
        total_revenue += event_revenue
        total_tickets_sold += event.get_sold_tickets()
        total_attendees += event.tickets.filter(
            status__in=["active", "scanned"]
        ).count()
    organiser_wallet, created = OrganizerWallet.objects.get_or_create(organiser=user)
    balance = organiser_wallet.available_withdraw_balance
    print(f"User account balance: {balance}")
    organizer_is_verified = OrganizerProfile.objects.filter(
        user=user,
        is_verified=True,
    ).exists()

    # Get total number of active events (events in the future)
    active_events = events.filter(Event_is_active=True).count()
    flagged_events = events.filter(Event_is_flagged=True)

    # Prepare context
    context = {
        "user": user,
        "events": events,
        "balance": balance,
        "total_tickets_sold": total_tickets_sold,
        "total_attendees": total_attendees,
        "total_events": events.count(),
        "active_events": active_events,
        "organizer_is_verified": organizer_is_verified,
        "flagged_events": flagged_events,
        "today": date.today(),
    }

    return render(request, "users/Event_organiser.html", context)


# change users details
@login_required
def ChangeUsersDetails(request):
    """
    Update the logged-in user's username and email address.
    This view handles POST requests to update the user's profile information. It checks for empty fields,
    validates the uniqueness of the username, and saves the changes to the database.
    """
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        mpesa_number = request.POST.get("phone-number")

        if not all([username, email, mpesa_number]):
            messages.error(request, "Please fill in all fields!")
            return redirect("finders_dashboard")
        elif (
            User.objects.filter(username=username).exclude(id=request.user.id).exists()
        ):
            messages.error(request, "Username already taken! Please choose another.")
            return redirect("finders_dashboard")
        else:
            try:
                user = request.user
                user.username = username
                user.email = email
                user.mpesa_number = mpesa_number
                user.save(update_fields=['username', 'email', 'mpesa_number'])
                messages.success(request, "Profile updated successfully!")
            except Exception as e:
                messages.error(
                    request, f"An error occurred while updating your profile"
                )
                print(f"Error updating user profile: {e}")
    return redirect("finders_dashboard")
