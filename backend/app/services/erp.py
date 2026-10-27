from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from threading import RLock
from time import monotonic
from typing import Any

from fastapi import HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import erp_connection

QUANTITY_STEP = Decimal("0.0001")
MAX_ERP_QUANTITY = Decimal("9999999999.9999")
CONTROL_START = 84333
_CATALOG_GROUPS = ("10.%", "11.%", "12.%", "13.%")
_ERP_AUDIT_COLUMNS = ("pridtalt", "prihralt")
_CATALOG_CACHE_TTL_SECONDS = 10.0
_CATALOG_CACHE_MAX_ENTRIES = 128
_CATALOG_CACHE: OrderedDict[tuple[str, int, int], tuple[float, tuple["Product", ...], bool]] = OrderedDict()
_CATALOG_CACHE_LOCK = RLock()

# These values are part of the ERP's accepted movement shape, not nullable omissions.
_ERP_MOVEMENT_DEFAULTS: dict[str, Any] = {
    "pricusto": Decimal("0.00"),
    "operacao": " " * 10,
    "prinivelb": 0,
    "pridocto": " " * 8,
    "pricompra": 0,
    "pritribfis": " " * 4,
    "prialqicms": Decimal("0.00"),
    "prialqipi": Decimal("0.00"),
    "pribaseipi": Decimal("0.0000"),
    "pribasicms": Decimal("0.0000"),
    "priicmfret": Decimal("0.00"),
    "privldesp": Decimal("0.00"),
    "privlfrete": Decimal("0.00"),
    "privlicms": Decimal("0.00"),
    "privlipi": Decimal("0.00"),
    "privlourec": Decimal("0.00"),
    "privlsegur": Decimal("0.00"),
    "privlsubst": Decimal("0.00"),
    "privltotal": Decimal("0.00"),
    "privldecon": Decimal("0.00"),
    "priclascod": " " * 5,
    "privlbipi": Decimal("0.00"),
    "privlbicms": Decimal("0.00"),
    "pritmpuni": Decimal("0.0000"),
    "pricmpseq": 0,
    "pricomiss": Decimal("0.00"),
    "pritabpre": " " * 3,
    "prialpis": Decimal("0.0000"),
    "privlpis": Decimal("0.00"),
    "prialcof": Decimal("0.0000"),
    "privlcof": Decimal("0.00"),
    "prialcsll": Decimal("0.00"),
    "privlcsll": Decimal("0.00"),
    "privlbpis": Decimal("0.00"),
    "prialret": Decimal("0.00"),
    "privlret": Decimal("0.00"),
    "pridesipi": Decimal("0.00"),
    "pridesfre": Decimal("0.00"),
    "pribssubst": Decimal("0.00"),
    "pribassub": Decimal("0.0000"),
    "prialqsub": Decimal("0.00"),
    "privlbret": Decimal("0.00"),
    "prifalipi": Decimal("0.00"),
    "prifbasipi": Decimal("0.0000"),
    "prifvlbipi": Decimal("0.00"),
    "prifvlripi": Decimal("0.00"),
    "pridespis": Decimal("0.00"),
    "pridescof": Decimal("0.00"),
    "privlrtab": Decimal("0.0000"),
    "pritriipi": " " * 2,
    "pritripis": " " * 2,
    "pritricof": " " * 2,
    "prialqdifi": Decimal("0.00"),
    "pribasdifi": Decimal("0.0000"),
    "privlbdifi": Decimal("0.00"),
    "privlrdifi": Decimal("0.00"),
    "priobserv": " " * 100,
    "priredmva": Decimal("0.0000"),
    "primvasub": Decimal("0.0000"),
    "pribasesub": Decimal("0.0000"),
    "pritriissq": " " * 3,
    "pricarmed": Decimal("0.0000"),
    "priforma": "M",
    "prideonde": " " * 6,
    "priusuario": " " * 10,
    "priqtgen": Decimal("0.0000"),
    "priunimed": " " * 2,
    "priumnf": " " * 6,
    "priqtdnf": Decimal("0.0000"),
    "priicmfic": Decimal("0.00"),
    "pribaspis": Decimal("0.0000"),
    "primotdesi": 0,
    "prialqdeso": Decimal("0.00"),
    "pribasdeso": Decimal("0.0000"),
    "privlbdeso": Decimal("0.00"),
    "privlrdeso": Decimal("0.00"),
    "pridesdsp": Decimal("0.00"),
    "pripedcmpi": " " * 15,
    "priseqpcmp": 0,
    "privlarr": Decimal("0.0000000000"),
    "prienqipi": " " * 3,
    "priemitido": " ",
    "priredpisc": Decimal("0.00"),
}
_ERP_REQUEST_FIELDS = (
    "itecontrol",
    "prisequen",
    "prideposit",
    "pritransac",
    "pridata",
    "priordem",
    "priproduto",
    "priquanti",
)
_ERP_INSERT_COLUMNS = (
    *_ERP_REQUEST_FIELDS,
    *_ERP_MOVEMENT_DEFAULTS,
    *_ERP_AUDIT_COLUMNS,
)
_ERP_INSERT_EXPRESSIONS = {
    "pridtalt": "CURRENT_DATE",
    "prihralt": "CAST(LOCALTIME(0) AS text)",
}


