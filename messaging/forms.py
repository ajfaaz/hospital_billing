# messaging/forms.py
from django import forms
from .models import Message
from billing.models import CustomUser


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['recipient', 'subject', 'body']

    recipient = forms.ModelChoiceField(
        queryset=CustomUser.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Recipient"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Group recipients by role
        roles = CustomUser.objects.values_list('role', flat=True).distinct()
        grouped_choices = []
        for role in roles:
            users = CustomUser.objects.filter(role=role)
            choices = [(u.id, f"{u.username}") for u in users]
            grouped_choices.append((role.capitalize(), choices))

        self.fields['recipient'].choices = grouped_choices
        self.fields['subject'].widget.attrs.update({'class': 'form-control'})
        self.fields['body'].widget.attrs.update({'class': 'form-control', 'rows': 5})
