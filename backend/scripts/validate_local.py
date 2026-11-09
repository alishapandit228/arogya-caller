"""Real TCP API + Ollama + SQLite validation. Run from the repository root.

Uses only synthetic data and an isolated temporary database/token. No download,
network exposure, mocks, or existing backend process is required.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
# Only fixed local Python/Uvicorn arguments are launched.
import subprocess  # nosec B404
import sys
import tempfile
import time

import httpx


ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    # Validate configuration through the backend's own settings (including local URL).
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.config import Settings
    token = secrets.token_urlsafe(48)
    settings = Settings(admin_api_token=token, ollama_model=model)
    with httpx.Client(base_url=settings.ollama_url, timeout=95, trust_env=False) as ollama:
        tags = ollama.get("/api/tags")
        tags.raise_for_status()
        require(model in {m["name"] for m in tags.json()["models"]},
                f"Selected model {model} is not present locally")
        prompt = ollama.post("/api/generate", json={
            "model": model, "prompt": "Identify yourself briefly as a local AI assistant.",
            "stream": False, "options": {"temperature": 0, "num_predict": 64},
        })
        prompt.raise_for_status()
        require(prompt.json().get("done") and prompt.json().get("response", "").strip(),
                "Real prompt did not finish")
    print(f"Real Ollama prompt passed: {model}", flush=True)

    # Ask the OS for a free loopback port, then launch only our own server.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="arogya-validation-") as directory:
        db = Path(directory) / "validation.db"
        env = dict(os.environ)
        env.update(ADMIN_API_TOKEN=token, OLLAMA_MODEL=model,
                   OLLAMA_URL=settings.ollama_url, DATABASE_URL=f"sqlite:///{db}",
                   TRUSTED_ORIGINS="[]")

        def start():
            # Fixed executable/module, no shell or user-provided command.
            return subprocess.Popen(  # nosec B603
                [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
                 "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(port),
                 "--workers", "1", "--no-access-log"],
                cwd=ROOT, env=env,
            )

        def ready(client, process):
            for _ in range(100):
                require(process.poll() is None, "Validation server exited")
                try:
                    if client.get("/health").status_code == 200:
                        return
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            raise RuntimeError("Validation server failed to become ready")

        def stop(process):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)

        saved = {}
        process = start()
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=100,
                              trust_env=False) as client:
                ready(client, process)
                require(client.get("/sessions").status_code == 401, "Missing authentication accepted")
                client.headers["Authorization"] = "Bearer " + token
                roles = {
                    "appointment": ([
                        "I want an annual checkup.", "December 20, 2099", "10:30 AM"
                    ], {"appointment_purpose", "preferred_date", "preferred_time"}),
                    "general": ([
                        "I need information about clinic opening hours.", "Tomorrow at 10 AM"
                    ], {"reason_for_contact", "preferred_follow_up_time"}),
                }
                for role, (answers, required) in roles.items():
                    created = client.post("/sessions", json={"role_id": role})
                    require(created.status_code == 201, created.text)
                    obj = created.json()
                    sid = obj["id"]
                    require(obj["status"] == "awaiting_consent", "Consent not requested")

                    def send(message):
                        response = client.post(f"/sessions/{sid}/reply", json={"message": message})
                        require(response.status_code == 200, response.text)
                        result = response.json()
                        print(json.dumps({"role": role, "response": result}, ensure_ascii=False), flush=True)
                        require(result["role_id"] == role, "Role changed")
                        return result

                    obj = send("Yes, I consent.")
                    require(obj["status"] == "active" and obj["consent"] and not obj["collected_data"],
                            "Consent transition invalid")
                    for answer in answers:
                        obj = send(answer)
                        require(obj["status"] == "active", "Premature completion")
                    require(obj["confirmation_pending"] and not obj["missing_fields"],
                            "Facts not fully extracted; inspect printed questions")
                    require(required <= obj["collected_data"].keys(), "Required fields missing")
                    require(obj["collected_data"].keys() <= required | ({"user_name"} if role == "general" else set()),
                            "Unexpected role fields")
                    if role == "appointment":
                        require(obj["collected_data"]["preferred_date"] == "2099-12-20", "Wrong date")
                        require(obj["collected_data"]["preferred_time"] == "10:30:00", "Wrong time")
                    require(client.get(f"/sessions/{sid}/result").status_code == 409,
                            "Unconfirmed result exposed")
                    obj = send("Yes, these details are correct.")
                    require(obj["status"] == "completed", "Confirmation failed")
                    response = client.get(f"/sessions/{sid}/result")
                    require(response.status_code == 200, response.text)
                    saved[sid] = response.json()
                    with sqlite3.connect(db) as connection:
                        row = connection.execute(
                            "SELECT status, data FROM sessions WHERE id = ?", (sid,)
                        ).fetchone()
                    require(row is not None and row[0] == "completed", "SQLite status differs")
                    require(json.loads(row[1]) == saved[sid]["data"], "SQLite data differs")

            stop(process)
            process = start()
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False,
                              headers={"Authorization": "Bearer " + token}) as client:
                ready(client, process)
                for sid, expected in saved.items():
                    response = client.get(f"/sessions/{sid}/result")
                    require(response.status_code == 200 and response.json() == expected,
                            "Result did not survive backend process restart")
            print("PASS: both real API flows, structured results, SQLite rows, and process restart persistence.")
        finally:
            stop(process)


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
