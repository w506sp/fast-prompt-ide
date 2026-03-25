from django import forms
from .models import Workspace, Project, Membership
from django.contrib.auth.models import User

class WorkspaceForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ['name', 'description']

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']

class AddMemberForm(forms.Form):
    username = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=Membership.ROLE_CHOICES)

    def clean_username(self):
        username = self.cleaned_data.get('username')
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError("User does not exist.")
        return user
