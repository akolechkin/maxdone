"""BR-38: the one automatic box move — pull LATER/WEEK tasks forward when their due_date
has come within an earlier box and isn't past. Also runs on board load; this command is
for a daily cron so it happens even if the board isn't opened.

    docker compose exec web python manage.py pull_forward_boxes
"""
from django.core.management.base import BaseCommand
from tasks import services


class Command(BaseCommand):
    help = "Pull WEEK/LATER tasks forward to an earlier box when their date has approached (BR-38)."

    def handle(self, *args, **options):
        moved = services.pull_forward()  # all users
        self.stdout.write(self.style.SUCCESS(f"Pulled {moved} task(s) forward."))
