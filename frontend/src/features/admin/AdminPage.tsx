import { useEffect, useState, type FormEvent } from 'react';
import { KeyRound, Plus, Save, UserRound, X } from 'lucide-react';
import { api } from '../../lib/api';
import type { Sector } from '../../lib/types';

export default function AdminPage() {
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [name, setName] = useState('');
  const [profile, setProfile] = useState<'solicitante' | 'almoxarifado'>('solicitante');
  const [leader, setLeader] = useState('');
  const [password, setPassword] = useState('');
  const [search, setSearch] = useState('');
  const [newPasswords, setNewPasswords] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const warehouseExists = sectors.some((sector) => sector.profile === 'almoxarifado');

  async function load() {
    try { setSectors(await api.sectors()); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível carregar os setores.'); }
  }
  useEffect(() => { void load(); }, []);

  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      await api.createSector({ name: profile === 'almoxarifado' ? 'Almoxarifado' : name.trim(), profile, leader_name: profile === 'solicitante' ? leader.trim() : null, password });
      setName(''); setLeader(''); setPassword(''); setNotice('Setor criado. A senha não será exibida novamente.'); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível criar o setor.'); }
    finally { setBusy(false); }
  }

  async function save(sector: Sector, nextName: string, nextLeader: string, active: boolean) {
    const nextPassword = newPasswords[sector.id]?.trim();
    const patch: { name?: string; leader_name?: string | null; active?: boolean; new_password?: string } = {};
    if (sector.profile === 'solicitante' && nextName.trim() !== sector.name) patch.name = nextName.trim();
    if (sector.profile === 'solicitante' && nextLeader.trim() !== (sector.leader_name ?? '')) patch.leader_name = nextLeader.trim();
    if (active !== Boolean(sector.active)) patch.active = active;
    if (nextPassword) patch.new_password = nextPassword;
    if (!Object.keys(patch).length) return;
    setBusy(true); setError(''); setNotice('');
    try { await api.updateSector(sector.id, patch); setNewPasswords((current) => ({ ...current, [sector.id]: '' })); setNotice(`Setor ${sector.name} atualizado. Senhas alteradas encerram as sessões existentes.`); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível atualizar o setor.'); }
    finally { setBusy(false); }
  }

  const visible = sectors.filter((sector) => `${sector.name} ${sector.leader_name ?? ''}`.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR')));
  return <section>
    <div className="page-heading"><div><span className="eyebrow">ADMINISTRAÇÃO</span><h1>Setores e acessos</h1><p>Cadastre o líder designado e gerencie a senha compartilhada de cada setor.</p></div></div>
    {notice && <div className="notice" style={{ background: '#eaf5ec', color: '#285d35', marginBottom: 14 }} role="status">{notice}<button className="text-button" style={{ marginLeft: 'auto' }} onClick={() => setNotice('')} aria-label="Fechar aviso"><X size={15} /></button></div>}
    {error && <div className="notice notice-error" role="alert">{error}<button className="text-button" style={{ marginLeft: 'auto' }} onClick={() => setError('')} aria-label="Fechar erro"><X size={15} /></button></div>}
    <div className="admin-layout" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(300px,360px)', gap: 16, alignItems: 'start' }}>
      <div className="panel panel-pad"><div className="toolbar"><div className="search-wrap"><UserRound size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filtrar setor ou líder" aria-label="Filtrar setores" /></div><span className="stock-label">{visible.length} setores</span></div>
        <div className="table-wrap"><table><thead><tr><th>Setor</th><th>Perfil / líder</th><th>Estado</th><th>Nova senha</th><th></th></tr></thead><tbody>{visible.map((sector) => <SectorRow key={sector.id} sector={sector} disabled={busy} password={newPasswords[sector.id] ?? ''} onPassword={(value) => setNewPasswords((current) => ({ ...current, [sector.id]: value }))} onSave={save} />)}{visible.length === 0 && <tr><td colSpan={5}><div className="empty-state">Nenhum setor cadastrado.</div></td></tr>}</tbody></table></div>
      </div>
      <form className="panel panel-pad" onSubmit={(event) => void create(event)}><div className="access-card-heading"><span className="icon-tile"><Plus size={19} /></span><div><h3>Novo acesso de setor</h3><p>Senha armazenada em hash, nunca exibida.</p></div></div>
        <div className="form-field"><label htmlFor="sector-profile">Tipo de acesso</label><select id="sector-profile" value={profile} onChange={(event) => setProfile(event.target.value as 'solicitante' | 'almoxarifado')}><option value="solicitante">Setor solicitante</option><option value="almoxarifado" disabled={warehouseExists}>Almoxarifado{warehouseExists ? ' (já cadastrado)' : ''}</option></select></div>
        <div className="form-field"><label htmlFor="sector-name">{profile === 'almoxarifado' ? 'Nome do acesso' : 'Nome do setor'}</label><input id="sector-name" value={profile === 'almoxarifado' ? 'Almoxarifado' : name} onChange={(event) => setName(event.target.value)} required disabled={profile === 'almoxarifado'} placeholder="Ex.: Serralheria" /></div>
        {profile === 'solicitante' && <div className="form-field"><label htmlFor="leader-name">Líder designado</label><input id="leader-name" value={leader} onChange={(event) => setLeader(event.target.value)} required placeholder="Nome do líder" /></div>}
        <div className="form-field"><label htmlFor="sector-new-password">Senha do setor (mínimo 12 caracteres)</label><input id="sector-new-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} required /></div>
        <button className="button button-primary full-width" disabled={busy}><Plus size={16} /> Criar setor</button>
      </form>
    </div>
  </section>;
}

function SectorRow({ sector, disabled, password, onPassword, onSave }: { sector: Sector; disabled: boolean; password: string; onPassword: (value: string) => void; onSave: (sector: Sector, name: string, leader: string, active: boolean) => void }) {
  const [name, setName] = useState(sector.name);
  const [leader, setLeader] = useState(sector.leader_name ?? '');
  const [active, setActive] = useState(Boolean(sector.active));
  useEffect(() => { setName(sector.name); setLeader(sector.leader_name ?? ''); setActive(Boolean(sector.active)); }, [sector.name, sector.leader_name, sector.active]);
  return <tr><td>{sector.profile === 'almoxarifado' ? <strong>Almoxarifado</strong> : <input className="field-control" aria-label={`Nome do setor ${sector.name}`} value={name} onChange={(event) => setName(event.target.value)} />}</td><td>{sector.profile === 'almoxarifado' ? 'Almoxarifado' : <input className="field-control" aria-label={`Líder de ${sector.name}`} value={leader} onChange={(event) => setLeader(event.target.value)} />}</td><td><label><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> {active ? 'Ativo' : 'Inativo'}</label></td><td><input type="password" autoComplete="new-password" minLength={12} maxLength={128} aria-label={`Nova senha de ${sector.name}`} placeholder="(não alterar)" value={password} onChange={(event) => onPassword(event.target.value)} /></td><td><button className="icon-button" aria-label={`Salvar ${sector.name}`} disabled={disabled} onClick={() => onSave(sector, name, leader, active)}><Save size={15} /></button><KeyRound size={15} aria-label="Senha armazenada em hash" /></td></tr>;
}
