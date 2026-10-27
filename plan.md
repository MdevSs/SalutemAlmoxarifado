# Plano — Salutem Almoxarifado

## Objetivo e requisitos confirmados

Aplicação interna em português brasileiro para requisição de materiais hospitalares, baseada no protótipo anexado. Stack obrigatória: React/TypeScript no frontend; Python 3.12.10/FastAPI no backend; PostgreSQL. A aplicação será instalada em um servidor/computador da rede local da Salutem — não será publicada como serviço externo que tente alcançar o ERP privado `192.168.1.2`.

Há duas bases PostgreSQL distintas:

1. **ERP existente em `192.168.1.2`**: catálogo/saldo somente leitura; cadastro de requisições no ERP por inserção de movimentos `public.toqmovi`, cujo gatilho operacional já atualiza estoque. A aplicação não atualiza diretamente produto nem saldo.
2. **PostgreSQL local novo**: persistência da aplicação com exatamente duas tabelas de negócio: `setores` e `requisicoes`. Não haverá tabela separada para itens, eventos, usuários, sessões ou outbox. Itens, trilha de eventos e resultado de sincronização ficam como JSONB em `requisicoes`. Um sequence do PostgreSQL pode gerar os números de controle sem constituir tabela.

## Arquitetura

- **Frontend:** React, TypeScript e Vite; cliente API relativo e telas de entrada, catálogo, carrinho, histórico e atendimento. Usar o logo Salutem fornecido na tela de acesso e no cabeçalho autenticado; remover o cartão genérico “Precisa de ajuda? Fale com o almoxarifado” e o rótulo “VERSÃO LAN · 0.2” da barra lateral. O login administrador pode alternar entre as telas de solicitante, Almoxarifado e administração de setores; a tela de setores não aparece no menu de Almoxarifado.
- **Backend:** Python 3.12.10, FastAPI, SQLAlchemy 2, Pydantic e driver psycopg. Configuração mantém duas conexões separadas: `APP_DATABASE_URL` (banco novo local) e `ERP_DATABASE_URL` (ERP em `192.168.1.2`). Senhas e URLs de banco só em variáveis do servidor, nunca no Git ou frontend. O papel administrador é uma conta especial registrada na tabela `setores`, provisionada por CLI interativa, sem tabela adicional.
- **Host LAN:** caminho de implantação documentado é Docker Compose no servidor/computador Linux com Docker Engine/Compose v2. O modo `pnpm dev` é somente para desenvolvimento; a aplicação de produção precisa alcançar o host ERP pela rede interna. A conta ERP recebe privilégios mínimos: SELECT nos objetos de catálogo/saldo e INSERT/SELECT estritamente necessário em `toqmovi` para idempotência. Não requer acesso de escrita a `produto` ou tabelas de saldo.
- **Catálogo:** consultar código/descrição/saldo em `public.vw_produto_saldo_estoque`, cruzar `public.produto` somente para filtrar `prostatus='A'`, limitar aos grupos de primeiro nível 10, 11, 12 e 13 e ao depósito 1; preservar código ERP `CHAR(16)` (trim somente para exibição). O limite escolhido pelo usuário controla a carga por página, padrão 20 e máximo 100; resultados usam navegação anterior/próxima, sem “carregar mais” nem filtro por grupo. A consulta retorna até `limit+1` linhas para informar `has_more`, evitando buscar registros extras ou contar todo o catálogo; a validação dos códigos submetidos segue os mesmos filtros.
- **Persistência local (exatamente duas tabelas):** `setores` mantém nome, líder designado, hash da senha compartilhada, indicador de ativo e tipo (`solicitante`, `almoxarifado` ou o perfil único `administrador`). A linha do Almoxarifado e a conta Administrador usam o mesmo mecanismo de setor/senha; um índice parcial garante uma conta Administrador. `requisicoes` guarda o número de controle, setor, data/instruções, status e JSONB de itens, histórico, responsável que confirmou, notas e sincronização ERP.
- **Acesso:** senha por setor, compartilhada por todos do setor; cada setor tem líder designado. A conta especial Administrador usa hash Argon2id, cookie HttpOnly, CSRF e limitação de tentativas; pode usar catálogo/carrinho/histórico de solicitante, atendimento/histórico completo de Almoxarifado e administração de setores. Pedidos feitos pelo administrador são associados à linha Administrador na tabela existente `setores`. Almoxarifado não administra setores. O nome informado na baixa continua sendo registro operacional, não autenticação individual.
- **Fluxo funcional:** cada card de produto mostra somente a ação Adicionar; ela abre modal para informar quantidade inteira e escolher unidade; ao confirmar, fecha o modal mantendo o usuário no catálogo. A entrada do solicitante e do Almoxarifado permanece inteira na unidade escolhida (zero é permitido apenas em entrega); o servidor valida inteiros, converte com operação/fator ERP e guarda snapshot no JSONB. `priquanti numeric(14,4)` pode ser fracionário após conversão para `unimedida`, até quatro casas decimais. Acompanhar estados Pendente/Em andamento/Finalizada/Parcial; registrar observações; aceitar entrega parcial; finalizar somente após confirmação ERP; manter detalhes/histórico em JSONB e exportação CSV.

