# MaxDone — реконструированная спецификация

Источник: декомпиляция `Maxdone_1_0_4_APKPure.apk` (пакет `lv.ipr.maxdone`, ORM greenDAO,
сетевой слой на Service/HttpService). Извлечено из DEX: схема сущностей, перечисления,
API-эндпоинты, бизнес-логика горизонтов и повторов. Серверная часть в APK отсутствует —
её контракт восстановлен по клиентским вызовам.

---

## 1. Доменная модель (схема БД — из greenDAO-сущностей)

### Task (43 поля)
Ключевое: `id` (String, UUID), `title`, `note`, `taskType` (горизонт), `state`, `priority` (Double),
`done` (Boolean), `project` (Boolean — задача-проект), `parentId`/`path`/`childrenIds` (дерево подзадач),
`checkListItems` (JSON-строка), `goalId`/`goalMilestoneId` (привязка к цели), `contextId`,
`startDate`/`dueDate`/`completionDate`/`hideUntilDate`, `recurRule`/`recurParentId`/`recurChildId`/`recurExcludeDates`,
`owners`/`createdBy`/`modifiedBy`/`userId` (мультипользовательность), `created`/`modified`/`localChangeDate`,
`sync` (Boolean), `archived` (Boolean), `allDay`.

### Goal (29 полей)
`id`, `title`, `description`, `goalType` (PRIVATE/CORPORATE), `status` (String),
`startPeriod`/`endPeriod`, `activeMilestoneId`, `parentGoalIds`, `goalTemplateId`/`parentGoalTemplateId`,
`responsibleId`, `shared`, `privateContributors`, `goalInfoMap` (JSON), `iconUrl`/`icon` (blob),
стандартные аудит-поля + `sync`/`archived`.

### Context (11 полей)
`id`, `title`, аудит-поля, `sync`, `archived`. Простая сущность-метка («@дома», «@5минут»).

### Категории
Отдельной таблицы нет — категории реализованы через `QueryBuilderUtil.buildCategoriesQuery` /
`buildCategoryTasksQuery`, то есть это представление поверх задач/целей (группировка), а не самостоятельная сущность.

### User (23 поля)
`id`, `username`, `email`/`emails`, `password`, `firstName`/`middleName`/`lastName`,
`pictureUrl`, `taskPreferences`/`goalPreferences`/`additionalInfo` (JSON-настройки), `current` (активный аккаунт),
`lastLogin`.

### CheckListItem (вложенный, не таблица)
`title`, `done` (boolean), `sortOrder` (int). Хранится сериализованным в `Task.checkListItems`.

### OAuthSession (8 полей)
`accessToken`, `refreshToken`, `tokenType`, `scope`, `expiresIn`, `created`, `userId`.

### Setting (6 полей)
`name`, `value`, `type`, `userId`, `sync`, `localChangeDate`. Key-value настройки.

### Шаблоны целей (контентная система «джедайских» сценариев)
- **GoalTemplate** (34 поля): `title`, `description`, `milestones`/`tasks` (JSON), `state` (DRAFT/PUBLISHED/UNPUBLISHED),
  `publicId`, `version`, `goalDueDateDays`, данные автора шаблона, `privateGoalCount`.
- **GoalMilestoneTemplate**: `title`, `description`, `dueDateDays`, `index`, `keyResults`.
- **GoalTaskTemplate**: `title`, `notes`, `checklistItems`, `recurRule`, `startDateDays`/`dueDateDays`/`hiddenUntilDays`, `milestoneId`.
- **KeyResultTemplate**: `title`, `keyResultType` (SIMPLE/SUM_RESULT/LAST_RESULT), `planned` (Double).

Шаблоны задают сроки в ОТНОСИТЕЛЬНЫХ днях (`*Days`) от старта цели — при создании цели из шаблона
(`CreateGoalFromTemplateAsyncTask`) даты вычисляются от выбранной даты старта.

---

## 2. Перечисления (точные значения из enum-классов)

- **TaskType** (горизонт планирования): `INBOX`, `TODAY`, `WEEK`, `LATER`, `UNDEFINED`
- **TaskState**: `ACTIVE`, `HIDDEN` (скрытая до `hideUntilDate`)
- **GoalType**: `PRIVATE`, `CORPORATE`
- **GoalTemplateState**: `DRAFT`, `PUBLISHED`, `UNPUBLISHED`
- **KeyResultType**: `SIMPLE`, `SUM_RESULT`, `LAST_RESULT`
- **MenuActionType** (навигация/фильтры): `TODAY`, `WEEK`, `LATER`, `INBOX`, `OVERDUE`, `COMPLETED`,
  `TODO`, `GOALS`, `GOAL`, `GOAL_EDIT`, `GOAL_TEMPLATE`, `CONTEXTS`, `CONTEXT`, `CATEGORIES`, `CATEGORY`,
  `ACTIVITY_ITEM`, `SETTINGS`, `FEEDBACK`, `LOGOUT`, `HOME_INIT`
- **MenuType** (вкладки): `HOME_TAB`, `MAIN_TAB`, `GOALS_TAB`, `GOAL_TEMPLATES_TAB`, `ACTIVITIES_TAB`, `WIDGET`, `DIALOG`

