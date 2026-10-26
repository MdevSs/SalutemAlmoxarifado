#!/usr/bin/env bash
# Mostra o que o ERP SIMULADO tem agora: movimentos gravados e saldos alterados.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
q() { docker compose -f dev/compose.dev.yaml exec -T fakeerp psql -U erp -d erp -c "$1"; }
echo "== Movimentos gravados pela aplicação (toqmovi) =="
q "SELECT itecontrol, prisequen, pridata, btrim(priproduto) AS produto, pritransac, priquanti FROM toqmovi ORDER BY itecontrol, prisequen"
echo "== Saldos do depósito 1 =="
q "SELECT btrim(codigo) AS codigo, descricao, saldo FROM produto_saldo WHERE deposito = 1 ORDER BY codigo"
