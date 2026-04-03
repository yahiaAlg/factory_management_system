# Place at: your_app/management/commands/seed_expense_categories.py

from django.core.management.base import BaseCommand
from expenses.models import ExpenseCategory  # adjust app label as needed

CATEGORIES = [
    ("salaries", "Salaires et charges sociales", 0),
    ("maintenance", "Maintenance et réparations", 1),
    ("energy", "Énergie et utilités", 2),
    ("transport", "Transport et logistique", 3),
    ("rent", "Loyers et charges locatives", 4),
    ("supplies", "Fournitures et consommables", 5),
    ("taxes", "Taxes et impôts", 6),
    ("insurance", "Assurances", 7),
    ("professional", "Services professionnels", 8),
    ("marketing", "Marketing et communication", 9),
    ("training", "Formation", 10),
    ("other", "Autres charges", 11),
]


class Command(BaseCommand):
    help = "Seed default ExpenseCategory rows (safe to re-run — uses update_or_create)"

    def handle(self, *args, **options):
        created_count = 0
        for code, label, order in CATEGORIES:
            _, created = ExpenseCategory.objects.update_or_create(
                code=code,
                defaults={"label": label, "order": order, "is_active": True},
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created: {code}")
            else:
                self.stdout.write(f"  Updated: {code}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created_count} created, "
                f"{len(CATEGORIES) - created_count} already existed."
            )
        )
