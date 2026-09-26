# МЕСТО

«Не выбираем квартиру. Моделируем жизнь вокруг неё».

МЕСТО — персональный геоаналитический сервис для выбора жилья и жизненного сценария в Красноярске. Работают инфраструктура, слой демонстрационных данных и новый frontend-концепт: landing, 10-шаговая анкета, экран анализа, демонстрационный результат и карта района. Scoring engine, реальные импортеры и Life Report ещё не реализованы.

## Архитектура

`Источники → адаптеры/ETL → проверка → PostgreSQL/PostGIS → аналитика → FastAPI → Next.js → Life Report`.

Подробности: [архитектура](docs/architecture.md), [модель данных](docs/data-model.md), [ETL](docs/etl.md), [анкета](docs/onboarding.md). Код конкретного источника живёт в `backend/app/data_sources`, единые схемы — в `backend/app/schemas.py`, таблицы — в `backend/app/models.py`. Бизнес логика будет работать с едиными моделями, без привязки к сайту или парсеру.

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

Страница: http://localhost:3000. Анкета: http://localhost:3000/onboarding. Демо-результат: http://localhost:3000/results. Карта: http://localhost:3000/district. API: http://localhost:8000/health. Документация API: http://localhost:8000/docs. При старте backend применяет миграции, создаёт расширение PostGIS и таблицы, затем добавляет synthetic данные без дублирования. Анкета сохраняется в браузере. С согласия пользователя она отправляется в существующий API; без backend или согласия открывается демонстрационный результат. Числа, POI, контур района и сценарии на экранах результата и карты иллюстративны.

Для локальной разработки без Docker задайте `DATABASE_URL`, установите зависимости из `backend/pyproject.toml`, затем в `backend` выполните `alembic upgrade head`, `python -m app.etl.seed` и `uvicorn app.main:app --reload`. Во `frontend` выполните `npm install` и `npm run dev`.

## Проверка

```sh
cd backend && pip install -e '.[test]' && pytest
cd frontend && npm install && npm run lint && npm run build
docker compose config
```

После `docker compose up --build` откройте главную страницу и пройдите анкету либо выберите «Посмотреть демо». API возвращает `503`, если база недоступна.

## Данные и будущий ETL

`data/raw` предназначен для исходных файлов, `data/processed` — для нормализованных, `data/synthetic` — для демонстрационных. Содержимое этих папок игнорируется Git. Новые адаптеры должны реализовать `SourceAdapter`, валидировать записи Pydantic схемами и сохранять происхождение каждой записи. Реальные данные, лицензии и даты актуальности должны проверяться до импорта. Синтетические записи всегда имеют `is_synthetic=true`.

Сейчас в репозитории нет расчётного скоринга и нет настоящих данных. Числовые выводы в следующих этапах следует строить только детерминированными расчётами с версией формулы и ссылками на источники. AI допустим только для разбора языка и объяснения уже рассчитанного результата.
