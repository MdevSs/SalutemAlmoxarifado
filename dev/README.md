# Ambiente de desenvolvimento com ERP simulado

Roda o fluxo completo (catálogo, pedido, atendimento, baixa, cancelamento, reconciliação) no seu
computador, sem tocar no ERP real. O "ERP" é um PostgreSQL descartável (`dev/fake-erp/schema.sql`)
com a view `vw_produto_saldo_estoque` e a tabela `toqmovi`; um gatilho baixa o saldo como o ERP real.

Requisitos: Docker, Node.js 22, pnpm 11.25.0, Python 3.12 e uv.

```bash
docker compose -f dev/compose.dev.yaml up -d      # banco da aplicação (5432) + ERP simulado (5433)
cp dev/env.dev.example .env                       # depois preencha APP_SESSION_SECRET
pnpm install && uv python install 3.12.10 && uv sync --project backend --all-extras --locked
(cd backend && .venv/bin/python -m app.devseed)   # cria setores de demonstração
pnpm dev                                          # abra http://localhost:3000
```

Acessos de demonstração (criados pelo `app.devseed`, que só roda com `ERP_ALLOWED_HOST=127.0.0.1`):

| Setor | Perfil | Senha |
|---|---|---|
| Serralheria (Erivaldo), Manutenção (Ana), Pintura (Carlos) | solicitante | `setor-demo-12345` |
| Almoxarifado | almoxarifado | `almox-demo-12345` |

## Roteiro de teste

1. Entre como **Serralheria**, adicione itens ao carrinho e envie. O número sai a partir de `REQ-84333`.
2. Entre como **Almoxarifado**, inicie o atendimento e finalize informando o responsável.
3. Rode `./dev/erp-status.sh`: as linhas aparecem em `toqmovi` e o saldo caiu.
4. Peça mais que o saldo (ex.: `Saco de lixo 100L`, saldo 3): a aplicação recusa por saldo insuficiente.
5. **Falha e reconciliação:** inicie outro pedido e, antes de finalizar, rode
   `docker compose -f dev/compose.dev.yaml stop fakeerp`. A finalização falha e o pedido fica
   "Pendente de reconciliação" (o cancelamento é bloqueado). Rode `... start fakeerp` e use o botão
   **Reconciliar pendências do ERP**: a baixa é gravada uma única vez.
6. Cancele um pedido pendente (setor) e um em andamento sem baixa preparada (Almoxarifado).

Para voltar ao estado inicial: `docker compose -f dev/compose.dev.yaml down` e suba de novo
(os dados só existem nos contêineres).

> O ERP simulado é uma aproximação: não reproduz os gatilhos, privilégios, numeração de `itecontrol`
> nem o cabeçalho de documento do ERP real. Ele serve para exercitar a aplicação, não para validá-la
> contra o ERP da Salutem.