def _catalog_params() -> dict[str, str]:
    return {f"group_{index}": pattern for index, pattern in enumerate(_CATALOG_GROUPS, start=10)}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_CATALOG_FILTER = """
    s.codigo_deposito_saldo_estoque = 1
    AND p.prostatus = 'A'
    AND (
        btrim(s.codigo_produto_saldo_estoque::text) LIKE :group_10
        OR btrim(s.codigo_produto_saldo_estoque::text) LIKE :group_11
        OR btrim(s.codigo_produto_saldo_estoque::text) LIKE :group_12
        OR btrim(s.codigo_produto_saldo_estoque::text) LIKE :group_13
    )
"""


@dataclass(frozen=True)
class Product:
    code: str
    description: str
    stock: Decimal
    deposit: int
    group: str
    default_unit: str = "UN"
    unit_options: tuple["UnitOption", ...] = ()


@dataclass(frozen=True)
class UnitOption:
    code: str
    description: str
    operation: str
    coefficient: Decimal
    result: str
    is_default: bool = False


def _group_from_code(code: str) -> str:
    parts = code.strip().split(".")
    if len(parts) >= 3:
        return ".".join(parts[:2])
    return "OUTROS"


def _load_unit_options(
    connection: Connection, codes: list[str], default_units: dict[str, str]
) -> dict[str, tuple[UnitOption, ...]]:
    options: dict[str, list[UnitOption]] = {}
    for code in codes:
        default_unit = default_units.get(code, "").strip().upper()
        options[code] = (
            [
                UnitOption(
                    code=default_unit,
                    description="Unidade padrão",
                    operation="M",
                    coefficient=Decimal("1.0000"),
                    result=f"1 {default_unit} = 1 {default_unit}",
                    is_default=True,
                )
            ]
            if default_unit
            else []
        )
    if not codes:
        return {code: tuple(value) for code, value in options.items()}

    query = text("""
        SELECT
            btrim(c.convprod::text) AS code,
            upper(btrim(c.cvunidade::text)) AS unit_code,
            upper(btrim(c.cvuopera::text)) AS operation,
            c.cvucoefici::numeric(15,4) AS coefficient,
            btrim(c.cvuresulta::text) AS result,
            btrim(c.cvunidesc::text) AS description
        FROM public.convers1 AS c
        WHERE btrim(c.convprod::text) IN :codes
        ORDER BY code, unit_code
    """).bindparams(bindparam("codes", expanding=True))
    try:
        rows = connection.execute(query, {"codes": codes}).mappings().all()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar as conversões de unidade do ERP; confirme o acesso de leitura à tabela convers1.",
        ) from error

    found: dict[tuple[str, str], UnitOption] = {}
    ambiguous: set[tuple[str, str]] = set()
    for row in rows:
        code = str(row["code"] or "").strip()
        unit_code = str(row["unit_code"] or "").strip().upper()
        default_unit = default_units.get(code, "").strip().upper()
        operation = str(row["operation"] or "").strip().upper()
        try:
            coefficient = Decimal(str(row["coefficient"] or "0"))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if (
            code not in options
            or not unit_code
            or unit_code == default_unit
            or operation not in {"M", "D"}
            or not coefficient.is_finite()
            or coefficient <= 0
        ):
            continue
        key = (code, unit_code)
        option = UnitOption(
            code=unit_code,
            description=str(row["description"] or "").strip() or unit_code,
            operation=operation,
            coefficient=coefficient.quantize(QUANTITY_STEP),
            result=str(row["result"] or "").strip(),
        )
        previous = found.get(key)
        if previous is not None and previous != option:
            ambiguous.add(key)
        else:
            found[key] = option
    for key, option in found.items():
        if key not in ambiguous:
            options[key[0]].append(option)
    return {code: tuple(value) for code, value in options.items()}


