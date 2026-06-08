import qrcode
import json
from io import BytesIO
import cloudinary.uploader
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from Events.models import Event
from .models import Ticket
import logging

logger = logging.getLogger(__name__)


def generate_qr_code(ticket):
    """Generate and upload QR code image for ticket"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(f"TICKET-ID: {ticket.ticket_id}")
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        if not ticket.ticket_qr_image:
            upload_result = cloudinary.uploader.upload(
                buffer,
                public_id=f"ticket_qr/{ticket.ticket_id}",
                format="png",
                overwrite=True,
                resource_type="image"
            )
            ticket.ticket_qr_image = upload_result['public_id']
            ticket.save()
            logger.info(f"QR code generated and uploaded for ticket {ticket.ticket_id}")
        return True
    except Exception as e:
        logger.error(f"Error generating QR code for ticket {ticket.ticket_id}: {str(e)}")
        return False


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
    
    # Generate QR code immediately
    if generate_qr_code(ticket):
        messages.success(request, 'Ticket booked successfully!')
    else:
        messages.warning(request, 'Ticket created, but QR code generation failed.')
    
    return redirect('users_tickets', ticket_id=ticket.ticket_id)


def create_ticket(request=None, payment_id=None):
    """Create ticket after payment is successful and generate QR code"""
    from Payments.models import Payment
    
    try:
        payment = Payment.objects.get(payment_id=payment_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found: {payment_id}")
        return None
    
    if request is not None and payment.user != request.user:
        return redirect('home')
    
    if not payment.event.has_available_tickets():
        if request is not None:
            messages.error(request, 'Sorry, all tickets for this event have been sold out.')
            return redirect('event_details', slug=payment.event.slug)
        logger.warning(f"No available tickets for event {payment.event.Event_title}")
        return None

    try:
        ticket, created = Ticket.objects.get_or_create(
            payment=payment,
            event=payment.event,
            user=payment.user,
            defaults={'status': 'active'}
        )
        
        # Generate QR code for the ticket
        if generate_qr_code(ticket):
            logger.info(f"Ticket {ticket.ticket_id} created and QR code generated for payment {payment_id}")
        else:
            logger.error(f"Ticket {ticket.ticket_id} created but QR code generation failed")
        
        if request is not None:
            return redirect('users_tickets', ticket_id=ticket.ticket_id)
        return ticket
    except Exception as e:
        logger.error(f"Error creating ticket for payment {payment_id}: {str(e)}")
        return None


@login_required
def create_ticket_qr(request, ticket_id):
    """Display ticket QR code (QR code should already be generated)"""
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    if ticket.user != request.user:
        return redirect('home')
    
    # If QR code doesn't exist, generate it now as fallback
    if not ticket.ticket_qr_image:
        generate_qr_code(ticket)

    return redirect('users_tickets', ticket_id=ticket.ticket_id)

@login_required
def render_users_tickets(request, ticket_id):
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    if ticket.user != request.user:
        return redirect('home')

    return render(request, 'tickets/tickets.html', {
        'ticket': ticket,
    })

# scanner page
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url='login')
def scanner_page(request):
    return render(request, 'tickets/tickets_scanner.html')

# validate ticket (mark as scanned)
@login_required
@require_POST
def validate_ticket(request):
    try:
        body = json.loads(request.body)
        ticket_id = body.get('ticket_id')
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing request body: {str(e)}")
        return JsonResponse({'error': 'Invalid request body'}, status=400)
    # Validate ticket ID
    if not ticket_id:
        logger.warning("Ticket ID is missing in request")
        return JsonResponse({'status': 'Error', 'message': 'Ticket ID is required'}, status=400)
    # Use transaction to ensure atomicity of validation process
    with transaction.atomic():
        try:
            ticket = Ticket.objects.select_for_update().get(ticket_id=ticket_id)
        except Ticket.DoesNotExist:
            logger.info(f"Ticket not found: {ticket_id}")
            return JsonResponse({'status': 'Error', 'message': 'Ticket does not exist'}, status=404)
        
        if ticket.status == 'cancelled':
            logger.info(f"Attempt to validate cancelled ticket: {ticket_id}")
            return JsonResponse({'status': 'Error', 'message': 'This ticket has been cancelled'}, status=400)
        elif ticket.is_scanned:
            logger.info(f"Attempt to re-validate already scanned ticket: {ticket_id}")
            return JsonResponse({'status': 'Error', 'message': 'This ticket has already been scanned'}, status=400)
        
        # Mark ticket as scanned
        ticket.mark_as_scanned()
        logger.info(f"Ticket validated and marked as scanned: {ticket_id}")
        return JsonResponse({'status': 'Success', 'message': 'Ticket validated successfully'}, status=200)
    
