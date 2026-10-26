# Changelog

## 0.3.0 — revisão de robustez

**Funcional**
- Novo status `Cancelada` e endpoint `POST /api/requests/{id}/cancel` (motivo obrigatório; bloqueado se há baixa preparada/incerta no ERP). UI no Kanban e no histórico.
- Endpoint `POST /api/requests/reconcile` e botão no Kanban para reenviar confirmações incertas com segurança (reutiliza a verificação idempotente).
- Data retroativa limitada por `APP_MAX_BACKDATE_DAYS` (padrão 7), pois vira `toqmovi.pridata`.
- Entrega parcial sem observação passa a ser detectada no cliente, sem depender de texto da mensagem de erro.

**Segurança**
- Rate limit de login passa a ver o IP real atrás do proxy (`--proxy-headers`); antes todos poderiam compartilhar o IP do gateway e bloquear um setor uns dos outros.
- `SameSite=Lax` por padrão (antes `None`, desnecessário na mesma origem).
- Cabeçalhos de segurança (CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy) e `Cache-Control: no-store` na API.
- Exportação CSV neutraliza injeção de fórmulas.
- Host do ERP configurável (`ERP_ALLOWED_HOST`).
- Frontend trata 401 (sessão expirada) voltando ao login.

**Operação e qualidade**
- Migrações SQL idempotentes (`database/migrations/`, `scripts/migrate_local_db.sh`).
- Teste de schema/migração em PostgreSQL real (`TEST_POSTGRES_URL`) e CI (GitHub Actions).
- Exemplo de proxy TLS (`deploy/Caddyfile.example`).
- Removidos artefatos do ambiente de geração (`app.config.ts`, `manus-routes.json`, caminhos absolutos no `pyrightconfig.json`).
- Data do carrinho calculada a cada render (não mais fixa no carregamento do módulo).

- Ambiente de desenvolvimento com ERP simulado (`dev/`): Docker, dados de exemplo, setores de demonstração (`app.devseed`) e roteiro de teste.

**Não alterado de propósito** (dependem de decisão/validação com o ERP): numeração de `itecontrol`, `priusuario` em branco, autenticação individual. Ver `TODO.md`.
