from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ide import ollama_client
from ide.models import (
    Workspace, Membership, Project, PromptTemplate, PromptVersion, Variable, Execution,
)


def _build_version(owner, content="hello {{name}}", model="llama3"):
    ws = Workspace.objects.create(name="ws", owner=owner)
    Membership.objects.create(user=owner, workspace=ws, role="admin")
    project = Project.objects.create(workspace=ws, name="p")
    template = PromptTemplate.objects.create(project=project, name="t")
    version = PromptVersion.objects.create(
        template=template, version_number=1, content=content, model_name=model,
    )
    Variable.objects.create(version=version, name="name", default_value="world")
    return version


class RunRedirectTests(TestCase):
    """The legacy /versions/<pk>/run/ endpoint now redirects into the IDE shell."""

    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.version = _build_version(self.user)
        self.client.login(username="alice", password="pw")

    def test_redirects_to_shell_with_template_and_version(self):
        resp = self.client.get(reverse("prompt_version_run", args=[self.version.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"t={self.version.template.pk}", resp.url)
        self.assertIn(f"v={self.version.pk}", resp.url)


class ExecutionViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.outsider = User.objects.create_user("bob", password="pw")
        self.version = _build_version(self.user)
        self.execution = Execution.objects.create(
            version=self.version, user=self.user,
            input_data={"name": "ada"}, output_text="hi", status="success",
            latency_ms=42, token_usage={"eval_count": 3},
        )

    def test_history_lists_executions_for_member(self):
        self.client.login(username="alice", password="pw")
        resp = self.client.get(reverse("execution_list", args=[self.version.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"#{self.execution.pk}")

    def test_outsider_cannot_view_execution(self):
        self.client.login(username="bob", password="pw")
        resp = self.client.get(reverse("execution_detail", args=[self.execution.pk]))
        self.assertEqual(resp.status_code, 404)
