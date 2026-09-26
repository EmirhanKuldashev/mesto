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
    return {"id": point.id, "type": point.kind, "name": point.label,
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
        "preferences": {name: getattr(preferences, name) for name in PreferencesInput.model_fields} if preferences else None,
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
        price_vs_time=payload.price_vs_time, today_vs_future=payload.today_vs_future,
        car_dependency=payload.car_dependency, data_processing_consent=True,
        consent_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    session.flush()
    session.add(models.UserPreferences(user_profile_id=profile.id,
                                       purchase_mode="either" if payload.housing_goal == "compare" else payload.housing_goal,
                                       weights=payload.preferences.model_dump(), **payload.preferences.model_dump()))
    if payload.partner:
        partner = payload.partner
        session.add(models.PartnerProfile(
            user_profile_id=profile.id, name=partner.name,
            work_location=geometry(partner.work_point.longitude, partner.work_point.latitude) if partner.work_point else None,
            transport_preferences=partner.transport_preferences, preferences=partner.preferences,
            life_goals=partner.life_goals,
        ))
    for item in payload.life_points:
        session.add(models.LifePoint(
            user_profile_id=profile.id, kind=item.type, label=item.name,
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
    if payload.id is not None:
        point = session.get(models.LifePoint, payload.id)
        if point is None or point.user_profile_id != profile.id:
            raise HTTPException(404, "Life point not found")
    else:
        point = models.LifePoint(user_profile_id=profile.id)
        session.add(point)
    point.kind = payload.type
    point.label = payload.name
    point.location = geometry(payload.longitude, payload.latitude)
    point.importance = payload.importance
    point.visits_per_week = payload.frequency_per_week
    session.commit()
    return life_point_data(session, point)


@router.post("/analysis/request", status_code=202)
def request_analysis(payload: AnalysisRequestCreate, session: Session = Depends(get_session)):
    profile = find_profile(session, payload.profile_id)
    if not profile.data_processing_consent or profile.consent_at is None:
        raise HTTPException(403, "Data processing consent is required")
    request = models.AnalysisRequest(user_profile_id=profile.id, status="pending")
    session.add(request)
    session.commit()
    session.refresh(request)
    return {"id": request.id, "profile_id": str(profile.public_id), "status": request.status,
            "created_at": request.created_at, "user_score": request.user_score,
            "partner_score": request.partner_score, "family_score": request.family_score}
