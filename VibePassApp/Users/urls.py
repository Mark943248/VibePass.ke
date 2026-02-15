from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.RegisterView, name='register'),
    path('login/', views.LoginView, name='login'),
    path('logout/', views.LogoutView, name='logout'),
    path('make_organiser/', views.make_event_organiser, name='make_organiser'),
    path('dashboard/Event_finder/', views.EventFindersDashboard, name='finders_dashboard'),
    path('dashboard/Event_organiser', views.EventOrganizersDashboard, name='organizers_dashboard'),
]