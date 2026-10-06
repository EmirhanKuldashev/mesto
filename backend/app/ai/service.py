"""Build factual model input from the database, cache by facts and questionnaire."""
import hashlib
import json
from collections import OrderedDict, deque
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from geoalchemy2 import Geography
from sqlalchemy import cast, func, select

from app import models
from app.analytics.service import AnalyticsService
from app.profile_api import find_profile, profile_data
from app.ai.provider import OrcaConfig, generate_summary
from app.market.service import MarketService

PROFILE_FIELDS = (
    "household_type", "adults_count", "children_count", "children", "housing_goal",
    "purchase_budget", "initial_payment", "comfortable_monthly_payment", "rent_budget",
    "planning_horizon", "car_availability", "transport_preferences", "preferences",
    "price_vs_time", "today_vs_future", "car_dependency", "future_changes", "home_values",
    "good_home_text", "commute_minutes",
)


def public_preferences(data: dict) -> dict:
    result = {key: data.get(key) for key in PROFILE_FIELDS}
    partner = data.get("partner")
    result["partner"] = {key: partner.get(key) for key in
        ("transport_preferences", "preferences", "life_goals")} if partner else None
    return result


def build_context(session, profile_id: UUID, district_id: int) -> dict:
    profile = find_profile(session, profile_id)
    if not profile.data_processing_consent:
        raise HTTPException(403, "Для персональной сводки необходимо согласие на обработку данных.")
    district = session.get(models.District, district_id)
    if district is None:
        raise HTTPException(404, "Район не найден.")
    if district.is_synthetic:
        raise HTTPException(409, "Сводка доступна только для реальных районов.")
    preferences = public_preferences(profile_data(session, profile))
    preferences["life_points"] = []
    for point in session.scalars(select(models.LifePoint).where(models.LifePoint.user_profile_id == profile.id)):
        distance = None
        if district.centroid is not None:
            distance = session.scalar(select(func.ST_Distance(
                cast(models.LifePoint.location, Geography(srid=4326)),
                cast(models.District.centroid, Geography(srid=4326))))
                .select_from(models.LifePoint).join(models.District, models.District.id == district_id)
                .where(models.LifePoint.id == point.id))
        preferences["life_points"].append({"type": point.kind, "owner_type": point.owner_type,
            "importance": point.importance, "frequency_per_week": point.visits_per_week,
            "straight_line_distance_to_district_center_km": round(distance / 1000, 1) if distance is not None else None})
    poi_rows = session.execute(select(models.POI.category, func.count(), func.max(models.POI.fetched_at))
        .where(models.POI.district_id == district_id, models.POI.is_synthetic.is_(False))
        .group_by(models.POI.category).order_by(models.POI.category)).all()
    housing = MarketService(session).assessment(profile_id, district_id)
    score = AnalyticsService(session).calculate(profile_id, [district_id])[0]
    if score.is_synthetic:
        raise HTTPException(409, "В оценке присутствуют демонстрационные данные; сводка недоступна.")
    return jsonable_encoder({"questionnaire": preferences,
        "district": {"name": district.name, "area_km2": district.area_km2,
            "population": district.population, "boundary_fetched_at": district.fetched_at,
            "infrastructure": [{"category": category, "count": count, "fetched_at": date}
                               for category, count, date in poi_rows],
            "housing": housing.model_dump(mode="json")},
        "analytics": score.model_dump(mode="json"),
        "limitations": ["Цены и инфраструктура — датированные снимки, не данные в реальном времени.",
            "Нет маршрутов, времени поездки и подтверждения наличия квартир.",
            "MESTO V2 score/current_score — равновесный индекс остановок, школ, детских садов, медицины и парков; "
            "бюджет и предпочтения в него не входят. Growth и future_score — отдельные будущие показатели.",
            "confidence — покрытие пяти обязательных компонентов MESTO, не полнота данных и не качество района.",
            "ObservedAffordability не входит в MESTO или Match: ranking_eligible=false. "
            "within_budget_share описывает выборку стартовых цен ЖК, не вероятность найти квартиру.",
            "Для жилья учитывай limitations и диапазон дат записей: дата конкретной price_from не гарантируется."]})


class SummaryRuntime:
    """Bounded per-process cache, request budget and duplicate-call protection."""
    def __init__(self):
        self.lock = Lock()
        self.cache = OrderedDict()
        self.requests = deque()
        self.inflight = set()

    def check_rate(self, profile_id):
        now = monotonic()
        with self.lock:
            while self.requests and self.requests[0][0] < now - 60:
                self.requests.popleft()
            if len(self.requests) >= 60 or sum(p == profile_id for _, p in self.requests) >= 20:
                raise HTTPException(429, "Слишком много запросов. Повторите через минуту.", headers={"Retry-After": "60"})
            self.requests.append((now, profile_id))

    def generate(self, context, config, profile_id, district_id, generator=generate_summary):
        digest = hashlib.sha256(json.dumps(["v1", config.model, str(profile_id), district_id, context],
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            hit = self.cache.get(digest)
            if hit and monotonic() - hit[0] < 300:
                return {**hit[1], "cached": True}
            if digest in self.inflight or len(self.inflight) >= 3:
                raise HTTPException(429, "Сводка ещё готовится. Повторите запрос через несколько секунд.", headers={"Retry-After": "5"})
            self.inflight.add(digest)
        try:
            result = {"district_id": district_id, "summary": generator(context, config),
                      "generated_at": datetime.now(timezone.utc).isoformat(), "cached": False}
            with self.lock:
                self.cache[digest] = (monotonic(), result)
                while len(self.cache) > 256:
                    self.cache.popitem(last=False)
            return result
        finally:
            with self.lock:
                self.inflight.discard(digest)


runtime = SummaryRuntime()
