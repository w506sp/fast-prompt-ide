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


class RunPromptVersionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.outsider = User.objects.create_user("bob", password="pw")
        self.version = _build_version(self.user)
        self.client.login(username="alice", password="pw")

    def test_get_renders_form_with_variable_field(self):
        resp = self.client.get(reverse("prompt_version_run", args=[self.version.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "var_name")

    def test_outsider_cannot_run(self):
        self.client.logout()
        self.client.login(username="bob", password="pw")
        resp = self.client.post(
            reverse("prompt_version_run", args=[self.version.pk]),
            {"var_name": "ada"},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(Execution.objects.count(), 0)

    def test_post_creates_execution_on_success(self):
        fake = {"response": "hi ada", "prompt_eval_count": 4, "eval_count": 7}
        with patch("ide.views.ollama_client.generate", return_value=fake) as mock_gen:
            resp = self.client.post(
                reverse("prompt_version_run", args=[self.version.pk]),
                {"var_name": "ada"},
            )

        execution = Execution.objects.get()
        self.assertEqual(execution.status, "success")
        self.assertEqual(execution.output_text, "hi ada")
        self.assertEqual(execution.input_data, {"name": "ada"})
        self.assertEqual(execution.token_usage, {"prompt_eval_count": 4, "eval_count": 7})
        self.assertIsNotNone(execution.latency_ms)
        self.assertEqual(execution.user, self.user)
        # Ollama was called with the rendered prompt
        args, kwargs = mock_gen.call_args
        self.assertEqual(args[0], "llama3")
        self.assertEqual(args[1], "hello ada")
        self.assertRedirects(resp, reverse("execution_detail", args=[execution.pk]))

    def test_post_records_error_when_ollama_fails(self):
        with patch(
            "ide.views.ollama_client.generate",
            side_effect=ollama_client.OllamaError("boom"),
        ):
            self.client.post(
                reverse("prompt_version_run", args=[self.version.pk]),
                {"var_name": "ada"},
            )

        execution = Execution.objects.get()
        self.assertEqual(execution.status, "error")
        self.assertEqual(execution.error_message, "boom")
        self.assertEqual(execution.output_text, "")


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
