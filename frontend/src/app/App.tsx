import { useEffect, useState } from 'react';
import { Activity, Archive, ClipboardList, LogOut, PackageSearch, Users, X } from 'lucide-react';
import AccessScreen from '../features/access/AccessScreen';
import CatalogPage from '../features/catalog/CatalogPage';
import CartPage from '../features/cart/CartPage';
import HistoryPage from '../features/requests/HistoryPage';
import KanbanBoard from '../features/requests/KanbanBoard';
import AdminPage from '../features/admin/AdminPage';
import { api } from '../lib/api';
import type { CurrentUser, MaterialRequest, RequestCreate } from '../lib/types';

type View = 'catalog' | 'cart' | 'history' | 'kanban' | 'sectors';
type CartLine = { material_code: string; description: string; stock: number; quantity: number };
type NotificationCursor = { at: string; control: number };

function loadNotificationCursor(sectorId: number): NotificationCursor {
  const key = `salutem:finalized-cursor:${sectorId}`;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw) {
      const cursor = JSON.parse(raw) as NotificationCursor;
      if (cursor.at && Number.isSafeInteger(cursor.control) && cursor.control >= 0) return cursor;
    }
  } catch { /* Se o armazenamento do navegador estiver bloqueado, usa cursor desta sessão. */ }
  const cursor = { at: new Date().toISOString(), control: 0 };
  try { window.localStorage.setItem(key, JSON.stringify(cursor)); } catch { /* A sessão continua sem persistência do cursor. */ }
  return cursor;
}

