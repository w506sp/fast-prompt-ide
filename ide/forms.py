from django import forms
from django.forms import inlineformset_factory
from .models import Workspace, Project, Membership, PromptTemplate, PromptVersion, Variable
from django.contrib.auth.models import User
from . import ollama_client

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

class PromptTemplateForm(forms.ModelForm):
    class Meta:
        model = PromptTemplate
        fields = ['name', 'description']

class PromptVersionForm(forms.ModelForm):
    class Meta:
        model = PromptVersion
        fields = ['content', 'model_name', 'commit_message']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 15, 'placeholder': 'Write your prompt here. Use {{variable_name}} for dynamic variables.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        models = ollama_client.list_models()
        if models:
            self.fields['model_name'] = forms.ChoiceField(
                choices=[(m, m) for m in models],
                help_text="Models discovered on the local Ollama server.",
            )


class PromptVersionMetaForm(forms.ModelForm):
    """Editable bits of an existing version — not the content (history is immutable)."""

    class Meta:
        model = PromptVersion
        fields = ['commit_message']


VariableFormSet = inlineformset_factory(
    PromptVersion,
    Variable,
    fields=['name', 'description', 'default_value'],
    extra=0,
    can_delete=False,
    widgets={
        'description': forms.TextInput(),
        'default_value': forms.Textarea(attrs={'rows': 2}),
    },
)


class RunPromptForm(forms.Form):
    """Dynamic form: one field per Variable on a PromptVersion."""

    def __init__(self, *args, variables=None, **kwargs):
        super().__init__(*args, **kwargs)
        for var in variables or []:
            self.fields[f'var_{var.name}'] = forms.CharField(
                label=var.name,
                required=False,
                initial=var.default_value,
                help_text=var.description or '',
                widget=forms.Textarea(attrs={'rows': 2}),
            )

    def variable_values(self):
        return {
            key[len('var_'):]: value
            for key, value in self.cleaned_data.items()
            if key.startswith('var_')
        }
