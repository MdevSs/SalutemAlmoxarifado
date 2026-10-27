# Salutem Almoxarifado

Sistema interno para solicitar e atender materiais da Salutem Hospitalares. A aplicação usa **React + TypeScript**, **Python 3.12.10 + FastAPI** e **PostgreSQL**. Ela foi desenhada para rodar em um servidor/computador **dentro da rede local** que alcança o ERP PostgreSQL em `192.168.1.2`.

> **Estado do ambiente:** o código, a configuração Compose e a documentação estão sendo preparados no Sandbox. Não há dispositivo da LAN autorizado nesta sessão; não executei consultas, migrações, INSERTs, nem teste de gatilho no ERP real. Os testes automatizados usam SQLite temporário e uma conexão ERP simulada. Valide em uma janela controlada no servidor da Salutem antes de liberar uso real.

## Arquitetura de dados

Há duas conexões PostgreSQL independentes:

1. **Banco ERP existente:** código/descrição/saldo são consultados na `public.vw_produto_saldo_estoque`; `public.produto` é cruzada para filtrar `prostatus = 'A'`, ler `unimedida` e restringir códigos aos grupos `10` a `13`; as unidades alternativas são lidas em lote da tabela `public.convers1`. Movimentos confirmados são inseridos na `public.toqmovi`. A aplicação não atualiza `produto`, `convers1` nem faz baixa paralela do saldo: a transação `pritransac=14` e os gatilhos do ERP devem executar a movimentação.
2. **Banco novo local da aplicação:** fica no serviço `database` do Compose, num volume persistente do servidor (ou PostgreSQL local no modo PowerShell de desenvolvimento). O schema de negócio tem somente duas tabelas, `setores` e `requisicoes`; a linha especial Administrador e os dados de setor compartilham `setores`, e itens/eventos de requisições ficam em JSONB. Uma sequence PostgreSQL (não uma tabela) gera controles a partir de `84333`.

O ERP é a autoridade do estoque. A aplicação primeiro registra a requisição local como pendente; no atendimento, todos os movimentos são enviados em uma única transação ERP. Como os bancos não compartilham transação ACID, uma queda durante a resposta pode deixar o status local pendente. A rotina reconcilia pelo par `(itecontrol, prisequen)` e compara os valores antes de qualquer repetição; divergência vira conflito para revisão, nunca sobrescrita ou reenvio cego.

O dump anexado foi lido como referência, não executado. Ele contém `CREATE DATABASE` e schema do ERP. **Não o use para criar o banco local.** A definição SQL da view e as funções gatilho não vieram no dump. Os campos `doc_controle`, `doc_operacao` e `notdtdigit` do exemplo não aparecem no DDL de `toqmovi`; são preservados como null no log local, mas não enviados como colunas inexistentes.

## Acesso e identidade

- Cada setor solicitante tem uma senha compartilhada do setor e um líder designado. O hash da senha é Argon2id.
- Há um único acesso compartilhado `Almoxarifado`, também com senha própria. Uma senha redefinida encerra as sessões antigas.
- Há um único acesso `Administrador`, separado, também com senha Argon2id; ele pode usar os fluxos de solicitante e de Almoxarifado e administrar setores. A conta é uma linha especial da tabela `setores`, criada/redefinida pelo CLI, sem terceira tabela.
- No fechamento, o atendente seleciona um nome já informado antes ou digita o nome do responsável. Como a credencial é compartilhada no Almoxarifado, esse campo registra quem foi informado, mas não autentica individualmente a pessoa.
- Sessões usam cookie `HttpOnly`, expiração, CSRF e limitação de tentativas; o backend valida o perfil em cada operação.

## Requisitos do servidor

- Docker Engine/Desktop com Docker Compose v2 e acesso de saída à Internet para baixar as imagens iniciais.
- A máquina deve permanecer ligada e alcançável pelos usuários internos.
- Rota/firewall do servidor até `192.168.1.2:5432` (confirme a porta real do ERP) e autorização do administrador para o usuário PostgreSQL da aplicação. O backend recusa uma `ERP_DATABASE_URL` apontada a outro host.
- PostgreSQL 16.14 local é iniciado pelo Compose; seu volume de dados persiste no disco do servidor e não é publicado na LAN.
- HTTPS interno para os navegadores, por proxy reverso que termine TLS; os cookies da aplicação em Compose usam `Secure` e `SameSite=None`.

Para desenvolvimento ou validação numa máquina Windows, também é possível usar PostgreSQL instalado localmente e executar React/FastAPI pelo PowerShell, sem Docker; veja **Execução local pelo PowerShell (sem Docker)** abaixo. Isso não substitui a implantação do servidor na LAN para acessar o ERP real.

Peça ao DBA do ERP o menor privilégio possível: `SELECT` na view de catálogo/saldo, nas colunas usadas de `public.produto` (incluindo `unimedida`) e nas colunas de conversão de `public.convers1`; `SELECT` em `toqmovi` para reconciliar e `INSERT` em `toqmovi` para gravar movimentos. Nenhuma migração/alteração de schema ERP é necessária. A validação deve confirmar se os gatilhos também precisam de privilégios em funções/objetos relacionados. Não conceda `UPDATE`/`DELETE` em produto/conversões/estoque à aplicação.

