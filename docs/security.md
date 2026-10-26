# Segurança e operação de acesso

## Credenciais

- Cada setor solicitante e o acesso único Almoxarifado possui senha compartilhada própria (mínimo 12 caracteres, máximo 128). Um setor é associado a um líder designado.
- O perfil Administrador é uma conta única separada, armazenada na tabela existente `setores`, sem senha padrão; provisionar/redefinir somente com `python -m app.cli criar-admin`, nunca pela tela de setores.
- Banco local guarda Argon2id, nunca senha em texto. O CLI usa `getpass` para criação inicial/redefinição; não passe senhas como argumento e não as registre no terminal.
- A troca de hash invalida sessões existentes. Login tem limite de tentativas em memória do processo.
- Segredos `APP_SESSION_SECRET`, `LOCAL_PG_PASSWORD` e DSNs ficam somente em `.env` local ignorado por Git ou cofre aprovado. Nunca imprimir DSN em log ou chat.

## Sessão web

A sessão é um cookie assinado, `HttpOnly`, com expiração. Cookie CSRF não HttpOnly é comparado com o header `X-CSRF-Token` em qualquer `POST`/`PATCH`/`PUT`. O perfil é lido do banco local em cada request. Em Compose, cookie é `Secure; SameSite=None` e o acesso deve passar por HTTPS interno. HTTP sem TLS não serve para produção.

O operador do Almoxarifado se autentica com a senha compartilhada da área e seleciona/digita um responsável no fechamento. Esse nome é log operacional, não identidade criptográfica nem assinatura individual; o acesso é rastreável somente ao setor, data/hora e texto informado. O Administrador tem acesso a catálogo/criação de pedidos, atendimento/histórico completo e administração; a sessão Almoxarifado não recebe o endpoint nem a aba de gerenciamento de setores.

## Privilégios PostgreSQL

Use conta de app local independente de superusuário. O backend só aceita `ERP_DATABASE_URL` cujo host é exatamente `192.168.1.2`; configure a porta real com o DBA. ERP deve receber somente `SELECT` na view de catálogo/saldo e na tabela `produto` (necessária para filtrar `prostatus = 'A'` e limitar grupos 10–13), além dos privilégios mínimos para verificar/inserir `toqmovi`; confirme funções/objetos dos gatilhos e grants com DBA. Não conceder `UPDATE`/`DELETE` em produto/estoque. Mantenha o serviço dentro da LAN/VPN autorizada e limite entrada com proxy TLS/firewall.

## Falhas parciais

O app registra pedido local antes de uma retirada. Se a resposta ERP for incerta, não apague nem envie novo controle manualmente. Use o mesmo pedido e reconciliação por `(itecontrol,prisequen)`; conflito de conteúdo exige revisão do responsável ERP. Não há transação distribuída entre as bases.

## Dados sensíveis em backup

Requisições podem conter observações de entrega e nomes de responsáveis. Os dumps do banco local devem ser criptografados, ter acesso restrito e uma retenção definida pela Salutem. Não versionar pasta `backups/`.
