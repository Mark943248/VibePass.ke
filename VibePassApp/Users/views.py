from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import Group
from Events.models import Event
from Tickets.models import Ticket
from django.db.models import Sum
from datetime import date
from .models import User

# view for user registration
def RegisterView(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        # ensure fields are filled
        if not all([username, email, password]):
            messages.error(request, 'Please fill in all fields!')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken! Please choose another.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered! Please use another email.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            user.save()
            messages.success(request, 'Account Created Succesfully, Login to verify your credentials!.')
            # group assignment based on role
            if user.is_Event_Organizer():
                group = Group.objects.get(name='Event Organizers')
            else:
                group = Group.objects.get(name='Event Finders')

            user.groups.add(group)
            return redirect('login')
    return render(request, 'users/register.html')
   
# view for user login
def LoginView(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('finders_dashboard')
        else:
            messages.error(request, 'Invalid login credentials. Please try again.')
    return render(request, 'users/login.html')

# make user an event organiser
@login_required
def make_event_organiser(request):
    user = request.user
    user.is_organiser = True
    user.save()
    group = Group.objects.get(name='Event Organizers')
    user.groups.add(group)
    messages.success(request, 'Create your events here.')
    return redirect('organizers_dashboard')


# view for user logout
def LogoutView(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

# view for user dashboards
# 1. Event Finders Dashboard
@login_required
def EventFindersDashboard(request):
    user = request.user
    events = Event.objects.order_by('-Event_created_at')[:4]
    tickets = Ticket.objects.filter(user=user).order_by('-created_at')
    return render(request, 'users/Event_finder.html', {'user': user, 'events': events, 'tickets': tickets})


# 2. Event Organizers Dashboard
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url='login')
def EventOrganizersDashboard(request):
    user = request.user
    
    # Get all events organized by the user
    events = Event.objects.filter(Event_organiser=user).order_by('-Event_created_at')
    
    # Calculate revenue for each event
    total_revenue = 0
    total_tickets_sold = 0
    total_attendees = 0
    account_balance = user.account_balance
    
    for event in events:
        event_revenue = event.payments.filter(payment_status='Completed').aggregate(total=Sum('amount'))['total'] or 0
        event.revenue = event_revenue
        total_revenue += event_revenue
        total_tickets_sold += event.get_sold_tickets()
        total_attendees += event.tickets.filter(status__in=['active', 'scanned']).count()
    
    # Subtract only the latest withdrawal that is pending, processing, or completed
    latest_withdrawal = user.withdrawals.filter(status__in=['pending', 'processing', 'completed']).order_by('-created_at').first()
    total_withdrawn = latest_withdrawal.amount if latest_withdrawal else 0
    account_balance = total_revenue - total_withdrawn
    if account_balance < 0:
        account_balance = 0
    user.account_balance = account_balance
    user.save(update_fields=['account_balance'])
    
    # Get total number of active events (events in the future)
    active_events = events.filter(Event_is_active=True).count()
    
    # Prepare context
    context = {
        'user': user,
        'events': events,
        'total_tickets_sold': total_tickets_sold,
        'total_attendees': total_attendees,
        'total_events': events.count(),
        'active_events': active_events,
        'today': date.today(),
        'account_balance': account_balance,
        'total_withdrawn': total_withdrawn,
    }
    
    return render(request, 'users/Event_organiser.html', context) 

# change users details
@login_required
def ChangeUsersDetails(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
       
        if not all([username, email]):
            messages.error(request, 'Please fill in all fields!')
            return redirect('finders_dashboard')
        elif User.objects.filter(username=username).exclude(id=request.user.id).exists():
            messages.error(request, 'Username already taken! Please choose another.')
            return redirect('finders_dashboard')
        else:
            try:
                user = request.user
                user.username = username
                user.email = email
                user.save()
                messages.success(request, 'Profile updated successfully!')
            except Exception as e:
                messages.error(request, f'An error occurred while updating your profile')
                print(f'Error updating user profile: {e}')
    return redirect('finders_dashboard')

    

