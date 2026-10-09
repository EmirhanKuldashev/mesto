# Match V2 — финальный аудит, 2026-10-09

## Вердикт: READY WITH LIMITATIONS

Можно готовить PR с выключенной по умолчанию новой выдачей и явно обозначенными
ограничениями. Это не разрешение на публичное включение: нагрузка/outage,
калибровка и дальнейший rollout требуют отдельного согласования.
После последней backend-правки полный suite: 822 passed / 0 failed / 0 skipped.
После последней frontend-правки и исправлений test setup полный E2E:
36 passed / 0 failed / 0 skipped. Работа остановлена на отчёте, без публикации.

## Scope и состояние Git

Аудит проводится в `codex/match-v2-recommendations`, HEAD
`bde56dd591dfcb347172a4a7047f47b9c2229e07`. Исходные 21 dirty/untracked
файла — результат предыдущей согласованной реализации; они сохранены.
Ни commit, ни push, ни merge, ни deploy не выполнялись. Ветка экспериментального
редизайна сохранена. Канонические Score/Local/Foundation и production DB не менялись.

Аудит включал чтение всех новых файлов, полного tracked diff, связанных
канонических калькуляторов, проверки provenance и пользовательского пути.
Были проверены read-only транзакции, формулы, веса, нулевые и отсутствующие
ответы, ограничения, сортировка, браузерная миграция, API-валидация и кэши.

## Найденные и исправленные ошибки

| Severity | Проблема и исправление | Файл / строка |
|---|---|---|
| High | Явно исключённая поездка с importance=0 и незаполненной частотой блокировала Mobility других поездок. Аналогично visits=0 при неизвестной importance. Ноль теперь исключает мягкую оценку, но не отключает hard limit. Добавлены два backend regression cases. | `C:/Users/Admin/mesto/backend/app/recommendations/v2_service.py:121` |
| Medium | В Results при включённом V2 оставался раздел объявлений, отфильтрованный по выбранному старой системой району. Он теперь скрывается вместе с legacy-выдачей и возвращается при выключении V2. | `C:/Users/Admin/mesto/frontend/app/results/page.tsx:67` |
| Medium | Валидатор frontend принимал некорректные actual/limit и непроверенные инфраструктурные explanations. Объект вместо числового actual мог привести к ошибке рендера. Проверяются числовые/Decimal значения, причины, coverage, contributions и district counts. Добавлен malformed-response case. | `C:/Users/Admin/mesto/frontend/lib/api/recommendations-v2.ts:10` |
| Low | Отсутствие оценки объяснялось слишком общо, намеренно исключённая область выглядела как обычная нехватка данных. Добавлены русские причины, явное исключение области и внутренние веса/вклады пяти infra-компонентов. | `C:/Users/Admin/mesto/frontend/components/match-recommendations.tsx:15` |
| Medium | Сравнение находилось после всех 108 карточек. Блок перенесён выше списка; выбранная карточка содержит прямую ссылку на сравнение. Добавлена проверка, что заголовок сравнения действительно находится во viewport после перехода. | `C:/Users/Admin/mesto/frontend/components/match-recommendations.tsx:66` |
| Medium | Переключатель V2 размонтировал старую форму Foundation и сбрасывал введённые legacy-приоритеты при возврате. Теперь форма скрывается без размонтирования; regression проверяет сохранение legacy school importance при включении/выключении V2 на обеих ширинах. | `C:/Users/Admin/mesto/frontend/app/district/page.tsx:80` |

Critical ошибок не обнаружено. Ни формулы MESTO Score V2, ни каноническая
пространственная нормализация не менялись.

## Математика и контракты

- Infrastructure Fit вызывает существующую функцию Foundation поверх Local.
  Нет отдельного бонуса Objective, сложения Local+Fit или скрытой калибровки.
- Mobility: 100 при t<=g, 0 при t>=b, между ними 100*(b-t)/(b-g).
  Вес поездки — importance*visits_per_week после явного подтверждения.
  Жёсткий максимум проверяется отдельно, в том числе для исключённой поездки.
- Affordability использует ту же кусочно-линейную полезность на Decimal-ценах.
  Цена ровно максимальному бюджету: PASS hard constraint, utility=0.
  Только maximum без comfortable даёт проверку бюджета, но не финансовый балл.
- Общий Match: alphaI*I+alphaM*M+alphaA*A. Заданные веса суммируются в 1;
  frontend нормирует явно выбранные относительные приоритеты, не меняя null в 0.
  Все нули дают null. Отсутствующий активный домен даёт null без перенормировки.
- FAIL имеет приоритет над UNKNOWN. Числовая диагностическая оценка при FAIL
  возможна, но такой объект не попадает в verified и лучший verified района.
