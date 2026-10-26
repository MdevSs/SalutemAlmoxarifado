# Revisão integral do Salutem Almoxarifado — 23/10/2026

## Resumo executivo

Foi feita uma revisão estática independente em cinco frentes: APIs/autenticação, persistência e integração ERP, interface React, documentação/implantação e cobertura de testes. A equipe corrigiu três defeitos de comportamento/segurança e fechou uma lacuna de migração do banco local. Depois, o log real do usuário identificou também a causa do 503 no controle `84346`: a expressão antiga de `prihralt` chamava `to_char(CURRENT_TIME, ...)`, função inexistente para o tipo PostgreSQL `time with time zone`. O código foi corrigido e testado; a confirmação de uma baixa bem-sucedida ainda depende do ERP da LAN.

A validação de código da geração `toqmovi` encontrou correspondência exata entre o `INSERT` do aplicativo e as 93 colunas do DDL ERP fornecido: oito campos de negócio permanecem controlados pela lógica da requisição, dois campos de auditoria são gerados pelo ERP/SQL e as 83 demais colunas recebem defaults explícitos e não nulos. Isso valida o código contra o dump recebido, não contra o esquema vivo do servidor.

## Correções feitas nesta revisão

1. **Diagnóstico do 503:** a exceção de SQLAlchemy/PostgreSQL agora gera no terminal da API uma linha com `itecontrol`, classe do erro, SQLSTATE, mensagem primária e metadados de schema/tabela/coluna/constraint. A mensagem HTTP continua genérica; o log não inclui SQL, parâmetros nem valores de linhas. O teste também confirma que credenciais na mensagem são redigidas.
2. **Exportação CSV:** células textuais iniciadas por `=`, `+`, `-` ou `@`, inclusive após espaços/caracteres de controle, recebem apóstrofo apenas na exportação para impedir interpretação como fórmula. O dado original no banco não é alterado; há cobertura de unidade e do endpoint CSV.
3. **Filtros de data:** Histórico e Kanban agora não enviam consultas nem páginas adicionais quando a data inicial é posterior à final; as telas apresentam a validação local.
4. **Servidor de desenvolvimento:** `pnpm dev:local` foi adicionado para PowerShell e escuta somente em `127.0.0.1`. O comando `pnpm dev` mantém `0.0.0.0` para o Preview Cloud do Webdev; a documentação alerta para não usar esse comando em uma máquina exposta à LAN sem proteção.
5. **Banco local:** as constraints JSONB de `itens` e `eventos` agora têm nomes estáveis no schema novo e uma migração aditiva idempotente para instalações existentes. A migração reconhece checks equivalentes do schema antigo e aborta sem corrigir/apagar linhas se encontrar dados incompatíveis. README documenta a ordem das migrações e usa `ON_ERROR_STOP` no `psql`.
6. **PowerShell:** o README esclarece quando criar a base local e inclui o comando `createdb` para instalações novas.

## Verificação da implementação `toqmovi`

A auditoria local comparou programaticamente `backend/app/services/erp.py` com o bloco `CREATE TABLE public.toqmovi` do dump recebido:

- 93 de 93 colunas do DDL são incluídas no `INSERT`, sem colunas extras;
- os campos protegidos permanecem dinâmicos: `itecontrol`, `prisequen`, `prideposit`, `pritransac`, `pridata`, `priordem`, `priproduto` e `priquanti`;
- `pridtalt` e `prihralt` continuam gerados por expressões SQL de data/hora, fora do mapa de defaults;
- as outras 83 colunas são supridas pelo mapa `_ERP_MOVEMENT_DEFAULTS`; nenhuma recebe `None` nesse mapa;
- os retries comparam os campos de negócio e todos os defaults; não fazem `UPDATE` nem `DELETE` em `toqmovi`.

**Limite importante do esquema:** `doc_controle`, `doc_operacao` e `notdtdigit`, mencionados como `null` no exemplo resumido inicial, não existem entre as colunas da tabela no dump fornecido. O aplicativo guarda esses nomes no JSON local de referência, mas não os envia ao `INSERT` ERP. Se estiverem presentes no esquema vivo, o DBA precisa fornecer o DDL atualizado para uma alteração segura. O mapeamento e essa ressalva também estão em `docs/erp-mapping.md`.

## Achados remanescentes e limitações

- **Confirmação ERP após a correção:** o erro registrado para `84346` aconteceu ao resolver a função inválida no `INSERT`, antes de gravar as linhas. A consulta sem resultados apresentada pelo usuário foi para `84345`, não `84346`. O código agora usa `CAST(LOCALTIME(0) AS text)`, que produz o horário local sem fuso no formato de 8 caracteres exigido; os testes e a verificação de parâmetros passaram, mas o Sandbox não tem conexão à LAN para confirmar a baixa. Antes de nova tentativa, consulte `84346` no ERP. Se houver linhas, não repita. Se não houver, atualize o código, reinicie `pnpm dev:local` e faça uma única tentativa; envie apenas a linha sanitizada do terminal se falhar.
- **Rate limit de login:** o limite de cinco falhas por quinze minutos é mantido em memória no processo. Reinício ou múltiplos workers podem contorná-lo; uma implantação com vários workers deve adotar rate limit compartilhado/centralizado por conta e IP.
- **Cobertura que ainda merece expansão:** testes dedicados para isolamento entre dois setores, falha de resposta após COMMIT ERP e reconciliação, migrações em PostgreSQL descartável, empates de cursor de notificação e comportamentos React em runtime. A suíte atual de backend roda em SQLite isolado e não prova particularidades de PostgreSQL.
- **Ambiente não reproduzido:** não executamos os comandos PowerShell no Windows e não aplicamos a nova migração em banco. Isso deve ocorrer primeiro numa cópia/base local de teste; a migração é exclusiva do PostgreSQL local da aplicação e nunca deve ser apontada ao ERP.

## Validações executadas

- Backend: **23 testes aprovados**; Ruff sem erros; OpenAPI carregado com 18 rotas.
- Frontend: `pnpm typecheck` aprovado e build Vite de produção aprovado.
- Diff: `git diff --check` aprovado.
- Uma advertência não bloqueante permanece: `StarletteDeprecationWarning` recomenda `httpx2` para `TestClient`; não causa falha nos testes.

Nenhum comando de escrita foi executado no banco local do usuário nem no ERP durante esta revisão.
