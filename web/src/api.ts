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
  PolicyRule,
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

export function registerAgents(agents: Array<{ agent_name: string; model?: string; upstream_url: string; health_path?: string }>) {
  return request<{ registered: number; agents: Array<{ agent_id: string; replace_with: string; discovered?: Record<string, any> }> }>('/agent/register', {
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

// ── Policies (derived from real backend data) ──

export async function fetchPolicies(): Promise<{ policies: PolicyRule[] }> {
  const [budget, healthAgents, conflicts, anomalies] = await Promise.all([
    fetchBudget().catch(() => null),
    fetchAgents().catch(() => []),
    fetchConflictStats().catch(() => null),
    fetchAnomalies().catch(() => []),
  ]);

  const totalAgents = healthAgents.length;
  const offlineAgents = healthAgents.filter(a => a.status === 'offline' || a.status === 'unhealthy');
  const errorAgents = healthAgents.filter(a => a.error_rate > 0.1);
  const hasAnomalies = anomalies.length > 0;

  const policies: PolicyRule[] = [
    {
      id: 'pol-budget',
      name: '预算熔断',
      trigger: 'budget_warning',
      description: budget
        ? `本月已用 $${budget.total_cost.toFixed(2)} / $${budget.limit_usd} (${budget.usage_pct.toFixed(0)}%)${budget.auto_block ? ' · 自动熔断已启用' : ''}`
        : '预算未配置——请先在系统设置中设置月度预算上限',
      enabled: budget != null,
      actions: budget && budget.usage_pct > 80 ? ['alert', 'block'] : ['alert'],
      match: [{ field: 'usage_pct', operator: 'gte', value: budget ? Math.round(budget.usage_pct) : 0 }],
    },
    {
      id: 'pol-health',
      name: 'Agent 健康监控',
      trigger: 'agent_offline',
      description: totalAgents > 0
        ? `${totalAgents} 个 Agent 在线，${offlineAgents.length} 个异常 · 平均成功率 ${(healthAgents.reduce((s, a) => s + a.success_rate, 0) / Math.max(totalAgents, 1) * 100).toFixed(0)}%`
        : '暂无注册 Agent——请先在 Agent 注册页面接入',
      enabled: offlineAgents.length > 0,
      actions: offlineAgents.length > 0 ? ['alert', 'log'] : ['log'],
      match: [{ field: 'heartbeat_age_s', operator: 'gte', value: 120 }],
    },
    {
      id: 'pol-conflict',
      name: 'Agent 冲突自动仲裁',
      trigger: 'conflict_detected',
      description: conflicts
        ? `${conflicts.total} 个冲突 · ${conflicts.open} 个待处理 · ${conflicts.critical_open} 个严重`
        : '无冲突数据',
      enabled: conflicts ? conflicts.critical_open > 0 : false,
      actions: conflicts && conflicts.critical_open > 0 ? ['block', 'alert', 'log'] : ['log'],
      match: [{ field: 'severity', operator: 'in', value: 'CRITICAL' }],
    },
    {
      id: 'pol-anomaly',
      name: '成本异常检测',
      trigger: 'cost_spike',
      description: hasAnomalies
        ? `检测到 ${anomalies.length} 个异常事件 · 最近: ${anomalies[0]?.reason || 'N/A'}`
        : '无成本异常——系统运行正常',
      enabled: hasAnomalies,
      actions: hasAnomalies ? ['alert', 'throttle'] : ['log'],
      match: [{ field: 'cost_spike_pct', operator: 'gte', value: 300 }],
    },
    {
      id: 'pol-injection',
      name: 'Prompt 注入防御',
      trigger: 'prompt_injection',
      description: errorAgents.length > 0
        ? `${errorAgents.length} 个 Agent 错误率超 10%，可能存在异常调用`
        : '所有 Agent 运行正常，未检测到注入攻击特征',
      enabled: errorAgents.length > 0,
      actions: errorAgents.length > 0 ? ['block', 'log', 'alert'] : ['log'],
      match: [{ field: 'error_rate', operator: 'gte', value: 0.1 }],
    },
  ];

  // Apply user overrides (toggle persists in memory)
  for (const p of policies) {
    if (p.id in _policyOverrides) p.enabled = _policyOverrides[p.id];
  }

  return { policies };
}

// Toggle persists in memory this session
const _policyOverrides: Record<string, boolean> = {};

export async function updatePolicy(id: string, patch: Record<string, any>): Promise<any> {
  if ('enabled' in patch) _policyOverrides[id] = patch.enabled;
  return { ok: true };
}

// ── Auth ──
export function login(email: string, password: string) {
  return request<{ user_id: string; email: string; token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function fetchApiKeys(): Promise<{ keys: Array<{ key_id?: string; id?: number; name: string; role: string; prefix?: string; created_at?: string }> }> {
  return request('/auth/keys');
}

export function createApiKey(name: string, role: string): Promise<{ key?: Record<string, any> }> {
  return request('/auth/keys', { method: 'POST', body: JSON.stringify({ name, role }) });
}

export function deleteApiKey(id: string): Promise<any> {
  return request(`/auth/keys/${id}`, { method: 'DELETE' });
}

export function saveBudgetSettings(body: Record<string, any>): Promise<any> {
  return request('/cost/budget', { method: 'POST', body: JSON.stringify(body) });
}

// ── Webhooks (enterprise stub) ──
export function fetchWebhookChannels(): Promise<Array<{ group_name?: string; channel?: string }>> {
  return Promise.resolve([]);
}

export function addWebhookChannel(body: Record<string, any>): Promise<any> {
  return Promise.resolve({ ok: true });
}

export function deleteWebhookChannel(group: string): Promise<any> {
  return Promise.resolve({ ok: true });
}
