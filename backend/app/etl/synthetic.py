"""Deterministic demonstration adapters. Coordinates are illustrative, not boundaries or listings."""

from datetime import date
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app import models
from app.etl.base import BaseDataAdapter

DISTRICTS = (
    ("Центральный", "centralny", 92.872, 56.015),
    ("Советский", "sovetsky", 93.015, 56.045),
    ("Октябрьский", "oktyabrsky", 92.765, 56.025),
    ("Железнодорожный", "zheleznodorozhny", 92.825, 56.010),
    ("Свердловский", "sverdlovsky", 92.875, 55.965),
    ("Ленинский", "leninsky", 93.015, 55.975),
    ("Кировский", "kirovsky", 92.925, 55.985),
)
POI_CATEGORIES = (
    "education", "kindergarten", "healthcare", "hospital", "pharmacy", "park",
    "sport", "shop", "mall", "transport_stop", "university", "cafe",
)


def point(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon:.6f} {lat:.6f})", srid=4326)


def rectangle(lon: float, lat: float) -> WKTElement:
    x1, x2, y1, y2 = lon - 0.018, lon + 0.018, lat - 0.012, lat + 0.012
    ring = f"{x1} {y1},{x2} {y1},{x2} {y2},{x1} {y2},{x1} {y1}"
    return WKTElement(f"MULTIPOLYGON((({ring})))", srid=4326)


class SyntheticAdapter(BaseDataAdapter):
    model: type

    def load(self, session: Session, records: list[dict[str, Any]]) -> list[Any]:
        instances = [self.model(**record) for record in records]
        session.add_all(instances)
        session.flush()
        return instances


class SyntheticDistrictAdapter(SyntheticAdapter):
    source_id = "synthetic-districts"
    model = models.District

    def fetch(self):
        for i, (name, slug, lon, lat) in enumerate(DISTRICTS):
            yield {"name": name, "slug": slug, "longitude": lon, "latitude": lat,
                   "district_index": i, "population": 75000 + i * 11000, "area_km2": 18 + i * 3}

    def normalize(self, raw, context):
        pop, area = raw["population"], raw["area_km2"]
        return {**self.source_fields(), "name": raw["name"], "slug": raw["slug"],
                "geometry": rectangle(raw["longitude"], raw["latitude"]),
                "centroid": point(raw["longitude"], raw["latitude"]),
                "population": pop, "area_km2": area, "density": round(pop / area, 2)}


class SyntheticPOIAdapter(SyntheticAdapter):
    source_id = "synthetic-poi"
    model = models.POI

    def fetch(self):
        for i in range(250):
            district = i % 7
            _, _, lon, lat = DISTRICTS[district]
            yield {"name": f"Demo POI {i + 1}", "district_index": district,
                   "longitude": round(lon + ((i * 7) % 19 - 9) * 0.001, 6),
                   "latitude": round(lat + ((i * 11) % 17 - 8) * 0.001, 6),
                   "category": POI_CATEGORIES[i % len(POI_CATEGORIES)], "external_id": f"demo-poi-{i + 1:03d}"}

    def normalize(self, raw, context):
        return {**self.source_fields(), "name": raw["name"], "external_id": raw["external_id"],
                "category": raw["category"], "subcategory": "demo", "district_id": context["district_ids"][raw["district_index"]],
                "location": point(raw["longitude"], raw["latitude"]),
                "geometry": point(raw["longitude"], raw["latitude"]), "metadata_json": {"demo": True}}


