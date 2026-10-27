import type { CurrentUser, MaterialRequest, Page, ProductPage, RequestCreate, Sector } from './types';

const BASE = '/api';
let csrfToken = '';
let csrfPromise: Promise<string> | null = null;

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join(' ');
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: 'same-origin' });
  if (!response.ok) {
    let message = `Falha ao consultar o serviço (${response.status}).`;
    try {
      const payload = await response.json() as { detail?: unknown };
      message = errorMessage(payload.detail, message);
    } catch { /* Mantém o status HTTP como mensagem. */ }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  csrf: async () => {
    if (csrfToken) return csrfToken;
    if (!csrfPromise) {
      csrfPromise = request<{ csrf_token: string }>('/auth/csrf')
        .then((result) => { csrfToken = result.csrf_token; return csrfToken; })
        .finally(() => { csrfPromise = null; });
    }
    return csrfPromise;
  },
  sectorsForLogin: () => request<Sector[]>('/auth/sectors'),
  login: async (sector_id: number, password: string) => {
    if (!csrfToken) await api.csrf();
    const result = await request<{ user: CurrentUser; csrf_token: string }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ sector_id, password }),
    });
    csrfToken = result.csrf_token;
    return result.user;
  },
  me: () => request<CurrentUser>('/auth/me'),
  logout: async () => {
    await request<void>('/auth/logout', { method: 'POST' });
    csrfToken = '';
    csrfPromise = null;
  },
  sectors: () => request<Sector[]>('/sectors'),
  createSector: (payload: { name: string; profile: 'solicitante' | 'almoxarifado'; leader_name: string | null; password: string }) =>
    request<Sector>('/sectors', { method: 'POST', body: JSON.stringify(payload) }),
  updateSector: (id: number, patch: { name?: string; leader_name?: string | null; active?: boolean; new_password?: string }) =>
    request<Sector>(`/sectors/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  materials: async (search = '', offset = 0, limit = 20) => {
    const query = new URLSearchParams({ search, offset: String(offset), limit: String(limit) });
    const page = await request<ProductPage>(`/materials?${query}`);
    return {
      ...page,
      items: page.items.map((item) => ({
        ...item,
        stock: Number(item.stock),
        unit_options: item.unit_options.map((unit) => ({ ...unit, coefficient: Number(unit.coefficient) })),
      })),
    };
  },
  requests: async (params: { status?: string; search?: string; date_from?: string; date_to?: string; offset?: number; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.search) query.set('search', params.search);
    if (params.date_from) query.set('date_from', params.date_from);
    if (params.date_to) query.set('date_to', params.date_to);
    query.set('offset', String(params.offset ?? 0));
    query.set('limit', String(params.limit ?? 200));
    const page = await request<Page<MaterialRequest>>(`/requests?${query}`);
    return { ...page, items: page.items.map(normalizeRequest) };
  },
  createRequest: async (payload: RequestCreate) => normalizeRequest(await request<MaterialRequest>('/requests', {
    method: 'POST', body: JSON.stringify(payload),
  })),
  startRequest: async (id: number) => normalizeRequest(await request<MaterialRequest>(`/requests/${id}/start`, { method: 'POST' })),
  finalizeRequest: async (id: number, payload: {
    responsible_name: string;
    warehouse_notes: string;
    confirm_partial_without_note: boolean;
    deliveries: Array<{ item_index: number; quantity: number }>;
  }) => normalizeRequest(await request<MaterialRequest>(`/requests/${id}/finalize`, {
    method: 'POST', body: JSON.stringify(payload),
  })),
  saveNotes: async (id: number, warehouse_notes: string) => normalizeRequest(await request<MaterialRequest>(`/requests/${id}/notes`, {
    method: 'PUT', body: JSON.stringify({ warehouse_notes }),
  })),
  responsibles: () => request<string[]>('/requests/responsibles'),
  finalizedNotifications: (after: string, afterControl: number) => {
    const query = new URLSearchParams({ after, after_control: String(afterControl) });
    return request<MaterialRequest[]>(`/requests/notifications/finalized?${query}`);
  },
  exportUrl: (dateFrom = '', dateTo = '') => {
    const query = new URLSearchParams();
    if (dateFrom) query.set('date_from', dateFrom);
    if (dateTo) query.set('date_to', dateTo);
    const queryString = query.toString();
    return `${BASE}/requests/export.csv${queryString ? `?${queryString}` : ''}`;
  },
};

function normalizeRequest(request: MaterialRequest): MaterialRequest {
  return {
    ...request,
    items: request.items.map((item) => ({
      ...item,
      requested_quantity: Number(item.requested_quantity),
      delivered_quantity: item.delivered_quantity === null ? null : Number(item.delivered_quantity),
      requested_unit_quantity: Number(item.requested_unit_quantity ?? item.requested_quantity),
      delivered_unit_quantity: item.delivered_unit_quantity == null
        ? (item.delivered_quantity === null ? null : Number(item.delivered_quantity))
        : Number(item.delivered_unit_quantity),
    })),
  };
}
