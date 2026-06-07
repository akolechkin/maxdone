# Spec: Доменная модель

> Статус: ИСТОЧНИК ИСТИНЫ. Регенерируемый артефакт.
> Из этого раздела детерминированно генерируются: `tasks/models.py`, миграции,
> сериализаторы. При расхождении кода и этого файла — прав этот файл.
> Происхождение: декомпиляция MaxDone APK (greenDAO-схема).

## Общие поля (миксин TimeStamped)
Присутствуют на каждой доменной сущности:
- `id` — CharField(32), PK, UUID hex, не редактируется
- `created` — DateTime, auto_now_add
- `modified` — DateTime, auto_now
- `local_change_date` — DateTime, auto_now (для будущей синхронизации)
- `archived` — Boolean, default False
- `owner` — FK на User, on_delete=CASCADE

## Enum: Task.Horizon (IntegerChoices)
Горизонт планирования. Значения и порядок ФИКСИРОВАНЫ (из APK TaskType):
| value | name      | label      |
|-------|-----------|------------|
| 0     | UNDEFINED | Не задан   |
| 1     | INBOX     | Входящие   |
| 2     | TODAY     | Сегодня    |
| 3     | WEEK      | Неделя     |
| 4     | LATER     | Позже      |

## Enum: Task.State (IntegerChoices)
| value | name   | label    |
|-------|--------|----------|
| 0     | ACTIVE | Активна  |
| 1     | HIDDEN | Скрыта   |

## Enum: Goal.Type (TextChoices)
| value     | label          |
|-----------|----------------|
| PRIVATE   | Личная         |
| CORPORATE | Корпоративная  |

## Сущность: Context (extends TimeStamped)
- `title` — Char(120)

## Сущность: Goal (extends TimeStamped)
- `title` — Char(255)
- `description` — Text, blank
- `goal_type` — Type, default PRIVATE
- `status` — Char(40), blank
- `start_period` / `end_period` — Date, nullable
- `shared` — Boolean, default False

## Сущность: Task (extends TimeStamped)
- `title` — Char(500)
- `note` — Text, blank
- `task_type` — Horizon, default INBOX
- `state` — State, default ACTIVE
- `priority` — Float, default 0.0  (дробный ранг для drag-and-drop)
- `done` — Boolean, default False
- `is_project` — Boolean, default False
- `goal` — FK Goal, nullable, SET_NULL, related_name="tasks"
- `context` — FK Context, nullable, SET_NULL, related_name="tasks"
- `parent` — FK self, nullable, CASCADE, related_name="children"
- `start_date` / `due_date` / `completion_date` / `hide_until_date` — DateTime, nullable
- `recur_rule` — Char(255), blank  (iCal RRULE)
- `recur_parent_id` — Char(32), blank
- `recur_exclude_dates` — Text, blank
- Meta.ordering = ["priority", "-created"]

## Сущность: CheckListItem
НЕ наследует TimeStamped (в оригинале — JSON внутри Task).
- `task` — FK Task, CASCADE, related_name="checklist"
- `title` — Char(300)
- `done` — Boolean, default False
- `sort_order` — Integer, default 0
- Meta.ordering = ["sort_order"]
