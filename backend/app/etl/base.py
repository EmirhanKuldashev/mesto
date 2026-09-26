"""Source-neutral four-step ETL contract."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session


class RawRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    district_index: int | None = Field(default=None, ge=0, le=6)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)


class BaseDataAdapter(ABC):
    source_id: str
    source_version = "demo-v1"
    source_type = "synthetic"
    fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    @abstractmethod
    def fetch(self) -> Iterable[dict[str, Any]]:
        """Retrieve source records without database side effects."""

    def validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Reject malformed source records before normalization."""
        return RawRecord.model_validate(raw).model_dump(exclude_none=True)

    @abstractmethod
    def normalize(self, raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Map source fields to a source-independent model."""

    @abstractmethod
    def load(self, session: Session, records: list[dict[str, Any]]) -> list[Any]:
        """Persist normalized records in the caller's transaction."""

    def source_fields(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "source_version": self.source_version,
            "fetched_at": self.fetched_at,
            "is_synthetic": True,
        }
