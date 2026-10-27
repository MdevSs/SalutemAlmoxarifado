import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, Text, and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_app_session
from app.core.security import CurrentSector, get_current_sector, require_csrf, require_warehouse
from app.models import Requisicao, Setor
from app.schemas.contracts import (
    FinalizeRequest,
    NotesUpdate,
    RequestCreate,
    RequestItemRead,
    RequestPage,
    RequestRead,
)
from app.services.erp import (
    Product,
    UnitOption,
    convert_quantity_to_default,
    erp_connection,
    find_products,
    post_requisition,
)

router = APIRouter(prefix="/requests", tags=["Requisições"])


def _now() -> datetime:
    return datetime.now(UTC)


def _event(actor: str, note: str) -> dict[str, str]:
    return {"at": _now().isoformat(), "actor": actor, "note": note}


def _request_query():
    return select(Requisicao)


def _apply_date_range(statement, date_from: date | None, date_to: date | None):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="A data inicial não pode ser posterior à data final.")
    if date_from:
        statement = statement.where(Requisicao.data_requisicao >= date_from)
    if date_to:
        statement = statement.where(Requisicao.data_requisicao <= date_to)
    return statement


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_pattern(value: str) -> str:
    terms = [_escape_like(part) for part in value.split()]
    return f"%{'%'.join(terms)}%" if terms else ""


def _json_array_values_match(column, keys: tuple[str, ...], pattern: str, dialect: str, alias: str):
    if dialect == "postgresql":
        elements = func.jsonb_array_elements(column).table_valued("value").alias(alias)
        values = [elements.c.value.op("->>")(key) for key in keys]
    elif dialect == "sqlite":
        elements = func.json_each(column).table_valued("key", "value").alias(alias)
        values = [func.json_extract(elements.c.value, f"$.{key}") for key in keys]
    else:
        return column.cast(Text).ilike(pattern, escape="\\")
    combined = func.coalesce(values[0], "")
    for value in values[1:]:
        combined = combined.op("||")(" ").op("||")(func.coalesce(value, ""))
    reverse_combined = func.coalesce(values[-1], "")
    for value in reversed(values[:-1]):
        reverse_combined = reverse_combined.op("||")(" ").op("||")(func.coalesce(value, ""))
    return (
        select(1)
        .select_from(elements)
        .where(
            or_(
                *(value.ilike(pattern, escape="\\") for value in values),
                combined.ilike(pattern, escape="\\"),
                reverse_combined.ilike(pattern, escape="\\"),
            )
        )
        .correlate(Requisicao)
        .exists()
    )


def _serialize(row: Requisicao) -> RequestRead:
    items = []
    for index, item in enumerate(row.itens, start=1):
        conversion = item.get("unit_conversion") or {}
        requested_quantity = Decimal(str(item["requested_quantity"]))
        delivered_quantity = (
            Decimal(str(item["delivered_quantity"]))
            if item.get("delivered_quantity") is not None
            else None
        )
        requested_unit_quantity = Decimal(
            str(item.get("requested_unit_quantity", item["requested_quantity"]))
        )
        delivered_unit_quantity = (
            Decimal(str(item.get("delivered_unit_quantity", item["delivered_quantity"])))
            if item.get("delivered_unit_quantity", item.get("delivered_quantity")) is not None
            else None
        )
        items.append(
            RequestItemRead(
                item_index=index,
                material_code=item["material_code"],
                description=item["description"],
                requested_quantity=requested_quantity,
                delivered_quantity=delivered_quantity,
                requested_unit_quantity=requested_unit_quantity,
                delivered_unit_quantity=delivered_unit_quantity,
                unit_code=conversion.get("unit_code"),
                unit_description=conversion.get("unit_description"),
                default_unit=conversion.get("default_unit"),
                conversion_result=conversion.get("result"),
            )
        )
    return RequestRead(
        itecontrol=row.itecontrol,
        number=f"REQ-{row.itecontrol}",
        sector_id=row.setor_id,
        sector_name=row.setor_nome_snapshot,
        leader_name=row.lider_nome_snapshot,
        requested_date=row.data_requisicao,
        delivery_instructions=row.instrucoes_entrega,
        status=row.status,
        warehouse_notes=row.observacoes_almoxarifado,
        responsible_name=row.responsavel_confirmacao,
        items=items,
        events=row.eventos or [],
        erp_status=row.erp_status,
        erp_error=row.erp_erro,
        created_at=row.criado_em,
        finalized_at=row.finalizado_em,
    )


