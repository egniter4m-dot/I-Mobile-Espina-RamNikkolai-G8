from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import MAX_HEIGHT, MAX_WEIGHT, MIN_HEIGHT, MIN_WEIGHT, User

BIOMETRIC_FIELDS = ["full_name", "email", "date_of_birth", "gender", "height_cm", "current_weight", "fitness_goal"]


class StyledFormMixin:
    """Adds the shared .field CSS class and mobile-friendly input attributes."""

    def style_fields(self):
        for field in self.fields.values():
            field.widget.attrs["class"] = "field"
        if "date_of_birth" in self.fields:
            self.fields["date_of_birth"].widget = forms.DateInput(
                attrs={"type": "date", "class": "field"}, format="%Y-%m-%d"
            )
        if "height_cm" in self.fields:
            self.fields["height_cm"].widget.attrs.update(
                {"min": str(MIN_HEIGHT), "max": str(MAX_HEIGHT), "step": "0.01", "inputmode": "decimal"}
            )
        if "current_weight" in self.fields:
            self.fields["current_weight"].widget.attrs.update(
                {"min": str(MIN_WEIGHT), "max": str(MAX_WEIGHT), "step": "0.01", "inputmode": "decimal"}
            )


class BiometricsFormMixin(StyledFormMixin):
    """Email + biometric validation shared by registration and profile edit (BR-01, BR-02).
    Range checks (age 13-120, height 50-272, weight 20-500) come from the model validators."""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        clash = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class RegistrationForm(BiometricsFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ["username", "email", "full_name", "date_of_birth", "gender", "height_cm", "current_weight", "fitness_goal"]
        labels = {
            "full_name": "Full name",
            "date_of_birth": "Date of birth",
            "height_cm": "Height (cm)",
            "current_weight": "Current weight (kg)",
            "fitness_goal": "Fitness goal",
        }
        help_texts = {"username": "Letters, digits and @ . + - _ only."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
        self.fields["password1"].help_text = "At least 8 characters; not too common or all numbers."

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                try:
                    password_validation.validate_password(p1)
                except forms.ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])  # hashed, never plain text
        user.role = "MEMBER"  # self-registration can never create an admin
        if commit:
            user.save()
        return user


class ProfileForm(BiometricsFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = BIOMETRIC_FIELDS
        labels = {
            "full_name": "Full name",
            "date_of_birth": "Date of birth",
            "height_cm": "Height (cm)",
            "current_weight": "Current weight (kg)",
            "fitness_goal": "Fitness goal",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Invalid username/email or password. Check your details and try again.",
        "inactive": "This account is inactive.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username or email"
        self.fields["username"].widget.attrs.update({"class": "field", "autocomplete": "username"})
        self.fields["password"].widget.attrs.update({"class": "field", "autocomplete": "current-password"})
