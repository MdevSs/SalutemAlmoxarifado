from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from app.core.security import CurrentSector, get_current_sector
from app.schemas.contracts import ProductPage, ProductRead, ProductUnitRead
from app.services.erp import list_products

router = APIRouter(prefix="/materials", tags=["Catálogo ERP"])


@router.get("", response_model=ProductPage)
async def materials(
    search: str = Query(default="", max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _sector: CurrentSector = Depends(get_current_sector),
) -> ProductPage:
    rows, has_more = await run_in_threadpool(list_products, search, offset, limit)
    return ProductPage(
        items=[
            ProductRead(
                code=row.code,
                description=row.description,
                stock=row.stock,
                deposit=row.deposit,
                group=row.group,
                default_unit=row.default_unit,
                unit_options=[
                    ProductUnitRead(
                        code=unit.code,
                        description=unit.description,
                        operation=unit.operation,
                        coefficient=unit.coefficient,
                        result=unit.result,
                        is_default=unit.is_default,
                    )
                    for unit in row.unit_options
                ],
            )
            for row in rows
        ],
        has_more=has_more,
        offset=offset,
        limit=limit,
    )