def _convert_saved_unit_quantity(item: dict[str, Any], quantity: Decimal) -> Decimal:
    conversion = item.get("unit_conversion") or {}
    unit_code = str(conversion.get("unit_code") or item.get("unit_code") or "UN").strip().upper()
    default_unit = str(conversion.get("default_unit") or unit_code).strip().upper()
    try:
        coefficient = Decimal(str(conversion.get("coefficient", "1.0000")))
    except (ArithmeticError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Snapshot de conversão inválido na requisição.") from error
    option = UnitOption(
        code=unit_code,
        description=str(conversion.get("unit_description") or unit_code),
        operation=str(conversion.get("operation") or "M").strip().upper(),
        coefficient=coefficient,
        result=str(conversion.get("result") or ""),
        is_default=unit_code == default_unit,
    )
    product = Product(
        code=str(item["material_code"]),
        description=str(item.get("description") or ""),
        stock=Decimal(0),
        deposit=1,
        group="",
        default_unit=default_unit,
        unit_options=() if unit_code == default_unit else (option,),
    )
    converted, _ = convert_quantity_to_default(
        quantity=quantity, product=product, unit_code=unit_code
    )
    return converted


def _get_request(session: Session, itecontrol: int) -> Requisicao:
    row = session.scalar(_request_query().where(Requisicao.itecontrol == itecontrol))
    if not row:
        raise HTTPException(status_code=404, detail="Requisição não encontrada.")
    return row


def _allocate_control() -> int:
    with erp_connection() as connection:
        return int(
            connection.execute(
                text(
                    "SELECT COALESCE(MAX(itecontrol), 0) + 1 AS proximo_id "
                    "FROM toqmovi"
                )
            ).scalar_one()
        )


@router.get("/responsibles", response_model=list[str])
def responsibles(
    _warehouse: CurrentSector = Depends(require_warehouse),
    session: Session = Depends(get_app_session),
) -> list[str]:
    names = session.scalars(
        select(Requisicao.responsavel_confirmacao)
        .where(Requisicao.responsavel_confirmacao.is_not(None))
        .distinct()
        .order_by(Requisicao.responsavel_confirmacao)
    ).all()
    return [name for name in names if name]


@router.get("", response_model=RequestPage)
def list_requests(
    status: str | None = Query(default=None),
    search: str = Query(default="", max_length=120),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current: CurrentSector = Depends(get_current_sector),
    session: Session = Depends(get_app_session),
) -> RequestPage:
    statement = _request_query()
    if current.profile == "solicitante":
        statement = statement.where(Requisicao.setor_id == current.id)
    if status:
        if status not in {"Pendente", "Em andamento", "Finalizada", "Parcial"}:
            raise HTTPException(status_code=422, detail="Status inválido.")
        statement = statement.where(Requisicao.status == status)
    statement = _apply_date_range(statement, date_from, date_to)
    term = search.strip()
    if term:
        values = {term}
        if term.casefold().startswith("req-"):
            values.add(term[4:])
        try:
            values.add(datetime.strptime(term, "%d/%m/%Y").date().isoformat())
        except ValueError:
            pass
        search_clauses = []
        dialect = session.get_bind().dialect.name
        for pattern_index, value in enumerate(values):
            pattern = _search_pattern(value)
            term_clauses = [
                or_(
                    Requisicao.itecontrol.cast(String).ilike(pattern, escape="\\"),
                    Requisicao.setor_nome_snapshot.ilike(pattern, escape="\\"),
                    Requisicao.lider_nome_snapshot.ilike(pattern, escape="\\"),
                    Requisicao.data_requisicao.cast(String).ilike(pattern, escape="\\"),
                    Requisicao.criado_em.cast(String).ilike(pattern, escape="\\"),
                    Requisicao.finalizado_em.cast(String).ilike(pattern, escape="\\"),
                    Requisicao.status.ilike(pattern, escape="\\"),
                    Requisicao.erp_status.ilike(pattern, escape="\\"),
                    Requisicao.instrucoes_entrega.ilike(pattern, escape="\\"),
                    Requisicao.observacoes_almoxarifado.ilike(pattern, escape="\\"),
                    func.coalesce(Requisicao.responsavel_confirmacao, "").ilike(
                        pattern, escape="\\"
                    ),
                    func.coalesce(Requisicao.erp_erro, "").ilike(pattern, escape="\\"),
                    _json_array_values_match(
                        Requisicao.itens,
                        ("material_code", "description"),
                        pattern,
                        dialect,
                        f"search_items_{pattern_index}",
                    ),
                    _json_array_values_match(
                        Requisicao.eventos,
                        ("actor", "note", "at"),
                        pattern,
                        dialect,
                        f"search_events_{pattern_index}",
                    ),
                )
            ]
            search_clauses.append(term_clauses[0])
        statement = statement.where(or_(*search_clauses))
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = (
        session.scalars(
            statement.order_by(Requisicao.criado_em.desc(), Requisicao.itecontrol.desc())
            .offset(offset)
            .limit(limit)
        )
        .unique()
        .all()
    )
    return RequestPage(
        items=[_serialize(row) for row in rows], total=int(total), offset=offset, limit=limit
    )


@router.post("", response_model=RequestRead, status_code=201)
def create_request(
    payload: RequestCreate,
    _csrf: None = Depends(require_csrf),
    current: CurrentSector = Depends(get_current_sector),
    session: Session = Depends(get_app_session),
) -> RequestRead:
    if current.profile not in {"solicitante", "administrador"}:
        raise HTTPException(
            status_code=403, detail="Somente setores solicitantes ou Administrador podem criar requisições."
        )
    if payload.requested_date > datetime.now(ZoneInfo("America/Sao_Paulo")).date():
        raise HTTPException(status_code=422, detail="A data da requisição não pode ser futura.")

    requested_codes = list(dict.fromkeys(line.material_code for line in payload.items))
    with erp_connection() as connection:
        products = find_products(connection, requested_codes)
    missing = sorted(set(requested_codes) - products.keys())
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Produtos não encontrados no ERP: {', '.join(missing)}."
        )

    combined: dict[tuple[str, str], Decimal] = {}
    for line in payload.items:
        product = products[line.material_code]
        selected_unit = (line.unit_code or product.default_unit).strip().upper()
        convert_quantity_to_default(
            quantity=line.quantity, product=product, unit_code=selected_unit
        )
        key = (line.material_code, selected_unit)
        combined[key] = combined.get(key, Decimal(0)) + line.quantity

    items = []
    for index, ((code, unit_code), quantity) in enumerate(combined.items(), start=1):
        product: Product = products[code]
        converted_quantity, option = convert_quantity_to_default(
            quantity=quantity, product=product, unit_code=unit_code
        )
        items.append(
            {
                "item_index": index,
                "material_code": product.code,
                "description": product.description,
                "requested_quantity": format(converted_quantity, ".4f"),
                "requested_unit_quantity": format(quantity, "f"),
                "delivered_quantity": None,
                "delivered_unit_quantity": None,
                "unit_conversion": {
                    "unit_code": option.code,
                    "unit_description": option.description,
                    "default_unit": product.default_unit,
                    "operation": option.operation,
                    "coefficient": format(option.coefficient, ".4f"),
                    "result": option.result,
                },
                "erp_null_fields": {
                    "doc_controle": None,
                    "doc_operacao": None,
                    "notdtdigit": None,
                },
            }
        )
    itecontrol = _allocate_control()
    sector = session.get(Setor, current.id)
    if not sector or not sector.ativo:
        raise HTTPException(status_code=401, detail="Setor inativo. Entre novamente.")
    row = Requisicao(
        itecontrol=itecontrol,
        setor_id=current.id,
        setor_nome_snapshot=sector.nome,
        lider_nome_snapshot=sector.lider_nome or sector.nome,
        data_requisicao=payload.requested_date,
        instrucoes_entrega=payload.delivery_instructions,
        status="Pendente",
        itens=items,
        eventos=[
            _event(sector.lider_nome or sector.nome, "Requisição registrada no sistema local.")
        ],
        erp_status="aguardando",
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="O controle local já está em uso; contate o administrador."
        ) from error
    return _serialize(_get_request(session, itecontrol))


