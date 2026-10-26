from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app.api import materials, requests, sectors

app = FastAPI(
    title="Salutem Almoxarifado API",
    description=(
        "Sistema local de requisições. Consulta catálogo/saldo no ERP e grava pedidos "
        "na base local e movimentos confirmados no ERP."
    ),
    version="0.2.0",
)
app.include_router(sectors.router, prefix="/api")
app.include_router(sectors.sectors_router, prefix="/api")
app.include_router(materials.router, prefix="/api")
app.include_router(requests.router, prefix="/api")


@app.exception_handler(OperationalError)
async def database_unavailable_handler(_request: Request, _error: OperationalError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Um banco PostgreSQL necessário está indisponível. Verifique a conectividade na rede local."
        },
    )


@app.get("/health", tags=["Sistema"], summary="Verifica se a aplicação HTTP está ativa")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "salutem-almoxarifado"}


@app.get("/api/health", tags=["Sistema"], summary="Verifica se a API está ativa")
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "salutem-almoxarifado-api"}


static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
