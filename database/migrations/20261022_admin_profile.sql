-- Aplicar somente no banco local da aplicação Salutem, não no banco ERP.
-- Permite provisionar a conta Administrador na tabela existente public.setores.
BEGIN;

ALTER TABLE public.setores DROP CONSTRAINT IF EXISTS setores_perfil_check;
ALTER TABLE public.setores DROP CONSTRAINT IF EXISTS ck_setores_perfil;
ALTER TABLE public.setores
    ADD CONSTRAINT ck_setores_perfil
    CHECK (perfil IN ('solicitante', 'almoxarifado', 'administrador'));

ALTER TABLE public.setores DROP CONSTRAINT IF EXISTS ck_setores_lider_por_perfil;
ALTER TABLE public.setores
    ADD CONSTRAINT ck_setores_lider_por_perfil CHECK (
        (perfil = 'solicitante' AND lider_nome IS NOT NULL AND length(trim(lider_nome)) > 0)
        OR (perfil IN ('almoxarifado', 'administrador') AND lider_nome IS NULL)
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_setores_administrador_single
    ON public.setores (perfil) WHERE perfil = 'administrador';

COMMIT;
