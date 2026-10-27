-- ERP SIMULADO, somente para desenvolvimento local. Reproduz só o que a aplicação usa:
--   public.vw_produto_saldo_estoque (leitura), public.produto (leitura),
--   public.convers1 (leitura) e public.toqmovi (INSERT + leitura).
-- Um gatilho imita o ERP real: transação 14 baixa o saldo e recusa saldo negativo.
-- NUNCA aponte isto (nem ERP_ALLOWED_HOST=127.0.0.1) para um ambiente de produção.

CREATE TABLE public.produto_saldo (
    codigo    char(16)      NOT NULL,
    descricao varchar(120)  NOT NULL,
    deposito  integer       NOT NULL DEFAULT 1,
    saldo     numeric(14,4) NOT NULL DEFAULT 0,
    PRIMARY KEY (codigo, deposito)
);

CREATE TABLE public.produto (
    produto    char(16) NOT NULL PRIMARY KEY,
    pronome    char(50) NOT NULL,
    prostatus  char(1)  NOT NULL DEFAULT 'A',
    unimedida  char(6)  NOT NULL DEFAULT 'UN'
);

CREATE TABLE public.convers1 (
    convprod   char(16)      NOT NULL,
    cvunidade  char(6)       NOT NULL,
    cvuopera   char(1)       NOT NULL CHECK (cvuopera IN ('M', 'D')),
    cvucoefici numeric(15,4) NOT NULL CHECK (cvucoefici > 0),
    cvuresulta char(30)      NOT NULL,
    cvunidesc  char(20)      NOT NULL,
    PRIMARY KEY (convprod, cvunidade)
);

CREATE VIEW public.vw_produto_saldo_estoque AS
SELECT codigo    AS codigo_produto_saldo_estoque,
       descricao AS descricao_produto_saldo_estoque,
       saldo     AS qtde_sldatu_saldo_estoque,
       deposito  AS codigo_deposito_saldo_estoque
FROM public.produto_saldo;

CREATE TABLE public.toqmovi (
    itecontrol integer       NOT NULL,
    prisequen  integer       NOT NULL,
    pridata    date          NOT NULL,
    priproduto char(16)      NOT NULL,
    prideposit integer       NOT NULL,
    pritransac integer       NOT NULL,
    priquanti  numeric(14,4) NOT NULL,
    operacao   char(10),
    pridocto   char(8),
    priemitido char(1),
    priusuario char(10),
    PRIMARY KEY (itecontrol, prisequen)
);

CREATE FUNCTION public.fn_toqmovi_baixa() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    novo numeric;
BEGIN
    IF NEW.pritransac = 14 THEN
        UPDATE public.produto_saldo
           SET saldo = saldo - NEW.priquanti
         WHERE codigo = NEW.priproduto AND deposito = NEW.prideposit
        RETURNING saldo INTO novo;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ERP simulado: produto % sem saldo no deposito %',
                btrim(NEW.priproduto), NEW.prideposit;
        END IF;
        IF novo < 0 THEN
            RAISE EXCEPTION 'ERP simulado: saldo negativo para %', btrim(NEW.priproduto);
        END IF;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_toqmovi_baixa
AFTER INSERT ON public.toqmovi
FOR EACH ROW EXECUTE FUNCTION public.fn_toqmovi_baixa();

INSERT INTO public.produto_saldo (codigo, descricao, deposito, saldo) VALUES
    ('10.001.0001', 'Parafuso sextavado inox M8 x 40', 1, 500),
    ('10.001.0007', 'Parafuso inox 6mm', 1, 100),
    ('10.001.0008', 'Produto de demonstração de conversão', 1, 100),
    ('10.001.0012', 'Porca sextavada inox M8', 1, 800),
    ('10.002.0001', 'Disco de corte 7 pol', 1, 60),
    ('10.002.0004', 'Lixa d''agua grao 220', 1, 150),
    ('20.001.0003', 'Lampada LED 9W', 1, 120),
    ('20.001.0009', 'Fita isolante 20m', 1, 45),
    ('20.002.0002', 'Cabo flexivel 2,5mm (rolo)', 1, 12),
    ('30.001.0001', 'Tinta acrilica branca 18L', 1, 8),
    ('30.001.0005', 'Rolo de pintura 23cm', 1, 25),
    ('40.001.0002', 'Detergente neutro 5L', 1, 30),
    ('40.001.0008', 'Saco de lixo 100L (pct)', 1, 3),
    ('50.001.0001', 'Luva nitrilica (par)', 1, 200),
    ('50.001.0004', 'Oculos de protecao', 1, 40),
    ('50.002.0001', 'Mascara PFF2', 1, 0),
    ('10.001.0001', 'Parafuso sextavado inox M8 x 40', 2, 999);

INSERT INTO public.produto (produto, pronome, prostatus, unimedida)
SELECT codigo, left(descricao, 50)::char(50), 'A', 'UN'
FROM public.produto_saldo
ON CONFLICT (produto) DO NOTHING;

-- Demonstra as duas conversões informadas pelo responsável para um mesmo produto.
INSERT INTO public.convers1
    (convprod, cvunidade, cvuopera, cvucoefici, cvuresulta, cvunidesc)
VALUES
    ('10.001.0008', 'KG', 'D', 21.1950, '1 KG = 0.0472 UN', 'KILOGRAMA'),
    ('10.001.0008', 'PT', 'M', 1.0000, '1 PT = 1.0000 UN', 'PACOTE');
