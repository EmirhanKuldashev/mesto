"""Select all available districts and rank their existing analytics signals for a profile."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.analytics.service import AnalyticsService
from app.recommendations.explanation import RecommendationExplanation
from app.recommendations.models import DistrictRecommendation, MatchProfile
from app.recommendations.ranking import personal_match


class RecommendationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.analytics = AnalyticsService(session)
        self.explanations = RecommendationExplanation()

    def recommend(self, profile_id: UUID) -> list[DistrictRecommendation]:
        profile = self.session.scalar(select(models.UserProfile).where(models.UserProfile.public_id == profile_id))
        if profile is None:
            raise HTTPException(404, "Profile not found")
        if not profile.data_processing_consent:
            raise HTTPException(403, "Profile consent is required")
        preferences = self.session.scalar(select(models.UserPreferences).where(
            models.UserPreferences.user_profile_id == profile.id))
        points = list(self.session.scalars(select(models.LifePoint).where(
            models.LifePoint.user_profile_id == profile.id)))
        work_priority = max((min(1.0, (point.importance or 0) / 10 *
                                 (point.visits_per_week or 0) / 7) for point in points
                             if point.kind in ("work", "partner_work")), default=0.0)
        match_profile = MatchProfile(
            household_type=profile.household_type,
            children_ages=tuple(child["age"] for child in (profile.children or [])
                                if isinstance(child, dict) and isinstance(child.get("age"), int)),
            housing_goal=profile.housing_goal,
            has_purchase_budget=bool(profile.purchase_budget),
            has_rent_budget=bool(profile.rent_budget),
            planning_horizon=profile.planning_horizon,
            transport_preferences=tuple(profile.transport_preferences or []),
            home_values=tuple(profile.home_values or []),
            preferences=preferences.preference_values or {} if preferences else {},
            life_point_kinds=tuple(point.kind for point in points),
            work_point_priority=work_priority,
        )
        district_ids = list(self.session.scalars(select(models.District.id).order_by(models.District.id)))
        if not district_ids:
            return []
        # AnalyticsService owns the score formula and snapshot persistence.
        scores = self.analytics.score(profile_id, district_ids)
        recommendations: list[DistrictRecommendation] = []
        now = datetime.now(timezone.utc)
        for district in scores:
            match = personal_match(district.categories, match_profile)
            if match.score is None:
                continue
            reasons, warnings = self.explanations.generate(district, match_profile, match)
            recommendations.append(DistrictRecommendation(
                district_id=district.district.id, district_name=district.district.name,
                profile_id=profile_id, match_score=match.score,
                district_score=district.score, future_score=district.future_score,
                rank=1, reasons=reasons, warnings=warnings, created_at=now,
            ))
        recommendations.sort(key=lambda item: (-item.match_score,
                              -(item.district_score if item.district_score is not None else -1),
                              item.district_id))
        return [item.model_copy(update={"rank": index})
                for index, item in enumerate(recommendations, start=1)]
