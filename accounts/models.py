"""
I'Mobile - Phase 1 (Account Feature) models.

Maps to SDD Section 4: USERS, HEALTH_PLANS, WEIGHT_LOGS.
Business rules enforced here: BR-01 (unique email), BR-02 (biometric bounds),
BR-03 (single active health plan), BR-09 (every record belongs to one user).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

# ------------------------------------------------------------------ BR-02 bounds
MIN_AGE, MAX_AGE = 13, 120
MIN_HEIGHT, MAX_HEIGHT = Decimal("50.00"), Decimal("272.00")
MIN_WEIGHT, MAX_WEIGHT = Decimal("20.00"), Decimal("500.00")


def calculate_age(dob, today=None):
    today = today or timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def validate_age_range(dob):
    if dob > timezone.localdate():
        raise ValidationError("Date of birth cannot be in the future.")
    age = calculate_age(dob)
    if not MIN_AGE <= age <= MAX_AGE:
        raise ValidationError(f"Age must be between {MIN_AGE} and {MAX_AGE} years (this date gives {age}).")


height_validators = [
    MinValueValidator(MIN_HEIGHT, f"Height must be at least {MIN_HEIGHT} cm."),
    MaxValueValidator(MAX_HEIGHT, f"Height must be at most {MAX_HEIGHT} cm."),
]
weight_validators = [
    MinValueValidator(MIN_WEIGHT, f"Weight must be at least {MIN_WEIGHT} kg."),
    MaxValueValidator(MAX_WEIGHT, f"Weight must be at most {MAX_WEIGHT} kg."),
]


class Role(models.TextChoices):
    MEMBER = "MEMBER", "Member"
    ADMIN = "ADMIN", "Admin"


class Gender(models.TextChoices):
    MALE = "Male", "Male"
    FEMALE = "Female", "Female"
    OTHER = "Other", "Other"


class FitnessGoal(models.TextChoices):
    WEIGHT_LOSS = "Weight Loss", "Weight Loss"
    MAINTAIN = "Maintain Weight", "Maintain Weight"
    HEALTH = "Health Improvement", "Health Improvement"


# ------------------------------------------------------------------ USERS
class User(AbstractUser):
    """Django auth user extended with the SDD USERS columns. Password is hashed by Django."""

    first_name = None  # replaced by full_name
    last_name = None

    full_name = models.CharField(max_length=100)
    email = models.EmailField(
        max_length=150,
        unique=True,  # BR-01
        error_messages={"unique": "An account with this email already exists."},
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    date_of_birth = models.DateField(validators=[validate_age_range])  # BR-02
    gender = models.CharField(max_length=20, choices=Gender.choices)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, validators=height_validators)
    current_weight = models.DecimalField(max_digits=5, decimal_places=2, validators=weight_validators)
    fitness_goal = models.CharField(max_length=30, choices=FitnessGoal.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["email", "full_name", "date_of_birth", "gender", "height_cm", "current_weight", "fitness_goal"]

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                condition=Q(height_cm__gte=MIN_HEIGHT) & Q(height_cm__lte=MAX_HEIGHT), name="users_height_range"
            ),
            models.CheckConstraint(
                condition=Q(current_weight__gte=MIN_WEIGHT) & Q(current_weight__lte=MAX_WEIGHT),
                name="users_weight_range",
            ),
            models.CheckConstraint(condition=Q(gender__in=Gender.values), name="users_gender_valid"),
            models.CheckConstraint(condition=Q(fitness_goal__in=FitnessGoal.values), name="users_goal_valid"),
            models.CheckConstraint(condition=Q(role__in=Role.values), name="users_role_valid"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.short_name

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    # ---- helpers used by views/templates
    @property
    def short_name(self):
        return self.full_name.split()[0] if self.full_name else self.username

    @property
    def age(self):
        return calculate_age(self.date_of_birth)

    @property
    def is_member(self):
        return self.role == Role.MEMBER

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN

    @property
    def dashboard_url_name(self):
        return "admin_dashboard" if self.is_admin_role else "member_dashboard"

    @property
    def bmi(self):
        meters = float(self.height_cm) / 100
        return round(float(self.current_weight) / (meters * meters), 1)

    @property
    def bmi_category(self):
        bmi = self.bmi
        if bmi < 18.5:
            return "Underweight"
        if bmi < 25:
            return "Normal range"
        if bmi < 30:
            return "Overweight"
        return "Obese"

    @property
    def active_plan(self):
        return self.health_plans.filter(is_active=True).first()


# ------------------------------------------------------------------ HEALTH_PLANS
class HealthPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="health_plans")
    daily_cal_limit = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    daily_burn_goal = models.PositiveIntegerField()
    daily_dist_goal = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "health_plans"
        ordering = ["-generated_at", "-id"]
        constraints = [
            # BR-03: at most one active plan per user, enforced by the database itself.
            models.UniqueConstraint(
                fields=["user"], condition=Q(is_active=True), name="one_active_plan_per_user"
            ),
            models.CheckConstraint(condition=Q(daily_cal_limit__gt=0), name="plan_cal_limit_positive"),
        ]

    def __str__(self):
        return f"Plan for {self.user.username} ({'active' if self.is_active else 'inactive'})"

    # Goal -> (calorie adjustment vs. TDEE in kcal, daily active-burn target in kcal)
    GOAL_RULES = {
        FitnessGoal.WEIGHT_LOSS: (-500, 400),
        FitnessGoal.MAINTAIN: (0, 250),
        FitnessGoal.HEALTH: (0, 300),
    }
    ACTIVITY_FACTOR = 1.375  # lightly active (TDEE = BMR x factor)
    CALORIE_FLOOR = 1200  # never recommend less than this per day
    KCAL_PER_KG_PER_KM = 0.75  # approximate energy cost of walking/jogging, used to turn burn goal into distance

    @classmethod
    def compute_targets(cls, user):
        """BMR (Mifflin-St Jeor) -> TDEE -> goal-adjusted targets (BR-03)."""
        weight, height, age = float(user.current_weight), float(user.height_cm), user.age
        sex_constant = {Gender.MALE: 5, Gender.FEMALE: -161}.get(user.gender, -78)  # 'Other' = average of both
        bmr = 10 * weight + 6.25 * height - 5 * age + sex_constant
        tdee = bmr * cls.ACTIVITY_FACTOR
        adjustment, burn_goal = cls.GOAL_RULES[user.fitness_goal]

        cal_limit = max(round(tdee + adjustment), cls.CALORIE_FLOOR)
        distance = burn_goal / (weight * cls.KCAL_PER_KG_PER_KM)
        distance = min(max(distance, 0.5), 20.0)
        return {
            "daily_cal_limit": cal_limit,
            "daily_burn_goal": burn_goal,
            "daily_dist_goal": Decimal(str(distance)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }

    @classmethod
    def regenerate_for(cls, user):
        """Deactivate every previous plan and create the single new active one (BR-03)."""
        with transaction.atomic():
            cls.objects.filter(user=user, is_active=True).update(is_active=False)
            return cls.objects.create(user=user, is_active=True, **cls.compute_targets(user))


# ------------------------------------------------------------------ WEIGHT_LOGS
class WeightLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="weight_logs")
    recorded_weight = models.DecimalField(max_digits=5, decimal_places=2, validators=weight_validators)
    logged_date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "weight_logs"
        ordering = ["-logged_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(recorded_weight__gte=MIN_WEIGHT) & Q(recorded_weight__lte=MAX_WEIGHT),
                name="weightlog_weight_range",
            ),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.recorded_weight} kg on {self.logged_date}"


# ------------------------------------------------------------------ PHASE 2 STUBS (do not migrate yet)
# class MealEntry(models.Model):                      # MEAL_ENTRIES, BR-07, BR-08
#     user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meal_entries")
#     meal_name = models.CharField(max_length=120)
#     meal_category = models.CharField(max_length=20)  # Breakfast | Lunch | Dinner | Snack
#     calories_intake = models.PositiveIntegerField()  # 1..10000
#     logged_at = models.DateTimeField(default=timezone.now)
#
# class ActivitySession(models.Model):                 # ACTIVITY_SESSIONS, BR-04, BR-05, BR-06
#     user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_sessions")
#     activity_type = models.CharField(max_length=20)  # Walking | Jogging | Hiking
#     start_time = models.DateTimeField()
#     end_time = models.DateTimeField(null=True, blank=True)
#     duration_seconds = models.PositiveIntegerField(default=0)
#     distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=0)
#     steps_estimated = models.PositiveIntegerField(default=0)
#     calories_burned = models.DecimalField(max_digits=6, decimal_places=2, default=0)
#     status = models.CharField(max_length=20)         # In_Progress | Completed | Cancelled
#     # BR-05: UniqueConstraint(fields=["user"], condition=Q(status="In_Progress"))
#
# class GpsRoutePoint(models.Model):                   # GPS_ROUTE_POINTS
#     session = models.ForeignKey(ActivitySession, on_delete=models.CASCADE, related_name="route_points")
#     latitude = models.DecimalField(max_digits=10, decimal_places=8)
#     longitude = models.DecimalField(max_digits=11, decimal_places=8)
#     recorded_at = models.DateTimeField(default=timezone.now)
