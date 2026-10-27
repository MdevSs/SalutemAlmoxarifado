# TODO — Salutem Almoxarifado

Critérios funcionais do protótipo e decisões posteriores do responsável. Itens permanecem em aberto até implementação observável. O banco ERP não foi acessado e nenhum DDL foi executado.

## Progresso e decisões atuais

- A arquitetura atual React/Vite + FastAPI usa PostgreSQL local para setores/requisições e adapter separado para o ERP. A versão atual passou `pnpm typecheck`, `pnpm build`, Ruff e 15 testes isolados; o catálogo busca até `limit + 1` (20 por padrão, máximo 100) e filtra ativos/grupos 10–13. As quantidades digitadas por solicitante e Almoxarifado são inteiras na unidade escolhida; o adapter ERP aceita o resultado canônico convertido com até quatro casas decimais. O Administrador tem acesso aos fluxos solicitante, Almoxarifado e setores, enquanto Almoxarifado não administra setores. Os testes usam SQLite e ERP simulado; não provam integração PostgreSQL/ERP real. A consulta LAN e migração no banco do cliente permanecem pendentes.
- Novo alvo: executar em servidor/computador dentro da LAN; ERP PostgreSQL em `192.168.1.2`; banco novo PostgreSQL local da aplicação.
- O dump `dump-salutem-202610211452.sql` foi inspecionado como texto, sem execução. Mostra DDL de `produto` e `toqmovi`; não tem dados, definição da view, funções gatilho, nem campos `doc_controle`, `doc_operacao`, `notdtdigit` que aparecem nulos no exemplo.
- Duas tabelas de negócio no banco novo: `setores` e `requisicoes`. Itens, eventos/auditoria e estado de sincronização ERP permanecem em JSONB dentro de `requisicoes`; não criar tabelas adicionais de itens, usuários, sessões ou logs.
- Autenticação definida como senha compartilhada por setor e um líder designado por setor. O Almoxarifado também é um setor/senha; na confirmação o operador seleciona ou digita o nome do responsável. O texto do responsável registra quem foi informado, mas não autentica individualmente essa pessoa.
- Sequence `itecontrol` do sistema novo inicia em `84333`; ERP recebe `pritransac=14`, `prideposit=1`, `pridata`, `priproduto`, `priquanti numeric(14,4)`, sequência `prisequen` por item e espaços nos campos de largura fixa especificados.
- O healthcheck local (`/health`) e o manifesto `/manus-routes.json` responderam corretamente. O Sandbox não tem Docker CLI, conectividade comprovada com `192.168.1.2` nem computador LAN autorizado nesta sessão; não executei Compose, migração, acesso real de leitura ou lançamento no ERP.

## Autenticação por setor e administrador — IMPLEMENTADO; PostgreSQL/LAN pendente

- Disponibilizar seleção de setor e autenticação com a senha desse setor; cada setor solicitante tem um líder designado que aparece como responsável pela requisição.
- Tratar Almoxarifado como um setor/senha para acessar atendimento e histórico completo; retirar a aba/seção Administração e a tela Setores e acessos do login Almoxarifado, mantendo a administração somente para o perfil Administrador.
- Armazenar somente hash Argon2id, nunca senha em texto; criar sessão segura e CSRF; aplicar limites de tentativa e autorização por setor/perfil no backend.
- Criar login Administrador com credencial própria; permitir acesso às telas do setor solicitante (catálogo e criação de requisições), do Almoxarifado (atendimento/histórico completo) e à administração de setores. Manter a conta especial na tabela `setores`, sem criar terceira tabela de negócio; requisições criadas pelo Administrador ficam associadas a essa conta.
- Ao sair, encerrar sessão e limpar estado do navegador.
- Na confirmação, permitir selecionar um nome já informado ou digitar o responsável pela baixa; gravar o nome informado e horário no log JSONB. Esse texto é anotação operacional, não autenticação individual.

## Catálogo e saldo vindos do ERP — IMPLEMENTADO; consulta real LAN pendente

