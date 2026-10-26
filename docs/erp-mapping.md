# Mapeamento ERP Salutem

Fonte: `dicionario_dados_produto_toqmovi_saldo_estoque.md` e `dump-salutem-202610211452.sql`, recebidos em 21/10/2026. O dump foi lido como texto; não foi executado nem usado para conectar ao ERP.

## Origem do catálogo e saldo

A view documentada `public.vw_produto_saldo_estoque` expõe os campos indicados no dicionário:

| Campo da view | Uso no aplicativo |
|---|---|
| `codigo_produto_saldo_estoque` | Código de produto, aparado apenas de padding CHAR para exibição e busca |
| `descricao_produto_saldo_estoque` | Descrição na lista/carrinho |
| `codigo_deposito_saldo_estoque` | Filtro fixo `1` |
| `qtde_sldatu_saldo_estoque` | Saldo vigente; quantidades representadas com escala de 4 |

A tabela `public.produto` usa `produto CHAR(16)` como chave primária e possui `pronome CHAR(50)` e `prostatus CHAR(1)`. O adapter cruza a view com `public.produto` usando o código aparado e convertido a `CHAR(16)`, aceita somente `prostatus = 'A'` e restringe códigos aos grupos de primeiro nível `10`, `11`, `12` e `13`. A tabela é consultada apenas para leitura; nenhuma escrita em `produto` é feita. O filtro vale para a página do catálogo e para a validação dos produtos enviados em requisições/baixas.

## Consulta do catálogo e desempenho

O endpoint `/api/materials` recebe pesquisa, `offset` e `limit` (padrão 20, máximo 100). O adapter solicita somente `limit + 1` linhas da view; a linha extra determina `has_more` e não é enviada ao navegador. Assim a interface pagina com Anterior/Próxima, sem buscar o catálogo inteiro, sem consulta separada de grupos e sem `COUNT(*)` total a cada pesquisa. A busca dos códigos de uma requisição é feita em lote numa única consulta, com os mesmos filtros de status, depósito e grupo.

Essa redução limita transferência de dados e evita varredura de contagem completa, mas o custo real depende da definição da view, índices e volume do ERP. A rede Sandbox não alcança o ERP: não foram medidos tempos reais nem executado `EXPLAIN ANALYZE`. Se a página continuar lenta na LAN, peça ao DBA para revisar o plano da consulta em janela controlada; não crie índices/objetos no ERP sem autorização.

> **A validar em LAN:** o dicionário não inclui o `CREATE VIEW`; confirme nomes/tipos das colunas com `information_schema.columns`/`pg_get_viewdef` somente em leitura no servidor autorizado, e confirme que os códigos da view correspondem à chave `public.produto.produto`. A descrição do dicionário também avisa que não é o schema completo de `produto`.

## Movimentos `public.toqmovi`

Chave primária observada: `(itecontrol, prisequen)`. Para cada item efetivamente atendido, a aplicação envia o conjunto completo das 93 colunas definidas no DDL recebido — não apenas os campos da chave e quantidade — para que os campos que o ERP espera não fiquem `NULL`.

| Campos | Valor/regra |
|---|---|
| `itecontrol` | Controle local único por requisição; sequence inicia em `84333`, mesmo controle em todas as linhas |
| `prisequen` | 1..N dentro do controle, contíguo entre linhas com quantidade positiva |
| `prideposit` | `1` |
| `pritransac` | `14` (requisição/retirada) |
| `pridata` | Data da requisição |
| `priordem` | `0`; evita associar a linha a uma ordem de compra |
| `priproduto` | Código retornado pelo ERP; o PostgreSQL completa `character(16)` com padding |
| `priquanti` | Quantidade atendida positiva e inteira, `numeric(14,4)` (ex.: `3.0000`) |
| `pridtalt` | Enviada como `CURRENT_DATE`; o gatilho `tg_toqmovi_datahora` pode sobrescrever |
| `prihralt` | `CAST(LOCALTIME(0) AS text)`, sem fuso e no formato `HH:MM:SS` de 8 caracteres; o gatilho `tg_toqmovi_datahora` pode sobrescrever |

