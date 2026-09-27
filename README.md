# МЕСТО

«Не выбираем квартиру. Моделируем жизнь вокруг неё».

МЕСТО — AI-платформа выбора места для жизни в Красноярске. Текущий MVP использует объяснимые правила без генеративного AI: профиль и жизненный сценарий → Analytics Core → персональные рекомендации → MESTO Score и Future Growth. Реальные объявления показываются только при наличии записей в базе; синтетические данные помечены.

## Архитектура

`Источники → адаптеры/ETL → проверка → PostgreSQL/PostGIS → аналитика → FastAPI → Next.js → Life Report`.

Подробности: [архитектура](docs/architecture.md), [модель данных](docs/data-model.md), [ETL](docs/etl.md), [анкета](docs/onboarding.md), [Analytics Core](docs/analytics-core.md). Код конкретного источника живёт в `backend/app/data_sources`, единые схемы — в `backend/app/schemas.py`, таблицы — в `backend/app/models.py`. Бизнес логика будет работать с едиными моделями, без привязки к сайту или парсеру.

## Пользовательский сценарий

Главная → сохранение сценария жизни → `/analysis` → автоматический запрос Analytics Core и Recommendation Engine → `/results` с ранжированными районами, Match Score, MESTO Score, Future Growth и сигналами → `/district` с реальными слоями карты. Если профиль или API недоступны, результат явно помечается `Demo mode`; демонстрационные значения не подменяют успешный ответ API. Для персонального результата требуется согласие на сохранение анкеты.

Основные модули: `backend/app/analytics` рассчитывает категории и объяснения; `backend/app/analytics/future_growth` оценивает будущие объекты; `backend/app/intelligence` хранит и отдаёт внешние сигналы без автоматического сбора; `backend/app/recommendations` ранжирует районы под профиль. Frontend находится в `frontend/app`, API-клиенты и состояние — в `frontend/lib`. Карта выводит только объекты с координатами из API; расстояния до центра района указаны по прямой, время в пути не моделируется.

## Стек

- Frontend: Next.js, TypeScript, App Router, Tailwind CSS, Radix/shadcn зависимости, Lucide, Recharts, MapLibre, Zustand, Framer Motion.
- Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic.
- Данные: PostgreSQL 16, PostGIS.
- Запуск: Docker Compose.

## Запуск

Нужны Docker Engine и Docker Compose. При необходимости скопируйте `.env.example` в `.env` и задайте локальные значения. `.env` не добавляется в Git. Затем:

```sh
docker compose up --build
```

Страница: http://localhost:3000. Создание сценария: http://localhost:3000/onboarding. Анализ: http://localhost:3000/analysis. Результаты: http://localhost:3000/results. Карта районов: http://localhost:3000/district. API: http://localhost:8000/health. Документация API: http://localhost:8000/docs. При старте backend применяет миграции и импортирует проверенный снимок районов и инфраструктуры OpenStreetMap; предложения жилья загружаются отдельно из подтверждённого источника. Анкета сохраняется в браузере и с согласия пользователя отправляется в API. Экран объявлений запрашивает только записи `source_id=cian`; вымышленные оценки и маркеры жилья не показываются. Координат объявлений в RAW данных нет.

Для локальной разработки без Docker задайте `DATABASE_URL`, установите зависимости из `backend/pyproject.toml`, затем в `backend` выполните `alembic upgrade head`, `python -m app.etl.bootstrap_data` и `uvicorn app.main:app --reload`. Во `frontend` выполните `npm install` и `npm run dev`.

## Проверка

```sh
cd backend && pip install -e '.[test]' && pytest
cd frontend && npm install && npm run lint && npm run build
docker compose config
```

После `docker compose up --build` откройте главную страницу и перейдите к объявлениям. Если база не содержит записей ЦИАН, сначала запустите loader по инструкции ниже. API возвращает `503`, если база недоступна.

### Проверка страницы поиска ЦИАН

