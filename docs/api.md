# API REST

A API é servida pelo mesmo host da interface em `/api`. A especificação OpenAPI está em `/openapi.json` e `/docs`.

## Sistema e sessão

| Método | Caminho | Acesso e comportamento |
|---|---|---|
| `GET` | `/health` | Liveness HTTP; não verifica conexão aos bancos. |
| `GET` | `/api/health` | Liveness da API; não atesta objetos ERP. |
| `GET` | `/api/auth/csrf` | Define cookie CSRF e retorna token a ser enviado no header `X-CSRF-Token`. |
| `GET` | `/api/auth/sectors` | Lista setores ativos para seleção na tela de acesso. |
| `POST` | `/api/auth/login` | `{sector_id, password}`; exige CSRF; cria cookie de sessão e retorna setor/líder. |
| `GET` | `/api/auth/me` | Retorna identidade atual, ou 401 se sessão ausente/expirada. |
| `POST` | `/api/auth/logout` | Exige sessão e CSRF; apaga cookies. |

A senha é compartilhada pelo setor e nunca retorna da API. Senhas novas têm mínimo de 12 caracteres, hash Argon2id, limite de 128 caracteres e são solicitadas no CLI/UI protegida; cookie de sessão é `HttpOnly`. Almoxarifado é um único acesso. O Administrador é uma única conta separada, armazenada como perfil na tabela `setores`, provisionada com `python -m app.cli criar-admin`; ela não pode ser criada/alterada na tela de setores. Nome digitado/selecionado pelo Almoxarifado registra quem foi informado, mas não substitui autenticação individual.

## Setores (Administrador)

| Método | Caminho | Corpo/uso |
|---|---|---|
| `GET` | `/api/sectors` | Lista setores operacionais (sem a conta Administrador), líder, perfil e ativo; restrito ao perfil Administrador. |
| `POST` | `/api/sectors` | `{name, profile, leader_name, password}`; líder obrigatório para `solicitante`; nome fixo `Almoxarifado` para o perfil único. |
| `PATCH` | `/api/sectors/{id}` | Campos parciais `name`, `leader_name`, `active`, `new_password`; mudança de nome/líder não altera snapshots em requisições existentes. |

Operações mutáveis exigem cookie de sessão, perfil Administrador e header CSRF. O Almoxarifado não recebe acesso ao endpoint nem à aba Setores e acessos. Setores são inativados, não removidos.

## Catálogo ERP (somente leitura)

| Método | Caminho | Parâmetros |
|---|---|---|
| `GET` | `/api/materials?search=&offset=0&limit=20` | Pesquisa por código/descrição; limite padrão 20, opções de 20 a 100 e `limit` máximo 100. Retorna apenas a página e `has_more`, sem contagem total do ERP. Requer sessão. |

