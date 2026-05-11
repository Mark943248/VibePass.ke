import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from .models import Payment
from django.contrib.auth.models import AnonymousUser
from asgiref.sync import async_to_sync


class PaymentStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.payment_id = self.scope['url_route']['kwargs']['payment_id']
        self.room_group_name = f'payment_{self.payment_id}'

        # Check if user is authenticated
        user = self.scope.get('user', AnonymousUser())
        if user.is_anonymous:
            await self.close()
            return

        # Verify the payment belongs to the user
        payment = await self.get_payment(user)
        if not payment:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial status
        await self.send_status_update(payment)

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        # We don't expect messages from client, but could handle them here if needed
        pass

    # Receive message from room group
    async def payment_status_update(self, event):
        payment = event['payment']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': payment.payment_status,
            'message': self.get_status_message(payment.payment_status),
            'payment_id': str(payment.payment_id),
            'amount': str(payment.amount),
            'receipt_number': payment.mpesa_receipt_number or ''
        }))

    @database_sync_to_async
    def get_payment(self, user):
        try:
            return Payment.objects.get(payment_id=self.payment_id, user=user)
        except Payment.DoesNotExist:
            return None

    async def send_status_update(self, payment):
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': payment.payment_status,
            'message': self.get_status_message(payment.payment_status),
            'payment_id': str(payment.payment_id),
            'amount': str(payment.amount),
            'receipt_number': payment.mpesa_receipt_number or ''
        }))

    def get_status_message(self, status):
        if status == 'Completed':
            return "Payment successful. Your ticket is being generated."
        elif status == 'Failed':
            return "Payment failed. Please try again."
        elif status == 'Pending':
            return "Payment is being processed..."
        return ""


def send_payment_status_update(payment):
    """
    Utility function to send payment status updates via WebSocket
    """
    channel_layer = get_channel_layer()
    room_group_name = f'payment_{payment.payment_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'payment_status_update',
            'payment': payment,
        }
    )