from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ide.models import Workspace, Membership, Project, PromptTemplate, PromptVersion


def _workspace_with(owner, members=None):
    ws = Workspace.objects.create(name="ws", owner=owner)
    Membership.objects.create(user=owner, workspace=ws, role="admin")
    for user, role in (members or []):
        Membership.objects.create(user=user, workspace=ws, role=role)
    return ws


class ProjectPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.member = User.objects.create_user("member", password="pw")
        self.viewer = User.objects.create_user("viewer", password="pw")
        self.outsider = User.objects.create_user("outsider", password="pw")
        self.ws = _workspace_with(self.owner, [(self.member, "member"), (self.viewer, "viewer")])

    def test_viewer_cannot_create_project(self):
        self.client.login(username="viewer", password="pw")
        resp = self.client.post(
            reverse("project_create", args=[self.ws.pk]),
            {"name": "p", "description": ""},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Project.objects.exists())

    def test_member_can_create_project(self):
        self.client.login(username="member", password="pw")
        resp = self.client.post(
            reverse("project_create", args=[self.ws.pk]),
            {"name": "p", "description": ""},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Project.objects.filter(name="p").exists())

    def test_outsider_cannot_see_workspace(self):
        self.client.login(username="outsider", password="pw")
        resp = self.client.get(reverse("workspace_detail", args=[self.ws.pk]))
        self.assertEqual(resp.status_code, 404)


class MemberRoleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.member = User.objects.create_user("member", password="pw")
        self.ws = _workspace_with(self.owner, [(self.member, "member")])

    def test_owner_can_change_role(self):
        self.client.login(username="owner", password="pw")
        resp = self.client.post(
            reverse("change_member_role", args=[self.ws.pk, self.member.pk]),
            {"role": "viewer"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Membership.objects.get(user=self.member, workspace=self.ws).role,
            "viewer",
        )

    def test_owner_role_cannot_be_changed(self):
        self.client.login(username="owner", password="pw")
        self.client.post(
            reverse("change_member_role", args=[self.ws.pk, self.owner.pk]),
            {"role": "viewer"},
        )
        self.assertEqual(
            Membership.objects.get(user=self.owner, workspace=self.ws).role,
            "admin",
        )

    def test_non_owner_cannot_change_role(self):
        self.client.login(username="member", password="pw")
        resp = self.client.post(
            reverse("change_member_role", args=[self.ws.pk, self.member.pk]),
            {"role": "admin"},
        )
        self.assertEqual(resp.status_code, 404)


class VersionAutoIncrementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pw")
        self.ws = _workspace_with(self.owner)
        self.project = Project.objects.create(workspace=self.ws, name="p")
        self.template = PromptTemplate.objects.create(project=self.project, name="t")
        self.client.login(username="owner", password="pw")

    @patch("ide.forms.ollama_client.list_models", return_value=[])
    def test_version_numbers_increment_and_variables_extracted(self, _mock):
        for content in ("hello {{name}}", "hi {{name}} from {{place}}"):
            self.client.post(
                reverse("prompt_version_create", args=[self.template.pk]),
                {"content": content, "model_name": "llama3", "commit_message": ""},
            )
        versions = list(self.template.versions.order_by("version_number"))
        self.assertEqual([v.version_number for v in versions], [1, 2])
        self.assertEqual(
            sorted(v.name for v in versions[1].variables.all()),
            ["name", "place"],
        )
