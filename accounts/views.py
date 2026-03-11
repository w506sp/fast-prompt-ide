from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.decorators import login_required

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
