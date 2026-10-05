# Архитектура данных

```text
Внешние источники → адаптеры → проверка → нормализация → PostgreSQL/PostGIS
                                                        ↓
                              детерминированная аналитика → FastAPI → Next.js → Life Report
```

Адаптеры в `backend/app/data_sources` возвращают Pydantic схемы из `app.schemas`. Слой ETL в `backend/app/etl` отвечает за загрузку, проверку и запись. Аналитический код должен читать только нормализованные таблицы, никогда напрямую HTML или API отдельного поставщика. Сейчас реализован контракт адаптера; реальные подключения и расчёты относятся к будущим этапам.

Для импортированных фактов обязательны `source_id`, `source_type`, `source_version`, `fetched_at`, `valid_from`, `valid_to` и `is_synthetic`. Если источник не сообщает срок действия, даты остаются пустыми. `fetched_at` показывает момент получения, а `valid_from` и `valid_to` — период применимости. Синтетические данные маркируются явно и не смешиваются с подтверждёнными фактами без указания происхождения.

Геометрии используют PostGIS и SRID 4326. Координаты API представлены как долгота, затем широта. Числовой скоринг и финансовые выводы должны формироваться версионированными детерминированными формулами. AI может разбирать запрос и объяснять рассчитанный результат, но не генерирует рейтинг.

## Canonical component evidence

`backend/app/analytics/stop_availability/` — внутренний объективный контракт
Stop Availability V1: координата → ближайшее активное реальное OSM наблюдение
`highway=bus_stop` → raw distribution / coverage для переданного набора точек.
Компонент работает параллельно текущему `objective-current-v1`; веса и scoring
не менялись. Grid500 — отдельный RESEARCH_ONLY consumer, не продуктовая методика.
Контракты, Code Map и ограничения: [Stop Availability evidence](stop-availability-evidence.md).

Параллельный внутренний normalized consumer использует
`district-territorial-grid250-v1` и frozen
`stop-availability-krasnoyarsk-relative-v1`: canonical distance → midrank empirical
CDF point utility → равное среднее района, с raw median/p90/coverage объяснениями.
Sampling, reference и point normalizer разделены; текущий MESTO не интегрирован.
Контракт и Code Map: [Stop Availability normalization](stop-availability-normalization.md).

`backend/app/analytics/school/` — внутренний School raw evidence V1:
координата → ближайшее активное OSM наблюдение `amenity=school` → median/p90
и coverage для переданного набора точек. `models.py` задаёт версии и контракты,
`service.py` выполняет точный geography batch search, `aggregation.py` строит
сырой summary, `research.py` использует grid250 только как RESEARCH_USE_FOR_SCHOOL.
School score, production sampler и интеграция в MESTO отсутствуют. Семантика
центров, неоднозначность taxonomy и ограничения: [School evidence](school-evidence.md).
