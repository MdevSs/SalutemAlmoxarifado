-- Aplicar somente no PostgreSQL local da aplicação Salutem, nunca no banco ERP.
-- Garante que os documentos JSONB usados como listas continuem sendo arrays.
-- Reconhece checks equivalentes que versões antigas do schema.sql nomearam automaticamente.
BEGIN;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.requisicoes'::regclass
          AND contype = 'c'
          AND (
              conname = 'ck_requisicoes_itens_array'
              OR position('jsonb_typeof(itens)' IN pg_get_constraintdef(oid)) > 0
          )
    ) THEN
        IF EXISTS (
            SELECT 1 FROM public.requisicoes
            WHERE jsonb_typeof(itens) IS DISTINCT FROM 'array'
        ) THEN
            RAISE EXCEPTION 'requisicoes contém itens que não são JSON arrays; inspecione os dados locais antes de aplicar a migração';
        END IF;
        ALTER TABLE public.requisicoes
            ADD CONSTRAINT ck_requisicoes_itens_array
            CHECK (jsonb_typeof(itens) = 'array') NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.requisicoes'::regclass
          AND contype = 'c'
          AND (
              conname = 'ck_requisicoes_eventos_array'
              OR position('jsonb_typeof(eventos)' IN pg_get_constraintdef(oid)) > 0
          )
    ) THEN
        IF EXISTS (
            SELECT 1 FROM public.requisicoes
            WHERE jsonb_typeof(eventos) IS DISTINCT FROM 'array'
        ) THEN
            RAISE EXCEPTION 'requisicoes contém eventos que não são JSON arrays; inspecione os dados locais antes de aplicar a migração';
        END IF;
        ALTER TABLE public.requisicoes
            ADD CONSTRAINT ck_requisicoes_eventos_array
            CHECK (jsonb_typeof(eventos) = 'array') NOT VALID;
    END IF;
END
$migration$;

DO $validation$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.requisicoes'::regclass
          AND conname = 'ck_requisicoes_itens_array'
          AND NOT convalidated
    ) THEN
        ALTER TABLE public.requisicoes
            VALIDATE CONSTRAINT ck_requisicoes_itens_array;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.requisicoes'::regclass
          AND conname = 'ck_requisicoes_eventos_array'
          AND NOT convalidated
    ) THEN
        ALTER TABLE public.requisicoes
            VALIDATE CONSTRAINT ck_requisicoes_eventos_array;
    END IF;
END
$validation$;

COMMIT;
