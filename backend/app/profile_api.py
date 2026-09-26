"""Consent-aware profile and onboarding endpoints. No score is calculated here."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.api import get_session
from app.profile_schemas import AnalysisRequestCreate, LifePointUpsert, PreferencesInput, ProfileCreate

router = APIRouter(prefix="/api")


def geometry(longitude: float, latitude: float) -> WKTElement:
    return WKTElement(f"POINT({longitude:.8f} {latitude:.8f})", srid=4326)


def find_profile(session: Session, public_id: UUID) -> models.UserProfile:
    profile = session.scalar(select(models.UserProfile).where(models.UserProfile.public_id == public_id))
    if profile is None:
        raise HTTPException(404, "Profile not found")
    return profile


def life_point_data(session: Session, point: models.LifePoint) -> dict:
    longitude, latitude = session.execute(select(func.ST_X(point.location), func.ST_Y(point.location))).one()
    return {"id": point.id, "type": point.kind, "name": point.label, "owner_type": point.owner_type,
            "longitude": longitude, "latitude": latitude, "importance": point.importance,
            "frequency_per_week": point.visits_per_week}


def profile_data(session: Session, profile: models.UserProfile) -> dict:
    preferences = session.scalar(select(models.UserPreferences).where(models.UserPreferences.user_profile_id == profile.id))
    partner = session.scalar(select(models.PartnerProfile).where(models.PartnerProfile.user_profile_id == profile.id))
    points = session.scalars(select(models.LifePoint).where(models.LifePoint.user_profile_id == profile.id).order_by(models.LifePoint.id)).all()
    partner_data = None
    if partner:
        work_point = None
        if partner.work_location is not None:
            lon, lat = session.execute(select(func.ST_X(partner.work_location), func.ST_Y(partner.work_location))).one()
            work_point = {"longitude": lon, "latitude": lat}
        partner_data = {"name": partner.name, "work_point": work_point,
                        "transport_preferences": partner.transport_preferences,
                        "preferences": partner.preferences, "life_goals": partner.life_goals}
    return jsonable_encoder({
        "id": str(profile.public_id), "name": profile.name, "household_type": profile.household_type,
        "adults_count": profile.adults_count, "children_count": profile.children_count,
        "children": profile.children, "housing_goal": profile.housing_goal,
        "purchase_budget": profile.purchase_budget, "initial_payment": profile.initial_payment,
        "comfortable_monthly_payment": profile.comfortable_monthly_payment,
        "rent_budget": profile.rent_budget, "planning_horizon": profile.planning_horizon,
        "car_availability": profile.car_availability, "transport_preferences": profile.transport_preferences,
        "preferences": preferences.preference_values if preferences else None,
        "price_vs_time": profile.price_vs_time, "today_vs_future": profile.today_vs_future,
        "car_dependency": profile.car_dependency, "future_changes": profile.future_changes,
        "home_values": profile.home_values, "good_home_text": profile.good_home_text,
        "partner": partner_data, "life_points": [life_point_data(session, point) for point in points],
        "data_processing_consent": profile.data_processing_consent,
        "consent_at": profile.consent_at,
    })


def save_profile(payload: ProfileCreate, session: Session) -> dict:
    profile = models.UserProfile(
        name=payload.name, household_size=payload.adults_count + payload.children_count,
        household_type=payload.household_type, adults_count=payload.adults_count,
        children_count=payload.children_count, children=[child.model_dump() for child in payload.children],
        housing_goal=payload.housing_goal, purchase_budget=payload.purchase_budget,
        initial_payment=payload.initial_payment,
        comfortable_monthly_payment=payload.comfortable_monthly_payment,
        rent_budget=payload.rent_budget, planning_horizon=payload.planning_horizon,
        car_availability=payload.car_availability,
        transport_preferences=payload.transport_preferences, future_changes=payload.future_changes,
        home_values=payload.home_values, good_home_text=payload.good_home_text,
        price_vs_time=payload.preferences.price_vs_time.value,
        today_vs_future=payload.preferences.today_vs_future.value,
        car_dependency=payload.preferences.car_dependency.value, data_processing_consent=True,
        consent_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    session.flush()
    preference_values = payload.preferences.model_dump()
    session.add(models.UserPreferences(
        user_profile_id=profile.id,
        purchase_mode="either" if payload.housing_goal == "compare" else payload.housing_goal,
        preference_values=preference_values,
        weights={name: item["value"] for name, item in preference_values.items() if item["is_answered"]},
        **{name: item["value"] for name, item in preference_values.items()
           if name not in ("price_vs_time", "today_vs_future", "car_dependency")},
    ))
    partner_profile = None
    if payload.partner:
        partner = payload.partner
        partner_profile = models.PartnerProfile(
            user_profile_id=profile.id, name=partner.name,
            work_location=geometry(partner.work_point.longitude, partner.work_point.latitude) if partner.work_point else None,
            transport_preferences=partner.transport_preferences,
            preferences={name: partner.preferences[name].model_dump() if name in partner.preferences else
                         {"value": None, "is_answered": False, "source": "default", "confidence": 0}
                         for name in PreferencesInput.model_fields},
            life_goals=partner.life_goals,
        )
        session.add(partner_profile)
        session.flush()
    for item in payload.life_points:
        session.add(models.LifePoint(
            user_profile_id=profile.id, kind=item.type, label=item.name,
            owner_type=item.owner_type,
            primary_user_id=profile.id if item.owner_type == "primary_user" else None,
            partner_profile_id=partner_profile.id if item.owner_type == "partner" else None,
            location=geometry(item.longitude, item.latitude), importance=item.importance,
            visits_per_week=item.frequency_per_week,
        ))
    session.commit()
    return profile_data(session, profile)


@router.post("/profile", status_code=201)
def create_profile(payload: ProfileCreate, session: Session = Depends(get_session)):
    return save_profile(payload, session)


@router.get("/profile/{profile_id}")
def get_profile(profile_id: UUID, session: Session = Depends(get_session)):
    return profile_data(session, find_profile(session, profile_id))


@router.post("/couple/profile", status_code=201)
def create_couple_profile(payload: ProfileCreate, session: Session = Depends(get_session)):
    if payload.household_type != "couple" or payload.partner is None:
        raise HTTPException(422, "Couple profile requires household_type=couple and partner")
    return save_profile(payload, session)


@router.post("/life-points", status_code=201)
def upsert_life_point(payload: LifePointUpsert, session: Session = Depends(get_session)):
    profile = find_profile(session, payload.profile_id)
    partner = session.scalar(select(models.PartnerProfile).where(models.PartnerProfile.user_profile_id == profile.id))
    if payload.owner_type == "partner" and partner is None:
        raise HTTPException(422, "Partner life point requires a partner profile")
    if payload.id is not None:
        point = session.get(models.LifePoint, payload.id)
        if point is None or point.user_profile_id != profile.id:
            raise HTTPException(404, "Life point not found")
    else:
        point = models.LifePoint(user_profile_id=profile.id)
        session.add(point)
    point.kind = payload.type
    point.owner_type = payload.owner_type
    point.primary_user_id = profile.id if payload.owner_type == "primary_user" else None
    point.partner_profile_id = partner.id if payload.owner_type == "partner" else None
    point.label = payload.name
    point.location = geometry(payload.longitude, payload.latitude)
    point.importance = payload.importance
    point.visits_per_week = payload.frequency_per_week
    session.commit()
    return life_point_data(session, point)


def create_analysis_snapshot(session: Session, profile: models.UserProfile) -> dict:
    """Capture detached JSON values so later edits cannot change this request."""
    current = profile_data(session, profile)
    partner = current.pop("partner")
    life_points = current.pop("life_points")
    preferences = current.pop("preferences")
    versions = session.scalars(select(models.SourceVersion).order_by(
        models.SourceVersion.source_id, models.SourceVersion.fetched_at.desc(), models.SourceVersion.id.desc())).all()
    latest_versions = {}
    for version in versions:
        latest_versions.setdefault(version.source_id, version)
    return {
        "profile_snapshot": current,
        "partner_snapshot": partner or {},
        "life_points_snapshot": life_points,
        "preferences_snapshot": preferences or {},
        "data_version_snapshot": {"sources": [jsonable_encoder({
            "id": version.id, "source_id": version.source_id, "source_version": version.source_version,
            "fetched_at": version.fetched_at, "valid_from": version.valid_from,
            "valid_to": version.valid_to, "checksum": version.checksum,
            "record_count": version.record_count,
        }) for version in latest_versions.values()]},
    }


@router.post("/analysis/request", status_code=202)
def request_analysis(payload: AnalysisRequestCreate, session: Session = Depends(get_session)):
    profile = find_profile(session, payload.profile_id)
    if not profile.data_processing_consent or profile.consent_at is None:
        raise HTTPException(403, "Data processing consent is required")
    request = models.AnalysisRequest(user_profile_id=profile.id, status="pending",
                                     **create_analysis_snapshot(session, profile))
    session.add(request)
    session.commit()
    session.refresh(request)
    return {"id": request.id, "profile_id": str(profile.public_id), "status": request.status,
            "created_at": request.created_at, "user_score": request.user_score,
            "partner_score": request.partner_score, "family_score": request.family_score,
            "profile_snapshot": request.profile_snapshot, "partner_snapshot": request.partner_snapshot,
            "life_points_snapshot": request.life_points_snapshot,
            "preferences_snapshot": request.preferences_snapshot,
            "data_version_snapshot": request.data_version_snapshot}
