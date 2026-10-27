import { useState } from 'react';
import { ArrowRight, Trash2 } from 'lucide-react';
import type { RequestCreate } from '../../lib/types';

type CartLine = {
  material_code: string;
  description: string;
  stock: number;
  default_unit: string;
  unit_code: string;
  unit_description: string;
  conversion_result: string;
  conversion_operation: 'M' | 'D';
  conversion_coefficient: number;
  quantity: number;
};
type Props = { leader: string; sector: string; cart: CartLine[]; onChange: (next: CartLine[]) => void; onSubmit: (payload: RequestCreate) => Promise<void> };
const localDate = () => { const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const today = localDate();
const quantityLabel = (value: number) => value.toLocaleString('pt-BR', { maximumFractionDigits: 4 });

function toDefaultUnit(quantity: number, item: CartLine): number {
  const raw = item.conversion_operation === 'M'
    ? quantity * item.conversion_coefficient
    : quantity / item.conversion_coefficient;
  return Math.round((raw + Number.EPSILON) * 10_000) / 10_000;
}

export default function CartPage({ leader, sector, cart, onChange, onSubmit }: Props) {
  const [requestedDate, setRequestedDate] = useState(today);
  const [instructions, setInstructions] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const hasStockWarning = cart.some((item) => toDefaultUnit(item.quantity, item) > item.stock);

  async function submit() {
    if (!cart.length) return setError('O carrinho está vazio. Adicione itens antes de enviar.');
    if (!requestedDate || requestedDate > today) return setError('Informe uma data válida que não seja futura.');
    if (cart.some((item) => !Number.isSafeInteger(item.quantity) || item.quantity <= 0)) return setError('As quantidades devem ser números inteiros positivos.');
    setSaving(true); setError('');
    try {
      await onSubmit({
        requested_date: requestedDate,
        delivery_instructions: instructions.trim(),
        items: cart.map((item) => ({ material_code: item.material_code, quantity: item.quantity, unit_code: item.unit_code })),
      });
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível enviar a requisição.'); }
    finally { setSaving(false); }
  }

  return <section>
    <div className="page-heading"><div><span className="eyebrow">NOVA SOLICITAÇÃO</span><h1>Minha requisição</h1><p>Revise os produtos, informe a entrega e envie ao Almoxarifado.</p></div><span className="stock-label">{cart.length} {cart.length === 1 ? 'item' : 'itens'}</span></div>
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    <div className="cart-summary"><div className="panel">
      {cart.length === 0 ? <div className="empty-state"><strong>Nenhum produto no carrinho</strong><p>Volte ao catálogo para selecionar os itens.</p></div> : cart.map((item) => {
        const lineKey = `${item.material_code}:${item.unit_code}`;
        const converted = toDefaultUnit(item.quantity, item);
        return <div className="cart-line" key={lineKey}>
          <div>
            <strong>{item.description}</strong>
            <small>{item.material_code} · unidade escolhida {item.unit_code} ({item.unit_description})</small>
            <small>Saldo ERP {quantityLabel(item.stock)} {item.default_unit}</small>
            {item.conversion_result && item.unit_code !== item.default_unit && <small>{item.conversion_result}</small>}
            {converted > item.stock && <small className="notice-inline" style={{ display: 'inline-block', marginTop: 5 }}>Equivalente estimado acima do saldo ERP; sujeito à conferência</small>}
          </div>
          <span className="stock-label">{quantityLabel(item.quantity)} {item.unit_code}</span>
          <input className="cart-qty" type="number" min="1" step="1" inputMode="numeric" aria-label={`Quantidade de ${item.material_code} em ${item.unit_code}`} value={item.quantity} onChange={(event) => {
            const raw = event.target.value;
            const amount = Number(raw);
            if (raw !== '' && !Number.isSafeInteger(amount)) { setError('As quantidades devem ser números inteiros.'); return; }
            onChange(cart.map((line) => line.material_code === item.material_code && line.unit_code === item.unit_code ? { ...line, quantity: amount } : line));
            setError('');
          }} />
          <button className="icon-remove" aria-label={`Remover ${item.material_code} em ${item.unit_code}`} onClick={() => onChange(cart.filter((line) => !(line.material_code === item.material_code && line.unit_code === item.unit_code)))}><Trash2 size={17} /></button>
        </div>;
      })}
      {cart.length > 0 && <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '12px 15px' }}><button className="text-button" onClick={() => onChange([])}>Esvaziar carrinho</button></div>}
    </div>
    <aside className="panel panel-pad"><span className="eyebrow">DADOS DA REQUISIÇÃO</span>
      <div className="form-field" style={{ marginTop: 17 }}><label>Líder solicitante / responsável</label><input value={leader} readOnly /></div>
      <div className="form-field"><label>Setor</label><input value={sector} readOnly /></div>
      <div className="form-field"><label htmlFor="requested-date">Data da requisição</label><input id="requested-date" type="date" max={today} value={requestedDate} onChange={(event) => setRequestedDate(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="delivery-instructions">Observações</label><textarea id="delivery-instructions" value={instructions} onChange={(event) => setInstructions(event.target.value)} /></div>
      <button className="button button-primary full-width" onClick={() => void submit()} disabled={saving}>{saving ? 'Registrando...' : 'Enviar requisição'} <ArrowRight size={16} /></button>
      {hasStockWarning && <p className="stock-label" style={{ marginBottom: 0 }}>O saldo será conferido novamente antes da baixa no ERP.</p>}
    </aside></div>
  </section>;
}
