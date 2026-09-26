from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_health_checks_database():
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value = 1
    with patch("app.main.create_session_factory", return_value=(None, engine)):
        response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    engine.connect.assert_called_once()


def test_health_reports_database_failure():
    with patch("app.main.create_session_factory", side_effect=RuntimeError("offline")):
        response = TestClient(app).get("/health")
    assert response.status_code == 503
