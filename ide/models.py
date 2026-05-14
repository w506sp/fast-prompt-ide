from django.db import models
from django.contrib.auth.models import User

class Workspace(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_workspaces')
    members = models.ManyToManyField(User, through='Membership', related_name='workspaces')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Membership(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'workspace')

class Project(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PromptVersion(models.Model):
    template = models.ForeignKey('PromptTemplate', on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    content = models.TextField()
    model_name = models.CharField(max_length=255)
    model_config = models.JSONField(default=dict, blank=True)
    commit_message = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ('template', 'version_number')

    def __str__(self):
        return f"{self.template.name} v{self.version_number}"

class Execution(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('streaming', 'Streaming'),
        ('success', 'Success'),
        ('error', 'Error'),
        ('timeout', 'Timeout'),
    )
    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='executions')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='executions')
    input_data = models.JSONField(default=dict)
    output_text = models.TextField(blank=True)
    latency_ms = models.IntegerField(null=True, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Execution {self.pk} — {self.status}"

class Variable(models.Model):
    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='variables')
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    default_value = models.TextField(blank=True)

    def __str__(self):
        return self.name

class PromptTemplate(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='templates')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
