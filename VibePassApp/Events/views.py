import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_POST
from .models import Event, TicketType
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone


logger = logging.getLogger(__name__)

# Create your views here.
@login_required
@user_passes_test(lambda u: u.is_organiser, login_url='login', redirect_field_name=None)
def CreateEvent(request, slug=None):
    """
    Handle both creating and editing events with multi-ticket types.
    If slug is provided, it's an edit operation; otherwise, it's a create operation.
    """
    event_instance = None
    ticket_types = []
    is_edit = False
    
    # Check if this is an edit operation
    if slug:
        is_edit = True
        try:
            event_instance = Event.objects.get(slug=slug)
            # Verify ownership - only the organizer can edit their event
            if event_instance.Event_organiser != request.user:
                messages.error(request, "Unauthorised request")
                return redirect('organizers_dashboard')
            ticket_types = event_instance.ticket_types.all()
            print(ticket_types)
        except Event.DoesNotExist:
            messages.error(request, "Event not found.")
            return redirect('list_event')
    
    if request.method == 'POST':
        data = request.POST
        is_free = data.get('Event_is_free') == 'on'

        event_data = {
            'Event_title': data.get('Event_title'),
            'Event_category': data.get('Event_category'),
            'Event_details': data.get('Event_details'),
            'Event_location': data.get('Event_location'),
            'Event_date': data.get('Event_date'),
            'Event_time': data.get('Event_time'),
            'Event_is_free': is_free,
        }

        # Only update flyer if a new one is provided
        if request.FILES.get('Event_flyer'):
            event_data['Event_flyer'] = request.FILES.get('Event_flyer')

        name = data.getlist('ticket_name[]')
        price = data.getlist('ticket_price[]')
        capacity = data.getlist('ticket_capacity[]')
        description = data.getlist('ticket_description[]')
        ticket_ids = data.getlist('ticket_id[]')

        print(f"{ticket_ids}")
        print(f"{name}")
        print(f"{price}")
        print(f"{capacity}")
        print(f"{description}")
        


        try:
            with transaction.atomic():
                if not is_free:
                    event_data['Event_mpesa_number'] = data.get('Event_mpesa_number')
                
                # Create or update event
                if event_instance:
                    # Update existing event
                    for key, value in event_data.items():
                        setattr(event_instance, key, value)
                    event_instance.save()
                    print("Event updated succesfully")
                    events = event_instance
                else:
                    # Create new event
                    event_data['Event_organiser'] = request.user
                    events = Event.objects.create(**event_data)

                # Handle ticket types - update existing and create new ones
                updated_ticket_ids = set()
                
                for idx in range(len(name)):
                    name_val = name[idx].strip() if idx < len(name) else None

                    if not name_val:
                        continue

                    # Clean price value
                    price_val = price[idx] if idx < len(price) else "0"
                    capacity_val = capacity[idx] if idx < len(capacity) else 0
                    desc_val = description[idx] if idx < len(description) else ""
                    ticket_id = ticket_ids[idx] if idx < len(ticket_ids) and ticket_ids[idx] else None
                    
                    # Clean price value
                    clean_price = 0.00 if (not price_val or str(price_val).strip() == "" or str(price_val).strip() == "0") else price_val

                    ticket_id = ticket_ids[idx] if idx < len(ticket_ids) and ticket_ids[idx] else None
                    print(ticket_id)

                    if ticket_id and ticket_id.isdigit():
                        # Update existing ticket type
                        try:
                            ticket_type = TicketType.objects.get(id=int(ticket_id), event=events)
                            ticket_type.name = name_val
                            ticket_type.price = clean_price 
                            ticket_type.capacity = capacity_val
                            ticket_type.description = desc_val
                            ticket_type.save()
                            print("Ticket types updated succesfully")
                            updated_ticket_ids.add(int(ticket_id))
                            print(updated_ticket_ids)
                        except TicketType.DoesNotExist:
                            # Create new ticket type if ID doesn't exist
                            logger.debug("Ticket does not exist")
                            new_ticket = TicketType.objects.create(
                                event=events,
                                name=name_val,
                                price=clean_price,
                                capacity=capacity_val,
                                description=desc_val
                            )
                            updated_ticket_ids.add(new_ticket.id)
                    else:
                        # Create new ticket type
                        new_ticket = TicketType.objects.create(
                            event=events,
                            name=name_val,
                            price=clean_price,
                            capacity=capacity_val,
                            description=desc_val
                        )
                        print(f"New ticket: {new_ticket}")
                        updated_ticket_ids.add(new_ticket.id)
                        

                # Delete ticket types that were removed
                if event_instance:
                    all_ticket_ids = set(events.ticket_types.values_list('id', flat=True))
                    tickets_to_delete = all_ticket_ids - updated_ticket_ids
                    TicketType.objects.filter(id__in=tickets_to_delete).delete()

                success_msg = "Event updated successfully!" if event_instance else "Event created successfully!"
                messages.success(request, success_msg)
                return redirect('list_event')

        except Exception as e:
            logger.error(f"Error {'updating' if event_instance else 'creating'} event: {e}")
            messages.error(request, f"Error {'updating' if event_instance else 'creating'} event. Please try again.")
            if event_instance:
                return redirect('edit_event', slug=event_instance.slug)
            return redirect('create_event')

    # GET request - render form
    context = {
        'is_edit': is_edit,
        'event': event_instance,
        'ticket_types': ticket_types,
    }
    return render(request, 'events/create_event.html', context)



