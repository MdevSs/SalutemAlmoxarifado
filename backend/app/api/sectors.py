from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_app_session
from app.core.security import (
    CurrentSector,
    clear_session,
    get_current_sector,
    hash_password,
    issue_session,
    require_admin,
    require_csrf,
    verify_password,
)
from app.models import Setor
from app.schemas.contracts import (
    AuthResponse,
    CsrfResponse,
    CurrentUser,
    LoginRequest,
    SectorCreate,
    SectorOption,
    SectorRead,
    SectorUpdate,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])
sectors_router = APIRouter(prefix="/sectors", tags=["Setores"])


@router.get("/sectors", response_model=list[SectorOption])
def login_options(session: Session = Depends(get_app_session)) -> list[SectorOption]:
    rows = session.scalars(
        select(Setor).where(Setor.ativo.is_(True)).order_by(func.lower(Setor.nome))
    ).all()
    return [
        SectorOption(id=row.id, name=row.nome, profile=row.perfil, leader_name=row.lider_nome)
        for row in rows
    ]


@router.get("/csrf", response_model=CsrfResponse)
def csrf_token(request: Request, response: Response) -> CsrfResponse:
    from secrets import token_urlsafe

    from app.core.config import get_settings
    from app.core.security import CSRF_COOKIE, SESSION_COOKIE, _serializer

    settings = get_settings()
    value = ""
    session_cookie = request.cookies.get(SESSION_COOKIE)
    if session_cookie:
        try:
            claims = _serializer().loads(session_cookie, max_age=settings.app_session_hours * 3600)
            claim = claims.get("csrf")
            if isinstance(claim, str):
                value = claim
        except (BadSignature, SignatureExpired, TypeError, ValueError):
            value = ""
    value = value or request.cookies.get(CSRF_COOKIE, "") or token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        value,
        max_age=settings.app_session_hours * 3600,
        httponly=False,
        secure=settings.app_cookie_secure,
        samesite=settings.app_cookie_samesite,
        path="/",
    )
    return CsrfResponse(csrf_token=value)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    _csrf: None = Depends(require_csrf),
    session: Session = Depends(get_app_session),
) -> AuthResponse:
    from app.core.security import allow_login_attempt, record_login_failure

    remote = request.client.host if request.client else "unknown"
    if not allow_login_attempt(remote, payload.sector_id):
        raise HTTPException(
            status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente."
        )
    sector = session.get(Setor, payload.sector_id)
    if (
        not sector
        or not sector.ativo
        or not verify_password(
            payload.password.get_secret_value(), sector.senha_hash if sector else None
        )
    ):
        record_login_failure(remote, payload.sector_id)
        raise HTTPException(status_code=401, detail="Setor ou senha inválidos.")
    from app.core.security import clear_login_attempts

    clear_login_attempts(remote, payload.sector_id)
    csrf = issue_session(response, sector)
    return AuthResponse(
        user=CurrentUser(
            sector_id=sector.id,
            sector_name=sector.nome,
            profile=sector.perfil,
            leader_name=sector.lider_nome,
        ),
        csrf_token=csrf,
    )


@router.get("/me", response_model=CurrentUser)
def me(sector: CurrentSector = Depends(get_current_sector)) -> CurrentUser:
    return CurrentUser(
        sector_id=sector.id,
        sector_name=sector.name,
        profile=sector.profile,
        leader_name=sector.leader_name,
    )


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    _sector: CurrentSector = Depends(get_current_sector),
    _csrf: None = Depends(require_csrf),
) -> Response:
    clear_session(response)
    response.status_code = 204
    return response


@sectors_router.get("", response_model=list[SectorRead])
def list_sectors(
    _admin: CurrentSector = Depends(require_admin),
    session: Session = Depends(get_app_session),
) -> list[SectorRead]:
    rows = session.scalars(
        select(Setor).where(Setor.perfil != "administrador").order_by(func.lower(Setor.nome))
    ).all()
    return [
        SectorRead(
            id=row.id,
            name=row.nome,
            profile=row.perfil,
            leader_name=row.lider_nome,
            active=row.ativo,
        )
        for row in rows
    ]