## Regras de inserção no ERP confirmadas

O dump mostra `toqmovi` com chave primária `(itecontrol, prisequen)`, `itecontrol bigint`, `prisequen smallint`, `priproduto CHAR(16)`, `prideposit smallint`, `pritransac smallint`, `pridata date` e `priquanti numeric(14,4)`. A experiência na integração LAN indicou que inserir só as colunas principais deixa vários campos operacionais como `NULL`, o que pode invalidar a requisição no ERP apesar de alterar o saldo. Por isso, o adapter envia explicitamente todas as colunas listadas no exemplo validado pelo responsável, usando zero numérico, espaços com largura fixa e `priforma='M'` conforme os valores especificados; `pridtalt`/`prihralt` são preenchidos com data/hora atuais e continuam sujeitos aos gatilhos ERP. O sistema continua gerando controle, sequência, data solicitada, depósito, transação, ordem, produto e quantidade conforme suas regras:

- `itecontrol`: sequence local inicia em **84333**, incrementando para cada requisição; mesmo valor para todos os itens da requisição;
- `prisequen`: 1, 2, ... por item dentro da requisição;
- `pridata`: data da requisição; `priproduto`: código retornado pelo ERP;
- `prideposit=1`, `pritransac=14`, `priordem=0` e `priquanti` com escala de 4 casas decimais;
- todas as demais colunas incluídas no exemplo são enviadas explicitamente com os respectivos zeros, strings em branco com largura exata ou `priforma='M'`; `pridtalt` e `prihralt` recebem data/hora do banco e podem ser sobrescritas pelo gatilho.

Antes do INSERT, validar colisão no ERP para `(itecontrol,prisequen)`. Uma colisão/conflito não será sobregravada nem contornada silenciosamente. A chave local fixa permite repetir uma tentativa após erro: a reconciliação compara os campos operacionais enviados (incluindo defaults explícitos) e reconhece sucesso idempotente; diferenças, inclusive campos ausentes/nulos em linhas legadas, viram conflito manual e não provocam nova baixa nem atualização automática. O banco local primeiro grava a requisição como pendente de sincronização, depois uma transação ERP tenta inserir todas as linhas; após confirmar ERP, a aplicação atualiza o status local. Como são duas conexões, não existe transação ACID distribuída: quedas serão reconciliadas por status e chaves determinísticas, sem repetir descontos.

## Limites conhecidos do dump

O anexo contém DDL de `produto` e `toqmovi`, mas **não** inclui o `CREATE VIEW` de `vw_produto_saldo_estoque` nem as definições das funções gatilho. A tabela `toqmovi` no dump também não declara os campos citados no exemplo `doc_controle`, `doc_operacao` e `notdtdigit`. Como estão nulos no exemplo e ausentes do DDL, não serão incluídos no INSERT ERP; podem ser preservados como null no log JSONB local. Confirmar a view/rotas e os gatilhos em execução de implantação somente leitura, no host LAN.

O dump fornecido é somente schema e contém `CREATE DATABASE`, `produto`, `toqmovi`, índices e gatilhos; **não é script para executar** na base nova nem na base ERP. Uma migração SQL separada criará somente `setores`, `requisicoes` e a sequence de controle no banco local vazio.

## Integridade, segurança e operação