- Consultar produtos/saldo na view ERP `public.vw_produto_saldo_estoque` e apresentar o código original de até 16 caracteres e a descrição fornecida pela view; cruzar por código com leitura de `public.produto` somente para filtrar `prostatus = 'A'`; excluir itens inativos e produtos fora dos grupos de primeiro nível `10`, `11`, `12` e `13`; não remover pontuação do código de lançamento.
- Reduzir o tempo de consulta trazendo somente até `limit + 1` produtos para detectar a próxima página; oferecer seletor de produtos por página com padrão `20` e máximo `100` validado no backend. Não contar todos os registros ERP em cada consulta. Implementar navegação Anterior/Próxima, removendo “Carregar mais”.
- Retirar da tela Catálogo o `<select class="field-control" aria-label="Filtrar por grupo">`; os grupos permitidos são fixos no backend em 10, 11, 12 e 13, sem filtro de grupo na interface.
- Consultar saldo na `public.vw_produto_saldo_estoque`, usando código, descrição, depósito e saldo; mostrar depósito 1. Pesquisa por código ou descrição e paginação anterior/próxima.
- Exibir saldo vigente e alertar quando a quantidade selecionada ultrapassar a disponibilidade lida no ERP.
- Catálogo e saldo são somente leitura na aplicação; remover cadastro/edição/importação CSV e ajustes manuais de estoque locais. Não criar/atualizar `produto` nem tabelas de saldo.
- Confirmar conexão somente de leitura à view e à coluna `public.produto.prostatus`, compatibilidade das quatro colunas da view e correspondência dos códigos exclusivamente na máquina da rede, sem exibir URL/credenciais nos logs.

## Carrinho e criação de requisição — IMPLEMENTADO

- Nos cards do catálogo, remover a entrada de quantidade e deixar somente o botão “Adicionar”; ao adicionar, exibir popup/modal para selecionar a quantidade a requisitar. Após confirmar a inclusão, permanecer na tela do Catálogo de Produtos, sem redirecionar para o carrinho.
- Permitir editar quantidade e remover linhas no carrinho; todos os campos de quantidade aceitam somente inteiros e a incrementação/decrementação ocorre em unidades inteiras, sem frações.
- Rejeitar carrinho vazio, quantidades não numéricas, zero/negativas para solicitação e quaisquer valores decimais digitados na interface ou API. A quantidade digitada permanece inteira na unidade escolhida; depois da conversão, `priquanti numeric(14,4)` pode conter até quatro casas decimais na unidade padrão do produto.
- Associar automaticamente o setor autenticado e líder designado; exigir data não futura e permitir instruções de entrega.
- Ao criar, gerar controle numérico com sequence local iniciando em **84333**, status Pendente e armazenamento dos itens/eventos em JSONB na tabela `requisicoes`.
- Mostrar identificador/controle criado; preservar registros locais em caso de indisponibilidade ERP, sem criar uma nova requisição ao repetir uma tentativa.

## Gravação ERP, atendimento e estoque — IMPLEMENTADO; ERP/LAN real pendente