- Цена берётся только из той же реальной CIAN-записи с валидной Point-геометрией;
  произвольной точке цена не присваивается. Район подтверждается покрытием
  координаты реальным OSM-полигоном. Несогласованная принадлежность не подменяется.
- Кандидаты сортируются по bucket, score, id; районы по лучшему verified и id.
  Веса не влияют на Objective. Отсутствующая цена не заменяется нулём.

## Реальные сценарии Красноярска

Источник — существующий каталог 108 реальных наблюдаемых CIAN ЖК в отдельном
локальном E2E-окружении. OSM/road graph — замороженные существующие baseline.
Это не новые объявления, не полный рынок, не реальные пользовательские профили.
Все шесть профилей — явно заданные эксперименты на реальных фактах.

Порядок infra: остановки, школа, детсад, медицина, парки. Порядок доменов: I/M/A.

| Профиль | Infra | I/M/A | Бюджет / комфорт | Поездка: координаты; g/b/hard, мин |
|---|---|---|---|---|
| Студент | 3/0/0/1/1 | .3/.4/.3 | 6/4 млн | 56.01,92.85; 8/25/40 |
| Семья | 1/3/3/2/2 | .7/.1/.2 | 10/7 млн | 56.02,92.90; 8/25/40 |
| Работа | 1/0/0/1/1 | .3/.6/.1 | 10/7 млн | 56.04,92.90; 8/25/35 |
| Парки/медицина | 0/0/0/3/3 | .8/0/.2 | 10/7 млн | Исключена |
| Высокий бюджет | 1/1/1/1/1 | .6/0/.4 | 20/12 млн | Исключена |
| Строгие ограничения | 1/3/3/1/1 | .4/.4/.2 | 5.5/4 млн | 56.04,92.90; 5/15/8 |

Для включённой поездки importance=3, visits_per_week=5, mode=car,
frequency_weighting_confirmed=true. Остальные поля профилей и top-5 зафиксированы
в локальном `C:/Users/Admin/mesto/backend/data/raw/match-v2-audit-results.json`.

| Профиль | Первый verified ЖК | Match | I / M / A | Objective района | verified / unknown / failed |
|---|---|---|---|---|---|
| Студент | №12 «Серебряный», Октябрьский | 92.9911 | 92.3232 / 88.2353 / 100 | 45.58 | 47 / 12 / 49 |
| Семья | №53 «АЭРО», Советский | 92.1884 | 88.8406 / 100 / 100 | 46.75 | 85 / 12 / 11 |
| Работа | №63 «RUNWAY», Советский | 97.0684 | 90.2281 / 100 / 100 | 46.75 | 85 / 12 / 11 |
| Парки/медицина | №103 «Олимп», Свердловский | 97.3026 | 96.6282 / excluded / 100 | 41.50 | 85 / 12 / 11 |
| Высокий бюджет | №103 «Олимп», Свердловский | 94.7291 | 91.2152 / excluded / 100 | 41.50 | 96 / 12 / 0 |
| Строгие ограничения | №81 «Квадро», Центральный | 69.6572 | 77.7759 / 89.25 / 14.234 | 59.22 | 1 / 6 / 101 |

У семьи выше вес школы/детсада, у специалиста — рабочего маршрута: «RUNWAY»
поднимается с №2 до №1. Парки/медицина и высокий бюджет имеют одного лидера,
но разные оценки и последующие позиции; перестановка искусственно не создавалась.
Один и тот же Objective района у разных ЖК не определяет их персональный score.
Ни один из 108 кандидатов не получил общий score=100 ни в одном из шести сценариев.
12 записей имеют неизвестную цену: UNKNOWN, если нет подтверждённого другого
нарушения; при подтверждённом нарушении времени — FAIL даже без цены.

В high-budget группировке Свердловский имеет 15 наблюдений и лучший 94.7291,
Советский — 33 наблюдения и лучший 92.8673. Количество не добавляется к score.
Однако maximum selection bias не устранён: это ограничение статистики,
а не доказательство равной полноты районных выборок. Показаны все counts;
максимум не называется совместимостью всего района.

## Производительность и кэши

Отдельный read-only checker с исходным кодом и счётчиками SQL/provider calls,
без модификации production или E2E-каталога:

| Запрос: 108 ЖК × 3 CAR-направления | Время | SQL | Router calls | Missing Mobility |
|---|---|---|---|---|
| Холодный кэш | 12.104 с | 10 | 324 | 0 |
| Повторный | 0.996 с | 3 | 0 | 0 |

Холодные шесть пространственных запросов — coverage и пять компонентов одним
пакетом, не 108 отдельных геоаналитик. Повторный не выполняет их. Полные ответы
идентичны. SQL-чтение каталога и live parity остаются, provenance не обходится.
Значения локальные, при параллельном тестировании, не SLA и не нагрузочный тест.

