# MaxDone — полный каталог фич (из APK)

Извлечено из декомпилированного `Maxdone_1.0.4`. Источники указаны как имена
классов/методов. Этот документ дополняет `spec/` и перечисляет ВСЕ обнаруженные
фичи и поведения, включая мелкие, которые легко упустить.

Легенда статуса для твоего проекта:
- ✅ уже в spec/коде
- 🔲 не реализовано — кандидат на спеку
- ⚙️ системное/Android-специфичное (на вебе делается иначе)

---

## 1. Задачи: горизонты и перемещение
- ✅ Горизонты INBOX/TODAY/WEEK/LATER/UNDEFINED (TaskType).
- 🔲 **Прямое перемещение между горизонтами**: `Manager.moveTaskToToday / moveTaskToWeek /
  moveTaskToLater`. Отдельные действия (не только через смену даты) — быстрые кнопки/свайпы.
- ✅ Авто-вычисление горизонта по датам: `TaskUtils.calculateTaskType`.
- 🔲 `Manager._updateTaskType` — пересчёт горизонта при изменениях (например, ежедневно
  "завтра" → "сегодня"). На вебе — фоновая задача/при загрузке.

## 2. Скрытие задач (это та самая фича "hide due to")
- ✅ Скрытие до даты: `state=HIDDEN` + `hide_until_date`; авто-возврат
  (`checkIfTaskIsHidden` / `checkIfShouldUnsetHidden`).
- 🔲 **Тоггл "показывать скрытые"**: `Manager.setShowHidden / shouldShowHidden`,
  `MenuManager._filterHiddenTasksFromList`. Пользователь может ВКЛючить показ скрытых
  задач в списке (глобальная настройка отображения).
- 🔲 **Скрытие всех задач цели**: `Manager.hideTasksForGoal / unHideTasksForGoal`.
  Когда цель ставится на паузу/откладывается — скопом скрываются все её задачи,
  и так же массово возвращаются. (UI: `CHANGE_GOAL_STATUS` связан с этим.)
- 🔲 **Скрытие распространяется на подзадачи**: ключ `CAN_HIDE_DESCENDANTS`.
  Скрытие задачи-родителя может скрыть всё поддерево.
- 🔲 UI выбора скрытия: `CHOOSE_HIDDEN / CHOOSE_HIDDEN_SET / CHOOSE_HIDDEN_UNSET`
  (диалог "скрыть до …" с пресетами и сбросом).

## 3. Подзадачи / дерево
- ✅ `parent` FK (модель).
- 🔲 **Иерархия задач**: поля `path`/`childrenIds` в оригинале — дерево произвольной
  вложенности, не только один уровень. Перемещение/скрытие учитывают поддерево.
- 🔲 **Задача-проект**: `is_project` (`project` boolean). Проект = задача-контейнер
  с подзадачами. Task preference запоминает "это проект" (`getTaskPreferenceProject`).

## 4. Чек-листы
- ✅ Пункты с `done` и `sort_order`.
- 🔲 Сериализация в JSON на задаче (`TaskUtils.checkListToJson / readCheckList`) —
  оригинал хранил чек-лист как JSON-поле; мы вынесли в таблицу (лучше, но учесть при импорте).

## 5. Повторы (RRULE)
- ✅ Хранение `recur_rule`, парсинг (`RRuleUtils.parseRRuleString`).
- 🔲 **Поддерживаемые частоты**: DAILY, WEEKLY, MONTHLY (MONTHLY_BY_DATE и
  MONTHLY_BY_NTH_DAY_OF_WEEK), YEARLY.
- 🔲 **Признак повторяющейся** `TaskUtils.isTaskRecuring`; серия через
  `recur_parent_id`, пропущенные даты `recur_exclude_dates`.
- ✅ Генерация следующего экземпляра при завершении (BR-5, `services.spawn_next_occurrence`).

## 6. Приоритет / сортировка
- ✅ Дробный ранг (`calcNewPriority`, `getMaxTaskPriority`).
- 🔲 **Раздельная сортировка по горизонтам**: `TaskUtils.sortTaskList` + варианты
  сортировки (по приоритету / срокам). Сорт-ключи из ресурсов:
  ENDING_SOON_FIRST, EXPIRING_SOON_FIRST, MOST_RECENT_FIRST, RECENTLY_UPDATED_FIRST.
- 🔲 Drag-and-drop переупорядочивание (ReorderRecyclerView в оригинале).

## 7. Копирование / дублирование задачи
- 🔲 **Копия задачи**: `TaskUtils.buildTaskCopy`, `EditTaskActivity$CopyClickListener`.
  Кнопка "дублировать" в редакторе (копирует поля и чек-лист).

## 8. Task preferences (запоминание выбора для новых задач)
- 🔲 Приложение запоминает последний выбор и подставляет в новую задачу:
  `getTaskPreferenceGoal / setTaskPreferenceGoal`,
  `getTaskPreferenceContext / setTaskPreferenceContext`,
  `getTaskPreferenceProject / setTaskPreferenceProject`,
  `getTaskPreferenceHideTaskBefore`. Удобство быстрого ввода.

## 9. Быстрое добавление (Quick Add)
- 🔲 **Тоггл строки быстрого добавления**: `getShowQuickAddSetting /
  setShowQuickAdd`. Можно включать/выключать инлайн-добавление вверху списка.

## 10. Цели
- ✅ PRIVATE/CORPORATE, статус, периоды.
- 🔲 **Смена статуса цели** через диалог: `GoalEditActivity$StatusClickListener`,
  `CHANGE_GOAL_STATUS`; статусы маппятся на ресурсы (`PrivateGoalUtils.getResIdFromGoalStatus`).
