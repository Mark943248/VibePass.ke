from django.urls import path
from . import views

urlpatterns = [
    path('creat_event/', views.CreateEvent, name='create_event'),
    path('list_event/', views.ListEvent, name='list_event'),
    path('event_details/<slug:slug>/', views.EventDetails, name='event_details'),
    path('search_event/', views.SearchEvent, name='search_event'),
    path('filter_by_category/<str:category>/', views.Filter_by_category, name='filter_by_category'),
    path('filter_by_time/', views.Filter_by_time, name='filter_by_time')
]