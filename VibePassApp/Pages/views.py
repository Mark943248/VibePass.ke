from django.shortcuts import render
from Events.models import Event
from django.utils import timezone

# Create your views here.

# homepage
def HomePage(request):
    # Get the 3 most recent events
    recent_events = Event.objects.order_by('-Event_created_at')[:3]
    date_today = timezone.now().date()
    context = {
        'recent_events': recent_events,
        'today': date_today
    }
    return render(request, 'pages/index.html', context)

# contact page
def ContactPage(request):
    return render(request, 'pages/contacts.html')

# about page
def AboutPage(request):
    return render(request, 'pages/about.html')