import time

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, DeleteView, UpdateView
from django.urls import reverse_lazy, reverse
from .models import Workspace, Project, Membership, PromptTemplate, PromptVersion, Variable, Execution
from .forms import WorkspaceForm, ProjectForm, AddMemberForm, PromptTemplateForm, PromptVersionForm, RunPromptForm
from . import ollama_client
from .utils import render_prompt
from django.contrib import messages
from django.core.exceptions import PermissionDenied

class WorkspaceListView(LoginRequiredMixin, ListView):
    model = Workspace
    template_name = 'ide/workspace_list.html'
    context_object_name = 'workspaces'

    def get_queryset(self):
        return Workspace.objects.filter(members=self.request.user)

class WorkspaceCreateView(LoginRequiredMixin, CreateView):
    model = Workspace
    form_class = WorkspaceForm
    template_name = 'ide/workspace_form.html'
    success_url = reverse_lazy('workspace_list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        Membership.objects.create(user=self.request.user, workspace=self.object, role='admin')
        return response

class WorkspaceDetailView(LoginRequiredMixin, DetailView):
    model = Workspace
    template_name = 'ide/workspace_detail.html'

    def get_queryset(self):
        return Workspace.objects.filter(members=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['projects'] = self.object.projects.all()
        context['memberships'] = Membership.objects.filter(workspace=self.object)
        context['member_form'] = AddMemberForm()
        
        # Rigorous check for current user's role
        current_membership = Membership.objects.get(user=self.request.user, workspace=self.object)
        context['user_role'] = current_membership.role
        context['can_manage_projects'] = current_membership.role in ['admin', 'member']
        context['is_owner'] = self.object.owner == self.request.user
        
        return context

class WorkspaceUpdateView(LoginRequiredMixin, UpdateView):
    model = Workspace
    form_class = WorkspaceForm
    template_name = 'ide/workspace_form.html'

    def get_queryset(self):
        # Only owner can edit workspace metadata
        return Workspace.objects.filter(owner=self.request.user)

    def get_success_url(self):
        return reverse('workspace_detail', kwargs={'pk': self.object.pk})

class WorkspaceDeleteView(LoginRequiredMixin, DeleteView):
    model = Workspace
    template_name = 'ide/workspace_confirm_delete.html'
    success_url = reverse_lazy('workspace_list')

    def get_queryset(self):
        # Only owner can delete workspace
        return Workspace.objects.filter(owner=self.request.user)

class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    model = Project
    template_name = 'ide/project_confirm_delete.html'

    def get_queryset(self):
        # Only admin or member of the workspace can delete projects
        return Project.objects.filter(
            workspace__membership__user=self.request.user,
            workspace__membership__role__in=['admin', 'member']
        ).distinct()

    def get_success_url(self):
        return reverse('workspace_detail', kwargs={'pk': self.object.workspace.pk})

@login_required
def create_project(request, workspace_pk):
    workspace = get_object_or_404(Workspace, pk=workspace_pk, members=request.user)
    
    # Rigid role check
    membership = get_object_or_404(Membership, workspace=workspace, user=request.user)
    if membership.role not in ['admin', 'member']:
        raise PermissionDenied("Viewers cannot create projects.")

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.workspace = workspace
            project.save()
            messages.success(request, f"Project '{project.name}' created.")
            return redirect('workspace_detail', pk=workspace.pk)
    else:
        form = ProjectForm()
    return render(request, 'ide/project_form.html', {'form': form, 'workspace': workspace})

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = 'ide/project_detail.html'

    def get_queryset(self):
        return Project.objects.filter(workspace__members=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['templates'] = self.object.templates.all().order_by('-created_at')
        membership = Membership.objects.get(user=self.request.user, workspace=self.object.workspace)
        context['can_manage'] = membership.role in ['admin', 'member']
        return context

def _ollama_models_or_none():
    """Return list of installed model names, or None if Ollama is unreachable/empty."""
    models = ollama_client.list_models()
    return models or None


class PromptTemplateCreateView(LoginRequiredMixin, CreateView):
    model = PromptTemplate
    form_class = PromptTemplateForm
    template_name = 'ide/prompt_template_form.html'

    def _get_project(self):
        return get_object_or_404(Project, pk=self.kwargs['project_pk'], workspace__members=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        project = self._get_project()
        membership = get_object_or_404(Membership, workspace=project.workspace, user=request.user)
        if membership.role not in ['admin', 'member']:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.project = self._get_project()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self._get_project()
        return context

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.project.pk})

class PromptTemplateDetailView(LoginRequiredMixin, DetailView):
    model = PromptTemplate
    template_name = 'ide/prompt_template_detail.html'
    context_object_name = 'prompt_template'

    def get_queryset(self):
        return PromptTemplate.objects.filter(project__workspace__members=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['versions'] = self.object.versions.all()
        membership = Membership.objects.get(user=self.request.user, workspace=self.object.project.workspace)
        context['can_manage'] = membership.role in ['admin', 'member']
        return context

@login_required
def create_prompt_version(request, template_pk):
    template = get_object_or_404(PromptTemplate, pk=template_pk, project__workspace__members=request.user)
    membership = get_object_or_404(Membership, workspace=template.project.workspace, user=request.user)
    if membership.role not in ['admin', 'member']:
        raise PermissionDenied

    if request.method == 'POST':
        form = PromptVersionForm(request.POST)
        if form.is_valid():
            version = form.save(commit=False)
            version.template = template
            last = template.versions.first()
            version.version_number = (last.version_number + 1) if last else 1
            version.save()
            from .utils import extract_variables
            for name in extract_variables(version.content):
                Variable.objects.get_or_create(version=version, name=name)
            messages.success(request, f"Version {version.version_number} saved.")
            return redirect('prompt_template_detail', pk=template.pk)
    else:
        form = PromptVersionForm()
    return render(request, 'ide/prompt_version_form.html', {
        'form': form,
        'prompt_template': template,
        'ollama_models': _ollama_models_or_none(),
    })

def _get_runnable_version(user, version_pk):
    """Return a PromptVersion the user is allowed to run, or 404."""
    return get_object_or_404(
        PromptVersion,
        pk=version_pk,
        template__project__workspace__members=user,
    )


@login_required
def run_prompt_version(request, version_pk):
    version = _get_runnable_version(request.user, version_pk)
    variables = list(version.variables.all())

    if request.method == 'POST':
        form = RunPromptForm(request.POST, variables=variables)
        if form.is_valid():
            values = form.variable_values()
            rendered = render_prompt(version.content, values)
            started = time.monotonic()
            execution = Execution(
                version=version,
                user=request.user,
                input_data=values,
            )
            try:
                response = ollama_client.generate(
                    version.model_name,
                    rendered,
                    options=version.model_config or None,
                )
                execution.output_text = response.get('response', '')
                execution.token_usage = {
                    'prompt_eval_count': response.get('prompt_eval_count'),
                    'eval_count': response.get('eval_count'),
                }
                execution.status = 'success'
            except ollama_client.OllamaError as exc:
                execution.status = 'error'
                execution.error_message = str(exc)
            execution.latency_ms = int((time.monotonic() - started) * 1000)
            execution.save()
            return redirect('execution_detail', pk=execution.pk)
    else:
        form = RunPromptForm(variables=variables)

    return render(request, 'ide/prompt_version_run.html', {
        'form': form,
        'version': version,
    })


class ExecutionDetailView(LoginRequiredMixin, DetailView):
    model = Execution
    template_name = 'ide/execution_detail.html'

    def get_queryset(self):
        return Execution.objects.filter(
            version__template__project__workspace__members=self.request.user,
        )


class ExecutionListView(LoginRequiredMixin, ListView):
    template_name = 'ide/execution_list.html'
    context_object_name = 'executions'
    paginate_by = 25

    def get_queryset(self):
        self.version = _get_runnable_version(self.request.user, self.kwargs['version_pk'])
        return self.version.executions.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['version'] = self.version
        return context


@login_required
def add_member(request, workspace_pk):
    # Only owner can add members
    workspace = get_object_or_404(Workspace, pk=workspace_pk, owner=request.user)
    if request.method == 'POST':
        form = AddMemberForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['username']
            role = form.cleaned_data['role']
            Membership.objects.get_or_create(user=user, workspace=workspace, defaults={'role': role})
            messages.success(request, f"User {user.username} added to workspace as {role}.")
        else:
            for error in form.errors.values():
                messages.error(request, error)
    return redirect('workspace_detail', pk=workspace.pk)

@login_required
def remove_member(request, workspace_pk, user_id):
    # Only owner can remove members
    workspace = get_object_or_404(Workspace, pk=workspace_pk, owner=request.user)
    membership = get_object_or_404(Membership, workspace=workspace, user_id=user_id)
    if membership.user != workspace.owner:
        membership.delete()
        messages.success(request, f"Member {membership.user.username} removed.")
    else:
        messages.error(request, "Cannot remove the workspace owner.")
    return redirect('workspace_detail', pk=workspace.pk)
