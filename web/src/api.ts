import type {
  DashboardData,
  AgentHealth,
  CostReport,
  BudgetStatus,
  AuditEvent,
  ConflictStats,
  RegisteredAgent,
  AnomalyEvent,
  Announcement,
} from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Health ──
export function fetchDashboard(): Promise<DashboardData> {
  return request('/health/dashboard');
}

export function fetchAgents(): Promise<AgentHealth[]> {
  return request('/health/agents');
}

export function fetchAgentHealth(name: string): Promise<AgentHealth> {
  return request(`/health/agents/${encodeURIComponent(name)}`);
}

// ── Cost ──
export function fetchCostReport(): Promise<CostReport> {
  return request('/cost/report');
}

export function fetchBudget(): Promise<BudgetStatus> {
  return request('/cost/budget');
}

export function fetchAnomalies(): Promise<AnomalyEvent[]> {
  return request('/cost/anomalies');
}

// ── Audit ──
export function fetchAuditRecent(n = 20): Promise<AuditEvent[]> {
  return request(`/audit/recent?n=${n}`);
}

// ── Conflicts ──
export function fetchConflictStats(): Promise<ConflictStats> {
  return request('/conflicts/stats');
}

// ── Agents ──
export function fetchAgentList(): Promise<{ agents: RegisteredAgent[] }> {
  return request('/agent/list');
}

export function registerAgents(agents: Array<{ agent_name: string; model: string; upstream_url: string }>) {
  return request<{ registered: number; agents: Array<{ agent_id: string; replace_with: string }> }>('/agent/register', {
    method: 'POST',
    body: JSON.stringify({ agents }),
  });
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  input_price: number;
  output_price: number;
}

export interface ModelListResponse {
  models: Record<string, ModelInfo[]>;
  quick_endpoints: Record<string, string>;
}

export function fetchModels(): Promise<ModelListResponse> {
  return request('/models');
}

// ── Announcements ──
export function fetchAnnouncements(): Promise<Announcement[]> {
  return request('/announcements');
}

// ── Auth ──
export function login(email: string, password: string) {
  return request<{ user_id: string; email: string; token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}
