import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Building2, ClipboardList, ShieldCheck } from 'lucide-react';
import { api } from '../../lib/api';
import type { CurrentUser, Sector } from '../../lib/types';

type Props = { onLogin: (user: CurrentUser) => void };

export default function AccessScreen({ onLogin }: Props) {
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [sectorId, setSectorId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const selected = useMemo(() => sectors.find((item) => item.id === Number(sectorId)), [sectors, sectorId]);

  useEffect(() => {
    void Promise.all([api.csrf(), api.sectorsForLogin()])
      .then(([, rows]) => setSectors(rows))
      .catch((cause: Error) => setError(cause.message));
  }, []);

  async function enter(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return setError('Selecione o acesso para continuar.');
    setLoading(true);
    setError('');
    try {
      onLogin(await api.login(selected.id, password));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível autenticar o acesso.');
    } finally {
      setLoading(false);
    }
  }

  const warehouse = selected?.profile === 'almoxarifado';
  const administrator = selected?.profile === 'administrador';
  const title = warehouse ? 'Almoxarifado' : administrator ? 'Administrador' : 'Setor solicitante';
  const description = warehouse
    ? 'Atenda pedidos e confirme retiradas no ERP.'
    : administrator
      ? 'Acesse catálogo, requisições, atendimento e administração de setores.'
      : 'Monte e acompanhe as requisições do seu setor.';
  const icon = warehouse ? <Building2 size={20} /> : administrator ? <ShieldCheck size={20} /> : <ClipboardList size={20} />;

  return (
    <main className="access-layout">
      {/* <section className="access-brand" aria-label="Salutem Hospitalares">
        <div className="brand-lockup brand-logo-frame"><img className="brand-logo brand-logo-access" src="/salutem-logo.png" alt="Salutem Hospitalares" /></div>
        <div className="access-brand-copy">
          <span className="eyebrow eyebrow-light">GESTÃO DE MATERIAIS</span>
          <h1>O cuidado começa com uma operação bem organizada.</h1>
          <p>Requisições claras, atendimento acompanhado e saldo consultado diretamente no ERP.</p>
        </div>
        <div className="access-meta"><span className="signal-dot" /> Portal interno · Rede Salutem</div>
      </section> */}
      <section className="access-content">
        <form className="access-form-wrap" onSubmit={(event) => void enter(event)}>
          <h2>Entre com seu acesso</h2>
          <article className="access-card">
            <div className="access-card-heading"><span className={`icon-tile${warehouse ? ' icon-tile-soft' : ''}`}>{icon}</span><div><h3>{title}</h3><p>{description}</p></div></div>
            <div className="form-field"><label htmlFor="sector-select">Setor ou tipo de acesso</label><select id="sector-select" required value={sectorId} onChange={(event) => setSectorId(event.target.value)}><option value="">Selecione o acesso</option>{sectors.map((item) => <option key={item.id} value={item.id}>{item.profile === 'almoxarifado' ? `${item.name} · atendimento` : item.profile === 'administrador' ? 'Administrador · acesso geral' : `${item.name} · ${item.leader_name ?? 'líder não definido'}`}</option>)}</select></div>
            <div className="form-field"><label htmlFor="sector-password">Senha</label><input id="sector-password" type="password" required autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Digite a senha" /></div>
            <button className={`button ${warehouse ? 'button-dark' : 'button-primary'} full-width`} disabled={loading || !selected}>{loading ? 'Verificando...' : `Entrar como ${title}`} <ArrowRight size={16} /></button>
          </article>
          {error && <div className="notice notice-error" role="alert">{error}</div>}
        </form>
      </section>
    </main>
  );
}
