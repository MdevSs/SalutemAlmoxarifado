-- Migração 001: adiciona o status 'Cancelada' a bancos locais já criados.
-- Idempotente. Aplicar somente no banco LOCAL da aplicação (nunca no ERP).
BEGIN;
ALTER TABLE public.requisicoes DROP CONSTRAINT IF EXISTS requisicoes_status_check;
ALTER TABLE public.requisicoes DROP CONSTRAINT IF EXISTS ck_requisicoes_status;
ALTER TABLE public.requisicoes ADD CONSTRAINT ck_requisicoes_status
    CHECK (status IN ('Pendente', 'Em andamento', 'Finalizada', 'Cancelada'));
COMMIT;
