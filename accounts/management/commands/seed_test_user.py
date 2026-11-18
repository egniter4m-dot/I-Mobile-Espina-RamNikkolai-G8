from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import HealthPlan, User, WeightLog

PASSWORD = "ChangeMe123!"

SEED_USERS = [
    {
        "username": "24-4749-939",
        "email": "ram.espina@example.com",
        "role": "MEMBER",
        "full_name": "Ram Nikkolai Espina",
        "date_of_birth": date(2003, 5, 14),
        "gender": "Male",
        "height_cm": Decimal("170.00"),
        "current_weight": Decimal("68.50"),
        "fitness_goal": "Weight Loss",
    },
    {
        "username": "admin_demo",
        "email": "admin@imobile.example.com",
        "role": "ADMIN",
        "full_name": "IMobile Administrator",
        "date_of_birth": date(1990, 1, 1),
        "gender": "Other",
        "height_cm": Decimal("165.00"),
        "current_weight": Decimal("60.00"),
        "fitness_goal": "Maintain Weight",
    },
]


class Command(BaseCommand):
    help = "Creates (or resets) the test Member and Admin accounts. Safe to run repeatedly."

    @transaction.atomic
    def handle(self, *args, **options):
        for data in SEED_USERS:
            username = data["username"]
            user, created = User.objects.get_or_create(username=username, defaults=data)
            if not created:
                for key, value in data.items():
                    setattr(user, key, value)
            user.is_staff = user.is_superuser = data["role"] == "ADMIN"
            user.set_password(PASSWORD)  # stored hashed
            user.save()

            if not user.weight_logs.exists():
                WeightLog.objects.create(user=user, recorded_weight=user.current_weight, notes="Starting weight")
            if not user.health_plans.filter(is_active=True).exists():
                HealthPlan.regenerate_for(user)

            self.stdout.write(self.style.SUCCESS(
                f"{'Created' if created else 'Reset'} {data['role']}: {username} / {PASSWORD}"
            ))
