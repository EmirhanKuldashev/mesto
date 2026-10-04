"""Read-only observations and budget comparisons; never used by Match/MESTO."""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.market.models import (
    AffordabilityResults, MarketAssessment, MarketContext, ObservedAffordability, SampleMetadata,
)

LIMITATIONS = (
    "Это снимок наблюдаемых ЖК и их стартовых цен, не полноценная статистика рынка района.",
    "Стартовая цена не подтверждает наличие подходящей квартиры сейчас, её площадь, число комнат или итоговую стоимость.",
    "Даты относятся к записям источника и не гарантируют дату конкретной цены: при обновлении записи могла сохраниться ранее полученная стартовая цена.",
    "Доля относится только к учтённым ЖК с известной стартовой ценой; это не вероятность найти квартиру и не доля доступного района.",
)


@dataclass(frozen=True)
class MarketSample:
    context: MarketContext
    prices: tuple[Decimal, ...]


def summarize_observations(district_id: int, observations: list[models.ResidentialComplex]) -> MarketSample:
    """Unknown/invalid prices remain unknown observations, never zero prices."""
    prices = tuple(Decimal(str(row.price_from)) for row in observations
                   if row.price_from is not None and Decimal(str(row.price_from)).is_finite()
                   and row.price_from > 0)
    dates = [row.fetched_at for row in observations if row.fetched_at is not None]
    limitations = list(LIMITATIONS)
    if len(prices) == 1:
        limitations.append("Известна стартовая цена только одного ЖК; единичное наблюдение не описывает район.")
    elif 1 < len(prices) < 5:
        limitations.append("Известные стартовые цены представлены малой выборкой ЖК; результат описывает только эти наблюдения.")
    context = MarketContext(
        district_id=district_id, observed_count=len(observations), known_price_count=len(prices),
        unknown_price_count=len(observations) - len(prices),
        min_starting_price=min(prices) if prices else None,
        median_starting_price=median(prices) if prices else None,
        max_starting_price=max(prices) if prices else None,
        source=sorted({row.source_id for row in observations}),
        source_version=sorted({row.source_version for row in observations}),
        snapshot_date_from=min(dates) if dates else None,
        snapshot_date_to=max(dates) if dates else None, limitations=limitations,
    )
    return MarketSample(context=context, prices=prices)


def assess_sample(sample: MarketSample, *, housing_goal: str, purchase_budget: Decimal | None,
                  rent_budget: Decimal | None) -> MarketAssessment:
    context = sample.context
    metadata = SampleMetadata.model_validate(context.model_dump())
    budget = purchase_budget if purchase_budget is not None and purchase_budget.is_finite() and purchase_budget > 0 else None
    count = share = ratio = None
    if housing_goal not in ("buy", "compare"):
        status, reason = "not_applicable", "goal_not_selected"
    elif budget is None:
        status, reason = "unknown", "budget_missing"
    elif not sample.prices:
        status, reason = "unknown", "no_observations"
    else:
        count = sum(price <= budget for price in sample.prices)
        share = count / len(sample.prices)
        ratio = float(budget / context.median_starting_price)
        status, reason = ("known_value", "observed_prices") if count else ("known_zero", "no_matches")
    purchase = ObservedAffordability(
        goal="purchase", status=status, reason_code=reason, budget=budget,
        observation_unit="residential_complex", price_basis="starting_price",
        within_budget_count=count, within_budget_share=share, budget_to_median_ratio=ratio,
        observed_count=metadata.observed_count, known_price_count=metadata.known_price_count,
        unknown_price_count=metadata.unknown_price_count, sample_metadata=metadata,
        limitations=context.limitations,
    )
    # This phase has no real rent ingestion. Purchase observations cannot fill this branch.
    rent_metadata = SampleMetadata(observed_count=0, known_price_count=0, unknown_price_count=0,
                                   source=[], source_version=[], snapshot_date_from=None, snapshot_date_to=None)
    rent_selected = housing_goal in ("rent", "compare")
    rent = ObservedAffordability(
        goal="rent", status="unknown" if rent_selected else "not_applicable",
        reason_code="no_observations" if rent_selected else "goal_not_selected",
        budget=rent_budget, observation_unit="listing", price_basis="monthly_rent",
        within_budget_count=None, within_budget_share=None, budget_to_median_ratio=None,
        observed_count=0, known_price_count=0, unknown_price_count=0, sample_metadata=rent_metadata,
        limitations=["В текущем контракте нет реальных наблюдений аренды по району; цены покупки и demo-аренда не используются."],
    )
    return MarketAssessment(market_context=context, affordability=AffordabilityResults(purchase=purchase, rent=rent))


class MarketService:
    def __init__(self, session: Session):
        self.session = session

    def _sample(self, district_id: int) -> MarketSample:
        district = self.session.get(models.District, district_id)
        if district is None or district.is_synthetic or district.source_type.strip().lower().startswith("synthetic"):
            raise HTTPException(404, "Real district not found")
        observations = list(self.session.scalars(select(models.ResidentialComplex).where(
            models.ResidentialComplex.district_id == district_id,
            models.ResidentialComplex.is_synthetic.is_(False),
            func.lower(func.trim(models.ResidentialComplex.source_type)).not_like("synthetic%"),
            func.lower(models.ResidentialComplex.source_id).not_like("synthetic%"),
        ).order_by(models.ResidentialComplex.id)))
        return summarize_observations(district_id, observations)

    def context(self, district_id: int) -> MarketContext:
        return self._sample(district_id).context

    def assessment(self, profile_id: UUID, district_id: int) -> MarketAssessment:
        profile = self.session.scalar(select(models.UserProfile).where(models.UserProfile.public_id == profile_id))
        if profile is None:
            raise HTTPException(404, "Profile not found")
        if not profile.data_processing_consent:
            raise HTTPException(403, "Profile consent is required")
        return assess_sample(self._sample(district_id), housing_goal=profile.housing_goal,
                             purchase_budget=profile.purchase_budget, rent_budget=profile.rent_budget)
