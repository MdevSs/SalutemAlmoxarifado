import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, Check, Clock3, PackageCheck, Save, X } from 'lucide-react';
import type { MaterialRequest, RequestStatus } from '../../lib/types';
import { api } from '../../lib/api';

type Props = {
  onStart: (id: number) => Promise<void>;
  onFinalize: (id: number, values: Parameters<typeof api.finalizeRequest>[1]) => Promise<void>;
};
type DayGroup = { date: string; requests: MaterialRequest[] };
const columns: RequestStatus[] = ['Pendente', 'Em andamento', 'Finalizada', 'Parcial'];
const PAGE_SIZE = 200;
const localDateInputValue = (value = new Date()) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};
const qty = (value: number) => value.toLocaleString('pt-BR', { maximumFractionDigits: 4 });
const dayLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });
const requestedQty = (item: MaterialRequest['items'][number]) => item.requested_unit_quantity ?? item.requested_quantity;
const unitCode = (item: MaterialRequest['items'][number]) => item.unit_code ?? item.default_unit ?? '';

export default function KanbanBoard({ onStart, onFinalize }: Props) {
  const [requests, setRequests] = useState<MaterialRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [dateFrom, setDateFrom] = useState(localDateInputValue);
  const [dateTo, setDateTo] = useState(localDateInputValue);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<MaterialRequest | null>(null);
  const [deliveries, setDeliveries] = useState<Record<number, number>>({});
  const [notes, setNotes] = useState('');
  const [responsible, setResponsible] = useState('');
  const [responsibles, setResponsibles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const queryVersion = useRef(0);
  const pollingRef = useRef(false);
  const followsTodayRef = useRef(true);

  const reload = useCallback(async () => {
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
      const page = await api.requests({ date_from: dateFrom || undefined, date_to: dateTo || undefined, offset: 0, limit: PAGE_SIZE });
      if (version === queryVersion.current) {
        setRequests(page.items);
        setTotal(page.total);
      }
    } catch (cause) {
      if (version === queryVersion.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o Kanban.');
    } finally {
      if (version === queryVersion.current) setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void reload(); }, 0);
    return () => { window.clearTimeout(timer); queryVersion.current += 1; };
  }, [reload]);

  useEffect(() => {
    let timer = 0;
    let active = true;
    const scheduleNextDay = () => {
      const now = new Date();
      const midnight = new Date(now);
      midnight.setHours(24, 0, 0, 0);
      timer = window.setTimeout(() => {
        if (!active) return;
        refreshForCurrentDay();
        scheduleNextDay();
      }, Math.max(1000, midnight.getTime() - now.getTime()));
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refreshForCurrentDay();
    };
    const refreshForCurrentDay = () => {
      const today = localDateInputValue();
      if (followsTodayRef.current && (dateFrom !== today || dateTo !== today)) {
        setDateFrom(today);
        setDateTo(today);
      } else {
        void reload();
      }
    };
    scheduleNextDay();
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      active = false;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [dateFrom, dateTo, reload]);

  useEffect(() => {
    if (loading || loadingMore || busy || (dateFrom && dateTo && dateFrom > dateTo)) return;
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
        // Mantém os dados visíveis em caso de falha transitória do polling.
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
  }, [dateFrom, dateTo, loading, loadingMore, busy, requests.length]);

  useEffect(() => { api.responsibles().then(setResponsibles).catch(() => setResponsibles([])); }, []);

  async function loadMore() {
    if (dateFrom && dateTo && dateFrom > dateTo) return;
    const version = queryVersion.current;
    const currentLength = requests.length;
    if (loadingMore || pollingRef.current || currentLength >= total) return;
    setLoadingMore(true);
    setError('');
    try {
      const page = await api.requests({ date_from: dateFrom || undefined, date_to: dateTo || undefined, offset: currentLength, limit: PAGE_SIZE });
      if (version === queryVersion.current) {
        setRequests((current) => current.length === currentLength ? [...current, ...page.items] : current);
        setTotal(page.total);
      }
    } catch (cause) {
      if (version === queryVersion.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar mais requisições.');
    } finally {
      if (version === queryVersion.current) setLoadingMore(false);
    }
  }

  const grouped = useMemo(() => Object.fromEntries(columns.map((status) => {
    const byDate = new Map<string, MaterialRequest[]>();
    requests
      .filter((request) => request.status === status)
      .sort((left, right) => right.requested_date.localeCompare(left.requested_date) || right.created_at.localeCompare(left.created_at))
      .forEach((request) => byDate.set(request.requested_date, [...(byDate.get(request.requested_date) ?? []), request]));
    const days: DayGroup[] = [...byDate.entries()].map(([date, dayRequests]) => ({ date, requests: dayRequests }));
    return [status, days];
  })) as Record<RequestStatus, DayGroup[]>, [requests]);

  async function start(id: number) {
    setBusy(true); setError('');
    try { await onStart(id); await reload(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível iniciar o atendimento.'); }
    finally { setBusy(false); }
  }

  async function saveNote() {
    if (!selected) return;
    setBusy(true); setError('');
    try {
      const updated = await api.saveNotes(selected.itecontrol, notes.trim());
      setSelected(updated);
      setNotes(updated.warehouse_notes);
      await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a observação.'); }
    finally { setBusy(false); }
  }

  async function finish(confirmed = false) {
    if (!selected) return;
    if (!responsible.trim()) return setError('Selecione ou informe quem está confirmando o atendimento.');
    if (selected.items.some((item) => !Number.isSafeInteger(deliveries[item.item_index] ?? requestedQty(item)))) return setError('As quantidades entregues devem ser números inteiros.');
    setBusy(true); setError('');
    try {
      await onFinalize(selected.itecontrol, {
        responsible_name: responsible.trim(), warehouse_notes: notes.trim(), confirm_partial_without_note: confirmed,
        deliveries: selected.items.map((item) => ({ item_index: item.item_index, quantity: deliveries[item.item_index] ?? requestedQty(item) })),
      });
      setSelected(null); setNotes(''); setResponsible('');
      await reload();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Não foi possível confirmar a retirada no ERP.';
      if (message.toLowerCase().includes('parcial') && !notes.trim() && !confirmed && window.confirm('Há itens com entrega parcial. Confirmar mesmo sem observação do Almoxarifado?')) await finish(true);
      else setError(message);
    } finally { setBusy(false); }
  }

  function openRequest(request: MaterialRequest) {
    setSelected(request); setNotes(request.warehouse_notes); setResponsible(request.responsible_name ?? '');
    setDeliveries(Object.fromEntries(request.items.map((item) => [item.item_index, item.delivered_unit_quantity ?? item.delivered_quantity ?? requestedQty(item)]))); setError('');
  }

  const validDateRange = !dateFrom || !dateTo || dateFrom <= dateTo;
  const changeDateFrom = (value: string) => {
    setDateFrom(value);
    followsTodayRef.current = value === dateTo && value === localDateInputValue();
  };
  const changeDateTo = (value: string) => {
    setDateTo(value);
    followsTodayRef.current = value === dateFrom && value === localDateInputValue();
  };

  return <section>
    <div className="page-heading"><div><span className="eyebrow">FLUXO DE ATENDIMENTO</span><h1>Quadro de requisições</h1></div><button className="button button-quiet" onClick={() => void reload()} disabled={loading}><Clock3 size={16} /> {loading ? 'Atualizando…' : 'Atualizar agora'}</button></div>
    <div className="toolbar request-filters kanban-filters">
      <label className="date-filter"><span>Data inicial</span><input className="field-control" type="date" value={dateFrom} onChange={(event) => changeDateFrom(event.target.value)} aria-label="Data inicial da requisição" /></label>
      <label className="date-filter"><span>Data final</span><input className="field-control" type="date" value={dateTo} onChange={(event) => changeDateTo(event.target.value)} aria-label="Data final da requisição" /></label>
      <span className="stock-label" aria-live="polite">{requests.length} de {total} requisições</span><span className="stock-label">Atualização automática: 10 s</span>
    </div>
    {!validDateRange && <div className="notice notice-error" role="alert">A data inicial não pode ser posterior à data final.</div>}
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {loading && <div className="loading-bar" aria-label="Carregando Kanban" />}
    <div className="kanban-grid">{columns.map((status) => <section className="kanban-column" key={status}><header className="kanban-head"><h2><StatusDot status={status} />{status}</h2><span className="kanban-count">{grouped[status].reduce((sum, day) => sum + day.requests.length, 0)}</span></header>
      {grouped[status].map((day) => <section className="kanban-date-group" key={`${status}-${day.date}`}><h3 className="kanban-date-heading">{dayLabel(day.date)}</h3>
        {day.requests.map((request) => <article className="kanban-card" key={request.itecontrol}><div className="kanban-card-top"><span className="request-number">{request.number}</span><span className="kanban-meta">{new Date(`${request.requested_date}T12:00:00`).toLocaleDateString('pt-BR')}</span></div>
          <h3>{request.leader_name ?? '—'}</h3><div className="kanban-meta">{request.sector_name}</div><div className="kanban-items">{request.items.slice(0, 2).map((item) => `${qty(requestedQty(item))} ${unitCode(item)} × ${item.description}`).join(' · ')}{request.items.length > 2 ? ` · +${request.items.length - 2} itens` : ''}</div>
          {request.status === 'Parcial' && <div className="notice-inline status-parcial-inline">Atendida parcialmente no ERP.</div>}
          {request.erp_status === 'falhou' || request.erp_status === 'conflito' ? <div className="notice-inline">{request.erp_status === 'conflito' ? 'Conflito no ERP; exige revisão.' : 'Sincronização pendente; reabra para tentar novamente.'}</div> : null}
          {status === 'Pendente' ? <button className="button button-quiet full-width" disabled={busy} onClick={() => void start(request.itecontrol)}>Iniciar atendimento <ArrowRight size={15} /></button> : status === 'Em andamento' ? <button className="button button-primary full-width" disabled={busy} onClick={() => openRequest(request)}>{request.erp_status === 'falhou' ? 'Revisar e reenviar' : 'Conferir e confirmar'} <PackageCheck size={15} /></button> : <button className="button button-quiet full-width" onClick={() => openRequest(request)}>Ver detalhes</button>}
        </article>)}
      </section>)}
      {!loading && grouped[status].length === 0 && <div className="empty-state" style={{ padding: '28px 8px' }}>Nenhum pedido nesta etapa.</div>}
    </section>)}</div>
    {validDateRange && requests.length < total && <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 14, marginTop: 18 }}>
      <span className="stock-label">Exibindo {requests.length} de {total} requisições</span>
      <button className="button button-quiet" onClick={() => void loadMore()} disabled={loadingMore || loading}>{loadingMore ? 'Carregando...' : `Carregar mais ${Math.min(PAGE_SIZE, total - requests.length)} requisições`}</button>
    </div>}
    {selected && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}><article className="dialog" role="dialog" aria-modal="true" aria-labelledby="handling-title">
      <header className="dialog-header"><div><span className="eyebrow">CONFERÊNCIA DO PEDIDO</span><h2 id="handling-title">{selected.number}</h2><span className="stock-label">{selected.leader_name ?? '—'} · {selected.sector_name}</span></div><button className="icon-button" onClick={() => setSelected(null)} aria-label="Fechar"><X size={18} /></button></header>
      <div className="dialog-body">{selected.items.map((item) => {
        const ordered = requestedQty(item);
        const unit = unitCode(item);
        const converted = Boolean(item.unit_code && item.default_unit && item.unit_code !== item.default_unit);
        return <div className="cart-line" key={item.item_index}>
        <div><strong>{item.description}</strong><small>{item.material_code} · pedido {qty(ordered)} {unit}</small>{converted && <small>{qty(item.requested_quantity)} {item.default_unit} na unidade padrão · {item.conversion_result}</small>}</div><span className="stock-label">A retirar ({unit || 'unidade'})</span>
        <input aria-label={`Quantidade a entregar para ${item.material_code} em ${unit || 'unidade solicitada'}`} className="cart-qty" type="number" min="0" step="1" inputMode="numeric" max={ordered} value={deliveries[item.item_index] ?? ordered} disabled={selected.status === 'Finalizada' || selected.status === 'Parcial' || selected.erp_status === 'conflito'} onChange={(event) => { const value = event.target.value; const amount = Number(value); if (value !== '' && !Number.isSafeInteger(amount)) { setError('As quantidades entregues devem ser números inteiros.'); return; } setDeliveries((state) => ({ ...state, [item.item_index]: Math.min(ordered, Math.max(0, amount || 0)) })); setError(''); }} />
        <span className="stock-label">/{qty(ordered)} {unit}</span>
      </div>;
      })}
        {selected.status !== 'Finalizada' && selected.status !== 'Parcial' && <div className="form-field" style={{ marginTop: 18 }}><label htmlFor="responsible-name">Responsável pela confirmação</label><input id="responsible-name" list="responsible-options" value={responsible} onChange={(event) => setResponsible(event.target.value)} placeholder="Selecione ou digite o nome" autoComplete="off" /><datalist id="responsible-options">{responsibles.map((name) => <option key={name} value={name} />)}</datalist></div>}
        <div className="form-field" style={{ marginTop: 18 }}><label htmlFor="warehouse-notes">Observações do Almoxarifado</label><textarea id="warehouse-notes" value={notes} disabled={selected.status === 'Finalizada' || selected.status === 'Parcial'} onChange={(event) => setNotes(event.target.value)} placeholder="Registre entrega parcial ou outras notas..." /></div>
        {error && <div className="notice notice-error" role="alert">{error}</div>}
        {selected.erp_error && <div className="notice notice-warning">Último retorno: {selected.erp_error}</div>}
        {selected.status === 'Parcial' && <div className="notice notice-warning">Atendimento parcial confirmado no ERP.</div>}
        {selected.status === 'Finalizada' && <div className="notice notice-warning">Confirmada integralmente no ERP por {selected.responsible_name ?? '—'} em {selected.finalized_at ? new Date(selected.finalized_at).toLocaleString('pt-BR') : '—'}.</div>}
      </div><footer className="dialog-footer">{selected.status !== 'Finalizada' && selected.status !== 'Parcial' && <button className="button button-quiet" onClick={() => void saveNote()} disabled={busy || notes.trim() === selected.warehouse_notes}><Save size={16} /> Salvar observação</button>}{selected.status === 'Em andamento' && selected.erp_status !== 'conflito' && <button className="button button-primary" onClick={() => void finish()} disabled={busy}><Check size={16} /> {busy ? 'Enviando ao ERP...' : 'Confirmar e dar baixa'}</button>}<button className="button button-quiet" onClick={() => setSelected(null)}>Fechar</button></footer>
    </article></div>}
  </section>;
}

function StatusDot({ status }: { status: RequestStatus }) {
  const color = status === 'Pendente' ? '#b88214' : status === 'Em andamento' ? '#3a67a3' : status === 'Parcial' ? '#bf7026' : '#3a7b4b';
  return <span style={{ width: 8, height: 8, background: color, borderRadius: '50%' }} />;
}
