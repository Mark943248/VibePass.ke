from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import Group
from .models import User

# view for user registration
def RegisterView(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        # ensure fields are filled
        if not all([username, email, password]):
            messages.error(request, 'Please fill in all fields!')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken! Please choose another.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered! Please use another email.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            user.save()
            messages.success(request, 'Account Created Succesfully, Login to verify your credentials!.')
            # group assignment based on role
            if user.is_Event_Organizer():
                group = Group.objects.get(name='Event Organizers')
            else:
                group = Group.objects.get(name='Event Finders')

            user.groups.add(group)
            return redirect('login')
    return render(request, 'users/register.html')
   
# view for user login
def LoginView(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('finders_dashboard')
        else:
            messages.error(request, 'Invalid login credentials. Please try again.')
    return render(request, 'users/login.html')

# make user an event organiser
@login_required
def make_event_organiser(request):
    user = request.user
    user.is_organiser = True
    user.save()
    group = Group.objects.get(name='Event Organizers')
    user.groups.add(group)
    messages.success(request, 'Create your events here.')
    return redirect('organizers_dashboard')


# view for user logout
def LogoutView(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

# view for user dashboards
# 1. Event Finders Dashboard
@login_required
def EventFindersDashboard(request):
    user = request.user
    return render(request, 'users/Event_finder.html', {'user': user})


# 2. Event Organizers Dashboard
@login_required
@user_passes_test(lambda u: u.is_Event_Organizer(), login_url='login')
def EventOrganizersDashboard(request):
    user = request.user
    return render(request, 'users/Event_organiser.html', {'user': user}) 