# list events view
def ListEvent(request):
    """List all events with pagination, ordered by creation date descending."""
    Events = Event.objects.all().order_by('-Event_created_at')
    paginator = Paginator(Events, 6)  # Show 10 events per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    date_today = timezone.now().date()
    context = {
        'page_obj': page_obj,
        'today': date_today
    }
    return render(request, 'events/list_event.html', context)

# search events view
def SearchEvent(request):
    """ Search for events based on query parameters in the GET request.
    The search is performed on event title, category, details, and location.
    """
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
    """ Filter events by category and paginate the results."""
    Events = Event.objects.filter(Event_category=category).order_by('-Event_created_at')
    if not Events:
        messages.error(request, f'No Events found under this {category}') 
    paginator = Paginator(Events, 10)  
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'events/list_event.html', {'page_obj':page_obj})

# Event details
@login_required
def EventDetails(request, slug):
    """ Display the details of a specific event, including its active ticket types."""
    event = get_object_or_404(Event, slug=slug)
    ticket_types = event.ticket_types.filter(is_active=True)

    if request.method == 'POST':
        data = json.loads(request.body)
        cart = data.get('cart', {})
        logger.info(f"cart data {cart}")

        checkout_items = []
        grand_total = 0
        total_tickets_selected = 0  # Track total items across all types

        for ticket_id, quantity in cart.items():
            try:
                quantity = int(quantity)
            except (ValueError, TypeError):
                continue  # Skip if quantity data is corrupted or bad input

            # If the user didn't buy this type, ignore it and check the next one
            if quantity <= 0:
                continue 
 
            total_tickets_selected += quantity

            try:
                ticket_type = TicketType.objects.get(id=ticket_id)
            except TicketType.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Invalid ticket selection.'}, status=400)
            
            line_total = ticket_type.price * quantity
            grand_total += line_total
            
            checkout_items.append({
                'id': ticket_type.id,
                'name': ticket_type.name,
                'quantity': quantity,
                'unit_price': float(ticket_type.price),
                'line_total': float(line_total)
            })
        
        # After looping, did they actually select any tickets?
        if total_tickets_selected == 0:
            return JsonResponse({
                'success': False,
                'message': 'Please select at least one ticket before proceeding to buy!'
            }, status=400)
            
        request.session['checkout_data'] = {
            'items': checkout_items,
            'grand_total': float(grand_total)
        }

        return JsonResponse({'success': True})

    return render(request, 'events/event_details.html', {
        'event': event, 
        'ticket_types': ticket_types
    })

# delete event view
@login_required
@user_passes_test(lambda u: u.is_organiser, login_url='login', redirect_field_name=None)
def delete_event_view(request, slug):
    """Delete an event if the user is the organiser and the request method is POST."""
    event = get_object_or_404(Event, slug=slug)
    # validate if user is the organiser
    if not event.Event_organiser == request.user:
        messages.error(request, "Sorry! you aren't authorised for this action")
        return redirect('organizers_dashboard')
    # validate request method
    if request.method == 'POST':
        event.delete()
        return JsonResponse({'message': 'Deleted successfully'}, status=200)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)
