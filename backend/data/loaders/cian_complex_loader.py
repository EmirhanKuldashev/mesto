"""Validate Cian ЖК RAW JSON and upsert existing residential_complexes."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from geoalchemy2.elements import WKTElement
from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models
from app.db import create_session_factory
from data.loaders.osm_district_loader import assign_complex_districts


RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "cian" / "complexes.json"
logger = logging.getLogger(__name__)


class CianComplex(BaseModel):
    complex_id: str = Field(min_length=1, max_length=120)
    source: Literal["cian"]
    url: HttpUrl
    name: str = Field(min_length=2, max_length=200)
    city: Literal["Красноярск"]
    address: str | None = Field(default=None, max_length=250)
    latitude: float | None = Field(default=None, ge=55, le=57)
    longitude: float | None = Field(default=None, ge=91, le=95)
    price_from: float | None = Field(default=None, gt=0)
    parsed_at: AwareDatetime

    @model_validator(mode="after")
    def check_identity(self):
        if self.url.scheme != "https" or self.url.host != self.complex_id:
            raise ValueError("ЖК URL and complex_id must match a Cian subdomain")
        if not self.complex_id.startswith("zhk-") or not self.complex_id.endswith(".cian.ru"):
            raise ValueError("ЖК must have a Cian complex subdomain")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("ЖК coordinates must be both present or both absent")
        return self


def load_cian_complexes(session: Session, path: Path = RAW_PATH) -> dict[str, int]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, list) or not payload:
        raise ValueError("CIAN ЖК RAW file must contain a nonempty JSON array")
    records = {}
    for index, item in enumerate(payload, start=1):
        try:
            complex_item = CianComplex.model_validate(item)
        except ValidationError as exc:
            raise ValueError(f"Invalid ЖК record {index}: {exc}") from exc
        if complex_item.complex_id in records:
            raise ValueError(f"Duplicate ЖК complex_id: {complex_item.complex_id}")
        records[complex_item.complex_id] = complex_item

    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == "cian"))
    if source is None:
        session.add(models.DataSource(
            source_id="cian", source_type="real_estate_portal", name="ЦИАН",
            url="https://www.cian.ru/", is_synthetic=False,
        ))
        session.flush()
    checksum = hashlib.sha256(raw).hexdigest()
    version_name = f"complex-{checksum[:20]}"
    version = session.scalar(select(models.SourceVersion).where(
        models.SourceVersion.source_id == "cian", models.SourceVersion.source_version == version_name,
    ))
    if version is None:
        session.add(models.SourceVersion(
            source_id="cian", source_version=version_name, checksum=checksum,
            fetched_at=max(item.parsed_at for item in records.values()), record_count=len(records),
        ))

    table = models.ResidentialComplex.__table__
    created = updated = 0
    for item in records.values():
        exists = session.scalar(select(models.ResidentialComplex.id).where(
            models.ResidentialComplex.source_id == "cian",
            models.ResidentialComplex.external_id == item.complex_id,
        )) is not None
        values = {
            "source_id": "cian", "source_type": "real_estate_portal",
            "source_version": version_name, "fetched_at": item.parsed_at,
            "is_synthetic": False, "external_id": item.complex_id,
            "name": item.name, "url": str(item.url), "address": item.address,
        }
        if item.price_from is not None:
            values["price_from"] = item.price_from
        if item.latitude is not None and item.longitude is not None:
            values["location"] = WKTElement(f"POINT({item.longitude} {item.latitude})", srid=4326)
        statement = insert(table).values(**values).on_conflict_do_update(
            constraint="uq_residential_complex_source_external",
            set_={key: value for key, value in values.items() if key not in ("source_id", "external_id")},
        )
        session.execute(statement)
        created += int(not exists)
        updated += int(exists)
    session.flush()
    assign_complex_districts(session)
    logger.info("Cian ЖК: read=%s created=%s updated=%s", len(records), created, updated)
    return {"read": len(records), "created": created, "updated": updated}


def main() -> None:
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            print(load_cian_complexes(session))
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