@router.get("/export.csv")
def export_csv(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _warehouse: CurrentSector = Depends(require_warehouse),
    session: Session = Depends(get_app_session),
) -> StreamingResponse:
    statement = _apply_date_range(_request_query(), date_from, date_to)
    rows = session.scalars(statement.order_by(Requisicao.criado_em.desc())).unique().all()
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "Controle ERP",
            "Data",
            "Setor",
            "Líder",
            "Status",
            "ERP",
            "Código",
            "Descrição",
            "Solicitado",
            "Entregue",
            "Instruções",
            "Observações",
            "Responsável",
            "Finalizada em",
        ]
    )
    for row in rows:
        for item in row.itens:
            writer.writerow(
                [
                    row.itecontrol,
                    row.data_requisicao.isoformat(),
                    row.setor_nome_snapshot,
                    row.lider_nome_snapshot,
                    row.status,
                    row.erp_status,
                    item["material_code"],
                    item["description"],
                    (
                        f"{item.get('requested_unit_quantity', item['requested_quantity'])} "
                        f"{(item.get('unit_conversion') or {}).get('unit_code', '')}"
                        + (
                            f" ({item['requested_quantity']} {(item.get('unit_conversion') or {}).get('default_unit', '')})"
                            if item.get("unit_conversion")
                            and (item.get("unit_conversion") or {}).get("unit_code")
                            != (item.get("unit_conversion") or {}).get("default_unit")
                            else ""
                        )
                    ),
                    (
                        f"{item.get('delivered_unit_quantity', item.get('delivered_quantity'))} "
                        f"{(item.get('unit_conversion') or {}).get('unit_code', '')}"
                        + (
                            f" ({item.get('delivered_quantity')} {(item.get('unit_conversion') or {}).get('default_unit', '')})"
                            if item.get("delivered_quantity") is not None
                            and item.get("unit_conversion")
                            and (item.get("unit_conversion") or {}).get("unit_code")
                            != (item.get("unit_conversion") or {}).get("default_unit")
                            else ""
                        )
                        if item.get("delivered_quantity") is not None
                        else ""
                    ),
                    row.instrucoes_entrega,
                    row.observacoes_almoxarifado,
                    row.responsavel_confirmacao or "",
                    row.finalizado_em.isoformat() if row.finalizado_em else "",
                ]
            )
    payload = "\ufeff" + output.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="requisicoes_{date.today().isoformat()}.csv"'
        },
    )


