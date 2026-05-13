from django.urls import path
from . import views

urlpatterns = [
    path('', views.WorkspaceListView.as_view(), name='workspace_list'),
    path('new/', views.WorkspaceCreateView.as_view(), name='workspace_create'),
    path('<int:pk>/', views.WorkspaceDetailView.as_view(), name='workspace_detail'),
    path('<int:pk>/edit/', views.WorkspaceUpdateView.as_view(), name='workspace_edit'),
    path('<int:pk>/delete/', views.WorkspaceDeleteView.as_view(), name='workspace_delete'),
    path('<int:workspace_pk>/projects/new/', views.create_project, name='project_create'),
    path('projects/<int:pk>/edit/', views.ProjectUpdateView.as_view(), name='project_edit'),
    path('projects/<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('<int:workspace_pk>/members/add/', views.add_member, name='add_member'),
    path('<int:workspace_pk>/members/remove/<int:user_id>/', views.remove_member, name='remove_member'),
    path('projects/<int:pk>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:project_pk>/templates/new/', views.PromptTemplateCreateView.as_view(), name='prompt_template_create'),
    path('templates/<int:pk>/', views.PromptTemplateDetailView.as_view(), name='prompt_template_detail'),
    path('templates/<int:pk>/edit/', views.PromptTemplateUpdateView.as_view(), name='prompt_template_edit'),
    path('templates/<int:pk>/delete/', views.PromptTemplateDeleteView.as_view(), name='prompt_template_delete'),
    path('templates/<int:template_pk>/versions/new/', views.create_prompt_version, name='prompt_version_create'),
    path('versions/<int:pk>/delete/', views.PromptVersionDeleteView.as_view(), name='prompt_version_delete'),
    path('versions/<int:version_pk>/run/', views.run_prompt_version, name='prompt_version_run'),
    path('versions/<int:version_pk>/executions/', views.ExecutionListView.as_view(), name='execution_list'),
    path('executions/<int:pk>/', views.ExecutionDetailView.as_view(), name='execution_detail'),
]
