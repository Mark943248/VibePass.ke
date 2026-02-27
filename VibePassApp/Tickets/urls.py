from django.urls import path
from . import views

urlpatterns = [
    path('ticket/<uuid:ticket_id>/', views.create_ticket_qr, name='create_ticket_qr'),
]