def convert_quantity_to_default(
    *, quantity: Decimal, product: Product, unit_code: str
) -> tuple[Decimal, UnitOption]:
    selected = unit_code.strip().upper()
    if not selected or not product.default_unit.strip():
        raise HTTPException(status_code=422, detail="Unidade padrão do produto não informada no ERP.")
    if not quantity.is_finite() or quantity < 0 or quantity != quantity.to_integral_value():
        raise HTTPException(
            status_code=422, detail="As quantidades digitadas devem ser números inteiros não negativos."
        )
    default_unit = product.default_unit.strip().upper()
    if selected == default_unit:
        option = UnitOption(
            code=default_unit,
            description="Unidade padrão",
            operation="M",
            coefficient=Decimal("1.0000"),
            result=f"1 {default_unit} = 1 {default_unit}",
            is_default=True,
        )
    else:
        option = next((unit for unit in product.unit_options if unit.code == selected), None)
        if option is None:
            raise HTTPException(
                status_code=422,
                detail=f"A unidade {selected} não possui conversão válida cadastrada para {product.code}.",
            )
    if quantity == 0:
        return Decimal("0.0000"), option
    if not option.coefficient.is_finite() or option.coefficient <= 0:
        raise HTTPException(status_code=422, detail="Coeficiente de conversão inválido no ERP.")
    try:
        if option.operation == "M":
            converted = quantity * option.coefficient
        elif option.operation == "D":
            converted = quantity / option.coefficient
        else:
            raise HTTPException(status_code=422, detail="Operação de conversão inválida no ERP.")
        converted = converted.quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise HTTPException(status_code=422, detail="Quantidade fora do limite numeric(14,4) do ERP.") from error
    if converted > MAX_ERP_QUANTITY:
        raise HTTPException(status_code=422, detail="Quantidade fora do limite numeric(14,4) do ERP.")
    if converted <= 0:
        raise HTTPException(
            status_code=422, detail="A quantidade convertida para a unidade padrão deve ser positiva."
        )
    return converted, option


def _catalog_query(search: str = "") -> tuple[str, dict[str, Any]]:
    predicates = [_CATALOG_FILTER]
    params: dict[str, Any] = _catalog_params()
    if search.strip():
        terms = [_escape_like(part) for part in search.strip().split()]
        params["term"] = f"%{'%'.join(terms)}%"
        predicates.append(
            r"""(
                btrim(s.codigo_produto_saldo_estoque::text) ILIKE :term ESCAPE E'\\'
                OR btrim(s.descricao_produto_saldo_estoque::text) ILIKE :term ESCAPE E'\\'
                OR (btrim(s.codigo_produto_saldo_estoque::text) || ' ' ||
                    btrim(s.descricao_produto_saldo_estoque::text)) ILIKE :term ESCAPE E'\\'
                OR (btrim(s.descricao_produto_saldo_estoque::text) || ' ' ||
                    btrim(s.codigo_produto_saldo_estoque::text)) ILIKE :term ESCAPE E'\\'
            )"""
        )
    sql = """
        SELECT DISTINCT
            btrim(s.codigo_produto_saldo_estoque::text) AS code,
            btrim(s.descricao_produto_saldo_estoque::text) AS description,
            s.qtde_sldatu_saldo_estoque::numeric(14,4) AS stock,
            s.codigo_deposito_saldo_estoque::integer AS deposit,
            upper(btrim(p.unimedida::text)) AS default_unit
        FROM public.vw_produto_saldo_estoque AS s
        JOIN public.produto AS p
          ON p.produto = btrim(s.codigo_produto_saldo_estoque::text)::char(16)
        WHERE """ + " AND ".join(predicates)
    return sql, params