Последняя пакетная реализация использует восемь работников только после
завершения DB/spatial work. SQLAlchemy session не передаётся worker threads.
Нет wall-clock усечения части кандидатов. Available маршрутные факты кэшируются
с ключом граф/endpoint/mode/exact coordinates; labels и предпочтения не кэшируются.
Кэши ограничены размером/TTL. Отказ источника не заменяется старым score.

## Оставшиеся ограничения

- Medium: нет общего SLA, global admission control и проверки нагрузки.
  При массовых provider timeouts полный ограниченный пакет может выполняться
  дольше 35-секундного client timeout; browser abort не отменяет sync server work.
  Для публичного включения нужны отдельные измерения concurrency/outage и политика
  отказов. Нельзя ускорять это молчаливым изменением состава score.
- Medium: max по районам подвержен различию размеров выборки. Коррекция требует
  отдельной согласованной методики; прямо показаны counts и предупреждение.
- Аренда/PT не поддерживают полный Match. CAR без текущих пробок, входного времени
  и гарантии rush-hour; OSM не оценивает вместимость/качество услуг.
- Наблюдаемая стартовая цена не гарантирует доступную квартиру. Координата —
  ориентир источника, не подтверждённый вход. Нет полного квартирного рынка.
- Настройки браузерные, нет cross-device persistence; шкала/линейная полезность
  не валидированы по фактической удовлетворённости пользователей.
- Low: существующие deprecation warnings Starlette/httpx, Alembic path_separator
  и Next lint; они не исправлялись в рамках Match V2.

## Финальная регрессия

Финальные полные прогоны используют последние версии соответствующего кода;
отдельные 99 backend cases проверены после последней backend-правки, до
последующей правки положения сравнения во frontend. Полный pytest выполнен
на отдельной `mesto_match_audit`, E2E — на `mesto_e2e`, обе БД внутри disposable
Compose PostgreSQL/PostGIS. Production endpoints не используются.

| Команда / проверка | Результат |
|---|---|
| `alembic upgrade head` для `mesto_match_audit` | Успешно; только disposable DB |
| `python -m pytest -p no:cacheprovider -q` на disposable PostgreSQL/PostGIS | 822 passed, 0 failed, 0 skipped; 743.60 с |
| `python -m pytest tests/test_match_v2.py tests/test_recommendations_v2.py -p no:cacheprovider -q` | 99 passed, 0 failed, 0 skipped; 17.02 с |
| `npm.cmd run e2e` после изменения сравнения, до сохранения Foundation | 36 passed, 0 failed, 0 skipped; 4.3 мин |
| Финальный `npm.cmd run e2e` с сохранением Foundation | 36 passed, 0 failed, 0 skipped; 3.0 мин |
| `npm.cmd run lint` из frontend | Exit 0, без ESLint warnings/errors |
| `npx.cmd tsc --noEmit` из frontend | Exit 0 |
| `docker compose -f docker-compose.e2e.yml --project-name mesto-match-v2-test build backend frontend` | Exit 0; Next production build успешен |
| `docker compose -f docker-compose.e2e.yml --project-name mesto-match-v2-test build frontend` после последней UX-правки | Exit 0; production build успешен |
| `git diff --check` | Exit 0 |

Первый backend-запуск на новой пустой audit-БД дал 575 passed / 247 setup errors
из-за неприменённых миграций, 0 skipped. Fixture правильно отказалась считать
пустую БД актуальной. После `alembic upgrade head` запущен полный повтор.
Первый расширенный E2E дал 34 passed / 2 failed: init script заново перезаписывал
черновик при каждом navigation. Исправлен тестовый setup, не продуктовый store;
второй полный прогон дал 36 passed. Неуспешные попытки не скрываются.
По просьбе пользователя работа и текущие процессы затем были остановлены:
полный backend suite дошёл примерно до 87%, но не завершился; build последней
UX-правки тоже был прерван. После «продолжай» начат полный backend повтор и
повторены frontend-проверки. Прерванные команды не считаются успешными.
Промежуточный frontend lint и отдельный `tsc --noEmit` снова завершились с exit 0;
полный E2E также проверил переход к сравнению во viewport на обеих ширинах.
Затем исправлено сохранение старой формы Foundation при переключении флага;
финальный frontend-прогон проверил обе UX-правки вместе.
Первый тест сохранения Foundation дал 34 passed / 2 failed: тест пытался выбрать
school importance до открытия старой формы кнопкой «Настроить приоритеты».
Исправлен test setup. Два сценария 1440/390 px после исправления прошли (19.3 с),
после чего запущен полный повтор; Assertion сохранения значения не удалялся.
Этот полный повтор завершился с 36 passed / 0 failed / 0 skipped. Продуктовый
код после финальных успешных проверок не изменялся; staging остаётся пустым.

## API и UI

