from django.urls import path
from . import views

urlpatterns = [
    path('checkout/<slug:slug>/', views.checkout, name='checkout'),
    path('initiate/<slug:slug>/', views.initiate_payment, name='initiate_payment'),
    path('mpesa_callback', views.mpesa_callback, name='mpesa_callback'),
    path('withdraw/request/', views.request_withdrawal, name='request_withdrawal'),
    path('mpesa_b2c_callback', views.mpesa_b2c_callback, name='mpesa_b2c_callback'),
    path('payment_waiting/<str:payment_id>/', views.payment_waiting, name='payment_waiting'),
    path('mpesa_b2c_timeout', views.mpesa_timeout_handler, name='mpesa_b2c_timeout_handler')
]