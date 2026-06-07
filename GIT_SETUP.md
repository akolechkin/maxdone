# Заливка в свой репозиторий

Этот каркас собран вне сети, поэтому пуш делаешь ты сам:

```bash
tar -xzf maxdone-django.tar.gz
cd maxdone-django

git init
git add .
git commit -m "init: maxdone spec-driven skeleton (Django+HTMX+Tailwind)"
git branch -M main
git remote add origin <URL-твоего-репозитория>
git push -u origin main
```

## Проверь, что всё работает
```bash
docker compose up web                                  # поднять
docker compose exec web python manage.py test          # тесты (BR-1..BR-6)
docker compose exec web python manage.py seed          # demo/demo
docker compose --profile assets up tailwind            # сборка CSS
```

Дальше открой папку в Claude Code — он прочитает CLAUDE.md и WORKFLOW.md
и поведёт разработку по spec-driven циклу с реальными коммитами и пушами.

## Что уже реализовано (целостный проход цикла)
- BR-1 видимость, BR-2 счётчики, BR-6 изоляция — вьюхи + тесты
- BR-3 completion_date, BR-4 priority — tasks/services.py + тесты
- enum-контракт из APK — тесты

## Следующие задачи для Claude Code (примеры промптов)
- "Реализуй BR-5 (повторы RRULE): при завершении повторяющейся задачи
   создавать следующий экземпляр. Обнови spec/02_rules.md со статусом, добавь тесты."
- "Добавь форму создания/редактирования задачи по spec/03_api_ui.md,
   используя services.create_task для авто-priority."
- "Добавь экран обзора списка (оставить/переформулировать/убить) — опиши
   сначала в spec/, потом реализуй с тестами."