Проверены реальный `/api/recommendations/v2`, Foundation
`/api/analytics/match-v2` (overall_match остаётся null), legacy профиль,
recommendations, analytics и карта в smoke/regression сценариях. Новые input
контракты не отправляются в legacy persisted profile schema.

E2E покрывает Onboarding→Results→District, одинаковую сохранённую новую анкету,
сравнение двух кандидатов, возврат к настройкам, включение/выключение флага,
старую education=90 без автоматической конвертации, реальные ответы API,
malformed schema, HTTP 500/retry, late-response cancellation, rent/PT и
responsive layouts. Общий профиль, сравнение и навигация проверены на 1440/390 px;
остальные новые сценарии используют стандартный viewport Playwright.
Существующие тесты также проверяют 360 px. Скриншоты первой карточки inspected на обеих ширинах.

Вердикт UX: пригоден для review и opt-in пилота. Все 108 карточек пока показываются
полным списком; это не окончательная UX-оптимизация и не пользовательский usability
study. При отключении V2 старый пользовательский flow сохраняется.

## Полный список файлов рабочего diff

Общий корень: `C:/Users/Admin/mesto/`. 9 modified tracked, 13 untracked новых
файлов; staging пуст. Следующий список включает реализацию и этот аудит.

```text
 M C:/Users/Admin/mesto/backend/app/main.py
 M C:/Users/Admin/mesto/e2e/mesto-smoke.spec.ts
 M C:/Users/Admin/mesto/e2e/mesto-v2-presentation.spec.ts
 M C:/Users/Admin/mesto/frontend/app/district/page.tsx
 M C:/Users/Admin/mesto/frontend/app/onboarding/page.tsx
 M C:/Users/Admin/mesto/frontend/app/results/page.tsx
 M C:/Users/Admin/mesto/frontend/components/recommendation-panel.tsx
 M C:/Users/Admin/mesto/frontend/lib/onboarding-store.ts
 M C:/Users/Admin/mesto/playwright.config.ts
?? C:/Users/Admin/mesto/backend/app/recommendations/v2_api.py
?? C:/Users/Admin/mesto/backend/app/recommendations/v2_math.py
?? C:/Users/Admin/mesto/backend/app/recommendations/v2_models.py
?? C:/Users/Admin/mesto/backend/app/recommendations/v2_service.py
?? C:/Users/Admin/mesto/backend/tests/test_recommendations_v2.py
?? C:/Users/Admin/mesto/docs/match-recommendations-v2.md
?? C:/Users/Admin/mesto/docs/match-v2-final-audit.md
?? C:/Users/Admin/mesto/e2e/mesto-recommendations-v2.spec.ts
?? C:/Users/Admin/mesto/frontend/components/match-preferences.tsx
?? C:/Users/Admin/mesto/frontend/components/match-recommendations.tsx
?? C:/Users/Admin/mesto/frontend/lib/api/recommendations-v2.ts
?? C:/Users/Admin/mesto/frontend/lib/match-profile.ts
?? C:/Users/Admin/mesto/frontend/types/recommendations-v2.ts
```

Игнорируемые локальные артефакты: `backend/data/raw/match-v2-audit.py`,
`match-v2-audit-results.json`, `match-v2-audit-pytest.log`,
`match-v2-audit-targeted.log`, `match-v2-audit-e2e.log`, Playwright test-results.
Финальные логи после возобновления: `match-v2-audit-pytest-final.log` и
`match-v2-audit-e2e-final.log` в том же ignored-каталоге.
После исправления сохранения Foundation — `match-v2-audit-e2e-last.log`.
Полный последний повтор — `match-v2-audit-e2e-complete.log`, отдельная проверка
переключения — `match-v2-audit-toggle.log`.
Они не staged и не являются готовым содержимым PR. Скрипт проверки использует
только очевидные disposable credentials; реальные пароли/API keys не добавлялись.

В самом аудите изменены: v2_service.py (zero exclusion), backend regression
tests, results/page.tsx (legacy section), frontend API validator, V2 presentation,
E2E cases и документация. Миграции, fixtures, каноническая аналитика, AI,
Recommendation Engine V1 и отменённый redesign не редактировались.

## Diff summary и следующий шаг

В tracked diff: 9 файлов, +34/-16 строк. Также 13 новых untracked файлов
реализации, тестов и документации; `git diff --stat` сам по себе их не включает.
Рабочее дерево намеренно dirty; HEAD не изменён, нового commit нет.
Проверены `git status --short`, `git diff --cached --stat`, `git diff --check`,
`git branch --show-current`, `git rev-parse HEAD` и наличие redesign-ветки.

Следующий шаг — review согласованных ограничений и разрешение на создание
commit/PR. Самостоятельно этот этап не выполнялся. До публичного включения:
нагрузка/concurrency/provider outage, политика отмены серверной работы,
калибровка на пользователях и решение по статистике районных выборок.
