from django.urls import path
from . import views

urlpatterns = [
    path(
        "event/<slug:slug>/book-free/", views.book_free_ticket, name="book_free_ticket"
    ),
    path(
        "create_ticket_qr/<uuid:ticket_id>/",
        views.create_ticket_qr,
        name="create_ticket_qr",
    ),
    path("tickets/<uuid:ticket_id>/", views.render_users_tickets, name="users_tickets"),
    path("scanner/", views.scanner_page, name="scanner"),
    path("validate/", views.validate_ticket, name="validate_ticket"),
]