## Instalação inicial no servidor LAN

1. Copie o repositório para a máquina do servidor e entre na raiz do projeto.
2. Crie `.env` a partir do exemplo. O exemplo não contém credenciais:

   ```bash
   cp .env.example .env
   ```

3. Preencha `LOCAL_PG_USER`, `LOCAL_PG_PASSWORD`, `ERP_DATABASE_URL` e `APP_SESSION_SECRET` somente no `.env` não versionado do servidor. Gere segredos no próprio host, por exemplo:

   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
   openssl rand -hex 24
   ```

   Use o primeiro valor em `APP_SESSION_SECRET` e um valor alfanumérico aleatório no `LOCAL_PG_PASSWORD`. A URL `ERP_DATABASE_URL` deve apontar ao PostgreSQL real da LAN; nunca a envie em chat nem a grave em Git.

4. Suba o banco novo local. Na primeira criação de um volume vazio, o PostgreSQL inicializa **somente** o schema da aplicação a partir de `database/schema.sql`:

   ```bash
   docker compose up -d database
   docker compose ps
   ```

   Opcionalmente, rode `./scripts/init_local_db.sh` para reaplicar o DDL idempotente no serviço local `database`. O script não aceita DSN ERP.

   Se o volume `salutem_data` já existia antes do perfil Administrador, o Compose não reaplica `schema.sql` automaticamente. Após o banco ficar saudável e **antes** de executar `criar-admin`, aplique a migração no banco local da aplicação:

   ```bash
   docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/migrations/20261022_admin_profile.sql
   ```

   A migração de Administrador atualiza somente `setores`; não a execute no banco ERP. Em seguida, numa instalação existente, aplique a migração local de status parcial e índice por data:

   ```bash
   docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/migrations/20261022_partial_status_and_dates.sql
   ```

   Em instalações existentes, aplique também a migração idempotente dos checks JSONB locais. Ela reconhece checks equivalentes do schema antigo e interrompe a transação sem alterar registros se encontrar documentos fora do formato esperado:

   ```bash
   docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/migrations/20261023_requisicoes_json_arrays.sql
   ```

   Em uma instalação nova, o `schema.sql` já inclui status `Parcial` e índice por data, então as migrações não são necessárias.

5. Construa e suba FastAPI + frontend React:

   ```bash
   docker compose up -d --build app
   docker compose logs --tail=100 app
   curl --fail http://127.0.0.1:8080/health
   ```

6. Provisione os setores iniciais de modo interativo. O terminal pede a senha e a confirmação sem colocá-las nos argumentos do processo:

   ```bash
   docker compose exec app python -m app.cli criar-setor \
     --nome Serralheria --perfil solicitante --lider Erivaldo
   docker compose exec app python -m app.cli criar-setor \
     --nome Almoxarifado --perfil almoxarifado
   docker compose exec app python -m app.cli criar-admin
   ```

   Repita para cada setor e seu líder. O mesmo comando pode redefinir uma senha existente; nomes/tipos de setor não são convertidos pelo CLI. Não reutilize senhas pessoais.

7. Configure o proxy HTTPS interno do host para encaminhar o hostname interno escolhido a `127.0.0.1:8080`. Distribua certificado/CA confiável nos computadores usuários. Não publique o app nem o Postgres na Internet. O app não escuta diretamente em IP de rede pelo Compose, para que somente o proxy faça a entrada TLS.

> **Sequência 84333:** confirme previamente com o DBA que esse controle está disponível no ERP. A aplicação não recalcula nem pula colisões. Se qualquer linha já existir no ERP com conteúdo diferente, a requisição ficará em conflito para revisão.

## Execução local pelo PowerShell (sem Docker)

Use este caminho para desenvolvimento numa máquina Windows com PostgreSQL local instalado. Para catálogo/saldo real, a máquina ainda precisa alcançar o ERP `192.168.1.2:5432` e ter acesso autorizado; sem essa rota, a API reportará o ERP indisponível.

1. Instale Node.js 22, pnpm 11.25.0, Python 3.12.10, uv 0.12.19 e PostgreSQL. Inicie o serviço PostgreSQL pelo Windows; use a base local existente ou crie-a no passo 3 se for uma instalação nova.
2. Abra PowerShell na raiz do repositório, instale as dependências e crie o `.env` privado:

   ```powershell
   pnpm install --frozen-lockfile
   uv python install 3.12.10
   uv sync --project backend --all-extras --locked
   Copy-Item .env.example .env
   notepad .env
   ```

   Preencha `APP_DATABASE_URL` com a conexão da base local; `ERP_DATABASE_URL` somente com a conexão aprovada do ERP; gere `APP_SESSION_SECRET` aleatório. Para HTTP local, configure `APP_COOKIE_SECURE=false` e `APP_COOKIE_SAMESITE=lax`. Não use nem envie o `.env` em Git/chat.

3. **Banco novo vazio:** crie uma base PostgreSQL local e aplique o schema da aplicação (somente ao banco novo/local, nunca ao ERP). Informe um usuário que seja dono da base/tabelas:

   ```powershell
   $pgUser = Read-Host "Usuário PostgreSQL dono da base local"
   # Rode somente se a base ainda não existir:
   createdb -h 127.0.0.1 -U $pgUser -O $pgUser salutem_dev
   psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U $pgUser -d salutem_dev -f .\database\schema.sql
   ```

   O `psql` solicita a senha no terminal. Se o banco já possui as tabelas da versão-base, não reaplique o schema inicial. Para instalações que ainda não receberam perfil Administrador, aplique primeiro a migração de Administrador:

   ```powershell
   psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U $pgUser -d salutem_dev -f .\database\migrations\20261022_admin_profile.sql
   ```

   Ajuste usuário/base aos nomes da sua instalação. Se a conta Administrador já existe (como na versão atualizada), aplique somente a migração nova:

   ```powershell
   psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U $pgUser -d salutem_dev -f .\database\migrations\20261022_partial_status_and_dates.sql
   ```

   Para bases existentes, aplique também o check JSONB local, que reconhece constraints equivalentes e aborta sem alterar registros se os arrays contiverem dados incompatíveis:

   ```powershell
   psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U $pgUser -d salutem_dev -f .\database\migrations\20261023_requisicoes_json_arrays.sql
   ```

   Essas migrações alteram somente a base local `salutem_dev`; nunca as execute no banco ERP. Uma base local recém-criada já recebe os checks, status `Parcial` e índice por data pelo `schema.sql`.

4. Provisione o login Administrador e os demais acessos. Execute a senha pelo prompt protegido do CLI:

   ```powershell
   Set-Location .\backend
   .\.venv\Scripts\python.exe -m app.cli criar-admin
   .\.venv\Scripts\python.exe -m app.cli criar-setor --nome Serralheria --perfil solicitante --lider Erivaldo
   .\.venv\Scripts\python.exe -m app.cli criar-setor --nome Almoxarifado --perfil almoxarifado
   Set-Location ..
   ```

5. Inicie frontend e API juntos em PowerShell:

   ```powershell
   pnpm dev:local
   ```

   Abra `http://localhost:3000`; o Vite encaminha `/api` para FastAPI em `http://127.0.0.1:8000`. Use `Ctrl+C` para encerrar. No PowerShell, `pnpm dev:local` escuta somente em `127.0.0.1` e não expõe as portas de desenvolvimento à LAN. O script `pnpm dev` usa `0.0.0.0` para o Preview Webdev; não o use numa máquina acessível pela rede sem firewall/proxy apropriados.

   Se uma baixa retornar 503, não repita antes de consultar `toqmovi` pelo `itecontrol`. O backend registra no terminal uma linha `ERP finalization DB error ...` com tipo, SQLSTATE e metadados de tabela/coluna/constraint, sem SQL nem valores da linha. Compartilhe essa linha para diagnóstico; a resposta HTTP continua genérica e não contém dados internos do banco. O erro PostgreSQL `42883: function to_char(time with time zone, unknown) does not exist` indica a expressão antiga de `prihralt`; a versão corrigida usa `CAST(LOCALTIME(0) AS text)`.