class SyntheticRealEstateAdapter(SyntheticAdapter):
    source_id = "synthetic-real-estate"

    def fetch(self):
        for i in range(12):
            d = i % 7
            _, _, lon, lat = DISTRICTS[d]
            yield {"name": f"Demo ЖК {i + 1}", "kind": "complex", "district_index": d,
                   "longitude": lon + i * 0.0003, "latitude": lat + i * 0.0002, "index": i}
        for i in range(60):
            d = i % 7
            _, _, lon, lat = DISTRICTS[d]
            yield {"name": f"Demo продажа {i + 1}", "kind": "sale", "district_index": d,
                   "longitude": lon + (i % 9) * 0.0005, "latitude": lat + (i % 7) * 0.0004, "index": i}
        for i in range(80):
            d = i % 7
            _, _, lon, lat = DISTRICTS[d]
            yield {"name": f"Demo аренда {i + 1}", "kind": "rent", "district_index": d,
                   "longitude": lon + (i % 11) * 0.0004, "latitude": lat + (i % 8) * 0.0003, "index": i}

    def normalize(self, raw, context):
        kind, i = raw["kind"], raw["index"]
        base = {**self.source_fields(), "district_id": context["district_ids"][raw["district_index"]],
                "location": point(raw["longitude"], raw["latitude"])}
        if kind == "complex":
            return {**base, "kind": kind, "name": raw["name"], "developer": f"Demo developer {i % 4 + 1}",
                    "building_class": ("comfort", "business")[i % 2], "delivery_date": date(2027 + i % 4, 12, 31),
                    "price_from": 4200000 + i * 120000, "price_per_sqm": 110000 + i * 2500,
                    "available_units": 15 + i * 2, "layouts": [{"rooms": 1}, {"rooms": 2}]}
        if kind == "sale":
            return {**base, "kind": kind, "index": i, "price": 4200000 + i * 145000,
                    "area_sqm": 32 + i % 45, "rooms": 1 + i % 4, "floor": 1 + i % 17,
                    "address": f"Демо адрес, дом {i + 1}", "external_id": f"demo-sale-{i + 1:03d}"}
        return {**base, "kind": kind, "monthly_rent": 22000 + i * 450,
                "area_sqm": 25 + i % 45, "rooms": 1 + i % 3,
                "address": f"Демо аренда, дом {i + 1}", "external_id": f"demo-rent-{i + 1:03d}"}

    def load(self, session: Session, records: list[dict[str, Any]]) -> list[Any]:
        complexes = [models.ResidentialComplex(**{k: v for k, v in r.items() if k != "kind"})
                     for r in records if r["kind"] == "complex"]
        session.add_all(complexes)
        session.flush()
        offers = []
        rents = []
        for record in records:
            if record["kind"] == "sale":
                data = {k: v for k, v in record.items() if k not in ("kind", "index")}
                data["complex_id"] = complexes[record["index"] % len(complexes)].id
                offers.append(models.PropertyOffer(**data))
            elif record["kind"] == "rent":
                rents.append(models.RentListing(**{k: v for k, v in record.items() if k != "kind"}))
        session.add_all(offers + rents)
        session.flush()
        return complexes + offers + rents


class SyntheticFutureAdapter(SyntheticAdapter):
    source_id = "synthetic-future"
    model = models.FutureObject

    def fetch(self):
        for i in range(20):
            _, _, lon, lat = DISTRICTS[i % 7]
            yield {"name": f"Demo будущий объект {i + 1}", "district_index": i % 7,
                   "longitude": lon + i * 0.0002, "latitude": lat + i * 0.0001,
                   "category": ("park", "transport_stop", "education")[i % 3], "index": i}

    def normalize(self, raw, context):
        return {**self.source_fields(), "name": raw["name"], "category": raw["category"],
                "district_id": context["district_ids"][raw["district_index"]],
                "location": point(raw["longitude"], raw["latitude"]), "status": "planned",
                "geometry": point(raw["longitude"], raw["latitude"]),
                "planned_year": 2028 + raw["index"] % 5, "confidence": 0.5,
                "source": "MESTO demo", "source_document": "Synthetic scenario, no official document",
                "source_date": date(2026, 1, 1)}


class SyntheticMortgageAdapter(SyntheticAdapter):
    source_id = "synthetic-mortgage"
    model = models.MortgageProgram

    def fetch(self):
        for i in range(8):
            yield {"name": f"Demo ипотека {i + 1}", "index": i}

    def normalize(self, raw, context):
        i = raw["index"]
        return {**self.source_fields(), "name": raw["name"], "provider": f"Demo bank {i % 3 + 1}",
                "annual_rate": 8 + i * 0.7, "down_payment_percent": 15 + i,
                "max_loan": 6000000 + i * 500000, "requirements": {"demo": True},
                "eligibility": {"demo": True}, "region": "Красноярский край"}
