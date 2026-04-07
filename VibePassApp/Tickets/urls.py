from django.urls import path
from . import views

urlpatterns = [
    path('event/<slug:slug>/book-free/', views.book_free_ticket, name='book_free_ticket'),
    path('ticket/<uuid:ticket_id>/', views.create_ticket_qr, name='create_ticket_qr'),
]