- Para confirmar/finalizar, enviar uma linha `toqmovi` por produto/linha atendida, todos com o mesmo `itecontrol` da requisição e `prisequen` sequencial por item.
- Manter gerados pelas regras do sistema `itecontrol`, `prisequen`, `prideposit`, `pritransac`, `pridata`, `priordem`, `priproduto` e `priquanti` (a coluna real chama-se `priquanti`, escala 4, quantidade canônica na unidade padrão do produto, com até quatro casas decimais após conversão); sem conversão, a quantidade inteira continua com fração `.0000`. No exemplo confirmado `prideposit=1`, `pritransac=14` e `priordem=0`.
- Não deixar como `NULL` as colunas presentes no registro de referência: enviar `0` em `prinivelb`, `pricompra`, `pricmpseq`, `primotdesi` e `priseqpcmp`; `0.00` em `pricusto`, `prialqicms`, `prialqipi`, `priicmfret`, `privldesp`, `privlfrete`, `privlicms`, `privlipi`, `privlourec`, `privlsegur`, `privlsubst`, `privltotal`, `privldecon`, `privlbipi`, `privlbicms`, `pricomiss`, `privlpis`, `privlcof`, `prialcsll`, `privlcsll`, `privlbpis`, `prialret`, `privlret`, `pridesipi`, `pridesfre`, `pribssubst`, `prialqsub`, `privlbret`, `prifalipi`, `prifvlbipi`, `prifvlripi`, `pridespis`, `pridescof`, `prialqdifi`, `privlbdifi`, `privlrdifi`, `priicmfic`, `prialqdeso`, `privlbdeso`, `privlrdeso`, `pridesdsp` e `priredpisc`; `0.0000` em `pribaseipi`, `pribasicms`, `pritmpuni`, `prialpis`, `prialcof`, `pribassub`, `prifbasipi`, `privlrtab`, `pribasdifi`, `priredmva`, `primvasub`, `pribasesub`, `pricarmed`, `priqtgen`, `priqtdnf`, `pribaspis` e `pribasdeso`; `privlarr=0.0000000000`.
- Enviar espaços de largura fixa exatamente como no exemplo: `operacao` (10), `pridocto` (8), `pritribfis` (4), `priclascod` (5), `pritabpre` (3), `pritriipi`/`pritripis`/`pritricof` (2 cada), `priobserv` (100), `pritriissq` (3), `prideonde` (6), `priusuario` (10), `priunimed` (2), `priumnf` (6), `pripedcmpi` (15), `prienqipi` (3) e `priemitido` (1); `priforma='M'`. `pridtalt` recebe a data atual e `prihralt` a hora atual no formato `HH:MM:SS`, ainda sujeitos aos gatilhos do ERP.
- Em retry, reconciliar também esses campos explícitos. Uma linha existente com divergência ou colunas novas nulas gera conflito para revisão manual; nunca inserir de novo, atualizar ou apagar a linha automaticamente, pois o gatilho pode já ter alterado o saldo.
- Não incluir campos que não existem no DDL anexado (`doc_controle`, `doc_operacao`, `notdtdigit`) no INSERT ERP; manter como null nos dados locais se necessário até confirmação de outro schema.
- Confirmar que transação 14 e gatilhos do ERP aplicam a baixa uma única vez; não editar saldo diretamente nem repetir baixa em outra rotina.
- A gravação do lote no ERP é atômica nessa base: ou todos os itens entram e disparam os gatilhos, ou nenhum. O Almoxarifado pode mover o estado operacional de Pendente para Em andamento durante a separação; só depois do commit ERP confirmado a requisição muda para Finalizada. Registrar atendente selecionado/digitado, hora e observações no JSONB.
- Em entrega parcial, registrar exatamente quantidade atendida. Não finalizar com todos os itens em zero; se parcial e sem observação, exigir confirmação explícita.
- Detectar colisão em `(itecontrol, prisequen)`. Não sobrescrever nem recalcular controle silenciosamente. Ao retomar erro de rede, conferir chaves e valores no ERP para reconhecer INSERT já concluído e evitar duplicidade de baixa; divergência passa a conflito para revisão manual.
- Se cada pedido tiver um único lançamento e confirmação, manter estados visíveis Pendente, Em andamento e Finalizada e registrar todos os eventos em `requisicoes` JSONB.

## Histórico e exportação — IMPLEMENTADO; PostgreSQL real pendente

- Líder vê apenas as requisições vinculadas ao seu setor; Almoxarifado vê histórico completo e estado de sincronização ERP. O Kanban do Almoxarifado também permite carregar páginas além dos primeiros 200 pedidos.
- Detalhes devem mostrar controle ERP, setor/líder, produtos/quantidades solicitadas e confirmadas, status, instruções/notas, responsável informado e eventos com data/hora.
- Oferecer busca literal por número, setor, líder, código/descrição, datas, status e responsável; curingas `%`, `_` e `\\` digitados são tratados como texto, e valores JSON são pesquisados sem fazer correspondência nas chaves do documento.
- Paginar resultados de busca do histórico para que requisições além dos primeiros 200 resultados continuem acessíveis; o filtro/pesquisa é aplicado no PostgreSQL local antes da paginação.
- Exportar CSV completo com separador `;`, UTF-8 com BOM, escape correto de aspas e linhas e inclusão do controle ERP e estado de sincronização.

## Setores e administração — IMPLEMENTADO; PostgreSQL real pendente

- O perfil Administrador pode listar, pesquisar, cadastrar, editar e ativar/inativar setores e informar o líder responsável; o login Almoxarifado não vê a aba Administração nem a tela Setores e acessos.
- Manter a linha especial do setor Almoxarifado (senha e perfil próprios); permitir cadastrar e redefinir senha sem mostrar hash/senha atual.
- Preservar requisições históricas vinculadas a setor/líder, mesmo após inativação.
- Não permitir mudanças no catálogo/saldo ERP pela interface.

