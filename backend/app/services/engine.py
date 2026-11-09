from fastapi import HTTPException
from pydantic import ValidationError
from app.agents.roles import ROLES
from app.schemas.conversation import Collected

TRANSITIONS = {
    "created": {"awaiting_consent"},
    "awaiting_consent": {"active", "cancelled", "failed"},
    "active": {"completed", "cancelled", "failed"},
    "completed": set(), "cancelled": set(), "failed": set(),
}


def transition(session, target):
    if target not in TRANSITIONS[session.status]:
        raise HTTPException(409, "Session cannot transition")
    session.status = target


def advance(session, turn):
    role = ROLES[session.role_id]
    if turn.intent in {"cancel", "refuse"}:
        transition(session, "cancelled")
        session.data = {}
        session.consent = False
        session.confirming = False
        session.missing = list(role.required_fields)
        return "The session is cancelled."
    if session.status == "awaiting_consent":
        if turn.intent == "consent":
            session.consent = True
            transition(session, "active")
            return turn.question
        return role.greeting
    if session.confirming and turn.intent == "confirm" and not turn.fields:
        transition(session, "completed")
        return role.completion
    if turn.intent in {"confirm", "consent"}:
        return "Please answer the current question or provide a correction."
    if turn.intent not in {"answer", "correct"}:
        return turn.question
    allowed = dict(role.goals)
    if any(key not in allowed for key in turn.fields):
        raise ValueError("Unexpected model field")
    try:
        validated = Collected.model_validate({**session.data, **turn.fields})
    except ValidationError:
        session.confirming = False
        return "That value is unclear or invalid. Please provide a specific value (date YYYY-MM-DD, time HH:MM)."
    session.data = validated.model_dump(mode="json", exclude_none=True)
    session.missing = [key for key in role.required_fields if not session.data.get(key)]
    session.confirming = not session.missing
    if session.confirming:
        # Summary is constructed from validated data; the model cannot approve itself.
        import json
        return "Please confirm these details, or provide corrections: " + json.dumps(session.data, ensure_ascii=False)
    return turn.question
