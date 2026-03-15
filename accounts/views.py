from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login, logout as auth_logout, get_user_model
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.decorators import login_required, user_passes_test

User = get_user_model()

def landing(request):
    return render(request, 'accounts/landing.html')

class SignUpView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'accounts/signup.html'

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        auth_logout(request)
        user.delete()
        return redirect('landing')
    return render(request, 'accounts/delete_confirm.html')

def is_superuser(user):
    return user.is_superuser

@user_passes_test(is_superuser)
def admin_dashboard(request):
    users = User.objects.all().order_by('username')
    return render(request, 'accounts/admin_dashboard.html', {'users': users})

@user_passes_test(is_superuser)
def admin_delete_user(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if target_user.is_superuser:
        return redirect('admin_dashboard')
    if request.method == 'POST':
        target_user.delete()
        return redirect('admin_dashboard')
    return render(request, 'accounts/admin_delete_confirm.html', {'target_user': target_user})
