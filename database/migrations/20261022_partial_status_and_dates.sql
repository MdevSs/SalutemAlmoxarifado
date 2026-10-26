-- Aplicar somente no PostgreSQL local da aplicação Salutem, nunca no banco ERP.
-- Permite status terminal Parcial e acelera filtros pelo dia da requisição.
BEGIN;

ALTER TABLE public.requisicoes
    DROP CONSTRAINT IF EXISTS ck_requisicoes_status;
ALTER TABLE public.requisicoes
    DROP CONSTRAINT IF EXISTS requisicoes_status_check;
ALTER TABLE public.requisicoes
    ADD CONSTRAINT ck_requisicoes_status
    CHECK (status IN ('Pendente', 'Em andamento', 'Finalizada', 'Parcial'));

CREATE INDEX IF NOT EXISTS ix_requisicoes_data_criado
    ON public.requisicoes (data_requisicao DESC, criado_em DESC);

COMMIT;