Para as outras colunas do exemplo, valores numéricos são explicitamente zero com a escala da coluna: inteiros `prinivelb`, `pricompra`, `pricmpseq`, `primotdesi`, `priseqpcmp`; valores monetários/percentuais de escala 2 `pricusto`, `prialqicms`, `prialqipi`, `priicmfret`, `privldesp`, `privlfrete`, `privlicms`, `privlipi`, `privlourec`, `privlsegur`, `privlsubst`, `privltotal`, `privldecon`, `privlbipi`, `privlbicms`, `pricomiss`, `privlpis`, `privlcof`, `prialcsll`, `privlcsll`, `privlbpis`, `prialret`, `privlret`, `pridesipi`, `pridesfre`, `pribssubst`, `prialqsub`, `privlbret`, `prifalipi`, `prifvlbipi`, `prifvlripi`, `pridespis`, `pridescof`, `prialqdifi`, `privlbdifi`, `privlrdifi`, `priicmfic`, `prialqdeso`, `privlbdeso`, `privlrdeso`, `pridesdsp`, `priredpisc`; valores de escala 4 `pribaseipi`, `pribasicms`, `pritmpuni`, `prialpis`, `prialcof`, `pribassub`, `prifbasipi`, `privlrtab`, `pribasdifi`, `priredmva`, `primvasub`, `pribasesub`, `pricarmed`, `priqtgen`, `priqtdnf`, `pribaspis`, `pribasdeso`; `privlarr` com escala 10. `priforma` recebe `M`.

Strings em branco são preenchidas com espaços na largura exata: `operacao` (10), `pridocto` (8), `pritribfis` (4), `priclascod` (5), `pritabpre` (3), `pritriipi`, `pritripis`, `pritricof` (2 cada), `priobserv` (100), `pritriissq` (3), `prideonde` (6), `priusuario` (10), `priunimed` (2), `priumnf` (6), `pripedcmpi` (15), `prienqipi` (3) e `priemitido` (1).

O banco apresenta gatilhos `tg_toqmovi`, `tg_toqmovi_datahora` e `tg_toqmovi_saldos` que chamam `fn_toqmovi`, `fn_toqmovi_datahora` e `fn_toqmovi_saldo`, respectivamente. Os corpos das funções não estão no dump; comportamento/ownership, validação de disponibilidade e efeitos colaterais precisam ser confirmados com DBA. O app só deve fazer `INSERT`, não recalcular saldo.

## Campos mencionados no exemplo mas ausentes no dump

O exemplo JSON do usuário contém `doc_controle`, `doc_operacao` e `notdtdigit` como null. Não constam entre as colunas da tabela `toqmovi` do dump. Consequência:

- os nomes/valores nulos são guardados nos metadados JSONB locais do item para não perder o exemplo;
- o adapter não tenta incluir colunas inexistentes no `INSERT` ERP;
- se o ambiente ERP de produção tiver outra versão/schema em que sejam colunas reais, o mapeamento deve ser confirmado e atualizado antes de liberar integração.

As colunas enviadas são verificadas também na reconciliação de retries. A aplicação exige igualdade dos campos de movimento/default e que `pridtalt`/`prihralt` não sejam nulos; não compara a hora exata porque ela é gerada na inserção. Qualquer diferença vira conflito para revisão manual: não há UPDATE, DELETE nem uma segunda tentativa de baixa automática.

## Regras de conflito e retry

A aplicação cria um controle local iniciando em 84333. Antes do INSERT busca as linhas com esse controle. Se corresponderem exatamente às linhas/quantidades e campos preenchidos já gravados, o retry é idempotente e não baixa novamente; se quantidade, data, produto ou qualquer campo operacional/default divergir, marca conflito e exige revisão. A aplicação não pula controle em colisão, não atualiza/edita movimento ERP e não tenta apagar linhas.

A verificação de produto/saldo e todos os INSERTs do pedido ocorrem na transação ERP. Um conflito de chave por atividade concorrente externa causa rollback do lote. Testar a semântica real do gatilho, uma retirada de teste e eventual compensação é responsabilidade do processo de implantação aprovado, não foi feito no Sandbox.
