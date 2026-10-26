"""Cria setores de DEMONSTRAÇÃO com senhas conhecidas.

Somente para o ambiente de desenvolvimento com ERP simulado (ERP_ALLOWED_HOST=127.0.0.1).
Recusa rodar contra qualquer outro host de ERP para não semear senhas públicas em produção.
Uso: cd backend && .venv/bin/python -m app.devseed
"""

import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_app_engine
from app.core.security import hash_password
from app.models import Setor

DEMO = [
    ("Serralheria", "solicitante", "Erivaldo", "setor-demo-12345"),
    ("Manutenção", "solicitante", "Ana", "setor-demo-12345"),
    ("Pintura", "solicitante", "Carlos", "setor-demo-12345"),
    ("Almoxarifado", "almoxarifado", None, "almox-demo-12345"),
]


def main() -> None:
    if get_settings().erp_allowed_host not in {"127.0.0.1", "localhost"}:
        sys.exit("Recusado: este script é só para o ERP simulado (ERP_ALLOWED_HOST=127.0.0.1).")
    engine = get_app_engine()
    if engine is None:
        sys.exit("Defina APP_DATABASE_URL no .env antes de semear os setores.")
    with Session(engine) as session:
        for nome, perfil, lider, senha in DEMO:
            sector = session.scalar(select(Setor).where(func.lower(Setor.nome) == nome.lower()))
            encoded = hash_password(senha)
            if sector is None:
                session.add(Setor(nome=nome, perfil=perfil, lider_nome=lider, senha_hash=encoded))
            else:
                sector.senha_hash = encoded
                sector.ativo = True
            print(f"{nome:<14} {perfil:<13} senha: {senha}")
        session.commit()


if __name__ == "__main__":
    main()
