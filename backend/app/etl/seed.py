"""Idempotent demo seed; run with ``python -m app.etl.seed`` after migrations."""

import hashlib
import json

from sqlalchemy import select

from app import models
from app.db import create_session_factory
from app.etl.synthetic import (
    DISTRICTS, SyntheticDistrictAdapter, SyntheticFutureAdapter,
    SyntheticMortgageAdapter, SyntheticPOIAdapter, SyntheticRealEstateAdapter,
)

ADAPTERS = (
    SyntheticDistrictAdapter(), SyntheticPOIAdapter(), SyntheticRealEstateAdapter(),
    SyntheticFutureAdapter(), SyntheticMortgageAdapter(),
)


def seed(session) -> dict[str, int]:
    counts = {}
    context = {}
    for adapter in ADAPTERS:
        raw = list(adapter.fetch())
        checksum = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        existing = session.scalar(select(models.SourceVersion).where(
            models.SourceVersion.source_id == adapter.source_id,
            models.SourceVersion.source_version == adapter.source_version,
        ))
        if existing:
            if existing.checksum != checksum:
                raise ValueError(f"Source version changed without a version bump: {adapter.source_id}")
            counts[adapter.source_id] = existing.record_count or len(raw)
        else:
            source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == adapter.source_id))
            if source is None:
                session.add(models.DataSource(source_id=adapter.source_id, source_type="synthetic",
                                              name=adapter.source_id, organization="MESTO demo",
                                              is_synthetic=True))
                session.flush()
            version = models.SourceVersion(source_id=adapter.source_id, source_version=adapter.source_version,
                                           fetched_at=adapter.fetched_at, checksum=checksum, record_count=len(raw))
            session.add(version)
            session.flush()
            records = [adapter.normalize(adapter.validate(item), context) for item in raw]
            instances = adapter.load(session, records)
            for instance in instances:
                session.add(models.DataQuality(source_version_id=version.id, record_type=instance.__tablename__,
                                               entity_type=instance.__tablename__, entity_id=instance.id,
                                               completeness=1, freshness=1, confidence=0.5,
                                               forecast_share=1 if isinstance(instance, models.FutureObject) else 0,
                                               limitations=["Synthetic demonstration data"],
                                               warnings=["Not a real observation"]))
            counts[adapter.source_id] = len(raw)
        if isinstance(adapter, SyntheticDistrictAdapter):
            by_name = {row.name: row.id for row in session.scalars(select(models.District).where(
                models.District.source_id == adapter.source_id)).all()}
            context["district_ids"] = [by_name[name] for name, _, _, _ in DISTRICTS]
    session.flush()
    return counts


def main() -> None:
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            print(seed(session))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