---

## 3. Логика горизонтов и состояний (из TaskUtils / DateUtils / QueryBuilderUtil)

- `calculateTaskType` — назначает горизонт (TODAY/WEEK/LATER/INBOX) по датам задачи.
- `getTodaySOD` / `getTodayEOD` — начало/конец сегодняшнего дня; основа для «сегодня» и «просрочено».
- `checkIfTaskIsHidden` / `checkIfShouldUnsetHidden` — задача со `state=HIDDEN` и `hideUntilDate` в будущем
  не показывается; по наступлении даты автоматически возвращается в список.
- `calcNewPriority` / `getMaxTaskPriority` — приоритет как Double (дробный ранг для drag-and-drop сортировки
  без перенумерации соседей).
- `sortTaskList` / `sortToday` / `sortWeek` / `sortLater` — раздельная сортировка по горизонтам.
- Готовые запросы-представления: `buildTodoTasksQuery`, `buildInboxTasksQuery`, `buildGoalTasksQuery`,
  `buildContextTasksQuery`, `buildCategoryTasksQuery`, `buildCompletedTasksQuery`, `buildArchivedTasksQuery`,
  `buildSearchTasksByTitleQuery`.

### Повторы (RRuleUtils, формат iCal RRULE)
- `recurRule` хранит RRULE-строку; `parseRRuleString` её разбирает.
- Частоты: `DAILY`, `WEEKLY`, `MONTHLY` (`MONTHLY_BY_DATE` / `MONTHLY_BY_NTH_DAY_OF_WEEK`), `YEARLY`.
- Модель повтора: задача-родитель (`recurParentId`) порождает экземпляры (`recurChildId`);
  `recurExcludeDates` — пропущенные даты. Это стандартный паттерн «series + exceptions».

---

## 4. API-контракт (из строк сетевого слоя)

**База:** `https://maxdone.micromiles.co/proxy/direct/`

**OAuth2** (`/oauth/token`), client_id=`maxdone_android`, grant types:
- `password` (логин: `&username=...&password=...`)
- `refresh_token`
Регистрация: `POST /signup`.

**REST v1** (`/v1/api/`):
- `users/global/me` — профиль текущего пользователя
- `users/global/verifyMainEmail` — подтверждение email
- `tasks/` — CRUD задач
- `user-contexts` , `user-contexts/{id}` — контексты
- `private-goals` , `private-goals/{id}` — личные цели
- `goal-templates/main/{id}` , `goal-templates/goalCountMap` — шаблоны целей
- `system/ping` — health-check
- `images` , `/services/v1/images` — загрузка картинок (иконки целей, аватары)

Все доменные объекты имеют JSON (de)serializer-классы (`TaskSerializer`, `GoalSerializer`,
`ContextSerializer` + соответствующие Deserializer), что отражает формат тела запросов/ответов.

---

## 5. Синхронизация (sync/SyncAdapter + поля)

- Каждая сущность несёт `sync` (Boolean — есть несинхронизированные изменения), `localChangeDate`,
  `modified`/`modifiedBy`, `owners`/`userId`.
- Запросы `buildSync*Query` и `buildNew*Query` отбирают изменённые/новые объекты для отправки.
- Реализовано через Android `SyncAdapter` + `AuthenticatorService` (системная синхронизация аккаунта).
- **Модель разрешения конфликтов:** поля `modified`/`localChangeDate` указывают на стратегию по времени
  (last-write-wins). В отзывах пользователей встречалась потеря данных при синхронизации — в новой
  реализации это место надо проектировать аккуратнее (например, пер-полевой merge или CRDT).

---

## 6. Экраны и навигация (из Activity/Fragment-классов)

- `LoginActivity` — вход/регистрация (email+пароль, OAuth).
- `MainActivity` — главный экран со списком, вкладки через `SlidingTabLayout` + `MenuFragment` (drawer).
- `TaskEditFragment` / `EditTaskActivity` — редактор задачи: вкладки Основное / Чек-лист / Заметка
  (`EditTaskSectionPagerAdapter`), выбор контекста/цели/дат, повтор (`RecurrencePickerDialog`), скрытие до даты.
- `GoalEditActivity` — редактор цели; `GoalTemplateViewActivity` / `GoalTaskTemplateViewActivity` —
  просмотр и применение шаблонов целей.
- `SearchActivity` — поиск по задачам и целям.
- `SettingsActivity` — настройки (в т.ч. поведение быстрого добавления: QUICK_ADD_CHECKED/UNCHECKED).
- `TodayWidgetProvider` / `TodayWidgetService` — виджет «Сегодня» на домашний экран.
- Быстрое добавление, drag-and-drop переупорядочивание (`ReorderRecyclerView`).

---

## 7. Что НЕ восстановимо из APK
- Серверный код, реальная БД на сервере, алгоритмы серверной валидации/мерджа.
- Точная вёрстка/дизайн (есть имена layout-ресурсов и id, но не пиксельный макет).
- Секреты сервера (client_secret `Marshmallow` — клиентский, не серверный).
