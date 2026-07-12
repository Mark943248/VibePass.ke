import qrcode
import json
from io import BytesIO
import cloudinary.uploader
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction, DatabaseError
from django.utils import timezone
from Events.models import Event, TicketType, EventScanner
from django.db.models import F
from .models import Ticket
import logging

logger = logging.getLogger(__name__)

# generate qr code view
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

# create free ticket view
@login_required
def book_free_ticket(request, slug):
    """Book a free ticket for an event"""
    event = get_object_or_404(Event, slug=slug)
    checkout_data = request.session.get('checkout_data')
    
    # Check if event is free
    if not event.Event_is_free:
        print("This is not a free event")
        return redirect('event_details', slug=slug)
    
    # Check if event is still active
    if not event.Event_is_active:
        messages.error(request, 'This event is no longer active.')
        return redirect('event_details', slug=slug)
    
    
    with transaction.atomic():
        try:
          for item in checkout_data['items']:
            ticket_type = TicketType.objects.select_for_update(nowait=True).get(id=item['id'])
            # Check if tickets are available
            if not ticket_type.has_available():
              messages.error(request, 'Sorry, all tickets for this event have been sold out.')
              return redirect('event_details', slug=slug)
            
            quantity = item['quantity']

            for _ in range(quantity):
                # Create ticket directly (no payment needed)
                ticket = Ticket.objects.create(
                   event=event,
                   ticket_type=ticket_type,
                   user=request.user,
                   payment=None,
                   status='active'
                )
                logger.info(f"Ticket generated {ticket}")

                  # Generate QR code immediately
                if generate_qr_code(ticket):
                   messages.success(request, 'Ticket booked successfully!')
                   return redirect('finders_dashboard')
                else:
                   messages.warning(request, 'Ticket created, but QR code generation failed.')
                   return redirect('finders_dashboard')
    
            ticket_type.sold_count = F('sold_count') + quantity
            ticket_type.save()
            logger.info(f"Updated stock for TicketType ID {item['id']}: +{quantity} sold.")
            logger.info(f"Total sold count is: {ticket_type.sold_count}")
        except DatabaseError as e:
            messages.warning(request, "The system is currently busy, please try again later!")
            logger.warning(f"Error has occured: {e}")
            redirect('event_details', slug=event.slug)
    
# create ticket view
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
    
    created_tickets = []
    try:
        with transaction.atomic():
            try:
              checkout_data = payment.checkout_data_snapshot
              for item in checkout_data['items']:
                ticket_type = TicketType.objects.select_for_update(nowait=True).get(id=item['id'])
                quantity = int(item['quantity'])

              # GUARD: Only process if the user actually requested 1 or more of this ticket type
              if quantity > 0:
                for _ in range(quantity):
                   ticket = Ticket.objects.create(
                      payment=payment,
                      ticket_type=ticket_type,
                      event=payment.event,
                      user=payment.user,
                      status='active'
                    )
                   logger.info(f"Ticket generated {ticket}")

                   # Generate QR code for the ticket
                   if generate_qr_code(ticket):
                      logger.info(f"Ticket {ticket.ticket_id} created and QR code generated for payment {payment_id}")
                   else:
                      logger.error(f"Ticket {ticket.ticket_id} created but QR code generation failed")
        
                   created_tickets.append(ticket)

                ticket_type.sold_count = F('sold_count') + quantity
                ticket_type.save()
                logger.info(f"Updated stock for TicketType ID {item['id']}: +{quantity} sold.")

              # Refresh stock objects if you need to accurately log values after using F() expressions
              if created_tickets:
                ticket_type.refresh_from_db()
                logger.info(f"Total sold count is now: {ticket_type.sold_count}")

            except DatabaseError as e:
                messages.warning(request, "The system is currently busy, please again try later!")
                logger.warning(f"Error has occurred: {e}")
                return redirect('checkout', slug=payment.event.slug)
               
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
    
    try:
        ticket = Ticket.objects.select_related('event', 'user').get(ticket_id=ticket_id)
    except Ticket.DoesNotExist:
        logger.info(f"Ticket not found: {ticket_id}")
        return JsonResponse({'status': 'Error', 'message': 'Ticket does not exist'}, status=404)
    
    event = ticket.event # gets the event associated with the ticket
    is_organiser = (event.Event_organiser == request.user) # check if the user is the organizer of the event
    is_authorized_scanner = EventScanner.objects.filter(event=event, user=request.user).exists() # check if the user is an authorized scanner for the event
    
    if not (is_organiser or is_authorized_scanner):
        logger.warning(f"Unauthorized scan attempt by user {request.user.id} for ticket {ticket_id}")
        return JsonResponse({'status': 'Error', 'message': 'You are not authorized to scan tickets for this event'}, status=403)

    # Use transaction to ensure atomicity of validation process
    with transaction.atomic():
        locked_ticket = Ticket.objects.select_for_update().get(ticket_id=ticket_id)
        if locked_ticket.status == 'cancelled':
            logger.info(f"Attempt to validate cancelled ticket: {ticket_id}")
            return JsonResponse({'status': 'Error', 'message': 'This ticket has been cancelled'}, status=400)
        elif locked_ticket.is_scanned:
            logger.info(f"Attempt to re-validate already scanned ticket: {ticket_id}")
            return JsonResponse({'status': 'Error', 'message': 'This ticket has already been scanned'}, status=400)
        
        # Mark ticket as scanned
        locked_ticket.mark_as_scanned()
        logger.info(f"Ticket validated and marked as scanned: {ticket_id}")
        return JsonResponse({'status': 'Success', 'message': 'Ticket validated successfully'}, status=200)
    
