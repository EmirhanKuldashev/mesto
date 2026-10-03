"""Scoring snapshots belong to explicit analytics requests, not read consumers."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.ai.service import build_context
from app.api import get_session
from app.db import create_session_factory
from app.main import app


@pytest.mark.integration
def test_analysis_consumers_do_not_duplicate_score_snapshots(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            def override_session():
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    yield session

            app.dependency_overrides[get_session] = override_session
            try:
                client = TestClient(app)
                created = client.post("/api/profile", json={
                    "housing_goal": "buy", "purchase_budget": 8000000,
                    "data_processing_consent": True,
                    "preferences": {"education_weight": {
                        "value": 80, "is_answered": True, "source": "user", "confidence": 1,
                    }},
                })
                assert created.status_code == 201, created.text
                public_id = UUID(created.json()["id"])
                request = {"profile_id": str(public_id)}
                assert client.post("/api/analysis/request", json=request).status_code == 202
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    profile_id = session.scalar(select(models.UserProfile.id).where(
                        models.UserProfile.public_id == public_id))
                    district_ids = list(session.scalars(select(models.District.id).where(
                        models.District.is_synthetic.is_(False)).order_by(models.District.id)))
                    assert len(district_ids) > 1

                    def snapshots():
                        return list(session.execute(select(
                            models.DistrictScore.id, models.DistrictScore.district_id,
                            models.DistrictScore.total_score,
                        ).where(models.DistrictScore.profile_id == profile_id)
                            .order_by(models.DistrictScore.id)))

                    # Recommendations also work before any snapshot exists.
                    initial = client.post("/api/recommendations", json=request)
                    assert initial.status_code == 200, initial.text
                    assert initial.json()["recommendations"]
                    assert snapshots() == []

                    scored = client.post("/api/analytics/score", json={
                        **request, "district_ids": district_ids,
                    })
                    assert scored.status_code == 200, scored.text
                    saved = snapshots()
                    assert len(saved) == len(district_ids)
                    assert {row.district_id for row in saved} == set(district_ids)
                    assert {row.id for row in saved} == {row["id"] for row in scored.json()}
                    totals = {row["district"]["id"]: row["score"] for row in scored.json()}
                    assert all(float(row.total_score) == totals[row.district_id] for row in saved)

                    for _ in range(2):
                        recommended = client.post("/api/recommendations", json=request)
                        assert recommended.status_code == 200, recommended.text
                        comparable = lambda response: [
                            {key: value for key, value in item.items() if key != "created_at"}
                            for item in response.json()["recommendations"]
                        ]
                        assert comparable(recommended) == comparable(initial)
                        assert all(item["district_score"] == totals[item["district_id"]]
                                   for item in recommended.json()["recommendations"])
                        context = build_context(session, public_id, district_ids[0])
                        assert context == build_context(session, public_id, district_ids[0])
                        assert context["analytics"] == {
                            key: value for key, value in scored.json()[0].items()
                            if key not in {"id", "created_at"}
                        }
                        assert snapshots() == saved

                    # A second explicit request remains a new historical snapshot.
                    repeated = client.post("/api/analytics/score", json={
                        **request, "district_ids": district_ids,
                    })
                    assert repeated.status_code == 200, repeated.text
                    assert not {row["id"] for row in repeated.json()} & {row.id for row in saved}
                    counts = dict(session.execute(select(
                        models.DistrictScore.district_id, func.count(),
                    ).where(models.DistrictScore.profile_id == profile_id)
                        .group_by(models.DistrictScore.district_id)).all())
                    assert counts == dict.fromkeys(district_ids, 2)
            finally:
                app.dependency_overrides.clear()
                transaction.rollback()
    finally:
        engine.dispose()
