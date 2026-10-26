export type RequestStatus = 'Pendente' | 'Em andamento' | 'Finalizada' | 'Parcial';
export type SectorProfile = 'solicitante' | 'almoxarifado' | 'administrador';
export type ERPStatus = 'aguardando' | 'enviado' | 'conflito' | 'falhou' | 'revisar_saldo';

export interface Sector {
  id: number;
  name: string;
  profile: SectorProfile;
  leader_name: string | null;
  active?: boolean;
}

export interface CurrentUser {
  sector_id: number;
  sector_name: string;
  profile: SectorProfile;
  leader_name: string | null;
}

export interface Product {
  code: string;
  description: string;
  stock: number;
  deposit: number;
  group: string;
}

export interface RequestItem {
  item_index: number;
  material_code: string;
  description: string;
  requested_quantity: number;
  delivered_quantity: number | null;
}

export interface RequestEvent {
  at: string;
  actor: string;
  note: string;
}

export interface MaterialRequest {
  itecontrol: number;
  number: string;
  sector_id: number;
  sector_name: string;
  leader_name: string | null;
  requested_date: string;
  delivery_instructions: string;
  status: RequestStatus;
  warehouse_notes: string;
  responsible_name: string | null;
  items: RequestItem[];
  events: RequestEvent[];
  erp_status: ERPStatus;
  erp_error: string | null;
  created_at: string;
  finalized_at: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProductPage {
  items: Product[];
  has_more: boolean;
  limit: number;
  offset: number;
}

export interface RequestCreate {
  requested_date: string;
  delivery_instructions: string;
  items: Array<{ material_code: string; quantity: number }>;
}
