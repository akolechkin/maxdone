from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tasks.models import Task, Goal, Context, GoalTemplate, MilestoneTemplate, TaskTemplate, KeyResult
from tasks import services
import os


class Command(BaseCommand):
    help = "Create a demo user with sample data"

    def handle(self, *args, **opts):
        user, created = User.objects.get_or_create(username="demo")
        if created:
            user.set_password("demo")
            user.save()
        else:
            self.stdout.write("demo user already seeded, skipping")
            return
        goal = Goal.objects.create(owner=user, title="Освоить джедайские техники",
                                   goal_type=Goal.Type.PRIVATE, status=Goal.Status.ACTIVE)
        ctx = Context.objects.create(owner=user, title="5 минут")
        t = services.create_task(user, "Подготовить квартальный отчёт",
                                 task_type=Task.Horizon.TODAY, goal=goal, context=ctx)
        for i, s in enumerate(["Собрать данные", "Свести в таблицу", "Написать выводы"]):
            t.checklist.create(title=s, sort_order=i, done=(i == 0))
        services.create_task(user, "Прочитать главу про мыслетопливо",
                             task_type=Task.Horizon.TODAY, goal=goal)
        tpl = GoalTemplate.objects.create(
            owner=user, title="Запустить блог", goal_type=Goal.Type.PRIVATE, published=True,
            description="Шаблон цели с майлстоунами и относительными сроками.")
        m1 = MilestoneTemplate.objects.create(template=tpl, title="Подготовка", sort_order=0)
        m2 = MilestoneTemplate.objects.create(template=tpl, title="Запуск", sort_order=1)
        TaskTemplate.objects.create(template=tpl, milestone=m1, title="Выбрать платформу", offset_days=0, sort_order=0)
        TaskTemplate.objects.create(template=tpl, milestone=m1, title="Написать 3 статьи", offset_days=7, sort_order=1)
        TaskTemplate.objects.create(template=tpl, milestone=m2, title="Опубликовать первый пост", offset_days=14, sort_order=0)
        KeyResult.objects.create(milestone=m2, title="Подписчиков", kind=KeyResult.Kind.SUM_RESULT, planned=100)

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
        self.stdout.write(self.style.SUCCESS("Seeded. App login: demo/demo  |  Admin: admin/admin"))