## PostgreSQL local e apenas duas tabelas — SCHEMA IMPLEMENTADO; aplicação na base do cliente pendente

- Criar script de bootstrap separado do dump ERP para uma base local vazia, com exatamente as tabelas de negócio `setores` e `requisicoes`; não executar o dump anexado.
- `setores`: identificador, nome, perfil/tipo, líder designado, hash da senha e ativo/audit timestamps.
- `requisicoes`: controle/identificador, FK setor, data, campos operacionais, JSONB dos itens/eventos e estado/error/timestamps de sincronização ERP. Manter item e log aninhados; sem terceira tabela de detalhe/outbox/auditoria.
- Criar sequence PostgreSQL local para `itecontrol` com início 84333. A sequence não é tabela. Verificar controle ERP antes do INSERT e falhar com conflito claro se já existir.
- Conectar a dois DSNs independentes em runtime (`APP_DATABASE_URL` local e `ERP_DATABASE_URL` LAN), limitar privilégios e não registrar credenciais. O servidor da aplicação precisa estar dentro da rede ou em ambiente VPN explicitamente autorizado; o backend rejeita `ERP_DATABASE_URL` que não aponta ao host fixado `192.168.1.2`.
- Documentar backup/restore do banco local, reconciliação de pendências e a ausência de transação ACID distribuída entre os bancos.

## Documentação, execução e entrega — DOCUMENTAÇÃO ATUALIZADA; implantação LAN pendente

- Documentar os campos e regras do ERP, processo de criação do banco local com só duas tabelas, instalação/execução no servidor LAN, variáveis, autenticação por setor, exportação, backup e reconciliação.
- Documentar que a view e as funções gatilho não constam do dump, e que os campos extras nulos do exemplo não existem na tabela `toqmovi` do DDL recebido.
- Manter OpenAPI atualizado, rotas e manifesto sincronizados, interface acessível/responsiva em português e direção visual **Clareza Clínica**. Exibir o logo Salutem fornecido na tela de acesso e no cabeçalho autenticado; remover da barra lateral o cartão “Precisa de ajuda? Fale com o almoxarifado” e o rótulo “VERSÃO LAN · 0.2”.
- Executar testes de unidade/local sem alcançar ERP real; teste de integração mutável só na máquina LAN, com janela/autorização do responsável.


## Melhorias adicionais solicitadas em 22/10/2026 — CÓDIGO IMPLEMENTADO; migração local pendente em bases existentes

### Status Parcial após atendimento incompleto — IMPLEMENTADO; executar migração em bases existentes
- Requisito original: “colocar status parcial quando a requisição não for completa”.
- Depois que o Almoxarifado confirmar no ERP, usar status `Parcial` se qualquer item tiver quantidade entregue abaixo da solicitada; usar `Finalizada` somente quando todas as quantidades solicitadas forem atendidas. A confirmação parcial continua registrada como finalizada operacionalmente, não pode ser editada/reconfirmada, e deve ficar identificável no Kanban, histórico e CSV.
- Alterar a constraint de status apenas no banco local da aplicação por migração aditiva; não alterar schema, saldo ou registros do ERP.

### Atualização e organização diária do Kanban — IMPLEMENTADO
- Requisito original: “atualizar diariamente o kanban e organizar por dadas”.
- Recarregar as requisições automaticamente na virada de cada dia local, ao retornar à aba e quando o usuário pedir atualização manual; organizar cards por data da requisição, em ordem mais recente primeiro, preservando as colunas de status.
- Aplicar filtros por data no servidor antes da paginação; não apagar nem modificar pedidos existentes durante a atualização.

### Notificação de finalização ao setor solicitante — IMPLEMENTADO
- Requisito original: “notificação na tela do setor que realizou a requisção quando o pedido for finalizado”.
- Enquanto o setor estiver autenticado na aplicação, exibir aviso acessível na tela quando uma requisição dele for concluída com status `Finalizada` ou `Parcial`. Não revelar requisições de outros setores; não apresentar o aviso inicial para concluir notificações antigas anteriores ao primeiro uso; evitar repetir o mesmo aviso após reconhecê-lo no navegador. O mecanismo é notificação dentro da aplicação, não push com o navegador fechado.
- Adendo de 23/10/2026: ao detectar a finalização, abrir um popup/modal central com destaque visual, número da requisição, estado concluído ou parcial e ações claras para dispensar ou abrir “Minhas requisições”.

