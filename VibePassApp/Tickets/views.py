import qrcode
import json
from io import BytesIO
import cloudinary.uploader
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .tasks import send_ticket_qr_code_to_user_task
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


def _get_checkout_items(checkout_data):
    """Return checkout items from the session when they are present and valid."""
    if not isinstance(checkout_data, dict):
        return []

    items = checkout_data.get("items") or []
    if not isinstance(items, list):
        return []

    valid_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ticket_type_id = item.get("id")
        quantity = item.get("quantity", 1)
        if ticket_type_id is None:
            continue
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        valid_items.append({"id": ticket_type_id, "quantity": quantity})

    return valid_items


# generate qr code view
def generate_qr_code(ticket):
    """Generate and upload QR code image for ticket"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(f"TICKET-ID: {ticket.ticket_id}")
        qr.make(fit=True)

        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=RadialGradiantColorMask(
                back_color=(255, 255, 255),
                center_color=(255, 107, 53),
                edge_color=(0, 201, 167),
            ),
        )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        if not ticket.ticket_qr_image:
            upload_result = cloudinary.uploader.upload(
                buffer,
                public_id=f"ticket_qr/{ticket.ticket_id}",
                format="png",
                overwrite=True,
                resource_type="image",
            )
            ticket.ticket_qr_image = upload_result["public_id"]
            ticket.save()
            logger.info(f"QR code generated and uploaded for ticket {ticket.ticket_id}")
        return True
    except Exception as e:
        logger.error(
            f"Error generating QR code for ticket {ticket.ticket_id}: {str(e)}"
        )
        return False


# create free ticket view
@login_required
def book_free_ticket(request, slug):
    """Book a free ticket for an event"""
    event = get_object_or_404(Event, slug=slug)
    checkout_data = request.session.get("checkout_data")

    # Check if event is free
    if not event.Event_is_free:
        logger.info(f"Attempt to book free ticket for non-free event: {event.slug}")
        messages.error(request, "This event is not free. Please select a paid ticket.")
        return redirect("event_details", slug=slug)

    # Check if event is still active
    if not event.Event_is_active:
        logger.info(f"Attempt to book ticket for inactive event: {event.slug}")
        messages.error(request, "This event is no longer active.")
        return redirect("event_details", slug=slug)

    items = _get_checkout_items(checkout_data)
    if not items:
        logger.warning(
            f"No valid ticket selection found in session for user {request.user.id} and event {event.slug}"
        )
        messages.error(
            request,
            "No valid ticket selection was found. Please choose a ticket first.",
        )
        return redirect("event_details", slug=slug)

    with transaction.atomic():
        try:
            created_ticket = None
            ticket_email_queued = False
            for item in items:
                ticket_type_id = item.get("id")
                if not ticket_type_id:
                    continue

                ticket_type = TicketType.objects.select_for_update(nowait=True).get(
                    id=ticket_type_id, event=event
                )
                if not ticket_type.has_available():
                    logger.warning(
                        f"Attempt to book ticket for event with no available tickets: {event.slug}"
                    )
                    messages.error(
                        request, "Sorry, all tickets for this event have been sold out."
                    )
                    return redirect("event_details", slug=slug)

                quantity = int(item.get("quantity", 1) or 1)
                if quantity <= 0:
                    continue

                for _ in range(ticket_type.group_size * quantity):
                    ticket = Ticket.objects.create(
                        event=event,
                        ticket_type=ticket_type,
                        user=request.user,
                        payment=None,
                        status="active",
                    )
                    logger.info(f"Ticket generated {ticket}")
                    created_ticket = ticket

                    if generate_qr_code(ticket):
                        logger.info(
                            f"QR code generated for free ticket {ticket.ticket_id}"
                        )
                        send_ticket_qr_code_to_user_task.delay(ticket)
                        ticket_email_queued = True
                    else:
                        logger.warning(
                            f"QR code generation failed for free ticket {ticket.ticket_id}"
                        )

                ticket_type.sold_count = F("sold_count") + quantity
                ticket_type.save()
                logger.info(
                    f"Updated stock for TicketType ID {ticket_type_id}: +{quantity} sold."
                )
                logger.info(f"Total sold count is: {ticket_type.sold_count}")

            if created_ticket is not None:
                if ticket_email_queued:
                    messages.success(
                        request,
                        "Ticket booked successfully! A copy of your ticket has been sent to your email.",
                    )
                else:
                    messages.success(request, "Ticket booked successfully!")
                return redirect("finders_dashboard")

            messages.warning(request, "No tickets were created.")
            return redirect("event_details", slug=slug)
        except DatabaseError as e:
            messages.warning(
                request, "The system is currently busy, please try again later!"
            )
            logger.warning(f"Error has occured: {e}")
            return redirect("event_details", slug=event.slug)


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
        return redirect("home")

    created_tickets = []
    try:
        with transaction.atomic():
            try:
                checkout_data = payment.checkout_data_snapshot or {}
                items = _get_checkout_items(checkout_data)
                if not items:
                    logger.warning(
                        f"No valid checkout items found for payment {payment_id}"
                    )
                    return None

                for item in items:
                    ticket_type_id = item.get("id")
                    if not ticket_type_id:
                        continue

                    ticket_type = TicketType.objects.select_for_update(nowait=True).get(
                        id=ticket_type_id, event=payment.event
                    )
                    quantity = int(item.get("quantity", 1) or 1)

                    # GUARD: Only process if the user actually requested 1 or more of this ticket type
                    if quantity > 0:
                        for _ in range(ticket_type.group_size * quantity):
                            ticket = Ticket.objects.create(
                                payment=payment,
                                ticket_type=ticket_type,
                                event=payment.event,
                                user=payment.user,
                                status="active",
                            )
                            logger.info(f"Ticket generated {ticket}")

                            # Generate QR code for the ticket
                            if generate_qr_code(ticket):
                                logger.info(
                                    f"Ticket {ticket.ticket_id} created and QR code generated for payment {payment_id}"
                                )
                                created_tickets.append(ticket)
                            else:
                                logger.error(
                                    f"Ticket {ticket.ticket_id} created but QR code generation failed"
                                )

                        ticket_type.sold_count = F("sold_count") + quantity
                        ticket_type.save()
                        logger.info(
                            f"Updated stock for TicketType ID {ticket_type_id}: +{quantity} sold."
                        )

                # Refresh stock objects if you need to accurately log values after using F() expressions
                if created_tickets:
                    ticket_type.refresh_from_db()
                    for ticket in created_tickets:
                        transaction.on_commit(
                            lambda tid=ticket.ticket_id: send_ticket_qr_code_to_user_task.delay(
                                tid
                            )
                        )
                    logger.info(f"Total sold count is now: {ticket_type.sold_count}")
                    return JsonResponse(
                        {
                            "status": "success",
                            "message": "Ticket purchased! A copy of your ticket has been sent to your email.",
                        }
                    )

            except DatabaseError as e:
                messages.warning(
                    request, "The system is currently busy, please again try later!"
                )
                logger.warning(f"Error has occurred: {e}")
                return redirect("checkout", slug=payment.event.slug)

        if request is not None and created_tickets:
            return redirect("users_tickets", ticket_id=created_tickets[-1].ticket_id)
        return created_tickets[-1] if created_tickets else None

    except Exception as e:
        logger.error(f"Error creating ticket for payment {payment_id}: {str(e)}")
        return None


@login_required
def create_ticket_qr(request, ticket_id):
    """Display ticket QR code (QR code should already be generated)"""
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    if ticket.user != request.user:
        return redirect("home")

    # If QR code doesn't exist, generate it now as fallback
    if not ticket.ticket_qr_image:
        generate_qr_code(ticket)

    return redirect("users_tickets", ticket_id=ticket.ticket_id)


@login_required
def render_users_tickets(request, ticket_id):
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    if ticket.user != request.user:
        return redirect("home")

    return render(
        request,
        "tickets/tickets.html",
        {
            "ticket": ticket,
        },
    )


# scanner page
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url="login")
def scanner_page(request):
    """Render the ticket scanner page for event organizers and authorized scanners."""
    return render(request, "tickets/tickets_scanner.html")


# validate ticket (mark as scanned)
@login_required
@require_POST
def validate_ticket(request):
    """Validate a ticket by its ID and mark it as scanned."""
    try:
        body = json.loads(request.body)
        ticket_id = body.get("ticket_id")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing request body: {str(e)}")
        return JsonResponse({"error": "Invalid request body"}, status=400)
    # Validate ticket ID
    if not ticket_id:
        logger.warning("Ticket ID is missing in request")
        return JsonResponse(
            {"status": "Error", "message": "Ticket ID is required"}, status=400
        )

    try:
        ticket = Ticket.objects.select_related("event", "user").get(ticket_id=ticket_id)
    except Ticket.DoesNotExist:
        logger.info(f"Ticket not found: {ticket_id}")
        return JsonResponse(
            {"status": "Error", "message": "Ticket does not exist"}, status=404
        )

    event = ticket.event  # gets the event associated with the ticket
    is_organiser = (
        event.Event_organiser == request.user
    )  # check if the user is the organizer of the event
    is_authorized_scanner = EventScanner.objects.filter(
        event=event, user=request.user
    ).exists()  # check if the user is an authorized scanner for the event

    if not (is_organiser or is_authorized_scanner):
        logger.warning(
            f"Unauthorized scan attempt by user {request.user.id} for ticket {ticket_id}"
        )
        return JsonResponse(
            {
                "status": "Error",
                "message": "You are not authorized to scan tickets for this event",
            },
            status=403,
        )

    # Use transaction to ensure atomicity of validation process
    with transaction.atomic():
        locked_ticket = Ticket.objects.select_for_update().get(ticket_id=ticket_id)
        if locked_ticket.status == "cancelled":
            logger.info(f"Attempt to validate cancelled ticket: {ticket_id}")
            return JsonResponse(
                {"status": "Error", "message": "This ticket has been cancelled"},
                status=400,
            )
        elif locked_ticket.is_scanned:
            logger.info(f"Attempt to re-validate already scanned ticket: {ticket_id}")
            return JsonResponse(
                {"status": "Error", "message": "This ticket has already been scanned"},
                status=400,
            )

        # Mark ticket as scanned
        locked_ticket.mark_as_scanned()
        logger.info(f"Ticket validated and marked as scanned: {ticket_id}")
        return JsonResponse(
            {"status": "Success", "message": "Ticket validated successfully"},
            status=200,
        )
