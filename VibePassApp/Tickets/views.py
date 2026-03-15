import qrcode
import base64
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Payment, Ticket

@login_required
def create_ticket(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if payment.user != request.user:
        return redirect('home')
    ticket, created = Ticket.objects.get_or_create(
        payment=payment,
        event=payment.event
    )
    
    return redirect('create_ticket_qr', ticket_id=ticket.id)

@login_required
def create_ticket_qr(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    if ticket.payment.user != request.user:
        return redirect('home')
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(f"TICKET-ID: {ticket.id}") # You could also put a verification URL here
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