- Quantidades digitadas em todos os formulários são inteiras; solicitação exige valor positivo, entrega permite zero/inteiro positivo, e o payload API rejeita valores decimais. O backend converte à unidade padrão do produto pelo snapshot `convers1`; `priquanti numeric(14,4)` recebe o resultado arredondado uma vez com `ROUND_HALF_UP` a até quatro casas decimais (por exemplo `0.4718`), ou a inteira com escala `.0000` quando não há conversão.
- O ERP é a autoridade para saldo; movimentos `pritransac=14` disparam os gatilhos de baixa. Não fazer outra baixa no banco local.
- Salvar pedido local com controle persistente antes de chamar o ERP; todos os itens são enviados numa única transação ERP. Falha, conflito ou indisponibilidade deixam estado visível e permitem reconciliação; nunca fazer reenvio cego.
- Sequence `itecontrol` usa `START 84333`; a sequência é do sistema novo. Um controle já existente no ERP resulta em conflito explícito, sem reutilização silenciosa.
- Senhas Argon2id; segredo de sessão aleatório via variável local; cookie seguro conforme HTTPS e origem do ambiente; endpoints exigem papel/setor autorizado e CSRF para escrita.
- Cópias de segurança do banco novo e do ERP permanecem políticas do administrador da rede; aplicação não fará downgrade destrutivo nem executará o dump do ERP.
- Rotas e contratos documentados em Markdown e OpenAPI; `GET /health` não deve expor credenciais.

## Estrutura do projeto

```text
salutemalm/
├── frontend/src/features/         # React: acesso, catálogo ERP, pedidos, atendimento e administração restrita ao admin
├── frontend/public/manus-routes.json
├── backend/app/api/               # endpoints e dependências de papel solicitante/almoxarifado/admin
├── backend/app/core/              # configuração, sessão e conexões de dois bancos
├── backend/app/models/            # apenas Setor e Requisicao
├── backend/app/services/          # ERP adapter, sequência, requisição e reconciliação
├── database/schema.sql            # criação explícita: duas tabelas + sequence local
├── scripts/                       # bootstrap, CLI de provisionamento admin/setores e backup
├── docs/                           # setup LAN, ERP mapping, API e segurança
├── compose.yaml                    # opção de instalação em servidor
├── .env.example                    # valores ilustrativos vazios
├── README.md
├── TODO.md
└── plan.md
```

## Direção visual aprovada — Clareza Clínica

- **Movimento:** clareza clínica aplicada a uma ferramenta interna de operações hospitalares; sobriedade e leitura imediata, sem ornamento que concorra com os dados.
- **Princípios:** legibilidade primeiro; estados sempre explícitos; ações reversíveis e previsíveis; informação operacional densa organizada em camadas.
- **Filosofia de cor:** verde-floresta `#14532D` comunica cuidado e confiabilidade; verde suave `#DFF3E4` cria superfícies de apoio; fundo claro e cinzas quentes reduzem fadiga. Amarelo, azul e verde representam Pendente, Em andamento e Finalizada, sempre com rótulo textual.
- **Layout:** navegação lateral compacta, cabeçalho contextual e conteúdo amplo; Kanban horizontal e tabelas adaptáveis.
- **Assinaturas:** trilha verde de navegação ativa; badges de status textuais; identificadores `REQ` tabulares destacados.
- **Interação/animação:** feedback inline, confirmação apenas para operações destrutivas; transições breves, sem animação contínua, respeitando `prefers-reduced-motion`.
- **Tipografia:** Atkinson Hyperlegible com fallback sans-serif do sistema; números tabulares.
- **Essência/voz:** clareza operacional para o cuidado hospitalar; confiável, humana e precisa. Microcopy direta: “Confira os itens e quantidades antes de enviar.”; “Movimentos confirmados no ERP. Requisição finalizada.”
- **Wordmark:** “Salutem” acompanhado por símbolo geométrico compacto de quatro módulos, sem alegar ser logotipo oficial.
- **Cor de marca:** verde-floresta `#14532D`.


## Ajustes adicionais solicitados — 22/10/2026