- 🔲 **Иконка цели**: `DEFAULT_GOAL_ICON_URL/PATH`, загрузка картинки (`fetchPictureByUrl`).
- 🔲 **Дата цели** с возможностью очистки (`GoalEditActivity$ClearDateClickListener`).
- 🔲 `initNewGoal` — преднастройка новой цели.
- 🔲 **Мои цели vs цели, в которые я вношу вклад**: `_getMyPrivateGoals` vs
  `_getMyContributingPrivateGoals` (совместные цели).

## 11. Шаблоны целей (контентная система)
> Milestone 4 (spec/08, BR-26..BR-29) сделал шаблоны ПОЛЬЗОВАТЕЛЬСКИМИ: каждый шаблон
> принадлежит владельцу, пользователь сам их создаёт/правит/удаляет. Опубликованные/
> черновики/счётчики из оригинала НЕ портируются (single-user). См. spec/08.
- ✅ **Каталог шаблонов**: список своих шаблонов (owner-scoped), CRUD шаблона.
  Опубликованные/черновики/счётчики использований — НЕ делаем (single-user, осознанно).
- ✅ **Создание цели из шаблона**: `services.create_goal_from_template`. Выбор даты
  старта → `offset_days` разворачиваются в реальные даты (дельта-дни в редакторе не
  выставляются, решение Milestone 3/4).
- ◑ **Майлстоуны и Key Results**: майлстоуны + задачи шаблона — CRUD есть (BR-28).
  KeyResults — модель есть, редактор пока НЕ создаёт/не правит (фаза 2). Группировка
  задач по майлстоунам — есть.
- ✅ **Задачи из шаблона защищены**: `BLOCKED_BY_GOAL_TEMPLATE` (`Task.from_template`),
  редактор read-only, `task_update` → 403.

## 12. Категории
- 🔲 **Категории как представление** (не таблица): `buildCategoriesQuery /
  buildCategoryTasksQuery`, меню `getCategoriesMenu / getCategoriesEditMenu /
  getCategoriesChooseMenu`. Группировка задач; создаются/удаляются
  (`createCategory / deleteCategory`).

## 13. Контексты
- ✅ Сущность Context.
- 🔲 Меню выбора/редактирования: `getContextsChooseMenu / getContextsEditMenu`,
  выбор/сброс при редактировании задачи (`CHOOSE_CONTEXT_SELECTED / _UNSET`).

## 14. Поиск
- 🔲 **Поиск по задачам и целям**: `findTasksByTitle / findGoalsByTitle`,
  `buildSearchTasksByTitleQuery / buildSearchGoalsByTitleQuery`, экран SearchActivity.

## 15. Завершённые / архив
- ✅ `done`, `completion_date`, `archived`.
- 🔲 **Список выполненных**: `getCompletedMenu`, `buildCompletedTasksQuery`.
- 🔲 **Архивные задачи/цели**: `buildArchivedTasksQuery / buildArchivedGoalsQuery`;
  чистка архива (`deleteArchivedTasks / deleteArchivedGoals`).

## 16. Аккаунт / авторизация
- ✅ OAuth2 password + refresh (в spec API).
- 🔲 **Регистрация**: `signUp` (экран с множеством шагов — LoginActivity$1..12).
- 🔲 **Верификация email**: `sendMainEmailVerification`, `verifyMainEmail`.
- 🔲 **Несколько аккаунтов / logins**: `findAllLogins / insertLogin`, `User.current`.
- ⚙️ Android AccountManager (`Authenticator`, `AuthenticatorService`) — на вебе это сессии.

## 17. Синхронизация (зона "руками", НЕ генерировать)
- ⚙️ `SyncAdapter.onPerformSync`, дельта-синк `getItemsChangesStartingFrom`,
  `getTasksStartingFrom` и т.п. (инкрементально "с момента X").
- ⚙️ Двусторонняя: `_syncLocalTaskToServer` + `_processServerTasks`.
- ⚙️ Состояния: `DM_STALE_SYNC_REQUIRED`, `DM_SYNC_DISABLED`, прогресс
  `DATA_SYNC_INTENT_PROGRESS`, разлогин `..._LOGGED_OUT`.
- ⚙️ Локальные ID до синка: `getNewTaskLocalId` (префиксы local-id) → серверные ID.
- ⚠️ Эволюция схемы: DBOpenHelper.v11..v30Update — БД мигрировала ~20 раз;
  на вебе это обычные Django-миграции, но показывает, что модель менялась активно.

## 18. Уведомления / виджет / система (⚙️ на вебе иначе)
- ⚙️ **Виджет "Сегодня"**: TodayWidgetProvider/Service — список на домашнем экране.
- ⚙️ Перезапуск синка после загрузки устройства: BootNotificationReceiver.
- ⚙️ Анимации показа/скрытия: `ALLOW_SHOW_HIDE_ANIMATIONS` (настройка).

## 19. Аналитика (что трекалось = что считали важным)
- Трекинг действий через Google Analytics (`AnalyticsConts$Action/Category/Label`,
  MMApplication$TrackerName). Полезно как подсказка, какие фичи были ключевыми:
  создание/завершение задач, перемещение по горизонтам, применение шаблонов,
  смена статуса цели.

---

## Приоритезация для веб-клона (рекомендация)
**Ядро (сделать первым):** перемещение по горизонтам (1), тоггл показа скрытых (2),
быстрое добавление + task preferences (8,9), копия задачи (7), поиск (14),
выполненные/архив (15).
**Методология MaxDone (отличие от Todoist):** скрытие задач цели (2), шаблоны
целей с майлстоунами (11), экран обзора списка (новое, в spec/03).
**Позже:** подзадачи-дерево (3), повторы-генерация (5), совместные цели (10).
**Не копировать буквально:** синхронизация (17), Android-система (16,18).
