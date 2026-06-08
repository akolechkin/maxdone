# Gap report: оригинал (APK) vs текущая реализация

Высчитано сопоставлением capability-методов APK с моделями/вьюхами/сервисами проекта.
Сводка: OK 11 · PARTIAL 6 · MISSING 16 · N/A 2.
Порядок работы: сначала PARTIAL (исправить расхождения), потом MISSING по приоритету.

## PARTIAL — реализовано неверно/неполно (чинить первым)
1. **Дата выполнения** — сейчас три datetime-local поля (срок/начало/скрыть) как равноправные.
   Оригинал: ОДНА due_date через date picker (+очистка). start_date убрать из формы.
   hide_until_date — отдельный контрол «скрыть до». [setDueDate/unsetDueDate/showDatePicker]
2. **Повтор** — сейчас текстовый input для recur_rule. Оригинал: RecurrencePickerDialog —
   вкл/выкл, частота (D/W/M/Y), интервал «каждые N», дни недели (WEEKLY), monthly by-date /
   by-nth-weekday, окончание (никогда / до даты / N раз) → собирает RRULE. [onRecurrenceSet]
3. **Подзадачи/дерево** — parent есть в модели, нет UI и логики поддерева. [parentId/path/childrenIds]
4. **Задача-проект** — is_project в модели, не используется в UI. [project flag]
5. **Смена статуса цели** — status как свободный текст; оригинал: диалог выбора статуса. [CHANGE_GOAL_STATUS]
6. **Архив** — archived в модели, нет экрана архива и чистки. [buildArchivedTasksQuery/deleteArchivedTasks]

## MISSING — отсутствует (добирать по приоритету)
### Приоритет A (ядро повседневного использования)
- **Список выполненных** — экран completed. [getCompletedMenu/buildCompletedTasksQuery]
- **Тоггл «показать скрытые»** — переключатель отображения скрытых. [setShowHidden/shouldShowHidden]
- **Копия задачи** — дублирование с чек-листом. [buildTaskCopy]
- **Варианты сортировки** — по приоритету/срокам. [sortTaskList + SORT_ORDER_*]
- **Тоггл быстрого добавления** — инлайн quick-add вверху списка. [getShowQuickAddSetting]
- **Task preferences** — память последнего выбора goal/context/project для новой задачи.

### Приоритет B (методология MaxDone — отличие от Todoist)
- **Скрытие задач цели** — пауза цели прячет её задачи скопом. [hideTasksForGoal/unHideTasksForGoal]
- **Скрытие поддерева** — скрытие родителя прячет потомков. [CAN_HIDE_DESCENDANTS]
- **Категории** — представление-группировка поверх задач. [buildCategoriesQuery/createCategory]
- **Шаблоны целей** — каталог, создание цели из шаблона, относительные сроки. [createGoalFromTemplate]
- **Майлстоуны / KeyResults** — структура шаблона цели. [KeyResultType SIMPLE/SUM/LAST]

### Приоритет C (аккаунт/совместность — позже)
- **Регистрация** [signUp], **верификация email** [verifyMainEmail], **несколько аккаунтов** [findAllLogins]
- **Цели: мои vs вклад** [_getMyContributingPrivateGoals], **иконка цели** [fetchPictureByUrl]

## OK — соответствует оригиналу
Создание/редактирование/удаление/завершение задачи, перемещение по горизонтам,
дробный приоритет, чек-лист, скрытие до даты (логика BR-1), цели CRUD, контексты CRUD, поиск.

## N/A — не для веб-клона
Дельта-синхронизация (зона «руками»), Android-виджет.