export default function App() {
  const [profile, setProfile] = useState<CurrentUser | null>(null);
  const [view, setView] = useState<View>('catalog');
  const [cart, setCart] = useState<CartLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmation, setConfirmation] = useState('');
  const [finalizedNotifications, setFinalizedNotifications] = useState<MaterialRequest[]>([]);
  const [notificationDialog, setNotificationDialog] = useState<HTMLDialogElement | null>(null);

  useEffect(() => {
    let active = true;
    void api.csrf().then(() => api.me()).then((user) => {
      if (!active) return;
      setProfile(user);
      setView(user.profile === 'almoxarifado' ? 'kanban' : 'catalog');
    }).catch(() => { if (active) setProfile(null); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!profile || !['solicitante', 'administrador'].includes(profile.profile)) {
      setFinalizedNotifications([]);
      return;
    }
    let active = true;
    let checking = false;
    let cursor = loadNotificationCursor(profile.sector_id);
    const storageKey = `salutem:finalized-cursor:${profile.sector_id}`;
    const checkForFinalizations = async () => {
      if (!active || checking || document.visibilityState !== 'visible') return;
      checking = true;
      try {
        const updates = await api.finalizedNotifications(cursor.at, cursor.control);
        if (!active || updates.length === 0) return;
        const last = updates[updates.length - 1];
        if (!last.finalized_at) return;
        cursor = { at: last.finalized_at, control: last.itecontrol };
        try { window.localStorage.setItem(storageKey, JSON.stringify(cursor)); } catch { /* Mantém cursor em memória nesta sessão. */ }
        setFinalizedNotifications((current) => {
          const seen = new Set(current.map((request) => request.itecontrol));
          return [...current, ...updates.filter((request) => !seen.has(request.itecontrol))].slice(-10);
        });
      } catch { /* Falhas transitórias são tentadas novamente no próximo ciclo. */ }
      finally { checking = false; }
    };
    const timer = window.setInterval(() => { void checkForFinalizations(); }, 10_000);
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') void checkForFinalizations(); };
    document.addEventListener('visibilitychange', onVisibilityChange);
    void checkForFinalizations();
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [profile]);

  useEffect(() => {
    if (!notificationDialog) return;
    if (finalizedNotifications.length > 0 && !notificationDialog.open) notificationDialog.showModal();
    if (finalizedNotifications.length === 0 && notificationDialog.open) notificationDialog.close();
  }, [notificationDialog, finalizedNotifications.length]);

  function addToCart(line: Omit<CartLine, 'quantity'>, quantity: number) {
    setCart((current) => {
      const existing = current.find((item) => item.material_code === line.material_code);
      if (existing) return current.map((item) => item.material_code === line.material_code ? { ...item, quantity: item.quantity + quantity } : item);
      return [...current, { ...line, quantity }];
    });
  }

  async function submitRequest(payload: RequestCreate) {
    if (profile?.profile !== 'solicitante' && profile?.profile !== 'administrador') return;
    const created = await api.createRequest(payload);
    setCart([]);
    setConfirmation(`Requisição ${created.number} registrada. O saldo será baixado no ERP quando o Almoxarifado confirmar o atendimento.`);
    setView('history');
  }

  async function startRequest(id: number) {
    if (profile?.profile !== 'almoxarifado' && profile?.profile !== 'administrador') return;
    await api.startRequest(id);
  }

  async function finalizeRequest(id: number, values: Parameters<typeof api.finalizeRequest>[1]) {
    await api.finalizeRequest(id, values);
  }

  async function exit() {
    try { await api.logout(); } catch { /* A limpeza local ainda encerra a sessão visual. */ }
    setProfile(null);
    setCart([]);
    setConfirmation('');
    setFinalizedNotifications([]);
    setView('catalog');
  }

  if (loading && !profile) return <main className="access-layout"><section className="access-content"><div className="panel panel-pad">Verificando sessão...</div></section></main>;
  if (!profile) return <AccessScreen onLogin={(user) => { setProfile(user); setView(user.profile === 'almoxarifado' ? 'kanban' : 'catalog'); }} />;

  const warehouse = profile.profile === 'almoxarifado';
  const administrator = profile.profile === 'administrador';
  const canRequest = profile.profile === 'solicitante' || administrator;
  const canWarehouse = warehouse || administrator;
  const displayName = warehouse || administrator ? profile.sector_name : (profile.leader_name ?? profile.sector_name);
  const cartCount = cart.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand-lockup brand-lockup-small" href="#inicio" onClick={(event) => { event.preventDefault(); setView(warehouse ? 'kanban' : 'catalog'); }}><img className="brand-logo" src="/salutem-logo.png" alt="Salutem Hospitalares" /><span className="brand-divider" /><span className="brand-area">Almoxarifado</span></a>
        <div className="topbar-actions"><span className="identity-chip"><span className="avatar-dot">{displayName.slice(0, 1).toUpperCase()}</span><span><strong>{displayName}</strong><small>{profile.profile === 'administrador' ? 'Acesso geral' : profile.sector_name}</small></span></span><button className="icon-button" onClick={() => void exit()} title="Sair" aria-label="Sair"><LogOut size={18} /></button></div>
      </header>
      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-label">ÁREA DE TRABALHO</div>
          {canRequest && <>
            <NavButton active={view === 'catalog'} icon={<PackageSearch size={18} />} label="Catálogo ERP" onClick={() => setView('catalog')} />
            <NavButton active={view === 'cart'} icon={<ClipboardList size={18} />} label="Minha requisição" onClick={() => setView('cart')} badge={cartCount || undefined} />
          </>}
          {canWarehouse && <NavButton active={view === 'kanban'} icon={<Activity size={18} />} label="Atendimento" onClick={() => setView('kanban')} />}
          <NavButton active={view === 'history'} icon={<Archive size={18} />} label={canWarehouse ? 'Histórico completo' : 'Minhas requisições'} onClick={() => setView('history')} />
          {administrator && <>
            <div className="sidebar-label sidebar-label-spaced">ADMINISTRAÇÃO</div>
            <NavButton active={view === 'sectors'} icon={<Users size={18} />} label="Setores e acessos" onClick={() => setView('sectors')} />
          </>}
        </aside>
        <main className="page-content">
          {confirmation && <div className="notice" style={{ background: '#eaf5ec', color: '#285d35' }} role="status" aria-live="polite"><span>{confirmation}</span><button className="text-button" onClick={() => setConfirmation('')} style={{ marginLeft: 'auto' }} aria-label="Fechar confirmação">Entendi</button></div>}
          {view === 'catalog' && canRequest && <CatalogPage onAdd={addToCart} />}
          {view === 'cart' && canRequest && <CartPage leader={profile.leader_name ?? (administrator ? 'Administrador' : '')} sector={profile.sector_name} cart={cart} onChange={setCart} onSubmit={submitRequest} />}
          {view === 'history' && <HistoryPage warehouse={canWarehouse} />}
          {view === 'kanban' && canWarehouse && <KanbanBoard onStart={startRequest} onFinalize={finalizeRequest} />}
          {view === 'sectors' && administrator && <AdminPage />}
          <dialog
            ref={setNotificationDialog}
            className="finalized-popup"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="finalized-popup-title"
            aria-describedby="finalized-popup-description"
            onCancel={(event) => {
              event.preventDefault();
              setFinalizedNotifications([]);
            }}
          >
            <div className="finalized-popup__header">
              <span className="finalized-popup__icon" aria-hidden="true"><Activity size={21} /></span>
              <div>
                <p className="finalized-popup__eyebrow">ATUALIZAÇÃO DO ALMOXARIFADO</p>
                <h2 id="finalized-popup-title" className="finalized-popup__title">
                  {finalizedNotifications.length === 1 ? 'Sua requisição foi atualizada' : 'Suas requisições foram atualizadas'}
                </h2>
              </div>
              <button className="finalized-popup__close" type="button" onClick={() => setFinalizedNotifications([])} aria-label="Fechar aviso"><X size={18} /></button>
            </div>
            <p id="finalized-popup-description" className="finalized-popup__description">O Almoxarifado atualizou o atendimento destas requisições:</p>
            <ul className="finalized-popup__list">
              {finalizedNotifications.map((request) => (
                <li key={request.itecontrol} className="finalized-popup__request">
                  <div className="finalized-popup__request-heading">
                    <strong>{request.number}</strong>
                    <span className={`finalized-popup__status ${request.status === 'Parcial' ? 'is-partial' : 'is-complete'}`}>
                      {request.status === 'Parcial' ? 'Atendimento parcial' : 'Atendimento concluído'}
                    </span>
                  </div>
                  <p>{request.status === 'Parcial' ? 'Parte dos itens foi atendida. Consulte o histórico para ver as quantidades.' : 'Todos os itens foram atendidos.'}</p>
                </li>
              ))}
            </ul>
            <div className="finalized-popup__actions">
              <button className="finalized-popup__button is-secondary" type="button" onClick={() => setFinalizedNotifications([])} autoFocus>Fechar</button>
              <button className="finalized-popup__button is-primary" type="button" onClick={() => { setFinalizedNotifications([]); setView('history'); }}>
                {canWarehouse ? 'Ver histórico completo' : 'Ver minhas requisições'}
              </button>
            </div>
          </dialog>
        </main>
      </div>
      <footer className="app-footer"><span>Salutem Hospitalares</span><span>Operação segura, materiais em ordem.</span></footer>
    </div>
  );
}

function NavButton({ active, icon, label, onClick, badge }: { active: boolean; icon: React.ReactNode; label: string; onClick: () => void; badge?: number }) {
  return <button className={`nav-button${active ? ' active' : ''}`} onClick={onClick}>{icon}<span>{label}</span>{badge !== undefined && <span className="nav-badge">{badge}</span>}</button>;
}
