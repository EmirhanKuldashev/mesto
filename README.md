# МЕСТО

«Не выбираем квартиру. Моделируем жизнь вокруг неё».

МЕСТО — персональный геоаналитический сервис для выбора жилья и жизненного сценария в Красноярске. На этом этапе создана основа платформы: интерфейс, API, схема данных и контракты источников. Персональный подбор, реальные импортеры и Life Report ещё не реализованы.

## Архитектура

`Источники → адаптеры/ETL → проверка → PostgreSQL/PostGIS → аналитика → FastAPI → Next.js → Life Report`.

Подробности: [docs/architecture.md](docs/architecture.md). Код конкретного источника живёт в `backend/app/data_sources`, единые схемы — в `backend/app/schemas.py`, таблицы — в `backend/app/models.py`. Бизнес логика будет работать с едиными моделями, без привязки к сайту или парсеру.

## Стек

- Frontend: Next.js, TypeScript, App Router, Tailwind CSS, Radix/shadcn зависимости, Lucide, Recharts, MapLibre, Zustand.
- Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic.
- Данные: PostgreSQL 16, PostGIS.
- Запуск: Docker Compose.

## Запуск

Нужны Docker Engine и Docker Compose. При необходимости скопируйте `.env.example` в `.env` и задайте локальные значения. `.env` не добавляется в Git. Затем:

```sh
docker compose up --build
```

Страница: http://localhost:3000. API: http://localhost:8000/health. Документация API: http://localhost:8000/docs. При старте backend применяет миграцию, создаёт расширение PostGIS и таблицы. Главная страница запрашивает `/health` через внутреннюю сеть Compose; зелёное состояние означает, что запрос дошёл до PostgreSQL.

Для локальной разработки без Docker задайте `DATABASE_URL`, установите зависимости из `backend/pyproject.toml`, затем в `backend` выполните `alembic upgrade head` и `uvicorn app.main:app --reload`. Во `frontend` выполните `npm install` и `npm run dev`.

## Проверка

```sh
cd backend && pip install -e '.[test]' && pytest
cd frontend && npm install && npm run lint && npm run build
docker compose config
```

После `docker compose up --build` откройте главную страницу и убедитесь, что она показывает «API и база данных доступны». API возвращает `503`, если база недоступна.

## Данные и будущий ETL

`data/raw` предназначен для исходных файлов, `data/processed` — для нормализованных, `data/synthetic` — для демонстрационных. Содержимое этих папок игнорируется Git. Новые адаптеры должны реализовать `SourceAdapter`, валидировать записи Pydantic схемами и сохранять происхождение каждой записи. Реальные данные, лицензии и даты актуальности должны проверяться до импорта. Синтетические записи всегда имеют `is_synthetic=true`.

Сейчас в репозитории нет расчётного скоринга и нет настоящих данных. Числовые выводы в следующих этапах следует строить только детерминированными расчётами с версией формулы и ссылками на источники. AI допустим только для разбора языка и объяснения уже рассчитанного результата.