@router.get("/notifications/finalized", response_model=list[RequestRead])
def finalized_notifications(
    finalized_after: datetime = Query(alias="after"),
    after_control: int = Query(default=0, ge=0),
    current: CurrentSector = Depends(get_current_sector),
    session: Session = Depends(get_app_session),
) -> list[RequestRead]:
    if current.profile not in {"solicitante", "administrador"}:
        raise HTTPException(status_code=403, detail="Notificações restritas ao setor solicitante.")
    if finalized_after.tzinfo is None or finalized_after.utcoffset() is None:
        finalized_after = finalized_after.replace(tzinfo=UTC)
    statement = _request_query().where(
        Requisicao.setor_id == current.id,
        Requisicao.status.in_(("Finalizada", "Parcial")),
        Requisicao.finalizado_em.is_not(None),
        or_(
            Requisicao.finalizado_em > finalized_after,
            and_(
                Requisicao.finalizado_em == finalized_after,
                Requisicao.itecontrol > after_control,
            ),
        ),
    )
    rows = session.scalars(
        statement.order_by(Requisicao.finalizado_em, Requisicao.itecontrol).limit(100)
    ).unique().all()
    return [_serialize(row) for row in rows]


@router.get("/{itecontrol}", response_model=RequestRead)
def get_request(
    itecontrol: int,
    current: CurrentSector = Depends(get_current_sector),
    session: Session = Depends(get_app_session),
) -> RequestRead:
    row = _get_request(session, itecontrol)
    if current.profile == "solicitante" and row.setor_id != current.id:
        raise HTTPException(status_code=404, detail="Requisição não encontrada.")
    return _serialize(row)


