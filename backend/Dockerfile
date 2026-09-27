FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY data/__init__.py ./data/__init__.py
COPY data/loaders ./data/loaders
COPY data/fixtures ./data/fixtures
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.etl.bootstrap_osm && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
