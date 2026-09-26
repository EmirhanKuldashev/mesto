"""Validate Cian RAW JSON and upsert it into existing property_offers."""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models
from app.db import create_session_factory


RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "cian" / "listings.json"
SOURCE_ID = "cian"  # Existing SourceFields convention: provider ID, not listing ID.
SOURCE_TYPE = "real_estate_portal"
logger = logging.getLogger(__name__)


class CianListing(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    listing_id: str = Field(pattern=r"^\d+$")
    source: Literal["cian"]
    url: HttpUrl
    title: str | None = None
    price: Decimal = Field(gt=0)
    rooms: int | None = Field(default=None, ge=0)
    area: Decimal = Field(gt=0)
    floor: int | None = Field(default=None, ge=0)
    address: str | None = Field(default=None, max_length=250)
    city: Literal["Красноярск"]
    parsed_at: AwareDatetime

    @field_validator("price", "area", mode="before")
    @classmethod
    def require_numeric_json(cls, value):
        if type(value) not in (int, float):
            raise ValueError("price and area must be JSON numbers")
        return value

    @model_validator(mode="after")
    def check_url_identity(self):
        host = self.url.host
        if host != "cian.ru" and not host.endswith(".cian.ru"):
            raise ValueError("URL must be on cian.ru")
        if self.url.scheme != "https" or not re.fullmatch(
            rf"/sale/flat/{re.escape(self.listing_id)}/?", self.url.path
        ):
            raise ValueError("URL must identify this Cian sale listing")
        return self


@dataclass(frozen=True)
class LoadResult:
    read: int
    created: int
    updated: int
    skipped: int


def load_cian_json(session: Session, path: Path = RAW_PATH) -> LoadResult:
    """Load one RAW file into the current transaction; caller owns commit/rollback."""
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Cian JSON: {path}") from exc
    if not isinstance(payload, list):
        raise ValueError("Cian RAW file must contain a JSON array")

    records: dict[str, CianListing] = {}
    skipped = 0
    for position, item in enumerate(payload, start=1):
        try:
            record = CianListing.model_validate(item)
        except ValidationError as exc:
            skipped += 1
            logger.warning("Skipping invalid Cian record %s: %s", position, exc.errors(include_url=False))
            continue
        previous = records.get(record.listing_id)
        if previous is not None:
            if previous != record:
                raise ValueError(f"Conflicting duplicate listing_id in RAW file: {record.listing_id}")
            skipped += 1
            continue
        records[record.listing_id] = record
    if not records:
        raise ValueError("Cian RAW file contains no valid listings")

    checksum = hashlib.sha256(raw_bytes).hexdigest()
    source_version = f"raw-{checksum[:20]}"
    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == SOURCE_ID))
    if source is None:
        session.add(models.DataSource(
            source_id=SOURCE_ID, source_type=SOURCE_TYPE, name="ЦИАН",
            url="https://www.cian.ru/", is_synthetic=False,
        ))
        session.flush()
    version = session.scalar(select(models.SourceVersion).where(
        models.SourceVersion.source_id == SOURCE_ID,
        models.SourceVersion.source_version == source_version,
    ))
    if version is None:
        session.add(models.SourceVersion(
            source_id=SOURCE_ID, source_version=source_version,
            fetched_at=max(record.parsed_at for record in records.values()),
            checksum=checksum, record_count=len(records),
        ))

    created = updated = 0
    table = models.PropertyOffer.__table__
    for record in records.values():
        identity = (models.PropertyOffer.source_id == SOURCE_ID,
                    models.PropertyOffer.external_id == record.listing_id)
        exists = session.scalar(select(models.PropertyOffer.id).where(*identity)) is not None
        values = {
            "source": record.source,
            "source_id": SOURCE_ID,
            "source_type": SOURCE_TYPE,
            "source_version": source_version,
            "fetched_at": record.parsed_at,
            "is_synthetic": False,
            "external_id": record.listing_id,
            "url": str(record.url),
            "title": record.title,
            "city": record.city,
            "price": record.price,
            "area_sqm": record.area,
            "rooms": record.rooms,
            "floor": record.floor,
            "address": record.address,
        }
        statement = insert(table).values(**values).on_conflict_do_update(
            constraint="uq_property_offers_source_external",
            set_={**{key: value for key, value in values.items()
                     if key not in ("source_id", "external_id")},
                  "updated_at": func.clock_timestamp()},
        )
        session.execute(statement)
        updated += int(exists)
        created += int(not exists)

    logger.info("Cian RAW: read=%s created=%s updated=%s skipped=%s",
                len(payload), created, updated, skipped)
    return LoadResult(read=len(payload), created=created, updated=updated, skipped=skipped)


def main() -> None:
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            result = load_cian_json(session)
        print(result)
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