- **Status parcial:** após confirmação bem-sucedida no ERP, marcar `Parcial` quando ao menos uma linha for atendida abaixo do solicitado; se todas forem atendidas integralmente, marcar `Finalizada`. Ambos são estados terminais do atendimento confirmado no ERP e devem aparecer no Kanban, histórico e CSV. A migração é somente no PostgreSQL local da aplicação.
- **Kanban por data e atualização diária:** buscar as requisições na API local com filtros/paginação, agrupá-las por data solicitada em ordem cronológica decrescente dentro de cada status, atualizar manualmente e automaticamente na virada do dia local; atualizar também quando a aba voltar ao primeiro plano. Atualizar significa recarregar do banco local, não alterar nem apagar registros.
- **Aviso para o setor:** enquanto a sessão do setor solicitante/Administrador estiver aberta, consultar periodicamente finalizações associadas ao próprio setor e exibir aviso acessível dentro da interface para status `Finalizada` ou `Parcial`. Usar cursor por setor no navegador para evitar repetir avisos já apresentados; não prometer push/notificação com o navegador fechado.
- **Filtro de data:** incluir datas inicial e final inclusivas (sobre `data_requisicao`) nas telas do Kanban e do histórico, para solicitante e Almoxarifado, aplicando os filtros no servidor antes da paginação; a exportação CSV do Almoxarifado também aceitará e respeitará o intervalo.
- **Pesquisa avançada no catálogo:** dividir a entrada em termos e buscar em sequência com semântica equivalente a `LIKE '%parâmetro1%parâmetro2%'`, comparando código e descrição combinados sem tratar caracteres `%`, `_` e `\\` digitados como curingas. Não retirar filtros de ativo/grupos/deposito.
- **Tempo de resposta do catálogo:** manter consulta paginada `limit + 1` sem `COUNT(*)` e usar cache em memória de curta duração, com limite de entradas, indexado por busca/offset/limite. A listagem pode ficar brevemente em cache; validação de disponibilidade/lançamento da requisição continua consultando o ERP sem esse cache.


## Extensão aprovada — unidade de medida e conversões (27/10/2026)

A consulta do catálogo também projetará `public.produto.unimedida` e, em uma consulta ERP agrupada pelos códigos da página, carregará as conversões correspondentes em `public.convers1`: `cvunidade`, `cvuopera`, `cvucoefici`, `cvuresulta` e `cvunidesc`. A API devolverá a unidade padrão e opções de conversão válidas; não serão feitas consultas por produto individual. O catálogo continuará somente leitura e com cache curto, e a validação das opções usadas para criar a requisição consultará o ERP novamente.

O card exibirá unidade padrão e saldo nessa unidade. O modal de Adicionar substituirá os marcadores `#` pela unidade padrão e terá seletor para a unidade padrão ou uma conversão ERP, com a descrição e a expressão da conversão. A quantidade digitada permanece inteira na unidade escolhida. A linha do carrinho é identificada por produto + unidade, para que o mesmo produto em unidades diferentes não seja somado incorretamente.

A API não confiará em coeficientes enviados pelo navegador. No cadastro, confirmará unidade/operação/coeficiente com o ERP, calculará a quantidade canônica em `unimedida` e guardará no JSONB tanto a quantidade/unidade original como um snapshot da conversão (unidade padrão, operação, coeficiente e expressão). Assim a separação e reconciliação de um pedido já criado não mudam caso a tabela ERP seja editada depois.

O Almoxarifado informará uma quantidade inteira na mesma unidade solicitada. O backend converterá usando o snapshot: `M` = multiplicar a quantidade pelo coeficiente; `D` = dividir pela quantidade pelo coeficiente. O resultado será arredondado uma vez para `numeric(14,4)` com `ROUND_HALF_UP`; um resultado não positivo será rejeitado. Entrega parcial compara quantidades canônicas. `toqmovi.priquanti` e a validação de saldo sempre usarão a quantidade canônica na unidade padrão; retries reutilizam o valor canônico já salvo e continuam idempotentes.

A aplicação local mantém apenas as tabelas de negócio `setores` e `requisicoes`; os novos campos são opcionais dentro do JSONB já existente, portanto não exigem migração local nem DDL no ERP. O schema do ERP simulado de desenvolvimento pode incluir `produto.unimedida` e `convers1` apenas para teste. A conta do adapter requer somente leitura de `public.produto.unimedida` e `public.convers1`; nenhuma escrita nessas tabelas.

Este adendo substitui decisões anteriores de que a quantidade enviada ao ERP seria sempre inteira: a quantidade digitada por pessoa permanece inteira; após conversão, o ERP pode receber quantidade fracionária com até quatro casas decimais na unidade padrão.
