import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import {
  ArrowUpRight, ArrowDownRight, Activity, DollarSign,
  ShieldAlert, Users,
} from 'lucide-react';
import type { DashboardData, CostReport, AuditEvent, ConflictStats } from '../../types';
import { fetchDashboard, fetchCostReport, fetchAuditRecent, fetchConflictStats } from '../../api';

export function Dashboard() {
  const [health, setHealth] = useState<DashboardData | null>(null);
  const [cost, setCost] = useState<CostReport | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [conflicts, setConflicts] = useState<ConflictStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchDashboard().catch(() => null),
      fetchCostReport().catch(() => null),
      fetchAuditRecent(6).catch(() => []),
      fetchConflictStats().catch(() => null),
    ]).then(([d, c, evts, cf]) => {
      setHealth(d); setCost(c); setEvents(evts); setConflicts(cf);
      if (!d && !c) setError('无法连接后端');
    }).catch(() => setError('后端不可达')).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-8 p-1 animate-pulse">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="card-elevated rounded-[32px] p-6 h-36" />
          ))}
        </div>
      </div>
    );
  }

  if (error && !health && !cost) {
    return (
      <div className="flex flex-col items-center justify-center p-20 text-center">
        <div className="w-16 h-16 bg-rose-50 dark:bg-rose-500/10 rounded-3xl flex items-center justify-center mb-6">
          <ShieldAlert className="text-rose-500" size={28} />
        </div>
        <h3 className="text-xl font-bold mb-2 text-surface-800 dark:text-surface-50">无法连接到后端</h3>
        <p className="text-surface-500 max-w-md text-sm">确认 backend 已启动 (localhost:8080)，然后刷新页面。</p>
        <button onClick={() => window.location.reload()} className="mt-6 px-6 py-2.5 bg-brand-600 text-white rounded-full text-sm font-bold hover:bg-brand-700 transition-all">重试</button>
      </div>
    );
  }

  const summary = health?.summary;
  const stats = [
    {
      label: '活跃 Agent', value: String(summary?.total_agents ?? '—'),
      change: summary ? `${summary.healthy} 健康` : '—',
      trend: (summary && summary.healthy === summary.total_agents ? 'up' : 'down') as 'up' | 'down',
      icon: Users, color: 'text-brand-500' as const,
    },
    {
      label: '系统响应率', value: summary?.system_success_rate != null ? `${summary.system_success_rate.toFixed(1)}%` : '—',
      change: summary?.degraded ? `${summary.degraded} 降级` : '全健康',
      trend: (summary?.degraded ? 'down' : 'up') as 'up' | 'down',
      icon: Activity, color: 'text-emerald-500' as const,
    },
    {
      label: '本月开销', value: cost ? `$${cost.total_cost_usd.toFixed(2)}` : '—',
      change: cost ? `${cost.calls} 调用` : '—',
      trend: 'neutral' as const,
      icon: DollarSign, color: 'text-amber-500' as const,
    },
    {
      label: '安全预警', value: conflicts ? String(conflicts.open) : '0',
      change: conflicts ? `${conflicts.total} 总计` : '—',
      trend: (conflicts?.open ? 'down' : 'up') as 'up' | 'down',
      icon: ShieldAlert, color: 'text-rose-500' as const,
    },
  ];

  return (
    <div className="space-y-8 p-1">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <motion.div key={stat.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}
            className="card-elevated rounded-[32px] p-6 flex flex-col justify-between">
            <div className="flex justify-between items-start mb-6">
              <div className="p-3 bg-surface-50 dark:bg-surface-800 rounded-2xl border border-surface-200 dark:border-surface-800">
                <stat.icon size={22} className={stat.color} />
              </div>
              <div className={`flex items-center text-xs font-bold px-2 py-1 rounded-lg ${
                stat.trend === 'up' ? 'text-emerald-600 bg-emerald-50' :
                stat.trend === 'down' ? 'text-rose-600 bg-rose-50' : 'text-surface-500 bg-surface-50'
              }`}>
                {stat.change}{stat.trend !== 'neutral' && (stat.trend === 'up' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />)}
              </div>
            </div>
            <div>
              <p className="text-sm font-medium text-surface-500 uppercase tracking-tight mb-1">{stat.label}</p>
              <h3 className="text-3xl font-bold tracking-tight text-surface-800 dark:text-surface-50">{stat.value}</h3>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 card-elevated rounded-[32px] p-8">
          <div className="flex items-center justify-between mb-10">
            <div>
              <h3 className="text-lg font-bold">Agent 响应延迟 (P95)</h3>
              <p className="text-xs text-surface-500 mt-1">各 Agent 最近延迟对比 — 颜色代表健康状态</p>
            </div>
          </div>
          <div className="h-64 flex items-end justify-between gap-3 px-2">
            {(health?.agents ?? []).slice(0, 12).map((a, i) => {
              const maxLat = Math.max(...(health?.agents ?? []).map(x => x.latency_p95), 1);
              const h = (a.latency_p95 / maxLat) * 100;
              return (
                <motion.div key={a.agent_name} initial={{ height: 0 }} animate={{ height: `${Math.max(h, 4)}%` }}
                  transition={{ delay: 0.5 + i * 0.05 }}
                  className={`flex-1 rounded-t-xl relative group cursor-pointer transition-all ${
                    a.status === 'healthy' ? 'bg-emerald-500/20 hover:bg-emerald-500/30' :
                    a.status === 'degraded' ? 'bg-amber-500/20 hover:bg-amber-500/30' :
                    'bg-rose-500/20 hover:bg-rose-500/30'
                  }`}>
                  <div className={`absolute inset-x-0 bottom-0 h-1/2 rounded-t-xl opacity-20 group-hover:opacity-40 transition-opacity ${
                    a.status === 'healthy' ? 'bg-emerald-500' : a.status === 'degraded' ? 'bg-amber-500' : 'bg-rose-500'
                  }`} />
                </motion.div>
              );
            })}
          </div>
          <div className="flex justify-between mt-6 px-2 text-[10px] font-bold text-surface-400 uppercase tracking-widest">
            {(health?.agents ?? []).slice(0, 12).map(a => (
              <span key={a.agent_name} className="truncate max-w-[60px]" title={a.agent_name}>{a.agent_name}</span>
            ))}
          </div>
        </div>

        <div className="card-elevated rounded-[32px] p-8">
          <h3 className="text-lg font-bold mb-8 uppercase tracking-wider text-surface-500 text-sm">实时审计看板</h3>
          <div className="space-y-6">
            {(events.length ? events : []).slice(0, 5).map((evt, i) => {
              const label = evt.event_type?.replace(/_/g, ' ') ?? 'SYSTEM';
              const isAlert = /ERROR|CONFLICT/.test(label);
              const isWarn = /WARN|BUDGET/.test(label);
              return (
                <div key={i} className="flex gap-4 group cursor-pointer hover:bg-surface-50 dark:hover:bg-surface-800 p-2 -mx-2 rounded-2xl transition-all duration-300 ease-out hover:scale-[1.01]">
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        isAlert ? 'text-rose-600 bg-rose-50' : isWarn ? 'text-amber-600 bg-amber-50' : 'text-brand-500 bg-brand-50'
                      }`}>{label.slice(0, 12)}</span>
                      <span className="text-[10px] text-surface-400 font-mono">
                        {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                      </span>
                    </div>
                    <p className="text-[13px] text-surface-700 dark:text-surface-300 font-medium leading-snug">
                      {evt.agent_name}{evt.details?.detail ? ` — ${String(evt.details.detail).slice(0, 60)}` : ''}
                    </p>
                  </div>
                </div>
              );
            })}
            {!events.length && <p className="text-[13px] text-surface-400 italic">审计日志为空 — 启动后端后自动填充 Demo 数据</p>}
          </div>
          <div className="mt-10 pt-6 border-t border-surface-100 dark:border-surface-800">
            <div className="p-4 bg-surface-950 text-white rounded-2xl font-mono text-[10px] space-y-2 opacity-90 overflow-hidden">
              {events.slice(0, 4).map((evt, i) => (
                <p key={i}>
                  <span className={evt.event_type?.includes('ERROR') ? 'text-rose-400' : 'text-emerald-400'}>
                    [{evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--'}]
                  </span>{' '}
                  {evt.event_type?.replace(/_/g, ' ')}{' '}
                  <span className="text-surface-500">{evt.agent_name}</span>
                </p>
              ))}
              {!events.length && <p className="text-surface-700 italic">// 等待审计流...</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
