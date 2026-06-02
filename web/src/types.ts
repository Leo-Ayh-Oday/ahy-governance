// ── Health ──
export interface AgentHealth {
  agent_name: string;
  status: string;
  success_rate: number;
  latency_p95: number;
  error_rate: number;
  last_heartbeat: string;
  total_calls: number;
}

export interface DashboardData {
  agents: AgentHealth[];
  summary: {
    total_agents: number;
    healthy_count: number;
    degraded_count: number;
    unhealthy_count: number;
    total_calls: number;
  };
}

// ── Cost ──
export interface CostReport {
  total_cost_usd: number;
  by_agent: Record<string, number>;
  by_model: Record<string, number>;
  total_tokens: number;
  calls: number;
}

export interface BudgetStatus {
  limit_usd: number;
  period: string;
  total_cost: number;
  usage_pct: number;
  alert_threshold: number;
  auto_block: boolean;
  near_limit: boolean;
  anomaly_count?: number;
  anomaly_threshold_usd?: number;
}

export interface AnomalyEvent {
  agent_name: string;
  model: string;
  cost_usd: number;
  tokens_total: number;
  reason: string;
  session_id: string;
  timestamp: string;
}

export interface AnomalyFinding {
  type: string;
  agent: string;
  severity: string;
  description: string;
  current_value: number;
  baseline_value: number;
  threshold: number;
  timestamp: string;
  evidence: Record<string, unknown>;
}

export interface RestoreContext {
  agent_name?: string;
  session_id?: string;
  checkpoint_id?: number;
  step?: string;
  created_at?: string;
  state?: Record<string, unknown>;
}

export interface HealingResult {
  agent_name: string;
  incident_type: string;
  action: {
    action_type: string;
    description: string;
    params: Record<string, unknown>;
    confidence: number;
    source: string;
  } | null;
  status: string;
  diagnosed_by: string;
  detail: string;
  incident_id: number;
  restore_context: RestoreContext | null;
}

export interface AnomalyHealResult {
  anomaly: AnomalyFinding;
  healing: HealingResult;
}

export interface RecoveryLedgerEntry {
  id?: number;
  incident_id?: number;
  agent_name: string;
  incident_type: string;
  error_message?: string;
  recovery_action: string;
  diagnosed_by?: string;
  success?: number | boolean;
  confidence?: number;
  evidence?: string | Record<string, unknown>;
  timestamp?: string;
}

// ── Audit ──
export interface AuditEvent {
  index: number;
  timestamp: string;
  event_type: string;
  agent_name: string;
  details: Record<string, unknown>;
  session_id: string;
  hash: string;
  prev_hash: string;
}

// ── Conflicts ──
export interface ConflictStats {
  total: number;
  open: number;
  resolved_today: number;
  critical_open: number;
  dismissed?: number;
  acknowledged?: number;
  by_severity?: Record<string, number>;
  by_type?: Record<string, number>;
}

// ── Agents ──
export interface RegisteredAgent {
  agent_id: string;
  agent_name: string;
  model: string;
  upstream_url: string;
  replace_with: string;
  created_at: string;
}

// ── Announcements ──
export interface Announcement {
  tag: string;
  title: string;
  warn: boolean;
  timestamp: string;
  source: string;
}

// ── Policies ──
export interface PolicyMatch {
  field: string;
  operator: string;
  value: number | string;
}

export interface PolicyRule {
  id: string;
  name: string;
  trigger: string;
  description: string;
  enabled: boolean;
  actions: string[];
  match: PolicyMatch[];
}
