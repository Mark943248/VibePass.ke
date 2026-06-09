from django.urls import path
from . import views

urlpatterns = [
    path('checkout/<slug:slug>/', views.checkout, name='checkout'),
    path('initiate/<slug:slug>/', views.initiate_payment, name='initiate_payment'),
    path('mpesa_callback', views.mpesa_callback, name='mpesa_callback'),
    path('check-status/<str:payment_id>/', views.check_payment_status, name='check_payment_status'),
    path('withdraw/request/', views.request_withdrawal, name='request_withdrawal'),
    path('mpesa_b2c_callback', views.mpesa_b2c_callback, name='mpesa_b2c_callback'),
    path('mpesa_b2c_timeout', views.mpesa_timeout_handler, name='mpesa_b2c_timeout_handler')
]