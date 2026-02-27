from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Ticket
from Payments.models import Payment
import qrcode
import base64
from io import BytesIO

# Qr code generation view
@login_required
def create_ticket_qr(request, ticket_id):
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    if Payment.user != request.user:
        return redirect('home')  # Redirect to home if the user is not the owner of the ticket
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(str(ticket.ticket_id))
    qr.make(fit=True) # Ensure the QR code fits the data
    img = qr.make_image(fill_color="black", back_color="white") # Generate the QR code image

    buffer = BytesIO() # creates a virtual file in memory to hold the image data
    img.save(buffer, format="PNG") # save the QR code image to the buffer in PNG format
    img_str = base64.b64encode(buffer.getvalue()).decode() # encode the image data in base64 and decode it to a string for embedding in HTML
    context = {
        'ticket': ticket,
        'qr_code': img_str,
    }
    return render(request, 'tickets/tickets.html', context)


