"""BR-5 catch-up: materialize overdue recurring occurrences.

Run periodically (cron / Celery-beat), e.g. once a day:
    docker compose exec web python manage.py materialize_recurrences
"""
from django.core.management.base import BaseCommand
from tasks import services


class Command(BaseCommand):
    help = "Generate overdue occurrences for recurring task series (BR-5 catch-up)."

    def handle(self, *args, **options):
        created = services.materialize_due_recurrences()
        self.stdout.write(self.style.SUCCESS(f"Materialized {created} recurring occurrence(s)."))
