from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Event
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone

# Create your views here.

@login_required
@user_passes_test(lambda u: u.is_organiser, login_url='login', redirect_field_name=None)
def CreateEvent(request):
    if request.method == 'POST':
        # Use .get() to prevent crashes if a field is hidden/missing
        data = request.POST
        is_free = data.get('Event_is_free') == 'on'
        
        # 1. Collect common fields
        params = {
            'Event_organiser': request.user,  # LINK THE USER!
            'Event_title': data.get('Event_title'),
            'Event_flyer': request.FILES.get('Event_flyer'),
            'Event_category': data.get('Event_category'),
            'Event_details': data.get('Event_details'),
            'Event_location': data.get('Event_location'),
            'Event_date': data.get('Event_date'),
            'Event_time': data.get('Event_time'),
            'Event_total_tickets': data.get('Event_total_tickets'),
            'Event_is_free': is_free,
        }

        # 2. Add Paid-only fields if it's NOT free
        if not is_free:
            params['Event_mpesa_number'] = data.get('Event_mpesa_number')
            params['Event_ticket_price'] = data.get('Event_ticket_price')
        else:
            params['Event_ticket_price'] = 0

        # 3. Simple Validation Check
        # Check if basic fields are present (Title, Date, etc.)
        if not all([params['Event_title'], params['Event_date']]):
            messages.error(request, 'Please fill in the required fields!')
        else:
            # 4. Create the event using the params dictionary
            Event.objects.create(**params)
            messages.success(request, 'Event created successfully!')
            return redirect('list_event')

    return render(request, 'events/create_event.html')

# list events view
def ListEvent(request):
    Events = Event.objects.all().order_by('-Event_created_at')
    paginator = Paginator(Events, 10)  # Show 10 events per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'events/list_event.html', {'page_obj': page_obj})

# search events view
def SearchEvent(request):
    query = request.GET.get('q')
    if query:
        Events = Event.objects.filter(
            Q(Event_title__icontains=query) |
            Q(Event_category__icontains=query) |
            Q(Event_details__icontains=query) |
            Q(Event_location__icontains=query)
        ).order_by('-Event_created_at')
        paginator = Paginator(Events, 10)  # Show 10 events per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        return render(request, 'events/list_event.html', {'page_obj': page_obj, 'query': query})


# filter product by category
def Filter_by_category(request, category):
    Events = Event.objects.filter(Event_category=category).order_by('-Event_created_at')
    if not Events:
        messages.error(request, f'No Events found under this {category}') 
    paginator = Paginator(Events, 10)  
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'events/list_event.html', {'page_obj':page_obj})

# filter based on time 
def Filter_by_time(request):
    now = timezone.now()
    Events = Event.objects.filter(Event_date__gte=now).order_by('-Event_created_at')
    paginator = Paginator(Events,10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'events/list_event.html', {'page_obj':page_obj})

# Event details
def EventDetails(request, slug):
    event = Event.objects.get(slug=slug)
    related_events = Event.objects.filter(
        Event_category=event.Event_category
        ).order_by('-Event_created_at').exclude(id=event.id)[:6]
    return render(request, 'events/event_details.html', {'event':event, 'related_events':related_events})

