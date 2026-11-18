from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse

from .decorators import admin_required, member_required
from .forms import LoginForm, ProfileForm, RegistrationForm
from .models import FitnessGoal, HealthPlan, Role, User, WeightLog

# Changing any of these regenerates the health plan (BR-03). Gender is included
# because the BMR equation depends on it.
PLAN_FIELDS = {"current_weight", "height_cm", "date_of_birth", "gender", "fitness_goal"}


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


# ------------------------------------------------------------------ registration / auth
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                WeightLog.objects.create(user=user, recorded_weight=user.current_weight, notes="Starting weight")
                HealthPlan.regenerate_for(user)
            messages.success(request, "Account created! Your first health plan is ready. Log in to see it.")
            return redirect("login")
        messages.error(request, "Please fix the highlighted fields and try again.")
    return render(request, "accounts/register.html", {"form": form})


class RoleLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse(self.request.user.dashboard_url_name)

    def form_valid(self, form):
        messages.success(self.request, f"Welcome back, {form.get_user().short_name}!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Invalid username/email or password.")
        return super().form_invalid(form)


class RoleLogoutView(LogoutView):
    """POST-only logout (Django 5+): ends the session cleanly."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You have been logged out.")
        return response


# ------------------------------------------------------------------ dashboards
@login_required
def dashboard(request):
    """Sends each user to the dashboard for their role."""
    return redirect(request.user.dashboard_url_name)


@member_required
def member_dashboard(request):
    user = request.user
    return render(
        request,
        "accounts/member_dashboard.html",
        {"plan": user.active_plan, "recent_weights": user.weight_logs.all()[:3]},
    )


@admin_required
def admin_dashboard(request):
    members = User.objects.filter(role=Role.MEMBER)
    total = members.count()
    counts = {r["fitness_goal"]: r["n"] for r in members.values("fitness_goal").annotate(n=Count("id"))}
    distribution = [
        {"label": g.label, "count": counts.get(g.value, 0), "pct": round(counts.get(g.value, 0) * 100 / total) if total else 0}
        for g in FitnessGoal
    ]
    context = {
        "total_members": total,
        "active_plans": HealthPlan.objects.filter(is_active=True, user__role=Role.MEMBER).count(),
        "distribution": distribution,
        "members": members.order_by("-created_at"),  # read-only directory
    }
    return render(request, "accounts/admin_dashboard.html", context)


# ------------------------------------------------------------------ profile (own data only, BR-09)
@login_required
def profile(request):
    # Always load the logged-in user's own record; no user id is ever taken from the URL or form.
    # A fresh instance keeps the navbar from showing unsaved/invalid edits.
    user = User.objects.get(pk=request.user.pk)
    form = ProfileForm(request.POST or None, instance=user)

    if request.method == "POST":
        if form.is_valid():
            changed = set(form.changed_data)
            with transaction.atomic():
                user = form.save()
                if "current_weight" in changed:
                    WeightLog.objects.create(user=user, recorded_weight=user.current_weight, notes="Updated from profile")
                if changed & PLAN_FIELDS:
                    HealthPlan.regenerate_for(user)
            if not changed:
                messages.info(request, "No changes to save.")
            elif changed & PLAN_FIELDS:
                messages.success(request, "Profile updated. A new health plan was generated from your details.")
            else:
                messages.success(request, "Profile updated.")
            return redirect("profile")
        messages.error(request, "Please fix the highlighted fields and try again.")

    return render(request, "accounts/profile.html", {"form": form, "profile_user": user, "plan": user.active_plan})
