import difflib
import time

from django.shortcuts import render, get_object_or_404, redirect
from django.http import StreamingHttpResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, DeleteView, UpdateView
from django.urls import reverse_lazy, reverse
from django.core.paginator import Paginator
from .models import Workspace, Project, Membership, PromptTemplate, PromptVersion, Variable, Execution
from .forms import WorkspaceForm, ProjectForm, AddMemberForm, PromptTemplateForm, PromptVersionForm, PromptVersionMetaForm, RunPromptForm, VariableFormSet
from . import ollama_client
from .utils import render_prompt
from django.contrib import messages
from django.core.exceptions import PermissionDenied

@login_required
def ide_shell(request):
    """Single-page IDE shell. Sidebar and panes are populated via HTMX partials."""
    return render(request, 'ide/shell.html')


@login_required
def ide_sidebar(request):
    """HTMX partial: workspace > project > template tree, plus recent runs."""
    workspaces = (
        Workspace.objects
        .filter(members=request.user)
        .prefetch_related('projects__templates')
        .order_by('name')
    )
    recent_runs = (
        Execution.objects
        .filter(version__template__project__workspace__members=request.user)
        .select_related('version__template')
        .order_by('-created_at')[:5]
    )
    selected_template_id = _safe_int(request.GET.get('t'))
    return render(request, 'ide/_sidebar.html', {
        'workspaces': workspaces,
        'recent_runs': recent_runs,
        'selected_template_id': selected_template_id,
    })


@login_required
def ide_editor(request):
    """HTMX partial: editor pane for a selected template/version. Stub for now."""
    return render(request, 'ide/_editor.html', {})


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class WorkspaceListView(LoginRequiredMixin, ListView):
    model = Workspace
    template_name = 'ide/workspace_list.html'
    context_object_name = 'workspaces'

    def get_queryset(self):
        qs = Workspace.objects.filter(members=self.request.user)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '').strip()
        context['recent_executions'] = (
            Execution.objects
            .filter(version__template__project__workspace__members=self.request.user)
            .select_related('version__template__project__workspace')
            .order_by('-created_at')[:5]
        )
        return context

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

class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'ide/project_form.html'

    def get_queryset(self):
        return Project.objects.filter(
            workspace__membership__user=self.request.user,
            workspace__membership__role__in=['admin', 'member'],
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workspace'] = self.object.workspace
        return context

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})


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
        templates_qs = self.object.templates.all().order_by('-created_at').prefetch_related('versions')
        paginator = Paginator(templates_qs, 10)
        page = paginator.get_page(self.request.GET.get('page'))
        context['templates'] = page.object_list
        context['page_obj'] = page
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

class PromptTemplateDeleteView(LoginRequiredMixin, DeleteView):
    model = PromptTemplate
    template_name = 'ide/prompt_template_confirm_delete.html'

    def get_queryset(self):
        return PromptTemplate.objects.filter(
            project__workspace__membership__user=self.request.user,
            project__workspace__membership__role__in=['admin', 'member'],
        ).distinct()

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.project.pk})


class PromptTemplateUpdateView(LoginRequiredMixin, UpdateView):
    model = PromptTemplate
    form_class = PromptTemplateForm
    template_name = 'ide/prompt_template_form.html'

    def get_queryset(self):
        return PromptTemplate.objects.filter(
            project__workspace__membership__user=self.request.user,
            project__workspace__membership__role__in=['admin', 'member'],
        ).distinct()

    def get_success_url(self):
        return reverse('prompt_template_detail', kwargs={'pk': self.object.pk})