@router.post("/{itecontrol}/start", response_model=RequestRead)
def start_request(
    itecontrol: int,
    _csrf: None = Depends(require_csrf),
    current: CurrentSector = Depends(require_warehouse),
    session: Session = Depends(get_app_session),
) -> RequestRead:
    row = session.scalar(
        select(Requisicao).where(Requisicao.itecontrol == itecontrol).with_for_update()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Requisição não encontrada.")
    if row.status != "Pendente":
        raise HTTPException(
            status_code=409, detail="Somente requisições pendentes podem iniciar atendimento."
        )
    row.status = "Em andamento"
    row.eventos = [*(row.eventos or []), _event(current.name, "Atendimento iniciado.")]
    session.commit()
    return _serialize(_get_request(session, itecontrol))


@router.put("/{itecontrol}/notes", response_model=RequestRead)
def update_notes(
    itecontrol: int,
    payload: NotesUpdate,
    _csrf: None = Depends(require_csrf),
    current: CurrentSector = Depends(require_warehouse),
    session: Session = Depends(get_app_session),
) -> RequestRead:
    row = session.scalar(
        select(Requisicao).where(Requisicao.itecontrol == itecontrol).with_for_update()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Requisição não encontrada.")
    if row.status in {"Finalizada", "Parcial"}:
        raise HTTPException(status_code=409, detail="Requisição finalizada não pode ser alterada.")
    row.observacoes_almoxarifado = payload.warehouse_notes
    row.eventos = [
        *(row.eventos or []),
        _event(current.name, "Observação do Almoxarifado atualizada."),
    ]
    session.commit()
    return _serialize(_get_request(session, itecontrol))


@router.post("/{itecontrol}/finalize", response_model=RequestRead)
def finalize_request(
    itecontrol: int,
    payload: FinalizeRequest,
    _csrf: None = Depends(require_csrf),
    current: CurrentSector = Depends(require_warehouse),
    session: Session = Depends(get_app_session),
) -> RequestRead:
    row = session.scalar(
        select(Requisicao).where(Requisicao.itecontrol == itecontrol).with_for_update()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Requisição não encontrada.")
    if row.status in {"Finalizada", "Parcial"} and row.erp_status == "enviado":
        return _serialize(_get_request(session, itecontrol))
    if row.status != "Em andamento":
        raise HTTPException(
            status_code=409, detail="Somente requisições em andamento podem ser finalizadas."
        )

    requested_lines = {index: item for index, item in enumerate(row.itens, start=1)}
    delivery_lines = {line.item_index: line.quantity for line in payload.deliveries}
    if len(delivery_lines) != len(payload.deliveries) or set(delivery_lines) != set(
        requested_lines
    ):
        raise HTTPException(status_code=422, detail="Informe a quantidade atendida para cada item.")

    converted_deliveries: dict[int, Decimal] = {}
    for index, item in requested_lines.items():
        requested_unit_quantity = Decimal(
            str(item.get("requested_unit_quantity", item["requested_quantity"]))
        )
        if delivery_lines[index] > requested_unit_quantity:
            raise HTTPException(
                status_code=422, detail="Quantidade atendida não pode superar a solicitada."
            )
        converted_deliveries[index] = _convert_saved_unit_quantity(item, delivery_lines[index])
    if sum(converted_deliveries.values(), Decimal(0)) <= 0:
        raise HTTPException(
            status_code=422,
            detail="Não é permitido confirmar com todas as quantidades iguais a zero.",
        )
    partial = any(
        converted_deliveries[index] < Decimal(str(item["requested_quantity"]))
        for index, item in requested_lines.items()
    )
    notes = payload.warehouse_notes.strip()
    if partial and not notes and not payload.confirm_partial_without_note:
        raise HTTPException(
            status_code=409,
            detail="Entrega parcial: registre observação ou confirme sem observação.",
        )

    stored_deliveries = [
        item.get("delivered_unit_quantity", item.get("delivered_quantity"))
        for item in row.itens
    ]
    if any(value is not None for value in stored_deliveries) and row.erp_status != "revisar_saldo":
        existing = [Decimal(str(value or "0")) for value in stored_deliveries]
        incoming = [delivery_lines[index] for index in requested_lines]
        if existing != incoming or row.responsavel_confirmacao != payload.responsible_name.strip():
            raise HTTPException(
                status_code=409,
                detail="A confirmação já foi preparada para sincronização; mantenha as quantidades e responsável originais.",
            )
    else:
        row.itens = [
            {
                **item,
                "delivered_quantity": format(converted_deliveries[index], ".4f"),
                "delivered_unit_quantity": format(delivery_lines[index], "f"),
            }
            for index, item in requested_lines.items()
        ]
        row.responsavel_confirmacao = payload.responsible_name.strip()
        row.observacoes_almoxarifado = notes
        row.erp_status = "aguardando"
        row.eventos = [
            *(row.eventos or []),
            _event(current.name, f"Confirmação preparada por {payload.responsible_name.strip()}."),
        ]
        session.commit()
        row = _get_request(session, itecontrol)

    try:
        exact_retry = post_requisition(
            itecontrol=row.itecontrol,
            requested_date=row.data_requisicao,
            items=row.itens,
        )
    except HTTPException as error:
        row.erp_status = (
            "conflito"
            if error.status_code == 409
            else ("revisar_saldo" if error.status_code == 422 else "falhou")
        )
        row.erp_erro = error.detail[:2000]
        row.eventos = [
            *(row.eventos or []),
            _event(current.name, f"Sincronização ERP não concluída: {error.detail}"),
        ]
        session.commit()
        raise
    except (OperationalError, SQLAlchemyError) as error:
        row.erp_status = "falhou"
        row.erp_erro = "Falha de conexão ou gravação no ERP; a confirmação ficou pendente de reconciliação segura."
        row.eventos = [*(row.eventos or []), _event(current.name, row.erp_erro)]
        session.commit()
        raise HTTPException(status_code=503, detail=row.erp_erro) from error

    row.erp_status = "enviado"
    row.erp_erro = None
    row.erp_enviado_em = _now()
    row.status = "Parcial" if partial else "Finalizada"
    row.finalizado_em = _now()
    suffix = " (reconciliação idempotente)" if exact_retry else ""
    row.eventos = [
        *(row.eventos or []),
        _event(
            current.name,
            f"Movimentos ERP confirmados{suffix}; status {row.status.lower()}; responsável informado: {row.responsavel_confirmacao}.",
        ),
    ]
    session.commit()
    return _serialize(_get_request(session, itecontrol))
