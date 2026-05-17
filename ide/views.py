import difflib
import time

from django.shortcuts import render, get_object_or_404, redirect
from django.http import StreamingHttpResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, DeleteView, UpdateView
from django.urls import reverse_lazy, reverse
from django.core.paginator import Paginator
from .models import Workspace, Project, Membership, PromptTemplate, PromptVersion, Variable, Execution, Favorite
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
    favorite_ids = set(
        Favorite.objects.filter(user=request.user).values_list('template_id', flat=True)
    )
    return render(request, 'ide/_sidebar.html', {
        'workspaces': workspaces,
        'recent_runs': recent_runs,
        'selected_template_id': selected_template_id,
        'favorite_ids': favorite_ids,
    })


@login_required
def ide_editor(request):
    """HTMX partial: editor pane for a selected template, optionally a specific version.
    If ?diff=<other_version_pk> is provided, render a unified diff against `selected`."""
    template_id = _safe_int(request.GET.get('t'))
    if template_id is None:
        return render(request, 'ide/_editor.html', {})
    template = get_object_or_404(
        PromptTemplate,
        pk=template_id,
        project__workspace__members=request.user,
    )
    versions = list(template.versions.all())
    version_id = _safe_int(request.GET.get('v'))
    selected = next((v for v in versions if v.pk == version_id), None) or (versions[0] if versions else None)
    membership = Membership.objects.get(
        user=request.user, workspace=template.project.workspace,
    )

    diff_lines = None
    diff_against = None
    diff_id = _safe_int(request.GET.get('diff'))
    if diff_id and selected:
        diff_against = next((v for v in versions if v.pk == diff_id and v.pk != selected.pk), None)
        if diff_against:
            old, new = sorted([diff_against, selected], key=lambda v: v.version_number)
            diff_lines = list(difflib.unified_diff(
                old.content.splitlines(),
                new.content.splitlines(),
                fromfile=f"v{old.version_number}",
                tofile=f"v{new.version_number}",
                lineterm='',
            ))

    return render(request, 'ide/_editor.html', {
        'prompt_template': template,
        'versions': versions,
        'selected': selected,
        'can_manage': membership.role in ['admin', 'member'],
        'diff_against': diff_against,
        'diff_lines': diff_lines,
    })


@login_required
def toggle_favorite(request, template_pk):
    """POST-only: toggle the current user's favorite for this template."""
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")
    template = get_object_or_404(
        PromptTemplate, pk=template_pk, project__workspace__members=request.user,
    )
    fav, created = Favorite.objects.get_or_create(user=request.user, template=template)
    if not created:
        fav.delete()
        is_fav = False
    else:
        is_fav = True
    # Return a fresh star button so HTMX can swap it in place.
    from django.http import HttpResponse
    star = '★' if is_fav else '☆'
    return HttpResponse(
        f'<button type="button" class="star-btn{" is-fav" if is_fav else ""}"'
        f' hx-post="/ide/templates/{template.pk}/favorite/"'
        f' hx-swap="outerHTML"'
        f' title="{"unfavorite" if is_fav else "favorite"}">{star}</button>'
    )


@login_required
def ide_palette_index(request):
    """JSON list of every template the user can reach, for the command palette."""
    from django.http import JsonResponse
    items = []
    templates = (
        PromptTemplate.objects
        .filter(project__workspace__members=request.user)
        .select_related('project__workspace')
        .order_by('name')
    )
    for t in templates:
        items.append({
            'id': t.pk,
            'name': t.name,
            'project': t.project.name,
            'workspace': t.project.workspace.name,
        })
    return JsonResponse({'items': items})


@login_required
def ide_run_panel(request):
    """HTMX partial: run panel for a selected version."""
    version_id = _safe_int(request.GET.get('v'))
    if version_id is None:
        return render(request, 'ide/_run_panel.html', {})
    version = get_object_or_404(
        PromptVersion,
        pk=version_id,
        template__project__workspace__members=request.user,
    )
    variables = list(version.variables.all())
    form = RunPromptForm(variables=variables)
    recent = version.executions.order_by('-created_at')[:5]
    return render(request, 'ide/_run_panel.html', {
        'version': version,
        'form': form,
        'recent': recent,
    })


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@login_required
def workspace_list_redirect(request):
    """Superseded by the IDE shell sidebar; bounce there."""
    return redirect('ide_shell')


WorkspaceListView = workspace_list_redirect  # keep import-time symbol for urls.py

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

@login_required
def project_detail_redirect(request, pk):
    """Superseded by IDE sidebar; bounce to the shell."""
    get_object_or_404(Project, pk=pk, workspace__members=request.user)
    return redirect('ide_shell')


ProjectDetailView = project_detail_redirect  # symbol kept for urls.py compatibility

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


@login_required
def prompt_template_detail_redirect(request, pk):
    """Superseded by IDE shell — sidebar selects templates; deep-link with ?t=."""
    get_object_or_404(PromptTemplate, pk=pk, project__workspace__members=request.user)
    return redirect(f"{reverse('ide_shell')}?t={pk}")


PromptTemplateDetailView = prompt_template_detail_redirect

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
    """Superseded by run panel in the IDE shell. Deep-link redirect."""
    version = _get_runnable_version(request.user, version_pk)
    return redirect(f"{reverse('ide_shell')}?t={version.template.pk}&v={version.pk}")


@login_required
def compare_versions(request, template_pk):
    """Superseded by inline diff in editor (shift-click chip). Bounce to shell."""
    template = get_object_or_404(
        PromptTemplate, pk=template_pk, project__workspace__members=request.user,
    )
    target = f"{reverse('ide_shell')}?t={template.pk}"
    left = _safe_int(request.GET.get('left'))
    right = _safe_int(request.GET.get('right'))
    if left and right and left != right:
        target += f"&v={right}&diff={left}"
    return redirect(target)


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
