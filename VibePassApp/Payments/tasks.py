import logging
from celery import shared_task
from .signals import payment_successful
from .models import Payment, Withdrawal
from django.http import JsonResponse
from .consumers import send_payment_status_update

logger = logging.getLogger(__name__)


@shared_task()
def process_mpesa_stk_callbacks(data):
    """
    This view processes M-Pesa STK callbacks via a Celery worker.
    """

    mpesa_info = data.get('Body', {}).get('stkCallback', {})
    checkout_request_id = mpesa_info.get('CheckoutRequestID')
    result_code = mpesa_info.get('ResultCode')
    result_desc = mpesa_info.get('ResultDesc', 'Unknown error')

    if not checkout_request_id:
        logger.error("No checkout_request_id in callback")
        return None

    try:
        payment = Payment.objects.get(checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found with checkout_request_id: {checkout_request_id}")
        return None

    try:
        result_code = int(result_code)
    except (TypeError, ValueError):
        logger.warning(
            f"Unexpected ResultCode type for payment {payment.payment_id}: {result_code}"
        )
        result_code = -1

    if result_code == 0:
        payment.payment_status = 'Completed'
        items = mpesa_info.get('CallbackMetadata', {}).get('Item', [])
        receipt_number = None
        for item in items:
            if item.get('Name') == 'MpesaReceiptNumber':
                receipt_number = item.get('Value')
                break

        if receipt_number:
            payment.mpesa_receipt_number = receipt_number
        payment.save()
        logger.info(f"Payment successful for payment_id: {payment.payment_id}")
        payment_successful.send(sender=Payment, payment=payment)
        send_payment_status_update(payment)
    else:
        payment.payment_status = 'Failed'
        payment.save()
        logger.info(
            f'Payment failed for payment ID {payment.payment_id} (Result Code: {result_code}): {result_desc}'
        )
        send_payment_status_update(payment)




@shared_task()
def process_mpesa_b2c_callbacks(data):
    """
    Processes M-Pesa B2C (Business to Customer) withdrawal callback payloads 
    asynchronously to update transaction status and adjust balance records.
    """

    originator_conversation_id = data.get("Result", {}).get("OriginatorConversationID", "unknown")
    mpesa_details = data.get("Result", {})
    Result_code = mpesa_details.get("ResultCode")
    originator_conversation_id = mpesa_details.get("OriginatorConversationID")
    transaction_id = mpesa_details.get("TransactionID")
    Result_desc = mpesa_details.get("ResultDesc")

    try:
        withdrawal = Withdrawal.objects.get(originator_conversation_id=originator_conversation_id)
        
        if Result_code == 0:
            withdrawal.status = 'completed'
            withdrawal.mpesa_receipt_number = transaction_id
            withdrawal.save()
            logger.info(f'Withdrawal completed successfully: {withdrawal.withdrawal_id}')
            user_account_balance = withdrawal.organiser.account_balance
            logger.info(f"Users account balance before deduction: {user_account_balance}")
            withdrawal.organiser.account_balance = user_account_balance - withdrawal.amount
            withdrawal.organiser.save()
            logger.info(f"Users account balance after deduction: {withdrawal.organiser.account_balance}")
        else:
            withdrawal.status = 'failed'
            withdrawal.reason = Result_desc
            withdrawal.save()
            logger.error(f'Withdrawal failed: {withdrawal.withdrawal_id} - Reason: {Result_desc}')

    except Withdrawal.DoesNotExist:
        logger.error(f'Transaction does not exist: {originator_conversation_id}')
       

