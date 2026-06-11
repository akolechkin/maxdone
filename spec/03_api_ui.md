# Spec: API и UI-флоу

> Статус: ИСТОЧНИК ИСТИНЫ для маршрутов и сценариев.
> Зона "руками под присмотром": вьюхи, HTMX-фрагменты, шаблоны.
> Генерируется частично; проверяется тестами на маршруты и HTMX-поведение.

## Маршруты
| path                          | view              | назначение                          |
|-------------------------------|-------------------|-------------------------------------|
| `/`                           | board             | главный экран; `?h=` выбор горизонта|
| `/task/<id>/`                 | task_detail       | фрагмент редактора (HTMX)            |
| `/task/<id>/toggle/`          | toggle_done       | POST: переключить done (фрагмент)    |
| `/check/<id>/toggle/`         | toggle_check_item | POST: переключить пункт чек-листа    |
| `/task/<id>/subtask/add/`     | subtask_add       | POST: добавить подзадачу (BR-7)      |
| `/task/<id>/move/<horizon>/`  | task_move         | POST: due_date→горизонт (BR-10; поддерево BR-7) |
| `/task/<id>/archive/`         | task_archive      | POST: в архив (+поддерево, BR-9)     |
| `/task/<id>/unarchive/`       | task_unarchive    | POST: восстановить из архива         |
| `/goals/<id>/archive/`        | goal_archive      | POST: цель в архив (BR-9)            |
| `/goals/<id>/unarchive/`      | goal_unarchive    | POST: восстановить цель              |
| `/archive/`                   | archive_list      | экран архива (задачи + цели)         |
| `/archive/clear/`             | archive_clear     | POST: удалить весь архив навсегда    |
| `/completed/`                 | completed_list    | экран выполненных (BR-10)            |
| `/task/<id>/copy/`            | task_copy         | POST: дублировать задачу + чек-лист  |
| `/settings/toggle/<key>/`     | toggle_setting    | POST: переключить show_hidden/quick_add (BR-11) |
| `/settings/sort/`             | set_sort          | POST: выбрать порядок сортировки (BR-13) |
| `/settings/group/`            | set_group         | POST: группировка списка (BR-17)     |
| `/templates/`                 | template_list     | каталог шаблонов целей (BR-18)       |
| `/templates/<id>/create-goal/`| template_create_goal | POST: создать цель из шаблона      |
| `/login/` `/logout/`          | auth              | вход/выход                           |

## HTMX-поведение
- Запрос с заголовком `HX-Request` к board → возвращается ТОЛЬКО `_task_list.html`.
- Обычный запрос → полная страница `board.html`.
- Клик по горизонту → hx-get, target `#task-list`, push-url.
- Клик по задаче → hx-get детали, target `#editor-body`; Alpine открывает панель.
- Чекбокс задачи/пункта → hx-post, swap outerHTML соответствующего фрагмента.

## UI-раскладка (десктоп)
Постоянный сайдбар (горизонты + счётчики + группировка) | колонка с верхними
вкладками (Задачи/Цели/Шаблоны/Лента) и списком | выезжающая справа панель редактора.
Дизайн-токены — в tailwind.config.js (акцент #534AB7, плоские поверхности, hairline).

## Зона "руками, НЕ генерировать из спеки"
- Синхронизация (в оригинале здесь был баг потери данных — требует ручных решений).
- Безопасность, аутентификация сверх базовой.
- Производительность, индексы, кэширование.

---

## UI-компоненты дат и повтора (уточнено из APK — было реализовано неверно)

### Дата выполнения (due_date)
В оригинале у задачи ОДНА основная дата — `due_date`, ставится через date picker.
- `TaskEditFragment.setDueDate / unsetDueDate / updateDueDateView`, диалог `showDatePicker`.
- В форме редактирования задачи показывается ТОЛЬКО due_date (+ кнопка очистки).
- `start_date` существует в модели, но НЕ часть основного флоу редактирования — не выводить
  как равноправное поле. `hide_until_date` — отдельный контрол «скрыть до» (см. фичу скрытия),
  тоже через date picker, НЕ как datetime-local в общем ряду.
- ОШИБКА текущей реализации: три datetime-local поля (срок/начало/скрыть) как равноправные.
  Исправить: due_date через date picker; start_date убрать из формы; hide_until_date — отдельный
  контрол скрытия.

### Повтор — селектор, НЕ текстовое поле RRULE
В оригинале `RecurrencePickerDialog` (НЕ ввод строки руками). Структура диалога:
- Переключатель «повторять / не повторять» (repeat_switch; STATE_NO_RECURRENCE / STATE_RECURRENCE).
- Частота (freqSpinner): DAILY / WEEKLY / MONTHLY / YEARLY.
- Интервал: «каждые N <единиц>» (interval, ≥1).
- WEEKLY: кнопки дней недели (mWeekByDayButtons → BYDAY).
- MONTHLY: радиовыбор «по дате месяца» (repeatMonthlyByNthDayOfMonth)
  ИЛИ «по N-му дню недели» (repeatMonthlyByNthDayOfTheWeek).
- Окончание: никогда / до даты (recurrence_end_date) / N раз (recurrence_end_count).
- На выходе формируется RRULE-строка (onRecurrenceSet) → сохраняется в `Task.recur_rule`.
- ОШИБКА текущей реализации: текстовый input для recur_rule. Исправить: диалог-селектор,
  собирающий RRULE; пользователь не печатает строку.

### Рекомендация по реализации на вебе
- Date picker: нативный `<input type="date">` для due_date (одно поле + очистка).
- Recurrence picker: Alpine-компонент (модалка) с теми же контролами; на выходе собирает
  RRULE-строку в скрытое поле recur_rule. Хранение в модели не меняется (recur_rule остаётся).
- Это UI-слой (зона «руками»), но контракт полей и значений — отсюда из спеки.

---

## Форма задачи и горизонты — Milestone 2 (см. spec/06_milestone2.md)
- Выбор горизонта (`task_type`) УБРАН из формы — горизонт следует из `due_date`
  (BR-7/BR-9). Поля формы: title, due_date (date picker + очистка), hide_until_date
  («скрыть до»), recur (recurrence picker → recur_rule), goal, context, note, is_project.
- Перемещение по горизонтам (`task_move`) и быстрое добавление меняют `due_date`,
  а не `task_type` (BR-10). Быстрое добавление датирует задачу в просматриваемую колонку.
- Счётчики горизонтов в сайдбаре обновляются out-of-band (`_counts_oob.html`,
  `id="count-<KEY>"` + `hx-swap-oob`) на КАЖДОМ мутирующем HTMX-ответе, включая
  завершение задачи; на полной (не-HTMX) странице OOB-спаны подавлены (BR-11).
