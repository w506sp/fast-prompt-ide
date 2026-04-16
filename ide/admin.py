from django.contrib import admin
from .models import Workspace, Project, Membership, PromptTemplate, PromptVersion, Variable, Execution

admin.site.register(Workspace)
admin.site.register(Project)
admin.site.register(Membership)
admin.site.register(PromptTemplate)
admin.site.register(PromptVersion)
admin.site.register(Variable)
admin.site.register(Execution)
