"""Read-only, source-neutral catalogue endpoints."""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import create_session_factory

router = APIRouter(prefix="/api")


def get_session() -> Iterator[Session]:
    factory, engine = create_session_factory()
    try:
        with factory() as session:
            yield session
    finally:
        engine.dispose()


def parse_bbox(bbox: str | None):
    if bbox is None:
        return None
    try:
        west, south, east, north = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(422, "bbox must be west,south,east,north") from exc
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(422, "bbox coordinates are invalid")
    return func.ST_MakeEnvelope(west, south, east, north, 4326)


def catalogue(session: Session, model, *, district_id=None, category=None, min_price=None, max_price=None, bbox=None):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "min_price must not exceed max_price")
    geom_names = [name for name in ("geometry", "centroid", "boundary", "location") if hasattr(model, name)]
    geom_columns = [func.ST_AsGeoJSON(getattr(model, name)).label(name) for name in geom_names]
    query = select(model, *geom_columns).order_by(model.id)
    if district_id is not None:
        if hasattr(model, "district_id"):
            query = query.where(model.district_id == district_id)
        elif model is models.District:
            query = query.where(model.id == district_id)
    if category is not None and hasattr(model, "category"):
        query = query.where(model.category == category)
    price_column = next((getattr(model, name) for name in ("price", "monthly_rent", "price_from") if hasattr(model, name)), None)
    if price_column is not None:
        if min_price is not None:
            query = query.where(price_column >= min_price)
        if max_price is not None:
            query = query.where(price_column <= max_price)
    geometry = next((getattr(model, name) for name in ("geometry", "location", "centroid") if hasattr(model, name)), None)
    envelope = parse_bbox(bbox)
    if envelope is not None and geometry is not None:
        query = query.where(func.ST_Intersects(geometry, envelope))
    output = []
    for row in session.execute(query):
        record = row[0]
        data = {column.name: getattr(record, "metadata_json" if column.name == "metadata" else column.key)
                for column in model.__table__.columns if column.name not in geom_names}
        data.update({name: json.loads(value) if value else None for name, value in zip(geom_names, row[1:])})
        output.append(jsonable_encoder(data))
    return output


@router.get("/districts")
def districts(district_id: int | None = None, bbox: str | None = None, session: Session = Depends(get_session)):
    return catalogue(session, models.District, district_id=district_id, bbox=bbox)


@router.get("/districts/{district_id}")
def district(district_id: int, session: Session = Depends(get_session)):
    rows = catalogue(session, models.District, district_id=district_id)
    if not rows:
        raise HTTPException(404, "District not found")
    return rows[0]


@router.get("/poi")
def poi(district_id: int | None = None, category: str | None = None, bbox: str | None = None,
        session: Session = Depends(get_session)):
    return catalogue(session, models.POI, district_id=district_id, category=category, bbox=bbox)


@router.get("/residential-complexes")
def residential_complexes(district_id: int | None = None, min_price: float | None = Query(default=None, ge=0),
                          max_price: float | None = Query(default=None, ge=0), bbox: str | None = None,
                          session: Session = Depends(get_session)):
    return catalogue(session, models.ResidentialComplex, district_id=district_id, min_price=min_price, max_price=max_price, bbox=bbox)


@router.get("/properties")
def properties(district_id: int | None = None, min_price: float | None = Query(default=None, ge=0),
               max_price: float | None = Query(default=None, ge=0), bbox: str | None = None,
               session: Session = Depends(get_session)):
    return catalogue(session, models.PropertyOffer, district_id=district_id, min_price=min_price, max_price=max_price, bbox=bbox)


@router.get("/rent")
def rent(district_id: int | None = None, min_price: float | None = Query(default=None, ge=0),
         max_price: float | None = Query(default=None, ge=0), bbox: str | None = None,
         session: Session = Depends(get_session)):
    return catalogue(session, models.RentListing, district_id=district_id, min_price=min_price, max_price=max_price, bbox=bbox)


@router.get("/future-objects")
def future_objects(district_id: int | None = None, category: str | None = None, bbox: str | None = None,
                   session: Session = Depends(get_session)):
    return catalogue(session, models.FutureObject, district_id=district_id, category=category, bbox=bbox)


@router.get("/mortgage-programs")
def mortgage_programs(session: Session = Depends(get_session)):
    return catalogue(session, models.MortgageProgram)


@router.get("/data-sources")
def data_sources(session: Session = Depends(get_session)):
    query = select(models.DataSource, models.SourceVersion).join(
        models.SourceVersion, models.DataSource.source_id == models.SourceVersion.source_id
    ).order_by(models.DataSource.source_id, models.SourceVersion.id)
    return [jsonable_encoder({"source_id": source.source_id, "name": source.name,
                              "organization": source.organization, "url": source.url,
                              "source_type": source.source_type, "is_synthetic": source.is_synthetic,
                              "source_version": version.source_version, "fetched_at": version.fetched_at,
                              "record_count": version.record_count, "checksum": version.checksum})
            for source, version in session.execute(query)]
