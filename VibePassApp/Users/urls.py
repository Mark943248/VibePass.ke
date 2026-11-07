from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.RegisterView, name="register"),
    path("verify-email/", views.otp_verification_view, name="verify_email"),
    path("resend-otp/", views.resend_otp_view, name="resend_otp"),
    path("login/", views.LoginView, name="login"),
    path("logout/", views.LogoutView, name="logout"),
    path("make_organiser/", views.make_event_organiser, name="make_organiser"),
    path(
        "dashboard/Event_finder/", views.EventFindersDashboard, name="finders_dashboard"
    ),
    path(
        "dashboard/Event_organiser",
        views.EventOrganizersDashboard,
        name="organizers_dashboard",
    ),
    path("change_details/", views.ChangeUsersDetails, name="change_details"),
]
