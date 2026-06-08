# Spec: Бизнес-правила

> Статус: ИСТОЧНИК ИСТИНЫ для поведения.
> Из этого раздела выводятся ПОВЕДЕНЧЕСКИЕ ТЕСТЫ (`tasks/tests/`).
> Тесты — арбитр: и код, и регенерация ядра проверяются ими.
> Реализация правил (вьюхи, сервисы) пишется руками под присмотром,
> но ДОЛЖНА проходить эти тесты.

## BR-1: Видимость задач
Задача показывается в списках, если:
- `archived == False`
- `done == False`
- НЕ (`state == HIDDEN` И `hide_until_date > сейчас`)

То есть скрытая задача с `hide_until_date` в будущем — невидима;
по наступлении даты — снова видима. (Из APK: checkIfTaskIsHidden / checkIfShouldUnsetHidden)

Запись: при сохранении задачи `state` ВЫВОДИТСЯ из `hide_until_date` —
если дата в будущем → `state = HIDDEN`, иначе (пусто или в прошлом) → `state = ACTIVE`.
Реализовано в `tasks/services.py::apply_hidden_state`.

## BR-2: Счётчики горизонтов
Для каждого из TODAY/WEEK/LATER/INBOX счётчик = число ВИДИМЫХ (BR-1)
задач с этим `task_type`.

## BR-3: Завершение задачи
Реализовано в `tasks/services.py::set_done`.
При `done = True` → `completion_date = сейчас`.
При снятии `done = False` → `completion_date = None`.

## BR-4: Приоритет (дробный ранг)
Реализовано в `tasks/services.py` (`next_priority`, `priority_between`, `create_task`).
Новая задача получает `priority` = (максимальный priority среди задач владельца) + 1.0.
Переупорядочивание между двумя соседями A и B: новый priority = (A.priority + B.priority) / 2.
Цель: вставка без перенумерации остальных. (Из APK: calcNewPriority / getMaxTaskPriority)

## BR-5: Повторы (RRULE)
`recur_rule` — строка iCal RRULE (FREQ=DAILY|WEEKLY|MONTHLY|YEARLY).
Завершение повторяющейся задачи порождает следующий экземпляр по правилу;
исходная серия — `recur_parent_id`, пропуски — `recur_exclude_dates`.
(Фаза 2 — пока правило только хранится и валидируется на синтаксис.)

## BR-6: Изоляция владельца
Любой запрос задач/целей/контекстов отфильтрован по `owner == request.user`.
Пользователь никогда не видит и не меняет чужие объекты.
