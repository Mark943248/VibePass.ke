from django.urls import path
from . import views

urlpatterns = [
    path('initiate/<slug:slug>/', views.initiate_payment, name='initiate_payment'),
    path('mpesa_callback', views.mpesa_callback, name='mpesa_callback'),
    path('check-status/<str:payment_id>/', views.check_payment_status, name='check_payment_status'),
]