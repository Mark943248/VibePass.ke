from urllib import request
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from Events.models import Event, EventScanner
from Users.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

# Create your views here.

# homepage
def HomePage(request):
    """ Render the homepage with the 3 most recent events and the current date. """
    # Get the 3 most recent events
    recent_events = Event.objects.order_by('-Event_created_at')[:3]
    date_today = timezone.now().date()
    context = {
        'recent_events': recent_events,
        'today': date_today
    }
    return render(request, 'pages/index.html', context)

# contact page
def ContactPage(request):
    """ Render the contact page. """
    return render(request, 'pages/contacts.html')

# about page
def AboutPage(request):
    """ Render the about page. """
    user = request.user if request.user.is_authenticated else None
    context = {
        'user': user
    }
    return render(request, 'pages/about.html', context)

# FAQS page
def faqsPage(request):
    """ Render the FAQs page. """
    return render(request, 'pages/faqs.html')

# add scanner page
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url='login')
def add_scanner(request):
    """ Render the add scanner page for event organizers to manage their event scanners.
    This view handles both GET and POST requests. On GET, it displays the user's events and existing scanners. On POST, it processes the addition of a new scanner to an event."""
    # These load on both GET and POST requests safely
    users_events = Event.objects.filter(Event_organiser=request.user) 
    organisers_scanners = EventScanner.objects.filter(added_by=request.user).select_related('event', 'user')

    if request.method == 'POST':
        username = request.POST.get('username') 
        event_slug = request.POST.get('event_slug') 
    
        # ALL database operations must be indented INSIDE the POST block
        try:
            event = Event.objects.get(slug=event_slug, Event_organiser=request.user)
            scanner_user = User.objects.get(username=username)

            today = timezone.now().date()

            if event.Event_date < today:
                logger.warning(f"Attempt to add scanner to past event '{event.Event_title}' by {request.user.username}")
                messages.error(request, f"Cannot add scanner. The event '{event.Event_title}' has already ended.")
                return redirect('add_scanner')
            
            if not event.Event_is_active:
                logger.warning(f"Attempt to add scanner to inactive event '{event.Event_title}' by {request.user.username}")
                messages.error(request, f"Cannot add scanner. The event '{event.Event_title}' is currently inactive.")
                return redirect('add_scanner')

            if EventScanner.objects.filter(event=event, user=scanner_user).exists():
                messages.error(request, f"{scanner_user.username} is already a scanner for {event.Event_title}.")
                return redirect('add_scanner')
            else:
                # Include added_by=request.user to track accountability!
                EventScanner.objects.create(
                    event=event, 
                    user=scanner_user, 
                    added_by=request.user
                )
                logger.info(f"User {scanner_user.id} added as scanner for event {event.id} by {request.user.id}")
                messages.success(request, f"{scanner_user.username} has been added as a scanner for {event.Event_title}.")
                return redirect('add_scanner')

        except Event.DoesNotExist:
            logger.error(f"Event with slug {event_slug} not found or unauthorized access attempt by {request.user.username}")
            messages.error(request, "Event not found or you do not have permission to add scanners for this event.")
            return redirect('add_scanner') 

        except User.DoesNotExist:
            logger.error(f"User with username {username} not found when trying to add scanner for event {event_slug}")
            messages.error(request, "User not found. Please check the username and try again.")
            return redirect('add_scanner') # Added redirect here to catch user lookup failures cleanly

    # This handles the normal GET request rendering smoothly
    context = {
        'users_events': users_events,
        'organisers_scanners': organisers_scanners,                  
    }
   
    return render(request, 'pages/add_scanners.html', context=context)

# remove scanner view
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url='login')
@require_POST  
def remove_scanner(request, scanner_id):
    """ Remove a scanner from an event. 
    This view handles POST requests to delete a scanner entry. 
    It checks if the scanner exists and is associated with the logged-in user before deletion. 
    Appropriate success or error messages are displayed based on the outcome.
    """
    try:
        scanner = EventScanner.objects.select_related('user', 'event').get(scanner_id=scanner_id, added_by=request.user)

        username = scanner.user.username
        event_title = scanner.event.Event_title

        scanner.delete()

        logger.info(f"Scanner {username} removed from event {event_title} by {request.user.username}")
        messages.success(request, f"{username} has been removed as a scanner for {event_title}.")
        
    except EventScanner.DoesNotExist:
        logger.error(f"Attempt to remove non-existent or unauthorized scanner with ID {scanner_id} by {request.user.username}")
        messages.error(request, "Scanner not found or you do not have permission to remove this scanner.")
    
    return redirect('add_scanner')