### Filtro de datas nas telas de registros — IMPLEMENTADO
- Requisito original: “filtro por data em todas as telas de registros de requisição”.
- Adicionar data inicial e data final inclusivas nas telas do Kanban e do histórico (incluindo “Minhas requisições”); aplicar intervalo sobre `data_requisicao` no backend antes de contar/paginar. Levar o intervalo selecionado à exportação CSV do Almoxarifado.

### Pesquisa multi-termo no catálogo — IMPLEMENTADO
- Requisito original: “na consulta deixar ela mais complexa ex: parafuso 4,5(ele vai pesquisar tudo que tem parafuso e 4,5, como se fosse um like "%parâmetro1%parametro2%"”.
- Dividir a busca em termos, considerar todos os termos na ordem informada como uma pesquisa contém equivalente a `%termo1%termo2%`, sobre código e descrição; manter o filtro existente de produtos ativos, grupos 10–13 e depósito 1.

### Desempenho da consulta do catálogo — IMPLEMENTADO
- Requisito original: “tentar carregar os dados mais rápido no catalogo”.
- Manter paginação ERP com no máximo a página escolhida mais uma linha para `has_more`, sem contagem total; evitar repetir a mesma consulta muito rapidamente com cache pequeno e de curta duração, sem usar o cache para validação ou baixa de estoque.


## Unidade padrão do produto e conversões — IMPLEMENTADO; validação LAN pendente

- Mostrar a unidade padrão lida de `public.produto.unimedida` em cada produto do catálogo, junto ao saldo. Substituir os dois marcadores `#` no popup de adição por texto informativo da unidade padrão do produto.
- No popup do catálogo, permitir escolher a unidade numa lista que inclua a unidade padrão e as conversões válidas do produto em `public.convers1`; exibir sigla (`cvunidade`), descrição (`cvunidesc`) e regra de conversão (`cvuresulta`).
- Ler `convers1` filtrando por `convprod` igual ao código do produto, usando `cvuopera` (`M`/`D`) e `cvucoefici`; não confiar em coeficiente enviado pelo frontend.
- A quantidade digitada pelo solicitante continua sendo um número inteiro positivo na unidade escolhida. Se `M`, converter pela multiplicação `quantidade × coeficiente`; se `D`, converter pela divisão `quantidade ÷ coeficiente`. Exemplos: 1 caixa com coeficiente 20/M resulta em 20 unidades padrão; 10 KG com coeficiente 2/D resulta em 5 unidades padrão.
- Permitir o resultado convertido com até 4 casas decimais, arredondando uma única vez para `numeric(14,4)` com `ROUND_HALF_UP`. Rejeitar unidade não cadastrada, operação diferente de `M`/`D`, coeficiente inválido/zero e resultado convertido não positivo; não fazer baixa zero.
- Guardar no JSONB da requisição quantidade digitada, sigla/descrição selecionadas, unidade padrão, expressão, operação e coeficiente usados, além da quantidade canônica convertida. O carrinho mantém linhas distintas para o mesmo produto quando as unidades selecionadas forem diferentes.
- O Almoxarifado visualiza unidade e quantidade originais e informa a quantidade inteira atendida na mesma unidade solicitada; a API converte com o snapshot do pedido, compara entrega parcial na unidade padrão e envia para `toqmovi.priquanti` somente a quantidade convertida na unidade padrão. Retentativas usam os valores salvos, sem recalcular conversões já confirmadas.
- Restringir leitura do ERP a `public.produto.unimedida` e às colunas `convprod`, `cvunidade`, `cvuopera`, `cvucoefici`, `cvuresulta` e `cvunidesc` de `public.convers1`; não escrever nessas tabelas nem criar tabela de unidade/conversão no banco local. Preservar as duas tabelas locais existentes, colocando novos metadados nos itens JSONB.
- Evidência local: quatro testes dirigidos de catálogo/conversão/criação/baixa passaram; `pnpm --dir frontend typecheck` e `pnpm --dir frontend build` passaram. A suíte completa mostrou falhas em testes de outros caminhos existentes; não foi testado acesso real ou gravação no ERP da LAN.
