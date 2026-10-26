from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


_JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Setor(Base):
    __tablename__ = "setores"
    __table_args__ = (
        CheckConstraint("length(trim(nome)) > 0", name="ck_setores_nome_nonempty"),
        CheckConstraint(
            "perfil IN ('solicitante', 'almoxarifado', 'administrador')",
            name="ck_setores_perfil",
        ),
        CheckConstraint(
            "(perfil IN ('almoxarifado', 'administrador') AND lider_nome IS NULL) OR "
            "(perfil = 'solicitante' AND lider_nome IS NOT NULL AND length(trim(lider_nome)) > 0)",
            name="ck_setores_lider_por_perfil",
        ),
        Index("uq_setores_nome_ci", text("lower(trim(nome))"), unique=True),
        Index(
            "uq_setores_almoxarifado_single",
            "perfil",
            unique=True,
            sqlite_where=text("perfil = 'almoxarifado'"),
            postgresql_where=text("perfil = 'almoxarifado'"),
        ),
        Index(
            "uq_setores_administrador_single",
            "perfil",
            unique=True,
            sqlite_where=text("perfil = 'administrador'"),
            postgresql_where=text("perfil = 'administrador'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True
    )
    nome: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    perfil: Mapped[str] = mapped_column(String(24), nullable=False)
    lider_nome: Mapped[str | None] = mapped_column(String(120))
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    requisicoes: Mapped[list["Requisicao"]] = relationship(back_populates="setor")


class Requisicao(Base):
    __tablename__ = "requisicoes"
    __table_args__ = (
        # CheckConstraint(
        #     "status IN ('Pendente', 'Em andamento', 'Finalizada', 'Parcial')",
        #     name="ck_requisicoes_status",
        # ),
        # CheckConstraint(
        #     "erp_status IN ('aguardando', 'enviado', 'conflito', 'falhou', 'revisar_saldo')",
        #     name="ck_requisicoes_erp_status",
        # ),
        Index("ix_requisicoes_setor_criado", "setor_id", text("criado_em DESC")),
        Index("ix_requisicoes_status_criado", "status", text("criado_em DESC")),
        Index("ix_requisicoes_data_criado", "data_requisicao", text("criado_em DESC")),
    )

    itecontrol: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    setor_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="RESTRICT"), nullable=False
    )
    setor_nome_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    lider_nome_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    data_requisicao: Mapped[date] = mapped_column(Date, nullable=False)
    instrucoes_entrega: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Pendente")
    observacoes_almoxarifado: Mapped[str] = mapped_column(Text, nullable=False, default="")
    responsavel_confirmacao: Mapped[str | None] = mapped_column(String(120))
    itens: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSON_DOCUMENT, nullable=False, default=list
    )
    eventos: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSON_DOCUMENT, nullable=False, default=list
    )
    erp_status: Mapped[str] = mapped_column(String(24), nullable=False, default="aguardando")
    erp_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erp_erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    setor: Mapped[Setor] = relationship(back_populates="requisicoes")
