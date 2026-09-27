"""Read existing records, calculate a score, and persist an auditable snapshot."""

from dataclasses import asdict
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.analytics.explanation.generator import ExplanationGenerator
from app.analytics.future_growth.service import FutureGrowthService
from app.analytics.models import CategoryScores, DistrictReference, DistrictScoreResponse
from app.analytics.scoring.calculators import (
    DistrictFacts, InfrastructureCalculator, MarketCalculator,
    TransportCalculator, lifestyle_score,
)
from app.analytics.scoring.engine import ScoringEngine
from app.analytics.scoring.weights import CALCULATION_VERSION
from app.intelligence.schemas import SignalImpactResponse


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.engine = ScoringEngine()
        self.infrastructure = InfrastructureCalculator()
        self.transport = TransportCalculator()
        self.market = MarketCalculator()
        self.future = FutureGrowthService(session)
        self.explanations = ExplanationGenerator()

    def _facts(self, district: models.District) -> DistrictFacts:
        facts = DistrictFacts(
            population=district.population,
            area_km2=float(district.area_km2) if district.area_km2 else None,
            synthetic=bool(district.is_synthetic),
        )
        category_aliases = {
            "school": "education", "clinic": "healthcare",
            "hospital": "healthcare", "bus_stop": "transport_stop",
        }
        for poi in self.session.scalars(select(models.POI).where(models.POI.district_id == district.id)):
            facts.poi_counts[category_aliases.get(poi.category, poi.category)] += 1
            facts.synthetic |= bool(poi.is_synthetic)
        for offer in self.session.scalars(select(models.PropertyOffer).where(models.PropertyOffer.district_id == district.id)):
            if offer.price and offer.price > 0:
                facts.sale_prices.append(float(offer.price))
            facts.synthetic |= bool(offer.is_synthetic)
        for rent in self.session.scalars(select(models.RentListing).where(models.RentListing.district_id == district.id)):
            if rent.monthly_rent and rent.monthly_rent > 0:
                facts.rent_prices.append(float(rent.monthly_rent))
            facts.synthetic |= bool(rent.is_synthetic)
        return facts

    def score(self, profile_id: UUID, district_ids: list[int]) -> list[DistrictScoreResponse]:
        profile = self.session.scalar(select(models.UserProfile).where(models.UserProfile.public_id == profile_id))
        if profile is None:
            raise HTTPException(404, "Profile not found")
        if not profile.data_processing_consent:
            raise HTTPException(403, "Profile consent is required")
        districts = {district.id: district for district in self.session.scalars(
            select(models.District).where(models.District.id.in_(district_ids)))}
        if len(districts) != len(district_ids):
            raise HTTPException(404, "District not found")
        preference_row = self.session.scalar(select(models.UserPreferences).where(
            models.UserPreferences.user_profile_id == profile.id))
        preferences = preference_row.preference_values if preference_row else {}
        results = []
        for district_id in district_ids:
            district = districts[district_id]
            facts = self._facts(district)
            future_result = self.future.calculate(district)
            facts.synthetic |= any(factor.is_synthetic for factor in future_result.factors)
            facts.synthetic |= any(signal.is_demo for signal in future_result.signal_impacts)
            categories = {
                "infrastructure": self.infrastructure.calculate(facts),
                "transport": self.transport.calculate(facts),
                "future_growth": future_result.score,
                "market": self.market.calculate(facts, goal=profile.housing_goal,
                                                purchase_budget=float(profile.purchase_budget) if profile.purchase_budget else None,
                                                rent_budget=float(profile.rent_budget) if profile.rent_budget else None),
            }
            lifestyle, unsupported = lifestyle_score(preferences, categories)
            categories["lifestyle"] = lifestyle
            combined = self.engine.calculate(categories)
            current_score, future_score = self.engine.calculate_outlook(categories)
            score = future_score if future_score is not None else current_score
            confidence = round(combined.coverage * (0.5 if facts.synthetic else 1.0), 3) if score is not None else 0
            reasons, warnings = self.explanations.generate(categories, facts,
                                                           unsupported_preferences=unsupported, future_result=future_result)
            row = models.DistrictScore(
                profile_id=profile.id, district_id=district_id, total_score=score,
                current_score=current_score, future_score=future_score,
                future_factors=[factor.model_dump(mode="json") for factor in future_result.factors]
                    + [{"kind": "external_signal", **asdict(signal)}
                       for signal in future_result.signal_impacts],
                lifestyle_score=lifestyle, infrastructure_score=categories["infrastructure"],
                transport_score=categories["transport"], future_growth_score=categories["future_growth"],
                market_score=categories["market"], confidence=confidence,
                calculation_version=CALCULATION_VERSION, is_synthetic=facts.synthetic,
            )
            self.session.add(row)
            self.session.flush()
            results.append(DistrictScoreResponse(
                id=row.id,
                district=DistrictReference(id=district.id, name=district.name, slug=district.slug),
                score=score, current_score=current_score, future_score=future_score,
                future_growth_score=future_result.score, future_factors=future_result.factors,
                future_impacts=future_result.category_impacts,
                external_signal_impacts=[SignalImpactResponse(**asdict(signal))
                                         for signal in future_result.signal_impacts],
                categories=CategoryScores(**categories),
                confidence=confidence, reasons=reasons, warnings=warnings,
                is_synthetic=facts.synthetic, calculation_version=CALCULATION_VERSION,
                created_at=row.created_at,
            ))
        self.session.commit()
        return results