class PromptTemplateDetailView(LoginRequiredMixin, DetailView):
    model = PromptTemplate
    template_name = 'ide/prompt_template_detail.html'
    context_object_name = 'prompt_template'

    def get_queryset(self):
        return PromptTemplate.objects.filter(project__workspace__members=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        versions_qs = self.object.versions.all()
        paginator = Paginator(versions_qs, 10)
        page = paginator.get_page(self.request.GET.get('page'))
        context['versions'] = page.object_list
        context['page_obj'] = page
        context['latest_version'] = versions_qs.first()
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
            messages.success(request, f"Version {version.version_number} saved — set variable defaults below.")
            return redirect('prompt_version_edit', version_pk=version.pk)
    else:
        form = PromptVersionForm()
    return render(request, 'ide/prompt_version_form.html', {
        'form': form,
        'prompt_template': template,
        'ollama_models': _ollama_models_or_none(),
    })

class PromptVersionDeleteView(LoginRequiredMixin, DeleteView):
    model = PromptVersion
    template_name = 'ide/prompt_version_confirm_delete.html'

    def get_queryset(self):
        return PromptVersion.objects.filter(
            template__project__workspace__membership__user=self.request.user,
            template__project__workspace__membership__role__in=['admin', 'member'],
        ).distinct()

    def get_success_url(self):
        return reverse('prompt_template_detail', kwargs={'pk': self.object.template.pk})


def _get_runnable_version(user, version_pk):
    """Return a PromptVersion the user is allowed to run, or 404."""
    return get_object_or_404(
        PromptVersion,
        pk=version_pk,
        template__project__workspace__members=user,
    )


@login_required
def edit_prompt_version(request, version_pk):
    """Combined editor for a saved version: commit message + variable metadata.
    Version content is treated as immutable history."""
    version = get_object_or_404(
        PromptVersion,
        pk=version_pk,
        template__project__workspace__members=request.user,
    )
    membership = get_object_or_404(
        Membership,
        workspace=version.template.project.workspace,
        user=request.user,
    )
    if membership.role not in ['admin', 'member']:
        raise PermissionDenied

    if request.method == 'POST':
        meta_form = PromptVersionMetaForm(request.POST, instance=version)
        formset = VariableFormSet(request.POST, instance=version)
        if meta_form.is_valid() and formset.is_valid():
            meta_form.save()
            formset.save()
            messages.success(request, "Version saved.")
            return redirect('prompt_template_detail', pk=version.template.pk)
    else:
        meta_form = PromptVersionMetaForm(instance=version)
        formset = VariableFormSet(instance=version)
    return render(request, 'ide/prompt_version_edit.html', {
        'version': version,
        'meta_form': meta_form,
        'formset': formset,
    })


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


@login_required
def compare_versions(request, template_pk):
    template = get_object_or_404(
        PromptTemplate,
        pk=template_pk,
        project__workspace__members=request.user,
    )
    versions = list(template.versions.all())
    if len(versions) < 2:
        messages.info(request, "Need at least two versions to compare.")
        return redirect('prompt_template_detail', pk=template.pk)

    def _pick(param, default):
        try:
            pk = int(request.GET.get(param, default))
        except (TypeError, ValueError):
            return default
        return pk if any(v.pk == pk for v in versions) else default

    left_pk = _pick('left', versions[1].pk)  # older
    right_pk = _pick('right', versions[0].pk)  # newer
    left = next(v for v in versions if v.pk == left_pk)
    right = next(v for v in versions if v.pk == right_pk)

    diff_lines = list(difflib.unified_diff(
        left.content.splitlines(),
        right.content.splitlines(),
        fromfile=f"v{left.version_number}",
        tofile=f"v{right.version_number}",
        lineterm='',
    ))
    return render(request, 'ide/version_compare.html', {
        'prompt_template': template,
        'versions': versions,
        'left': left,
        'right': right,
        'diff_lines': diff_lines,
    })


@login_required
def start_streaming_run(request, version_pk):
    """POST handler: validate run form, create pending Execution, return partial
    containing the SSE container that will subscribe to execution_stream."""
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")
    version = _get_runnable_version(request.user, version_pk)
    variables = list(version.variables.all())
    form = RunPromptForm(request.POST, variables=variables)
    if not form.is_valid():
        return render(request, 'ide/prompt_version_run.html', {
            'form': form, 'version': version,
        })
    values = form.variable_values()
    execution = Execution.objects.create(
        version=version,
        user=request.user,
        input_data=values,
        status='pending',
    )
    return render(request, 'ide/_execution_stream.html', {'execution': execution})


@login_required
def execution_stream(request, pk):
    """SSE endpoint: runs Ollama, emits text chunks, finalizes the Execution."""
    execution = get_object_or_404(
        Execution,
        pk=pk,
        version__template__project__workspace__members=request.user,
    )

    def event_stream():
        if execution.status != 'pending':
            yield f"event: done\ndata: {execution.pk}\n\n"
            return
        version = execution.version
        rendered = render_prompt(version.content, execution.input_data or {})
        execution.status = 'streaming'
        execution.save(update_fields=['status'])
        started = time.monotonic()
        buffer = []
        last_chunk = None
        try:
            for chunk in ollama_client.generate_stream(
                version.model_name,
                rendered,
                options=version.model_config or None,
            ):
                text = chunk.get('response', '')
                if text:
                    buffer.append(text)
                    # SSE: a single event with one data: line per text line;
                    # the browser rejoins them with '\n'.
                    payload = '\n'.join(f"data: {line}" for line in text.split('\n'))
                    yield payload + "\n\n"
                last_chunk = chunk
                if chunk.get('done'):
                    break
            execution.output_text = ''.join(buffer)
            execution.token_usage = {
                'prompt_eval_count': (last_chunk or {}).get('prompt_eval_count'),
                'eval_count': (last_chunk or {}).get('eval_count'),
            }
            execution.status = 'success'
        except ollama_client.OllamaError as exc:
            execution.status = 'error'
            execution.error_message = str(exc)
            yield f"event: error\ndata: {exc}\n\n"
        execution.latency_ms = int((time.monotonic() - started) * 1000)
        execution.save()
        yield f"event: done\ndata: {execution.pk}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


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
def change_member_role(request, workspace_pk, user_id):
    # Only owner can change roles
    workspace = get_object_or_404(Workspace, pk=workspace_pk, owner=request.user)
    membership = get_object_or_404(Membership, workspace=workspace, user_id=user_id)
    if membership.user == workspace.owner:
        messages.error(request, "Cannot change the owner's role.")
        return redirect('workspace_detail', pk=workspace.pk)
    if request.method == 'POST':
        new_role = request.POST.get('role')
        valid_roles = {choice[0] for choice in Membership.ROLE_CHOICES}
        if new_role in valid_roles:
            membership.role = new_role
            membership.save()
            messages.success(request, f"{membership.user.username} is now {new_role}.")
        else:
            messages.error(request, "Invalid role.")
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