Из корня проекта перейдите в `backend`. На Windows используйте Python виртуального окружения, чтобы Playwright был доступен без изменения политики PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -e ".[scrape]"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scrapers\cian.py
```

После активации этого окружения можно запускать `python scrapers/cian.py`. Скрипт открывает страницу продажи квартир в Красноярске, сохраняет снимок в `backend/data/raw/cian/screenshots/`, HTML и метаданные в `backend/data/raw/cian/`, затем записывает проверенные карточки в `backend/data/raw/cian/listings.json`. Неизвестные поля остаются `null`; карточки без URL или подтверждённого города Красноярск пропускаются. Скрипт не обходит CAPTCHA и не отправляет данные в API или базу.

В Git Bash на Windows без активации окружения эквивалентная команда: `./.venv/Scripts/python.exe scrapers/cian.py` из папки `backend`.

## Данные и будущий ETL

### Загрузка RAW объявлений ЦИАН

После `alembic upgrade head` и настройки `DATABASE_URL` из каталога `backend` запустите:

```sh
python -m data.loaders.cian_loader
```

Loader читает `backend/data/raw/cian/listings.json`, проверяет обязательные поля и обновляет существующие записи в `property_offers` по паре `(source_id, external_id)`. В текущей модели `source_id` — идентификатор источника `cian`, а `external_id` — `listing_id` объявления. `created_at` сохраняется при обновлении, `updated_at` меняется. Записи без обязательной для таблицы положительной площади пропускаются с предупреждением; остальные ошибки БД отменяют транзакцию.

`data/raw` предназначен для исходных файлов, `data/processed` — для нормализованных, `data/synthetic` — для демонстрационных. Содержимое этих папок игнорируется Git. Новые адаптеры должны реализовать `SourceAdapter`, валидировать записи Pydantic схемами и сохранять происхождение каждой записи. Реальные данные, лицензии и даты актуальности должны проверяться до импорта. Синтетические записи всегда имеют `is_synthetic=true`.

На странице `/district` работает расчёт соответствия ЖК ответам анкеты. Он использует координаты ЖК ЦИАН и объекты инфраструктуры OpenStreetMap. Оценка от 0 до 1 зависит от бюджета, наличия детей, явно отвеченных предпочтений и точек жизни. Школы, детсады, парки, медучреждения и остановки оцениваются по расстоянию по прямой; это не время в пути. `Покрытие` показывает долю критериев, для которых удалось найти данные. Если координат ЖК или ответов недостаточно, оценка отсутствует. На общем виде реальные административные районы Красноярска окрашены по средней оценке расположенных в них ЖК. После выбора района карта и список показывают оценки отдельных ЖК. Красный — ниже 0,4, жёлтый — от 0,4 до 0,7, зелёный — от 0,7, серый — без оценки. Границы получены из OpenStreetMap и хранятся в PostGIS отдельно от синтетических демонстрационных районов.

### Сбор ЖК и инфраструктуры для карты

Из `backend` после установки Playwright Chromium и применения миграций:

```powershell
.\.venv\Scripts\python.exe -m scrapers.cian --complexes
.\.venv\Scripts\python.exe -m data.loaders.cian_complex_loader
.\.venv\Scripts\python.exe -m data.loaders.osm_poi_loader
.\.venv\Scripts\python.exe -m data.loaders.osm_district_loader
```

Скрипт ЖК обходит страницы публичного поиска Красноярска и прекращает сбор при HTTP ошибке или неполной пагинации. Детальные страницы посещаются последовательно, а прогресс хранится в `backend/data/raw/cian/complexes.json`. Для продолжения после ошибки: `python -m scrapers.cian --resume-complexes`. Не найденные на странице координаты остаются `null`; такие ЖК не получают оценку. Загрузчики делают upsert в существующие таблицы. OSM загрузчик инфраструктуры выполняет один ограниченный запрос Overpass и хранит ответ в `backend/data/raw/osm/poi.json`. Загрузчик границ однократно получает семь административных полигонов через Nominatim с паузой между запросами, кэширует их в `backend/data/raw/osm/krasnoyarsk_districts.json` и связывает ЖК с районами через PostGIS. Содержимое `data/raw` не хранится в Git: на новой базе эти команды надо выполнить отдельно. Результат сбора зависит от доступности сайтов и может измениться.

## Analytics Core

Этап 4.1 добавляет детерминированный расчёт районов на основе существующих записей БД. Формула, ограничения и пример API описаны в [документации](docs/analytics-core.md). Результат явно помечает синтетические данные и отсутствующие категории; вычисления ЖК на frontend остаются отдельным существующим сценарием.
