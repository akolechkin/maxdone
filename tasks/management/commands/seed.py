from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tasks.models import Task, Goal, Context
from tasks import services


class Command(BaseCommand):
    help = "Create a demo user with sample data"

    def handle(self, *args, **opts):
        user, created = User.objects.get_or_create(username="demo")
        if created:
            user.set_password("demo")
            user.save()
        goal = Goal.objects.create(owner=user, title="Освоить джедайские техники",
                                   goal_type=Goal.Type.PRIVATE, status="В работе")
        ctx = Context.objects.create(owner=user, title="5 минут")
        t = services.create_task(user, "Подготовить квартальный отчёт",
                                 task_type=Task.Horizon.TODAY, goal=goal, context=ctx)
        for i, s in enumerate(["Собрать данные", "Свести в таблицу", "Написать выводы"]):
            t.checklist.create(title=s, sort_order=i, done=(i == 0))
        services.create_task(user, "Прочитать главу про мыслетопливо",
                             task_type=Task.Horizon.TODAY, goal=goal)
        self.stdout.write(self.style.SUCCESS("Seeded. Login: demo / demo"))
