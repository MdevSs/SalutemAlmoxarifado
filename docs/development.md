# Desenvolvimento e operação local

## Estrutura

- `frontend/src/app/`: sessão, navegação e shell React.
- `frontend/src/features/`: acesso, catálogo, carrinho, requisições, Kanban e administração de setores.
- `frontend/src/lib/`: cliente HTTP/CSRF, contratos TypeScript.
- `backend/app/api/`: endpoints de autenticação/setores, leitura ERP e requisições.
- `backend/app/core/`: settings e engines independentes local/ERP.
- `backend/app/models/`: apenas `Setor` e `Requisicao` no PostgreSQL local.
- `backend/app/services/erp.py`: consulta de saldo, movimentos e reconciliação idempotente.
- `database/schema.sql`: somente duas tabelas de negócio locais e a sequence; não é schema ERP.
- `scripts/`: bootstrap local e backup lógico do banco da aplicação.
- `docs/`: API, arquitetura, mapeamento ERP e este guia.

## Ambiente de desenvolvimento

Usar Python 3.12.10 e uv 0.12.19; frontend usa Node.js 22 e pnpm 11.25.0.

```bash
pnpm install
uv python install 3.12.10
uv sync --project backend --all-extras --locked
cp .env.example .env
```

`pnpm dev` inicia Vite em `:3000` e Uvicorn em `:8000`; Vite encaminha `/api` ao backend. Defina `APP_DATABASE_URL` em uma base PostgreSQL local descartável. Para desenvolvimento HTTP local, configure `APP_COOKIE_SECURE=false` e `APP_COOKIE_SAMESITE=lax`; não use esses atributos na implantação HTTPS. Configure `ERP_DATABASE_URL` apenas num host de desenvolvimento que tenha autorização de acesso à LAN. Testes unitários não precisam dessa conexão.

## Ambiente servidor via Compose

`compose.yaml` inicializa PostgreSQL 16.14 no serviço `database` e serve React/FastAPI pelo `app`; os dados do PostgreSQL ficam no volume `salutem_data`, sem porta publicada na LAN. Em volume novo vazio, `database/schema.sql` inicializa automaticamente somente a base local. `scripts/init_local_db.sh` reaplica o DDL idempotente apenas dentro do serviço Compose `database`.

1. Copie `.env.example` para `.env`; defina `LOCAL_PG_USER`, `LOCAL_PG_PASSWORD`, `ERP_DATABASE_URL` e `APP_SESSION_SECRET` no host, sem commitar.
2. `docker compose up -d database`; confira `docker compose ps` e logs de inicialização. Não monte o dump ERP.
3. `docker compose up -d --build app`; escute em `127.0.0.1:8080` por padrão. Use proxy TLS interno para os clientes.
4. Crie/sete senhas iniciais interativamente sem colocá-las na linha de comando:
   ```bash
   docker compose exec app python -m app.cli criar-setor --nome Serralheria --perfil solicitante --lider Erivaldo
   docker compose exec app python -m app.cli criar-setor --nome Almoxarifado --perfil almoxarifado
   ```
5. Confirme `curl http://127.0.0.1:8080/health`. Esse endpoint não executa teste SQL; rode checks de leitura do ERP separadamente no host.

Se já existir volume, não o apague para reaplicar schema. `docker compose down -v` remove o volume Postgres e os dados locais; nunca execute sem cópia, revisão e autorização. `schema.sql` usa `CREATE TABLE IF NOT EXISTS`, mas só é adequado à base dedicada nova da aplicação.

## Privilégios e campos ERP

A API usa `ERP_DATABASE_URL` só no backend. Confirme com o DBA o endereço/porta, `pg_hba.conf`, grants, nome da view, colunas atuais e comportamento transacional dos triggers antes de liberar. Não conceda UPDATE/DELETE do catálogo/estoque. `toqmovi` requer SELECT/INSERT para o adapter; funções acionadas por trigger podem precisar de grants próprios, dependendo de `SECURITY DEFINER`/`INVOKER`.

O dump fornecido tem `CREATE DATABASE`, tabela `produto`, tabela `toqmovi`, índices e triggers, mas não traz conteúdo, DDL da view ou definições de função. Ele é documentação do ERP e não deve ser importado em nenhuma instância. Ver `erp-mapping.md` para a lista de campos e ausências observadas.

## Provisionamento de setores e sessões

Não há cadastro público. Crie o Almoxarifado e depois os setores solicitantes via CLI inicial ou interface interna. Cada setor tem uma senha compartilhada individualmente definida e um líder designado; as senhas não são mostradas de volta. O Almoxarifado tem uma conta compartilhada. A lista/seleção ou texto do responsável ao finalizar é uma anotação informada, não autenticação da pessoa.

O rate limit de login reside em memória do único worker do Compose. Não aumente o número de workers sem projetar um rate limit compartilhado ou na borda (sem criar tabela adicional se a restrição das duas tabelas persistir). Cookies em produção são `HttpOnly`, `Secure; SameSite=None`; configure certificado HTTPS interno confiável nos clientes.

## Verificações

```bash
pnpm typecheck
pnpm build
(cd backend && .venv/bin/ruff check app tests)
(cd backend && .venv/bin/pytest -q)
```

Os testes usam SQLite efêmero e fakes do ERP; não chamam `192.168.1.2`. Não substituem o smoke test autorizado de SELECT na view e um INSERT transacional de teste no ERP. Execute validação mutável só em janela de teste aceita pelo DBA e faça confirmação de reversão no procedimento do ERP; movimentos de estoque podem ser irreversíveis.

## Backup e recuperação

`./scripts/backup_local_db.sh` grava um dump custom do banco local em `backups/`; o diretório está no `.gitignore`/`.dockerignore`. Copie-o para backup criptografado e teste restore somente em base aprovada. `pg_restore --clean` destrói o conteúdo alvo; não executar em produção sem autorização e plano de recuperação. O backup ERP pertence à política do DBA, não a esta aplicação.
