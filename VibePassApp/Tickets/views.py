import qrcode
import base64
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from Events.models import Event
from .models import Ticket

@login_required
def book_free_ticket(request, slug):
    """Book a free ticket for an event"""
    event = get_object_or_404(Event, slug=slug)
    
    # Check if event is free
    if not event.Event_is_free:
        messages.error(request, 'This is not a free event. Please use the checkout page.')
        return redirect('event_details', slug=slug)
    
    # Check if event is still active
    if not event.Event_is_active:
        messages.error(request, 'This event is no longer active.')
        return redirect('event_details', slug=slug)
    
    # Check if user already has a ticket
    if Ticket.objects.filter(event=event, user=request.user, status__in=['active', 'scanned']).exists():
        messages.warning(request, 'You already have a ticket for this event.')
        return redirect('event_details', slug=slug)
    
    # Check if tickets are available
    if not event.has_available_tickets():
        messages.error(request, 'Sorry, all tickets for this event have been sold out.')
        return redirect('event_details', slug=slug)
    
    # Create ticket directly (no payment needed)
    ticket = Ticket.objects.create(
        event=event,
        user=request.user,
        payment=None,
        status='active'
    )
    
    messages.success(request, 'Ticket booked successfully!')
    return redirect('create_ticket_qr', ticket_id=ticket.ticket_id)

def create_ticket(request=None, payment_id=None, redirect_to_qr=True):
    """Create ticket after payment is successful"""
    from Payments.models import Payment
    
    payment = get_object_or_404(Payment, payment_id=payment_id)
    if request is not None and payment.user != request.user:
        return redirect('home')
    
    if not payment.event.has_available_tickets():
        messages.error(request, 'Sorry, all tickets for this event have been sold out.')
        return redirect('event_details', slug=payment.event.slug)

    ticket, created = Ticket.objects.get_or_create(
        payment=payment,
        event=payment.event,
        user=payment.user,
        defaults={'status': 'active'}
    )
    
    if redirect_to_qr and request is not None:
        return redirect('create_ticket_qr', ticket_id=ticket.ticket_id)
    return ticket

@login_required
def create_ticket_qr(request, ticket_id):
    """Generate and display QR code for ticket"""
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    if ticket.user != request.user:
        return redirect('home')
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(f"TICKET-ID: {ticket.ticket_id}")
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    context = {
        'ticket': ticket,
        'qr_code': img_str,
    }
    return render(request, 'tickets/tickets.html', context)