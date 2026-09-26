"""Load linked future objects and measure their distance to the district geometry."""

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app import models
from app.analytics.future_growth.calculator import FutureGrowthCalculator
from app.analytics.future_growth.models import FutureGrowthResult, FutureObjectEvidence


class FutureGrowthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.calculator = FutureGrowthCalculator()

    def calculate(self, district: models.District) -> FutureGrowthResult:
        location = func.coalesce(models.FutureObject.location, models.FutureObject.geometry)
        boundary = func.coalesce(models.District.geometry, models.District.boundary)
        distance_km = func.ST_Distance(
            cast(location, Geography(geometry_type="POINT", srid=4326)),
            cast(boundary, Geography(geometry_type="MULTIPOLYGON", srid=4326)),
        ) / 1000.0
        query = (select(models.FutureObject, distance_km)
                 .join(models.District, models.District.id == district.id)
                 .where(models.FutureObject.district_id == district.id)
                 .order_by(models.FutureObject.id))
        evidence = [FutureObjectEvidence(
            id=item.id, district_id=item.district_id, name=item.name,
            category=item.category, status=item.status,
            planned_year=item.planned_year, expected_date=item.expected_date,
            confidence=float(item.confidence) if item.confidence is not None else None,
            distance_km=float(distance) if distance is not None else None,
            is_synthetic=bool(item.is_synthetic),
        ) for item, distance in self.session.execute(query)]
        return self.calculator.calculate(district.id, evidence)