O app aceita somente grupos ERP 10, 11, 12 e 13, produtos ativos `prostatus='A'`, e pagina catálogo com 20 itens por padrão (seletor até 100). `pnpm typecheck`, `pnpm build` e os comandos Ruff/pytest abaixo servem para validar a instalação:

```powershell
pnpm typecheck
pnpm build
Set-Location .\backend
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\pytest.exe -q
Set-Location ..
```

Os testes automatizados isolados não acessam os DSNs configurados nem enviam movimento ao ERP. `/docs` e `/openapi.json` apresentam o contrato da API; `GET /health` verifica apenas o processo HTTP, não prova que os bancos ou a view estejam acessíveis.

## Backup local

O backup neste projeto cobre somente o PostgreSQL local da aplicação, não o banco ERP:

```bash
./scripts/backup_local_db.sh
```

O arquivo é gravado em `backups/` com permissão restrita e excluído do Git e do build Docker. Copie-o para um destino de backup corporativo criptografado e defina retenção/recovery point com o responsável da Salutem. A restauração lógica com `pg_restore --clean` é destrutiva: faça-a somente numa base de recuperação aprovada após preservar o estado atual.

## Estrutura principal

- `frontend/src/features/`: acesso, catálogo, carrinho, histórico, Kanban e administração de setores.
- `backend/app/api/`: autenticação, setores, materiais ERP e requisições.
- `backend/app/core/`: configuração, cookies/CSRF e engines independentes.
- `backend/app/models/`: somente os modelos locais `Setor` e `Requisicao`.
- `backend/app/services/erp.py`: consulta de saldo, mapeamento de `toqmovi` e reconciliação idempotente.
- `database/schema.sql`: DDL do banco local; não contém DDL ERP.
- `database/migrations/`: evolução de constraints da conta Administrador sem tabela extra.
- `docs/`: arquitetura, mapeamento ERP, API e operação.

Mais decisões e critérios estão em [plan.md](plan.md) e [TODO.md](TODO.md).
