import argparse
from getpass import getpass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_app_engine
from app.core.security import hash_password
from app.models import Setor


def main() -> None:
    parser = argparse.ArgumentParser(description="Administração local de acessos Salutem")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "criar-setor", help="Cria ou atualiza um setor e solicita a senha interativamente"
    )
    create.add_argument("--nome", required=True)
    create.add_argument("--perfil", choices=("solicitante", "almoxarifado"), required=True)
    create.add_argument(
        "--lider", default=None, help="Líder designado (obrigatório para solicitante)"
    )
    commands.add_parser(
        "criar-admin", help="Cria ou redefine o único acesso Administrador interativamente"
    )
    args = parser.parse_args()

    if args.command == "criar-admin":
        name, profile, leader = "Administrador", "administrador", None
    else:
        name, profile, leader = args.nome.strip(), args.perfil, args.lider
        if profile == "solicitante" and not (leader and leader.strip()):
            parser.error("Informe --lider para um setor solicitante.")
        if profile == "almoxarifado":
            if name != "Almoxarifado":
                parser.error("O nome do acesso único deve ser Almoxarifado.")
            if leader:
                parser.error("Almoxarifado não usa líder designado.")

    engine = get_app_engine()
    if engine is None:
        parser.error("Defina APP_DATABASE_URL no ambiente local antes de provisionar acessos.")
    password = getpass("Senha (mínimo 12 caracteres): ")
    confirmation = getpass("Confirme a senha: ")
    if password != confirmation:
        parser.error("As senhas não coincidem.")
    try:
        encoded = hash_password(password)
    except ValueError as error:
        parser.error(str(error))

    with Session(engine) as session:
        if profile in {"almoxarifado", "administrador"}:
            sector = session.scalar(select(Setor).where(Setor.perfil == profile))
        else:
            sector = session.scalar(
                select(Setor).where(func.lower(Setor.nome) == name.lower())
            )
        if sector is None:
            sector = Setor(
                nome=name,
                perfil=profile,
                lider_nome=leader.strip() if leader else None,
                senha_hash=encoded,
            )
            session.add(sector)
        else:
            if sector.perfil != profile:
                parser.error("O perfil de um setor existente não pode ser convertido pelo CLI.")
            sector.nome = name
            sector.perfil = profile
            sector.lider_nome = leader.strip() if leader else None
            sector.senha_hash = encoded
            sector.ativo = True
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            parser.error(
                "Conflito ao provisionar o acesso. Verifique se o nome/perfil já existe e, "
                "para um banco criado antes do Administrador, aplique "
                "database/migrations/20261022_admin_profile.sql."
            )
        print(f"Acesso {sector.nome!r} provisionado; senha armazenada como hash.")


if __name__ == "__main__":
    main()
