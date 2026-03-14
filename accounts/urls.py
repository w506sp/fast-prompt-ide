from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='landing'), name='logout'),
    path('delete/', views.delete_account, name='delete_account'),
    path('admin-tools/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-tools/delete/<int:user_id>/', views.admin_delete_user, name='admin_delete_user'),
]
