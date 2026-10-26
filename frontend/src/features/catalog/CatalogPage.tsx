import { useEffect, useRef, useState } from 'react';
import { PackagePlus, Search, X } from 'lucide-react';
import { api } from '../../lib/api';
import type { Product } from '../../lib/types';

type Props = { onAdd: (line: { material_code: string; description: string; stock: number }, quantity: number) => void };
const qty = (value: number) => value.toLocaleString('pt-BR', { maximumFractionDigits: 4 });
const PAGE_SIZES = [20, 40, 60, 100];

export default function CatalogPage({ onAdd }: Props) {
  const [search, setSearch] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [quantityError, setQuantityError] = useState('');
  const queryVersion = useRef(0);
  const offset = (currentPage - 1) * pageSize;

  useEffect(() => {
    const version = ++queryVersion.current;
    setLoading(true);
    setProducts([]);
    setHasMore(false);
    setError('');
    const timer = window.setTimeout(() => {
      api.materials(search, offset, pageSize).then((page) => {
        if (version !== queryVersion.current) return;
        setProducts(page.items);
        setHasMore(page.has_more);
        setError('');
      }).catch((cause: Error) => {
        if (version === queryVersion.current) setError(cause.message);
      }).finally(() => {
        if (version === queryVersion.current) setLoading(false);
      });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      if (queryVersion.current === version) queryVersion.current += 1;
    };
  }, [search, offset, pageSize]);

  function openAdd(product: Product) {
    setSelectedProduct(product);
    setQuantity('1');
    setQuantityError('');
  }

  function confirmAdd() {
    const amount = Number(quantity);
    if (!Number.isSafeInteger(amount) || amount < 1) {
      setQuantityError('Informe uma quantidade inteira maior que zero.');
      return;
    }
    if (!selectedProduct) return;
    onAdd({
      material_code: selectedProduct.code,
      description: selectedProduct.description,
      stock: selectedProduct.stock,
    }, amount);
    setSelectedProduct(null);
  }

  function productCard(product: Product) {
    return <article className="panel material-card" key={product.code}>
      <span className="material-card-code">{product.code}</span>
      <h3>{product.description}</h3>
      <div className="material-card-bottom"><span className="stock-label">Saldo ERP <strong>{qty(product.stock)}</strong></span><span className={`stock-pill${product.stock === 0 ? ' low' : ''}`}>{product.stock > 0 ? 'Disponível' : 'Sem saldo'}</span></div>
      <div className="material-card-bottom" style={{ marginTop: 12 }}>
        <button className="button button-primary full-width" onClick={() => openAdd(product)}><PackagePlus size={15} /> Adicionar</button>
      </div>
    </article>;
  }

  return <section>
    <div className="page-heading"><div><span className="eyebrow">SOLICITAÇÃO DE MATERIAIS</span><h1>Catálogo ERP</h1></div><div className="heading-actions"><span className="stock-label">Página {currentPage}</span></div></div>
    <div className="toolbar">
      <div className="search-wrap"><Search size={17} /><input aria-label="Buscar produto" value={search} onChange={(event) => { setSearch(event.target.value); setCurrentPage(1); }} placeholder="Buscar por código ou descrição..." /></div>
      <label className="catalog-page-size"><span>Produtos por página</span><select className="field-control" aria-label="Produtos por página" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setCurrentPage(1); }}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
    </div>
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {loading && products.length === 0 && <div className="panel empty-state" role="status">Consultando catálogo ERP...</div>}
    {!loading && !error && products.length === 0 && <div className="panel empty-state"><span className="empty-icon"><PackagePlus size={20} /></span><strong>Nenhum produto encontrado</strong><p>Revise o código ou a descrição da busca.</p></div>}
    <div className="material-grid">{products.map(productCard)}</div>
    {(currentPage > 1 || hasMore) && <nav className="pagination catalog-pagination" aria-label="Páginas do catálogo">
      <button className="button button-quiet" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={loading || currentPage <= 1}>Anterior</button>
      <span>Página {currentPage} · {products.length} produtos nesta página</span>
      <button className="button button-quiet" onClick={() => setCurrentPage((page) => page + 1)} disabled={loading || !hasMore}>Próxima</button>
    </nav>}
    {selectedProduct && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedProduct(null); }}><article className="dialog catalog-quantity-dialog" role="dialog" aria-modal="true" aria-labelledby="add-product-title">
      <header className="dialog-header"><div><span className="eyebrow">ADICIONAR AO CARRINHO</span><h2 id="add-product-title">Quantidade solicitada</h2><span className="stock-label">{selectedProduct.code} · saldo ERP {qty(selectedProduct.stock)} #</span></div><button className="icon-button" onClick={() => setSelectedProduct(null)} aria-label="Fechar"><X size={18} /></button></header>
      <div className="dialog-body"><strong># - {selectedProduct.description}</strong><div className="form-field" style={{ marginTop: 18 }}><label htmlFor="add-product-quantity">Quantidade (unidades inteiras)</label><input id="add-product-quantity" autoFocus type="number" min="1" step="1" inputMode="numeric" value={quantity} onChange={(event) => { setQuantity(event.target.value); setQuantityError(''); }} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); confirmAdd(); } }} /></div>
        {Number(quantity) > selectedProduct.stock && <div className="notice notice-warning">A quantidade é maior que o saldo informado pelo ERP; o Almoxarifado conferirá novamente.</div>}
        {quantityError && <div className="notice notice-error" role="alert">{quantityError}</div>}
      </div><footer className="dialog-footer"><button className="button button-quiet" onClick={() => setSelectedProduct(null)}>Cancelar</button><button className="button button-primary" onClick={confirmAdd}><PackagePlus size={16} /> Adicionar ao carrinho</button></footer>
    </article></div>}
  </section>;
}
