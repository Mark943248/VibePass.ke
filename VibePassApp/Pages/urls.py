from django.urls import path
from . import views

urlpatterns = [
    path('', views.HomePage, name='home'),
    path('contact/', views.ContactPage, name='contact'),
    path('about/', views.AboutPage, name='about'),
    path('faqs/', views.faqsPage, name='faqs')
]