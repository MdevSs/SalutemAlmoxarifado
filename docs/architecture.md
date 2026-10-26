# Arquitetura

## Contexto de execução

A aplicação é um monólito modular React/TypeScript + FastAPI em um servidor da LAN Salutem. O navegador conversa com endpoints relativos `/api`; em produção o próprio FastAPI serve o build de Vite. O Compose publica o container apenas em `127.0.0.1:8080`; proxy reverso interno termina HTTPS e encaminha a porta local. A API é stateless entre requisições, com identidade assinada em cookie e dados persistentes exclusivamente no PostgreSQL local e no ERP.

O sandbox de desenvolvimento não tem rota para `192.168.1.2`. Portanto, execução Compose, conectividade LAN, certificados, grants e gatilhos ERP precisam ser validados no host interno; não assumir que o healthcheck do Sandbox demonstra essa conectividade.

## Fronteiras de dados

### PostgreSQL local novo

O schema `public` do banco novo tem duas tabelas de negócio:

- `setores`: setor, perfil, líder atualmente designado, hash de senha Argon2id, ativo e timestamps. Existe um único acesso Almoxarifado. Inativar um setor não remove requisições antigas.
- `requisicoes`: `itecontrol` como chave primária local, FK para o setor, snapshots imutáveis do nome do setor/líder no momento do pedido, data, instruções, status, notas/responsável, arrays JSONB de itens e eventos e estado de sincronização ERP.

Uma sequence PostgreSQL independente `salutem_itecontrol_seq` começa em 84333. Sequence e índices não são tabelas. Itens, atendimentos, logs e outbox não viram tabelas extras. Os valores `doc_controle`, `doc_operacao` e `notdtdigit` são registrados como null nos metadados JSON locais de cada item porque aparecem no exemplo, mas não são colunas do DDL recebido.

`database/schema.sql` contém apenas objetos do banco local. Ele se monta no diretório de inicialização da imagem PostgreSQL, que o aplica na primeira inicialização de um volume vazio; o script `scripts/init_local_db.sh` reaplica o schema somente no serviço Compose `database`. Não execute o dump do ERP.

### PostgreSQL ERP

O adaptador `backend/app/services/erp.py` usa outro engine, parametrizado por `ERP_DATABASE_URL`:

- Consulta somente `public.vw_produto_saldo_estoque`, depósito 1; usa as quatro colunas documentadas para código, descrição, depósito e saldo. Faz trim de espaços de `CHAR` para apresentação/comparação; o PostgreSQL completa novamente a largura `CHAR(16)` na escrita.
- Antes da retirada, lê a disponibilidade atual para detectar falta de saldo.
- Grava em `public.toqmovi` uma linha por item atendido, em uma única transação, com `pritransac=14`, `prideposit=1`, `pridata`, código e `priquanti NUMERIC(14,4)`. Os campos vazios informados são strings com largura exata: `operacao` 10 espaços, `pridocto` 8, `priemitido` 1 e `priusuario` 10. `pridtalt` e `prihralt` pertencem ao gatilho ERP.
- Gatilhos ERP podem modificar o saldo. A aplicação não edita tabela `produto` nem qualquer tabela de saldo.

O dicionário não trouxe o `CREATE VIEW` nem corpos de funções de gatilho. Também há três chaves no exemplo (`doc_controle`, `doc_operacao`, `notdtdigit`) ausentes de `toqmovi` no dump. O adapter não tenta gravar colunas que não existem. Confirme nomes de objetos, comportamento real dos gatilhos e concessões no host LAN antes de liberar escrita.

## Sincronização entre bancos

Não existe commit distribuído entre local e ERP. O fluxo é deliberadamente idempotente:

1. Validar sessão, dono, quantidades, data e existência/saldo dos produtos.
2. Reservar via `nextval` um `itecontrol` local e persistir o pedido como Pendente; uma falha consome um número e pode criar lacuna, o que é normal para sequence PostgreSQL.
3. Na conferência, gravar no JSON os valores entregues e responsável antes da chamada ERP.
4. Na transação ERP, tomar advisory lock pelo controle e consultar todas as linhas existentes. Se corresponderem exatamente, tratar como retry já concluído; se divergirem, encerrar como conflito; se não existirem, verificar produto/saldo e inserir linhas com `prisequen` contíguo entre as quantidades positivas.
5. Somente após commit ERP, marcar a requisição local como Finalizada/enviada. Falha de rede mantém estado ERP visível; novo envio não é cego.

A chave primária do ERP `(itecontrol, prisequen)` é a última proteção contra colisões com outros usuários. A sequence de 84333 coordena instâncias desta aplicação, não atividades externas do ERP. Colisões externas não são puladas ou sobrescritas automaticamente.

## Identidade e segurança

- O perfil vem do setor autenticado e é validado no backend, nunca de um campo editável no navegador.
- Senhas compartilhadas por setor armazenam-se apenas como Argon2id. Não há tabelas de usuário ou sessão.
- Cookie de sessão é assinado e `HttpOnly`, tem expiração e invalidada por mudança de hash de senha; cookie CSRF separado protege operações mutáveis.
- Em Preview/Compose HTTPS, cookie `Secure; SameSite=None`, necessário porque o Preview pode usar iframe cross-site. Em localhost HTTP de desenvolvimento, configure `Secure=false; SameSite=Lax` somente nesse processo local.
- As tentativas são limitadas em memória pelo processo atual. Container de produção executa um worker; expansão para múltiplos workers requer rate limit compartilhado fora do modelo de duas tabelas ou na borda.
- O nome do responsável do Almoxarifado é informativo/auditável, mas não prova identidade pessoal porque a senha do setor é compartilhada.
- Acesso ERP deve ser least privilege; segredos apenas via `.env` local ignorado por Git ou cofre do servidor.

## Deploy, observabilidade e backup

`Dockerfile` constrói React e a imagem Python com FastAPI; `compose.yaml` executa o app e o PostgreSQL local num volume persistente privado. `/health` é somente liveness; ele não valida ERP, senha, tabela ou gatilhos. A checagem de ERP deve ser um comando separado de leitura, executado no host autorizado.

`scripts/backup_local_db.sh` faz dump lógico do banco local; backups ficam fora de Git e do contexto Docker. Dados ERP seguem a política de backup do DBA. Não há rotina automática de downgrade/restauração destrutiva.
