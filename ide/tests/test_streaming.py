from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ide.models import (
    Workspace, Membership, Project, PromptTemplate, PromptVersion, Variable, Execution,
)


def _build_version(owner):
    ws = Workspace.objects.create(name="ws", owner=owner)
    Membership.objects.create(user=owner, workspace=ws, role="admin")
    project = Project.objects.create(workspace=ws, name="p")
    template = PromptTemplate.objects.create(project=project, name="t")
    version = PromptVersion.objects.create(
        template=template, version_number=1,
        content="hello {{name}}", model_name="llama3",
    )
    Variable.objects.create(version=version, name="name", default_value="world")
    return version


class StartStreamingRunTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.version = _build_version(self.user)
        self.client.login(username="alice", password="pw")

    def test_post_creates_pending_execution_and_returns_partial(self):
        resp = self.client.post(
            reverse("prompt_version_run_stream", args=[self.version.pk]),
            {"var_name": "ada"},
        )
        self.assertEqual(resp.status_code, 200)
        execution = Execution.objects.get()
        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.input_data, {"name": "ada"})
        self.assertContains(resp, f"executions/{execution.pk}/stream")

    def test_get_rejected(self):
        resp = self.client.get(reverse("prompt_version_run_stream", args=[self.version.pk]))
        self.assertEqual(resp.status_code, 400)


class ExecutionStreamTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.outsider = User.objects.create_user("bob", password="pw")
        self.version = _build_version(self.user)
        self.execution = Execution.objects.create(
            version=self.version, user=self.user,
            input_data={"name": "ada"}, status="pending",
        )

    def test_streams_chunks_and_finalizes_execution(self):
        fake_chunks = [
            {"response": "hi ", "done": False},
            {"response": "ada", "done": False},
            {"response": "", "done": True, "prompt_eval_count": 5, "eval_count": 11},
        ]
        with patch("ide.views.ollama_client.generate_stream", return_value=iter(fake_chunks)):
            self.client.login(username="alice", password="pw")
            resp = self.client.get(reverse("execution_stream", args=[self.execution.pk]))
            body = b"".join(resp.streaming_content).decode()
        self.assertIn("data: hi ", body)
        self.assertIn("data: ada", body)
        self.assertIn(f"event: done\ndata: {self.execution.pk}", body)
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "success")
        self.assertEqual(self.execution.output_text, "hi ada")
        self.assertEqual(
            self.execution.token_usage,
            {"prompt_eval_count": 5, "eval_count": 11},
        )

    def test_records_error_on_ollama_failure(self):
        from ide import ollama_client
        with patch(
            "ide.views.ollama_client.generate_stream",
            side_effect=ollama_client.OllamaError("boom"),
        ):
            self.client.login(username="alice", password="pw")
            resp = self.client.get(reverse("execution_stream", args=[self.execution.pk]))
            body = b"".join(resp.streaming_content).decode()
        self.assertIn("event: error", body)
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "error")
        self.assertEqual(self.execution.error_message, "boom")

    def test_outsider_cannot_open_stream(self):
        self.client.login(username="bob", password="pw")
        resp = self.client.get(reverse("execution_stream", args=[self.execution.pk]))
        self.assertEqual(resp.status_code, 404)
