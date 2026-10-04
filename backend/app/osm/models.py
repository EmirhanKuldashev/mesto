"""Immutable OSM history and the explicit current compatibility projection."""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OsmDataset(Base):
    __tablename__ = "osm_datasets"
    __table_args__ = (
        UniqueConstraint("source_id", "scope_id", name="uq_osm_dataset_source_scope"),
        CheckConstraint("source_id = 'osm'", name="ck_osm_dataset_source"),
        ForeignKeyConstraint(["id", "active_snapshot_id"], ["osm_snapshots.dataset_id", "osm_snapshots.id"],
            name="fk_osm_active_same_dataset", use_alter=True, deferrable=True, initially="DEFERRED"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement="ignore_fk")
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.source_id"))
    dataset_key: Mapped[str] = mapped_column(String(100))
    scope_id: Mapped[str] = mapped_column(String(220))
    active_snapshot_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OsmSnapshot(Base):
    __tablename__ = "osm_snapshots"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_osm_snapshot_version"),
        UniqueConstraint("dataset_id", "id", name="uq_osm_snapshot_dataset_id"),
        CheckConstraint("status IN ('CANDIDATE','VALIDATED','ACTIVE','RETIRED','REJECTED')", name="ck_osm_snapshot_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("osm_datasets.id"), index=True)
    version: Mapped[str] = mapped_column(String(220))
    status: Mapped[str] = mapped_column(String(20))
    is_legacy: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sealed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    manifest_checksum: Mapped[str | None] = mapped_column(String(64))
    canonical_checksum: Mapped[str] = mapped_column(String(64))
    query_version: Mapped[str | None] = mapped_column(String(100))
    query_hash: Mapped[str | None] = mapped_column(String(64))
    manifest_json: Mapped[dict | None] = mapped_column(JSONB)
    canonical_json: Mapped[dict] = mapped_column(JSONB)
    build_report: Mapped[dict] = mapped_column(JSONB)
    quality: Mapped[dict] = mapped_column(JSONB)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_base_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activation_review: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OsmSnapshotObservation(Base):
    __tablename__ = "osm_snapshot_observations"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "osm_type", "osm_id", name="uq_osm_snapshot_identity"),
        CheckConstraint("osm_type IN ('node','way','relation') AND osm_id > 0", name="ck_osm_observation_identity"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("osm_snapshots.id"), index=True)
    osm_type: Mapped[str] = mapped_column(String(8))
    osm_id: Mapped[int] = mapped_column(BigInteger)
    eligible: Mapped[bool] = mapped_column(Boolean)
    observation: Mapped[dict] = mapped_column(JSONB)
    # Full historical consumer payload; district assignment is derived, not identity.
    projection: Mapped[dict | None] = mapped_column(JSONB)
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))


class OsmActivePoi(Base):
    __tablename__ = "osm_active_pois"
    __table_args__ = (
        UniqueConstraint("dataset_id", "osm_type", "osm_id", name="uq_osm_active_identity"),
        ForeignKeyConstraint(["dataset_id", "snapshot_id"], ["osm_snapshots.dataset_id", "osm_snapshots.id"], name="fk_osm_projection_dataset"),
        ForeignKeyConstraint(["snapshot_id", "osm_type", "osm_id"],
            ["osm_snapshot_observations.snapshot_id", "osm_snapshot_observations.osm_type", "osm_snapshot_observations.osm_id"], name="fk_osm_projection_observation"),
    )
    poi_id: Mapped[int] = mapped_column(ForeignKey("pois.id"), primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("osm_datasets.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(Integer)
    osm_type: Mapped[str] = mapped_column(String(8))
    osm_id: Mapped[int] = mapped_column(BigInteger)
