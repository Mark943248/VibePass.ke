from django.urls import path
from . import views

urlpatterns = [
    path('ticket/<uuid:ticket_id>/', views.create_ticket_qr, name='create_ticket_qr'),
    path('create_ticket/', views.create_ticket, name='create_ticket'),
]