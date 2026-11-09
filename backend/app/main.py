import secrets
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agents.roles import ROLES
from app.core.config import Settings
from app.models.session import Base, Conversation
from app.schemas.conversation import CreateSession, Reply
from app.services.engine import advance, transition
from app.services.ollama import ModelError, Ollama


def create_app(settings=None, model=None):
    settings = settings or Settings()
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 10})
    factory = sessionmaker(engine, expire_on_commit=False)
    model = model or Ollama(settings)
    lock = threading.Lock()
    histories = OrderedDict()

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        yield
        histories.clear()
        engine.dispose()

    app = FastAPI(title="Arogya Caller", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=settings.trusted_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 8192:
                return JSONResponse({"error": "Request body too large"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"error": "Invalid request"}, status_code=422)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    bearer = HTTPBearer(auto_error=False)

    def auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), settings.admin_api_token.get_secret_value().encode()
        ):
            raise HTTPException(401, "Invalid authentication", headers={"WWW-Authenticate": "Bearer"})

    def db():
        with factory() as session:
            yield session

    def find(session, session_id):
        item = session.get(Conversation, str(session_id))
        if item is None:
            raise HTTPException(404, "Session not found")
        return item

    def view(item, message=None):
        result = {"id": item.id, "role_id": item.role_id, "status": item.status,
                  "consent": item.consent, "collected_data": item.data,
                  "missing_fields": item.missing, "confirmation_pending": item.confirming,
                  "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}
        if message is not None:
            result["message"] = message
        return result

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/roles", dependencies=[Depends(auth)])
    def roles():
        return [{"id": r.id, "name": r.name, "description": r.description,
                 "required_fields": r.required_fields} for r in ROLES.values()]

    @app.post("/sessions", status_code=201, dependencies=[Depends(auth)])
    def create(payload: CreateSession, session=Depends(db)):
        role = ROLES.get(payload.role_id)
        if role is None:
            raise HTTPException(422, "Unknown role")
        item = Conversation(id=str(uuid4()), role_id=role.id, status="created",
                            data={}, missing=list(role.required_fields), consent=False)
        transition(item, "awaiting_consent")
        session.add(item)
        session.commit()
        return view(item, role.greeting)

    @app.get("/sessions", dependencies=[Depends(auth)])
    def listing(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=100000), session=Depends(db)):
        return [view(item) for item in session.scalars(select(Conversation).order_by(
            Conversation.created_at.desc(), Conversation.id).offset(offset).limit(limit))]

    @app.get("/sessions/{session_id}", dependencies=[Depends(auth)])
    def get(session_id: UUID, session=Depends(db)):
        return view(find(session, session_id))

    @app.get("/sessions/{session_id}/result", dependencies=[Depends(auth)])
    def result(session_id: UUID, session=Depends(db)):
        item = find(session, session_id)
        if item.status != "completed":
            raise HTTPException(409, "Result is not confirmed")
        return {"id": item.id, "role_id": item.role_id, "data": item.data}

    @app.post("/sessions/{session_id}/cancel", dependencies=[Depends(auth)])
    def cancel(session_id: UUID, session=Depends(db)):
        if not lock.acquire(blocking=False):
            raise HTTPException(429, "Conversation engine busy")
        try:
            item = find(session, session_id)
            transition(item, "cancelled")
            item.data = {}
            item.consent = False
            item.confirming = False
            histories.pop(item.id, None)
            session.commit()
            return view(item, "The session is cancelled.")
        finally:
            lock.release()

    @app.post("/sessions/{session_id}/reply", dependencies=[Depends(auth)])
    def reply(session_id: UUID, payload: Reply, session=Depends(db)):
        if not lock.acquire(blocking=False):
            raise HTTPException(429, "Conversation engine busy")
        try:
            item = find(session, session_id)
            if item.status not in {"awaiting_consent", "active"}:
                raise HTTPException(409, "Session is closed")
            if item.turns >= 40:
                transition(item, "failed")
                histories.pop(item.id, None)
                session.commit()
                raise HTTPException(409, "Conversation turn limit reached")
            role = ROLES[item.role_id]
            context = {"role": role.name, "instructions": role.instructions, "goals": dict(role.goals),
                       "status": item.status, "data": item.data, "missing": item.missing,
                       "confirmation_pending": item.confirming}
            try:
                turn = model.turn(context, histories.get(item.id, []), payload.message)
                # Model intent alone cannot authorize consent or final confirmation.
                explicit = payload.message.strip().lower().rstrip(".!")
                accepted = {"yes", "yes, i consent", "i consent", "i agree",
                            "yes, these details are correct", "confirm", "confirmed"}
                if turn.intent in {"consent", "confirm"} and explicit not in accepted:
                    turn.intent = "unclear"
                    turn.fields = {}
                message = advance(item, turn)
            except (ModelError, ValueError):
                transition(item, "failed")
                histories.pop(item.id, None)
                session.commit()
                raise HTTPException(503, "AI service unavailable or invalid response; start a new session") from None
            item.turns += 1
            if item.status in {"completed", "cancelled"}:
                histories.pop(item.id, None)
            else:
                history = histories.pop(item.id, [])
                history.extend([{"role": "user", "content": payload.message},
                                {"role": "assistant", "content": message}])
                histories[item.id] = history[-8:]
                while len(histories) > 100:
                    histories.popitem(last=False)
            session.commit()
            return view(item, message)
        finally:
            lock.release()

    return app
