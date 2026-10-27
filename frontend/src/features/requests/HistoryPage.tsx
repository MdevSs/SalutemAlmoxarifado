import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, FileText, Search, X } from 'lucide-react';
import type { MaterialRequest, RequestStatus } from '../../lib/types';
import { api } from '../../lib/api';

type Props = { warehouse: boolean };
const dateLabel = (value: string) => new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('pt-BR');
const quantityLabel = (value: number) => value.toLocaleString('pt-BR', { maximumFractionDigits: 4 });
const PAGE_SIZE = 200;

export default function HistoryPage({ warehouse }: Props) {
  const [requests, setRequests] = useState<MaterialRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('Todas');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<MaterialRequest | null>(null);
  const queryVersion = useRef(0);
  const pollingRef = useRef(false);
  const validDateRange = !dateFrom || !dateTo || dateFrom <= dateTo;

  const refresh = useCallback(async () => {
    const version = ++queryVersion.current;
    setLoading(true);
    setLoadingMore(false);
    setError('');
    setRequests([]);
    setTotal(0);
    if (dateFrom && dateTo && dateFrom > dateTo) {
      setLoading(false);
      return;
    }
    try {
      const page = await api.requests({
        search: search.trim(),
        status: status === 'Todas' ? undefined : status,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        offset: 0,
        limit: PAGE_SIZE,
      });
      if (version === queryVersion.current) {
        setRequests(page.items);
        setTotal(page.total);
      }
    } catch (cause) {
      if (version === queryVersion.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o histórico.');
    } finally {
      if (version === queryVersion.current) setLoading(false);
    }
  }, [search, status, dateFrom, dateTo]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 200);
    return () => { window.clearTimeout(timer); queryVersion.current += 1; };
  }, [refresh]);

  useEffect(() => {
    if (loading || loadingMore || !validDateRange) return;
    let active = true;
    const refreshQuietly = async () => {
      if (!active || pollingRef.current || document.visibilityState !== 'visible') return;
      pollingRef.current = true;
      const version = queryVersion.current;
      const pagesNeeded = Math.ceil(Math.max(PAGE_SIZE, requests.length) / PAGE_SIZE);
      const refreshed: MaterialRequest[] = [];
      let refreshedTotal = 0;
      try {
        for (let pageIndex = 0; pageIndex < pagesNeeded; pageIndex += 1) {
          const page = await api.requests({
            search: search.trim(),
            status: status === 'Todas' ? undefined : status,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            offset: pageIndex * PAGE_SIZE,
            limit: PAGE_SIZE,
          });
          if (pageIndex === 0) refreshedTotal = page.total;
          refreshed.push(...page.items);
          if (refreshed.length >= page.total || page.items.length === 0) break;
        }
        if (!active || version !== queryVersion.current) return;
        setRequests(refreshed);
        setTotal(refreshedTotal);
        setSelected((current) => current
          ? refreshed.find((request) => request.itecontrol === current.itecontrol) ?? current
          : null);
      } catch {
        // Preserva a última lista válida durante falhas transitórias de rede.
      } finally {
        pollingRef.current = false;
      }
    };
    const timer = window.setInterval(() => { void refreshQuietly(); }, 10_000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void refreshQuietly();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [search, status, dateFrom, dateTo, validDateRange, loading, loadingMore, requests.length]);

  async function loadMore() {
    if (dateFrom && dateTo && dateFrom > dateTo) return;
    const version = queryVersion.current;
    const currentLength = requests.length;
    setLoadingMore(true);
    setError('');
    try {
      const page = await api.requests({
        search: search.trim(),
        status: status === 'Todas' ? undefined : status,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        offset: currentLength,
        limit: PAGE_SIZE,
      });
      if (version === queryVersion.current) {
        setRequests((current) => current.length === currentLength ? [...current, ...page.items] : current);
        setTotal(page.total);
      }
    } catch (cause) {
      if (version === queryVersion.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar a próxima página.');
    } finally {
      if (version === queryVersion.current) setLoadingMore(false);
    }
  }

  return <section>
    <div className="page-heading"><div><span className="eyebrow">{warehouse ? 'ALMOXARIFADO' : 'ACOMPANHAMENTO'}</span><h1>{warehouse ? 'Histórico completo' : 'Minhas requisições'}</h1><p>{warehouse ? 'Pedidos e estado dos movimentos enviados ao ERP.' : 'Acompanhe as solicitações do seu setor.'}</p></div>{warehouse && <div className="heading-actions"><a className={`button button-quiet${validDateRange ? '' : ' button-disabled'}`} href={validDateRange ? api.exportUrl(dateFrom, dateTo) : undefined} aria-disabled={!validDateRange}><ArrowDownToLine size={16} /> Exportar CSV</a></div>}</div>
    <div className="toolbar request-filters">
      <div className="search-wrap"><Search size={17} /><input aria-label="Pesquisar histórico" maxLength={120} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar: parafuso 4,5, controle, setor, líder..." /></div>
      <select className="field-control request-status-filter" value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filtrar por status"><option>Todas</option><option>Pendente</option><option>Em andamento</option><option>Finalizada</option><option>Parcial</option></select>
      <label className="date-filter"><span>Data inicial</span><input className="field-control" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} aria-label="Data inicial da requisição" /></label>
      <label className="date-filter"><span>Data final</span><input className="field-control" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} aria-label="Data final da requisição" /></label>
      <span className="stock-label" aria-live="polite">{requests.length} de {total} requisições</span>
      <span className="stock-label">Atualização automática: 10 s</span>
      <button className="text-button" onClick={() => void refresh()}>Atualizar</button>
    </div>
    {!validDateRange && <div className="notice notice-error" role="alert">A data inicial não pode ser posterior à data final.</div>}
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {loading && <div className="loading-bar" aria-label="Carregando histórico" />}
    <div className="panel table-wrap"><table><thead><tr><th>Controle</th><th>Data</th>{warehouse && <th>Líder / setor</th>}<th>Materiais</th><th>Status</th>{warehouse && <th>ERP</th>}<th></th></tr></thead><tbody>
      {requests.map((request) => <tr key={request.itecontrol}><td><button className="text-button" onClick={() => setSelected(request)}>{request.number}</button></td><td>{dateLabel(request.requested_date)}</td>{warehouse && <td>{request.leader_name ?? '—'}<small style={{ display: 'block', color: '#77847a' }}>{request.sector_name}</small></td>}<td>{request.items.length} {request.items.length === 1 ? 'item' : 'itens'}</td><td><Status status={request.status} /></td>{warehouse && <td><ERPBadge status={request.erp_status} /></td>}<td><button className="icon-button" aria-label={`Detalhes ${request.number}`} onClick={() => setSelected(request)}><FileText size={16} /></button></td></tr>)}
      {!loading && requests.length === 0 && <tr><td colSpan={warehouse ? 7 : 5}><div className="empty-state"><strong>Nenhuma requisição encontrada</strong><p>Revise a busca e os filtros de status ou data.</p></div></td></tr>}
    </tbody></table></div>
    {validDateRange && requests.length < total && <div className="history-load-more"><button className="button button-quiet" onClick={() => void loadMore()} disabled={loadingMore}>{loadingMore ? 'Carregando…' : `Carregar mais ${Math.min(PAGE_SIZE, total - requests.length)} requisições`}</button></div>}
    {selected && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}><article className="dialog" role="dialog" aria-modal="true" aria-labelledby="request-title">
      <header className="dialog-header"><div><span className="eyebrow">DETALHES DA SOLICITAÇÃO</span><h2 id="request-title">{selected.number}</h2></div><button className="icon-button" onClick={() => setSelected(null)} aria-label="Fechar"><X size={18} /></button></header>
      <div className="dialog-body"><div className="toolbar"><Status status={selected.status} /><ERPBadge status={selected.erp_status} /><span className="stock-label">{dateLabel(selected.requested_date)}</span></div>
        <p><strong>{selected.leader_name ?? '—'}</strong> · {selected.sector_name}</p>{selected.delivery_instructions && <p><strong>Instruções:</strong> {selected.delivery_instructions}</p>}
        {selected.erp_error && <div className="notice notice-error">{selected.erp_error}</div>}
        <div className="table-wrap"><table><thead><tr><th>Material</th><th>Pedido</th><th>Entregue</th></tr></thead><tbody>{selected.items.map((item) => {
          const unit = item.unit_code ?? item.default_unit ?? '';
          const requestedInUnit = item.requested_unit_quantity ?? item.requested_quantity;
          const deliveredInUnit = item.delivered_unit_quantity ?? item.delivered_quantity;
          const converted = Boolean(item.unit_code && item.default_unit && item.unit_code !== item.default_unit);
          return <tr key={item.item_index}>
            <td>{item.description}<small style={{ display: 'block', color: '#77847a' }}>{item.material_code}</small></td>
            <td>{quantityLabel(requestedInUnit)} {unit}{converted && <small style={{ display: 'block', color: '#77847a' }}>{quantityLabel(item.requested_quantity)} {item.default_unit} · {item.conversion_result}</small>}</td>
            <td>{deliveredInUnit === null ? '—' : <>{quantityLabel(deliveredInUnit)} {unit}{converted && item.delivered_quantity !== null && <small style={{ display: 'block', color: '#77847a' }}>{quantityLabel(item.delivered_quantity)} {item.default_unit} no ERP</small>}</>}</td>
          </tr>;
        })}</tbody></table></div>
        {selected.status === 'Parcial' && <div className="notice notice-warning" style={{ marginTop: 14 }}>Atendimento parcial confirmado no ERP.</div>}
        {selected.warehouse_notes && <div className="notice notice-warning" style={{ marginTop: 14 }}><span><strong>Observações do Almoxarifado:</strong> {selected.warehouse_notes}</span></div>}
        {selected.responsible_name && <p className="stock-label">Responsável informado: {selected.responsible_name}{selected.finalized_at ? ` · ${new Date(selected.finalized_at).toLocaleString('pt-BR')}` : ''}</p>}
        <h3 style={{ fontSize: '.9rem', marginTop: 22 }}>Movimentações</h3>{selected.events.map((event, index) => <p className="stock-label" key={`${event.at}-${index}`}>{new Date(event.at).toLocaleString('pt-BR')} · {event.actor}: {event.note}</p>)}
      </div><footer className="dialog-footer"><button className="button button-quiet" onClick={() => setSelected(null)}>Fechar</button></footer>
    </article></div>}
  </section>;
}

function Status({ status }: { status: RequestStatus }) {
  const className = status === 'Pendente' ? 'status-pendente' : status === 'Em andamento' ? 'status-andamento' : status === 'Parcial' ? 'status-parcial' : 'status-finalizada';
  return <span className={`status ${className}`}>{status}</span>;
}
function ERPBadge({ status }: { status: string }) {
  const labels: Record<string, string> = { aguardando: 'Aguardando baixa', enviado: 'ERP confirmado', conflito: 'Conflito ERP', falhou: 'Pendente de reconciliação', revisar_saldo: 'Revisar saldo' };
  return <span className={`status ${status === 'enviado' ? 'status-finalizada' : status === 'conflito' || status === 'falhou' ? 'status-pendente' : 'status-andamento'}`}>{labels[status] ?? status}</span>;
}