@sectors_router.post("", response_model=SectorRead, status_code=201)
def create_sector(
    payload: SectorCreate,
    _admin: CurrentSector = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    session: Session = Depends(get_app_session),
) -> SectorRead:
    password = payload.password.get_secret_value()
    try:
        encoded = hash_password(password)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if payload.profile == "almoxarifado" and payload.name != "Almoxarifado":
        raise HTTPException(
            status_code=422, detail="O acesso único do Almoxarifado deve usar esse nome fixo."
        )
    if payload.profile == "almoxarifado" and payload.leader_name:
        raise HTTPException(status_code=422, detail="Almoxarifado não usa líder designado.")
    if payload.profile == "solicitante" and not payload.leader_name:
        raise HTTPException(
            status_code=422, detail="Setor solicitante exige o nome do líder designado."
        )
    sector = Setor(
        nome=payload.name,
        perfil=payload.profile,
        lider_nome=payload.leader_name,
        senha_hash=encoded,
    )
    session.add(sector)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe um setor com esse nome ou o acesso único do Almoxarifado já foi criado.",
        ) from error
    session.refresh(sector)
    return SectorRead(
        id=sector.id,
        name=sector.nome,
        profile=sector.perfil,
        leader_name=sector.lider_nome,
        active=sector.ativo,
    )


@sectors_router.patch("/{sector_id}", response_model=SectorRead)
def update_sector(
    sector_id: int,
    payload: SectorUpdate,
    _admin: CurrentSector = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    session: Session = Depends(get_app_session),
) -> SectorRead:
    sector = session.get(Setor, sector_id)
    if not sector:
        raise HTTPException(status_code=404, detail="Setor não encontrado.")
    if sector.perfil == "administrador":
        raise HTTPException(
            status_code=409, detail="A conta Administrador é provisionada pelo CLI do servidor."
        )
    if sector.perfil == "almoxarifado" and payload.active is False:
        active_warehouse = session.scalar(
            select(func.count())
            .select_from(Setor)
            .where(Setor.perfil == "almoxarifado", Setor.ativo.is_(True))
        )
        if active_warehouse <= 1:
            raise HTTPException(
                status_code=409, detail="Mantenha ao menos um acesso ativo ao Almoxarifado."
            )
    values = payload.model_dump(exclude_unset=True)
    new_password = payload.new_password.get_secret_value() if payload.new_password else None
    values.pop("new_password", None)
    if "active" in values and values["active"] is None:
        raise HTTPException(status_code=422, detail="O estado ativo/inativo não pode ser nulo.")
    if "name" in values and values["name"] is None:
        raise HTTPException(status_code=422, detail="O nome do setor não pode ser nulo.")
    if new_password:
        try:
            sector.senha_hash = hash_password(new_password)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if "leader_name" in values and sector.perfil == "almoxarifado":
        raise HTTPException(status_code=422, detail="Almoxarifado não tem líder designado.")
    if sector.perfil == "almoxarifado" and values.get("name", sector.nome) != "Almoxarifado":
        raise HTTPException(
            status_code=422, detail="O acesso único deve permanecer com o nome Almoxarifado."
        )
    if sector.perfil == "solicitante" and values.get("leader_name", sector.lider_nome) is None:
        raise HTTPException(
            status_code=422, detail="Mantenha um líder designado para o setor solicitante."
        )
    if "name" in values:
        sector.nome = values["name"]
    if "leader_name" in values:
        sector.lider_nome = values["leader_name"]
    if "active" in values:
        sector.ativo = values["active"]
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="O nome do setor já está em uso.") from error
    session.refresh(sector)
    return SectorRead(
        id=sector.id,
        name=sector.nome,
        profile=sector.perfil,
        leader_name=sector.lider_nome,
        active=sector.ativo,
    )
