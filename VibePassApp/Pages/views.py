from django.shortcuts import render
from Events.models import Event
from django.contrib.auth.decorators import login_required, user_passes_test
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

# FAQS page
def faqsPage(request):
    return render(request, 'pages/faqs.html')

# add scanner page
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url='login')
def add_scanner(request):
    if request.method == 'POST':
        username = request.POST.get('username') # usename
        event = request.POST.get('event') # event
        users_events = Event.objects.filter(organiser=request.user) # gets users events

        
    return render(request, 'pages/add_scanners.html')