def list_products(
    search: str = "", offset: int = 0, limit: int = 20
) -> tuple[list[Product], bool]:
    search_text = search.strip()
    cache_key = (search_text, offset, limit)
    now = monotonic()
    with _CATALOG_CACHE_LOCK:
        cached = _CATALOG_CACHE.get(cache_key)
        if cached:
            expires_at, cached_products, cached_has_more = cached
            if expires_at > now:
                _CATALOG_CACHE.move_to_end(cache_key)
                return list(cached_products), cached_has_more
            del _CATALOG_CACHE[cache_key]

    query, params = _catalog_query(search_text)
    with erp_connection() as connection:
        rows = (
            connection.execute(
                text(
                    f"SELECT * FROM ({query}) AS catalog "
                    "ORDER BY code LIMIT :fetch_limit OFFSET :offset"
                ),
                {**params, "fetch_limit": limit + 1, "offset": offset},
            )
            .mappings()
            .all()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        codes = [row["code"] for row in rows]
        defaults = {
            row["code"]: str(row.get("default_unit") or "").strip().upper()
            for row in rows
        }
        unit_options = _load_unit_options(connection, codes, defaults)
    products = [
        Product(
            code=row["code"],
            description=row["description"],
            stock=Decimal(row["stock"] or 0).quantize(QUANTITY_STEP),
            deposit=int(row["deposit"]),
            group=_group_from_code(row["code"]),
            default_unit=defaults[row["code"]],
            unit_options=unit_options.get(row["code"], ()),
        )
        for row in rows
    ]
    with _CATALOG_CACHE_LOCK:
        _CATALOG_CACHE[cache_key] = (
            monotonic() + _CATALOG_CACHE_TTL_SECONDS,
            tuple(products),
            has_more,
        )
        _CATALOG_CACHE.move_to_end(cache_key)
        while len(_CATALOG_CACHE) > _CATALOG_CACHE_MAX_ENTRIES:
            _CATALOG_CACHE.popitem(last=False)
    return products, has_more


def find_products(connection: Connection, codes: list[str]) -> dict[str, Product]:
    if not codes:
        return {}
    query = text(f"""
        SELECT DISTINCT
            btrim(s.codigo_produto_saldo_estoque::text) AS code,
            btrim(s.descricao_produto_saldo_estoque::text) AS description,
            s.qtde_sldatu_saldo_estoque::numeric(14,4) AS stock,
            s.codigo_deposito_saldo_estoque::integer AS deposit,
            upper(btrim(p.unimedida::text)) AS default_unit
        FROM public.vw_produto_saldo_estoque AS s
        JOIN public.produto AS p
          ON p.produto = btrim(s.codigo_produto_saldo_estoque::text)::char(16)
        WHERE {_CATALOG_FILTER}
          AND btrim(s.codigo_produto_saldo_estoque::text) IN :codes
    """).bindparams(bindparam("codes", expanding=True))
    rows = connection.execute(query, {**_catalog_params(), "codes": codes}).mappings().all()
    defaults = {
        row["code"]: str(row.get("default_unit") or "").strip().upper()
        for row in rows
    }
    unit_options = _load_unit_options(connection, [row["code"] for row in rows], defaults)
    return {
        row["code"]: Product(
            code=row["code"],
            description=row["description"],
            stock=Decimal(row["stock"] or 0).quantize(QUANTITY_STEP),
            deposit=int(row["deposit"]),
            group=_group_from_code(row["code"]),
            default_unit=defaults[row["code"]],
            unit_options=unit_options.get(row["code"], ()),
        )
        for row in rows
    }


def _close(actual: Any, expected: Decimal) -> bool:
    if actual is None:
        return False
    try:
        return Decimal(str(actual)).quantize(QUANTITY_STEP) == expected.quantize(QUANTITY_STEP)
    except (ArithmeticError, ValueError):
        return False


def _matches_existing(actual: Any, wanted: dict[str, Any]) -> bool:
    try:
        return (
            actual["prisequen"] is not None
            and int(actual["prisequen"]) == wanted["prisequen"]
            and actual["pridata"] == wanted["pridata"]
            and str(actual["priproduto"] or "").strip() == wanted["priproduto"]
            and actual["prideposit"] is not None
            and int(actual["prideposit"]) == wanted["prideposit"]
            and actual["pritransac"] is not None
            and int(actual["pritransac"]) == wanted["pritransac"]
            and actual["priordem"] == wanted["priordem"]
            and _close(actual["priquanti"], wanted["priquanti"])
            and all(actual[column] == wanted[column] for column in _ERP_MOVEMENT_DEFAULTS)
            and all(actual[column] is not None for column in _ERP_AUDIT_COLUMNS)
        )
    except (KeyError, TypeError, ValueError):
        return False


def post_requisition(*, itecontrol: int, requested_date: date, items: list[dict[str, Any]]) -> bool:
    """Post movements in one ERP transaction; returns True when this was an exact retry."""
    quantities: list[tuple[dict[str, Any], Decimal]] = []
    for item in items:
        try:
            quantity = Decimal(str(item.get("delivered_quantity") or "0"))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=422, detail="A quantidade convertida precisa ser numérica."
            ) from error
        if not quantity.is_finite() or quantity < 0:
            raise HTTPException(
                status_code=422,
                detail="A quantidade convertida para o ERP pode ter no máximo quatro casas decimais.",
            )
        try:
            normalized = quantity.quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)
        except InvalidOperation as error:
            raise HTTPException(
                status_code=422,
                detail="A quantidade convertida excede o limite numeric(14,4) do ERP.",
            ) from error
        if quantity != normalized or normalized > MAX_ERP_QUANTITY:
            raise HTTPException(
                status_code=422,
                detail="A quantidade convertida para o ERP deve caber em numeric(14,4) e ter até quatro casas decimais.",
            )
        quantities.append((item, quantity))
    if not any(quantity > 0 for _, quantity in quantities):
        raise HTTPException(
            status_code=422,
            detail="A confirmação precisa retirar pelo menos uma quantidade positiva.",
        )
    expected = []
    for item, whole_quantity in quantities:
        quantity = whole_quantity.quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)
        if quantity <= 0:
            continue
        expected.append(
            {
                "prisequen": len(expected) + 1,
                "pridata": requested_date,
                "priproduto": str(item["material_code"]).strip(),
                "prideposit": 1,
                "pritransac": 14,
                "priordem": 0,
                "priquanti": quantity,
                **_ERP_MOVEMENT_DEFAULTS,
            }
        )

    with erp_connection() as connection:
        # Serializa tentativas da aplicação para esse controle; ERP PK permanece a última barreira.
        connection.execute(text("SELECT pg_advisory_xact_lock(:control)"), {"control": itecontrol})
        existing = (
            connection.execute(
                text(
                    f"SELECT {', '.join('btrim(priproduto::text) AS priproduto' if column == 'priproduto' else column for column in _ERP_INSERT_COLUMNS if column != 'itecontrol')} "
                    "FROM public.toqmovi WHERE itecontrol = :control ORDER BY prisequen"
                ),
                {"control": itecontrol},
            )
            .mappings()
            .all()
        )
        if existing:
            if len(existing) != len(expected):
                raise HTTPException(
                    status_code=409,
                    detail="O controle ERP já existe com outra quantidade de linhas; não foi alterado.",
                )
            for actual, wanted in zip(existing, expected, strict=True):
                if not _matches_existing(actual, wanted):
                    raise HTTPException(
                        status_code=409,
                        detail="O controle ERP já existe com dados diferentes; revisão manual necessária.",
                    )
            return True

        products = find_products(connection, [row["priproduto"] for row in expected])
        for row in expected:
            product = products.get(row["priproduto"])
            if product is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Produto {row['priproduto']} não encontrado no saldo do depósito 1.",
                )
            if row["priquanti"] > product.stock:
                raise HTTPException(
                    status_code=422,
                    detail=f"Saldo ERP insuficiente para {row['priproduto']}: disponível {product.stock}, solicitado {row['priquanti']}.",
                )

        insert_columns = ", ".join(_ERP_INSERT_COLUMNS)
        insert_values = ", ".join(
            _ERP_INSERT_EXPRESSIONS.get(column, f":{column}")
            for column in _ERP_INSERT_COLUMNS
        )
        insert = text(
            f"INSERT INTO public.toqmovi ({insert_columns}) VALUES ({insert_values})"
        )
        for row in expected:
            params = {
                column: row[column]
                for column in _ERP_INSERT_COLUMNS
                if column not in _ERP_INSERT_EXPRESSIONS and column != "itecontrol"
            }
            connection.execute(insert, {**params, "itecontrol": itecontrol})
    return False
