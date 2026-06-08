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

## Enum: Goal.Status (TextChoices)
Статус цели выбирается из фиксированного набора (в оригинале — диалог
`CHANGE_GOAL_STATUS`, маппинг `getResIdFromGoalStatus`), НЕ свободный текст.
| value    | label       |
|----------|-------------|
| ACTIVE   | В работе    |
| PAUSED   | На паузе    |
| ACHIEVED | Достигнута  |
| DROPPED  | Отменена    |

## Сущность: Context (extends TimeStamped)
- `title` — Char(120)

## Сущность: Goal (extends TimeStamped)
- `title` — Char(255)
- `description` — Text, blank
- `goal_type` — Type, default PRIVATE
- `status` — Status, default ACTIVE
- `start_period` / `end_period` — Date, nullable
- `shared` — Boolean, default False
- `icon` — Char(255), blank  (эмодзи или URL картинки; из APK fetchPictureByUrl)

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

## Шаблоны целей (контентная система, из APK GoalTemplate/TaskTemplate)

### Enum: KeyResult.Kind (TextChoices)
Тип ключевого результата (из APK KeyResultType). Значения ФИКСИРОВАНЫ.
| value       | label        |
|-------------|--------------|
| SIMPLE      | Простой      |
| SUM_RESULT  | Сумма        |
| LAST_RESULT | Последнее    |

### Сущность: GoalTemplate (extends TimeStamped)
Шаблон цели. `owner` — автор шаблона.
- `title` — Char(255)
- `description` — Text, blank
- `goal_type` — Goal.Type, default PRIVATE
- `published` — Boolean, default False  (published vs draft)

### Сущность: MilestoneTemplate
НЕ наследует TimeStamped.
- `template` — FK GoalTemplate, CASCADE, related_name="milestones"
- `title` — Char(255)
- `sort_order` — Integer, default 0
- Meta.ordering = ["sort_order"]

### Сущность: TaskTemplate
НЕ наследует TimeStamped.
- `template` — FK GoalTemplate, CASCADE, related_name="task_templates"
- `milestone` — FK MilestoneTemplate, nullable, CASCADE, related_name="task_templates"
- `title` — Char(500)
- `offset_days` — Integer, default 0  (относительный срок от даты старта)
- `sort_order` — Integer, default 0
- Meta.ordering = ["sort_order"]

### Сущность: KeyResult
НЕ наследует TimeStamped. Структура шаблона (план), не рантайм-прогресс.
- `milestone` — FK MilestoneTemplate, CASCADE, related_name="key_results"
- `title` — Char(255)
- `kind` — Kind, default SIMPLE
- `planned` — Float, default 0.0
- Meta.ordering = ["id"]
