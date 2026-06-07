# maxdone (Django + HTMX + Tailwind)

Функциональный аналог MaxDone. Доменная модель и горизонты восстановлены
из декомпилированного APK; реализация собственная.

## Запуск

```bash
# 1. Собрать CSS (один раз или в watch-режиме)
docker compose --profile assets up tailwind   # отдельный терминал

# 2. Поднять приложение + БД
docker compose up web

# 3. Тестовые данные
docker compose exec web python manage.py seed
```

Откройте http://localhost:8000 — логин `demo` / `demo`.

## Архитектура
- **MPA + HTMX**: вьюхи отдают HTML-фрагменты (`_task_list`, `_task_editor`,
  `_task_row`), HTMX подменяет куски страницы — ощущается как SPA.
- **Alpine.js**: локальное UI-состояние (открыта ли панель редактора).
- **Tailwind**: дизайн-токены MaxDone в `tailwind.config.js` (акцент #534AB7,
  плоские поверхности, hairline-границы).

## Сущности (из APK greenDAO-схемы)
Task (горизонты INBOX/TODAY/WEEK/LATER, state ACTIVE/HIDDEN, дробный priority,
recur RRULE, hide_until_date), Goal (PRIVATE/CORPORATE), Context, CheckListItem.

## Дальше
- DRF-слой для будущих мобильных приложений
- Экран обзора списка (оставить / переформулировать / убить)
- Применение шаблонов целей