Código, descrição e saldo são consultados em `public.vw_produto_saldo_estoque`; o adapter cruza a view com `public.produto` por código e só retorna registros com `prostatus = 'A'`, depósito 1 e códigos dos grupos de primeiro nível `10`, `11`, `12` ou `13`. A pesquisa divide a entrada em termos na ordem digitada: `parafuso 4,5` equivale a uma busca contém como `%parafuso%4,5%`, aplicada ao código, à descrição e à combinação dos dois. Os curingas `%`, `_` e `\` digitados pelo usuário são tratados como texto. O adapter mantém a linha extra para detectar próxima página sem `COUNT(*)`; páginas idênticas podem ser reutilizadas por 10 segundos, somente na listagem. A validação de códigos/estoque e os lançamentos continuam consultando o ERP diretamente.

A resposta de cada produto inclui `default_unit` de `public.produto.unimedida` e `unit_options` (unidade padrão e conversões válidas lidas em lote de `public.convers1`). Cada opção informa `code`, `description`, `operation` (`M` ou `D`), `coefficient`, `result` e `is_default`. A conta de integração precisa de leitura dessas colunas; o aplicativo não escreve em `produto` nem em `convers1`.

## Requisições

| Método | Caminho | Acesso e comportamento |
|---|---|---|
| `GET` | `/api/requests?status=&search=&date_from=&date_to=&offset=0&limit=50` | Setor solicitante vê somente seus próprios registros; Almoxarifado e Administrador veem todos. `date_from` e `date_to` são inclusivas e filtram a data da requisição antes da contagem/paginação. `search` aceita vários termos em sequência (`%termo1%termo2%`) em controle, setor/líder, datas, status, ERP, instruções, notas, responsável, código/descrição e ator/nota/data dos eventos; `%`, `_` e `\` são escapados como texto. Aceita `REQ-84333` e datas `dd/mm/aaaa`. Intervalo invertido retorna 422; `limit` máximo 200. Ordena por criação decrescente e, em empate, `itecontrol` decrescente. |
| `POST` | `/api/requests` | `{requested_date, delivery_instructions, items:[{material_code, quantity, unit_code}]}`; papel solicitante ou Administrador, CSRF. A API lê descrição, unidade padrão e conversões no ERP, resolve setor/líder da sessão e não confia em coeficiente enviado pelo cliente. `quantity` deve ser um inteiro positivo na unidade selecionada; `unit_code` deve ser a unidade padrão ou uma conversão ERP válida. |
| `GET` | `/api/requests/responsibles` | Nomes previamente informados; restrito ao Almoxarifado e Administrador. |
| `GET` | `/api/requests/notifications/finalized?after=<ISO-8601>&after_control=0` | Setor solicitante ou Administrador; retorna até 100 novas requisições `Finalizada`/`Parcial` do próprio setor, ordenadas por data de finalização e controle. O cursor pareado evita repetir avisos com timestamps iguais; Almoxarifado e outros setores não acessam esses avisos. |
| `GET` | `/api/requests/export.csv?date_from=&date_to=` | Histórico CSV com `;` e BOM UTF-8, restrito ao Almoxarifado e Administrador. Intervalo inclusivo filtra `data_requisicao`; sem datas exporta tudo. |
| `GET` | `/api/requests/{itecontrol}` | Detalhe; setor solicitante só acessa o próprio, Almoxarifado e Administrador acessam todos. |
| `POST` | `/api/requests/{itecontrol}/start` | Almoxarifado/Administrador + CSRF; muda Pendente para Em andamento. |
| `PUT` | `/api/requests/{itecontrol}/notes` | Almoxarifado/Administrador + CSRF; atualiza observação antes de finalização. |
| `POST` | `/api/requests/{itecontrol}/finalize` | Almoxarifado/Administrador + CSRF; `{responsible_name, warehouse_notes, confirm_partial_without_note, deliveries:[{item_index, quantity}]}`. As quantidades são inteiras não negativas na unidade originalmente solicitada e não podem superar o pedido. O backend usa o snapshot de conversão do item, compara atendimento parcial na unidade padrão e envia apenas quantidades canônicas positivas ao ERP. |

O número legível é `REQ-{itecontrol}`. Controle local inicia em 84333; cada linha ERP usa esse `itecontrol` e sequência `prisequen` de 1..N. A interface e a API aceitam quantidades digitadas inteiras na unidade selecionada. `toqmovi.priquanti numeric(14,4)` contém a quantidade convertida para `unimedida`, arredondada uma vez com `ROUND_HALF_UP` a no máximo quatro casas decimais; sem conversão, a representação permanece como `3.0000`. O pedido local guarda a unidade e o fator usados, para que a baixa e a reconciliação não dependam de futuras alterações em `convers1`.

## Estados e erros

Estado operacional: `Pendente` → `Em andamento` → `Finalizada` ou `Parcial`. Depois que o ERP confirma o lote, `Parcial` é usado quando ao menos uma linha teve quantidade entregue menor que a solicitada; `Finalizada` indica atendimento integral. Ambos são estados terminais e têm data/responsável de finalização. A constraint e o índice de data alterados por esta versão pertencem somente ao banco local da aplicação e são atualizados por `database/migrations/20261022_partial_status_and_dates.sql`; não execute a migração no ERP. Uma falha ERP não marca pedido como Finalizada/Parcial e não autoriza repetição cega. `erp_status` pode ser `aguardando`, `enviado`, `conflito`, `falhou` ou `revisar_saldo`.

- `401`: sessão ausente, inválida, expirada, setor inativo ou senha alterada.
- `403`: CSRF inválido ou perfil sem autorização.
- `404`: controle inexistente ou recurso não visível ao setor.
- `409`: estado incompatível, controle já usado com dados diferentes ou entrega parcial sem nota/confirmação.
- `422`: payload, intervalo de data, saldo ou quantidade inválidos.
- `503`: banco necessário indisponível/não configurado.

O Kanban busca requisições do banco local, agrupa cards por data em cada coluna e atualiza na virada do dia local, ao retornar à aba ou manualmente. Quando uma requisição do setor fica `Finalizada` ou `Parcial`, a tela do setor abre um popup/modal com o número do pedido, o status e ações para fechar ou abrir o histórico. A verificação ocorre enquanto a sessão está aberta; o navegador não gera push quando a aplicação está fechada. Todo POST/PATCH/PUT mutável usa CSRF. Exceções de banco não retornam DSN, senha ou stack trace ao navegador.


O cursor de notificações aceita timestamp ISO-8601 com fuso explícito (recomendado); timestamps sem offset são interpretados como UTC. A interface persiste o timestamp retornado sem truncar microssegundos.


## Diagnóstico e exportação segura

O endpoint `GET /api/requests/export.csv` prefixa com apóstrofo células textuais que começam com `=`, `+`, `-` ou `@`, inclusive quando esses caracteres são precedidos por espaços ou controles, para impedir que o arquivo exportado seja interpretado como fórmula de planilha. Os dados armazenados não são alterados.

Quando `POST /api/requests/{itecontrol}/finalize` retorna 503 por erro SQLAlchemy/PostgreSQL, a resposta HTTP permanece genérica. O backend registra no terminal do servidor o controle, tipo, SQLSTATE, mensagem primária e metadados de tabela/coluna/constraint, sem SQL nem valores da linha. Esse diagnóstico serve à equipe técnica; ele não prova que o ERP fez rollback. Antes de outra tentativa, consulte o mesmo `itecontrol` no ERP e use somente o mesmo controle/quantidades para reconciliação.
