import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_app_session
from app.models import Setor

SESSION_COOKIE = "salutem_session"
CSRF_COOKIE = "salutem_csrf"
_password_hasher = PasswordHash.recommended()
_dummy_hash = _password_hasher.hash("not-a-real-password")
_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempts_lock = threading.Lock()
_MAX_ATTEMPTS = 5
_ATTEMPT_WINDOW_SECONDS = 15 * 60


@dataclass(frozen=True)
class CurrentSector:
    id: int
    name: str
    profile: Literal["solicitante", "almoxarifado", "administrador"]
    leader_name: str | None

    @property
    def display_name(self) -> str:
        return self.leader_name or self.name


def allow_login_attempt(remote: str, sector_id: int) -> bool:
    key = f"{remote}:{sector_id}"
    now = time.monotonic()
    with _attempts_lock:
        history = _attempts[key]
        while history and now - history[0] > _ATTEMPT_WINDOW_SECONDS:
            history.popleft()
        return len(history) < _MAX_ATTEMPTS


def clear_login_attempts(remote: str, sector_id: int) -> None:
    with _attempts_lock:
        _attempts.pop(f"{remote}:{sector_id}", None)


def record_login_failure(remote: str, sector_id: int) -> None:
    key = f"{remote}:{sector_id}"
    now = time.monotonic()
    with _attempts_lock:
        history = _attempts[key]
        while history and now - history[0] > _ATTEMPT_WINDOW_SECONDS:
            history.popleft()
        history.append(now)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("A senha deve conter pelo menos 12 caracteres.")
    if len(password) > 128:
        raise ValueError("A senha não pode exceder 128 caracteres.")
    return _password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        valid = _password_hasher.verify(password, encoded or _dummy_hash)
    except (ValueError, TypeError):
        valid = False
    return bool(encoded) and bool(valid)


def _serializer() -> URLSafeTimedSerializer:
    secret = get_settings().app_session_secret
    if not secret or len(secret.get_secret_value()) < 32:
        raise HTTPException(
            status_code=503,
            detail="Sessão não configurada. Defina APP_SESSION_SECRET com pelo menos 32 caracteres.",
        )
    return URLSafeTimedSerializer(secret.get_secret_value(), salt="salutem-session-v1")


def issue_session(response: Response, sector: Setor) -> str:
    settings = get_settings()
    csrf = secrets.token_urlsafe(32)
    payload = {
        "sector_id": sector.id,
        "profile": sector.perfil,
        "credential_version": sha256(sector.senha_hash.encode()).hexdigest(),
        "csrf": csrf,
        "issued_at": int(time.time()),
    }
    token = _serializer().dumps(payload)
    max_age = settings.app_session_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.app_cookie_secure,
        samesite=settings.app_cookie_samesite,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.app_cookie_secure,
        samesite=settings.app_cookie_samesite,
        path="/",
    )
    return csrf


def clear_session(response: Response) -> None:
    settings = get_settings()
    for name, httponly in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(
            name,
            path="/",
            httponly=httponly,
            secure=settings.app_cookie_secure,
            samesite=settings.app_cookie_samesite,
        )


def require_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Token CSRF ausente ou inválido.")


def get_current_sector(
    request: Request, session: Session = Depends(get_app_session)
) -> CurrentSector:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    try:
        payload = _serializer().loads(token, max_age=get_settings().app_session_hours * 3600)
    except SignatureExpired as error:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre novamente.") from error
    except BadSignature as error:
        raise HTTPException(status_code=401, detail="Sessão inválida. Entre novamente.") from error

    csrf = request.cookies.get(CSRF_COOKIE, "")
    if not csrf or not hmac.compare_digest(csrf, str(payload.get("csrf", ""))):
        raise HTTPException(status_code=401, detail="Sessão inválida. Entre novamente.")
    sector = session.get(Setor, payload.get("sector_id"))
    if not sector or not sector.ativo:
        raise HTTPException(status_code=401, detail="Setor inativo. Entre novamente.")
    current_version = sha256(sector.senha_hash.encode()).hexdigest()
    if not hmac.compare_digest(current_version, str(payload.get("credential_version", ""))):
        raise HTTPException(status_code=401, detail="Senha alterada. Entre novamente.")
    if payload.get("profile") != sector.perfil:
        raise HTTPException(status_code=401, detail="Perfil alterado. Entre novamente.")
    return CurrentSector(
        id=sector.id,
        name=sector.nome,
        profile=sector.perfil,  # type: ignore[arg-type]
        leader_name=sector.lider_nome,
    )


def require_warehouse(
    sector: CurrentSector = Depends(get_current_sector),
) -> CurrentSector:
    if sector.profile not in {"almoxarifado", "administrador"}:
        raise HTTPException(status_code=403, detail="Acesso restrito ao Almoxarifado.")
    return sector


def require_admin(
    sector: CurrentSector = Depends(get_current_sector),
) -> CurrentSector:
    if sector.profile != "administrador":
        raise HTTPException(status_code=403, detail="Acesso restrito ao Administrador.")
    return sector
