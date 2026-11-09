"""Opt-in checks against real local Ollama; no model mocks or fallback."""
import os
import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_OLLAMA_INTEGRATION") != "1",
        reason="Opt in to real local Ollama with RUN_OLLAMA_INTEGRATION=1",
    ),
]


def settings_for(tmp_path):
    return Settings(
        admin_api_token=secrets.token_urlsafe(48),
        database_url=f"sqlite:///{tmp_path / 'real.db'}",
        _env_file=None,
    )


def authenticated(app, settings):
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer " + settings.admin_api_token.get_secret_value()
    return client


def send(client, sid, message):
    response = client.post(f"/sessions/{sid}/reply", json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def test_real_model_prompt(tmp_path):
    settings = settings_for(tmp_path)
    with httpx.Client(base_url=settings.ollama_url, timeout=90, trust_env=False) as client:
        try:
            tags = client.get("/api/tags")
            tags.raise_for_status()
            assert settings.ollama_model in {
                model["name"] for model in tags.json()["models"]
            }, f"Pull {settings.ollama_model} before running real integration tests"
            response = client.post("/api/generate", json={
                "model": settings.ollama_model,
                "prompt": "Identify yourself briefly as a local AI assistant.",
                "stream": False,
                "options": {"temperature": 0, "num_predict": 64, "num_ctx": 2048},
            })
            response.raise_for_status()
        except httpx.HTTPError as exc:
            pytest.fail(f"Real local Ollama unavailable: {type(exc).__name__}")
        body = response.json()
        assert body.get("done") is True
        assert isinstance(body.get("response"), str) and body["response"].strip()


@pytest.mark.parametrize("role,answers,expected", [
    ("appointment", [
        "I want an annual checkup.",
        "December 20, 2099",
        "10:30 AM",
    ], {
        "appointment_purpose": "annual checkup",
        "preferred_date": "2099-12-20",
        "preferred_time": "10:30:00",
    }),
    ("general", [
        "I am contacting you to request information about clinic opening hours.",
        "Please follow up tomorrow at 10 AM.",
    ], {
        "reason_for_contact": "clinic",
        "preferred_follow_up_time": "10",
    }),
])
def test_real_conversation_and_persistence(tmp_path, role, answers, expected):
    settings = settings_for(tmp_path)
    with authenticated(create_app(settings), settings) as client:
        response = client.post("/sessions", json={"role_id": role})
        assert response.status_code == 201
        obj = response.json()
        sid = obj["id"]
        assert obj["status"] == "awaiting_consent"
        assert not obj["consent"] and not obj["collected_data"]
        assert "AI assistant" in obj["message"]

        obj = send(client, sid, "Yes, I consent.")
        assert obj["status"] == "active" and obj["consent"]
        assert obj["collected_data"] == {}, "Consent must not collect facts"
        assert obj["message"].strip() and obj["message"].count("?") <= 1
        previous_missing = set(obj["missing_fields"])
        for message in answers:
            obj = send(client, sid, message)
            assert obj["status"] == "active", "Must not complete before explicit confirmation"
            assert obj["role_id"] == role
            assert set(obj["missing_fields"]) < previous_missing, obj
            previous_missing = set(obj["missing_fields"])
            assert obj["message"].strip() and obj["message"].count("?") <= 1

        assert obj["confirmation_pending"] and obj["missing_fields"] == []
        for field, value in expected.items():
            actual = obj["collected_data"][field].lower()
            if field in {"preferred_date", "preferred_time"}:
                assert actual == value
            else:
                assert value in actual
        assert client.get(f"/sessions/{sid}/result").status_code == 409
        obj = send(client, sid, "Yes, these details are correct.")
        assert obj["status"] == "completed"
        result = client.get(f"/sessions/{sid}/result")
        assert result.status_code == 200
        saved = result.json()
        assert client.post(f"/sessions/{sid}/reply", json={"message": "Change it"}).status_code == 409

    # New engine/app reads the same SQLite file with no in-memory history.
    with authenticated(create_app(settings), settings) as restarted:
        assert restarted.get(f"/sessions/{sid}/result").json() == saved
        assert restarted.get(f"/sessions/{sid}").json()["status"] == "completed"


def test_real_consent_refusal(tmp_path):
    settings = settings_for(tmp_path)
    with authenticated(create_app(settings), settings) as client:
        sid = client.post("/sessions", json={"role_id": "general"}).json()["id"]
        obj = send(client, sid, "No, I do not consent. Please cancel.")
        assert obj["status"] == "cancelled"
        assert not obj["consent"] and obj["collected_data"] == {}
        assert client.get(f"/sessions/{sid}/result").status_code == 409
