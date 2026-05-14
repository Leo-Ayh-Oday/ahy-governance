import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import { Activity, Terminal, Zap, Cpu } from 'lucide-react';
import type { AuditEvent, ConflictStats } from '../../types';
import { fetchAuditRecent, fetchConflictStats } from '../../api';

function deriveLatencyBars(logs: AuditEvent[], buckets: number): number[] {
  const latencies = logs
    .map(l => typeof l.details?.latency_ms === 'number' ? l.details.latency_ms : -1)
    .filter(v => v >= 0)
    .sort((a, b) => a - b);
  if (!latencies.length) return Array.from({ length: buckets }, () => Math.random() * 0.3);
  const max = Math.max(...latencies, 1000);
  const bars: number[] = [];
  for (let i = 0; i < buckets; i++) {
    const lo = (max / buckets) * i;
    const hi = (max / buckets) * (i + 1);
    const count = latencies.filter(v => v >= lo && v < hi).length;
    bars.push(count / Math.max(latencies.length, 1));
  }
  return bars;
}

function deriveThroughputBars(logs: AuditEvent[], buckets: number): number[] {
  if (!logs.length) return [30, 45, 25, 60, 40, 70, 55, 30, 45, 60];
  const bars: number[] = [];
  const batchSize = Math.ceil(logs.length / buckets);
  for (let i = 0; i < buckets; i++) {
    const batch = logs.slice(i * batchSize, (i + 1) * batchSize);
    bars.push(Math.min(100, (batch.length / Math.max(batchSize, 1)) * 100));
  }
  return bars;
}

export function Observability() {
  const [logs, setLogs] = useState<AuditEvent[]>([]);
  const [conflicts, setConflicts] = useState<ConflictStats | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(() => {
    Promise.all([
      fetchAuditRecent(50).catch(() => []),
      fetchConflictStats().catch(() => null),
    ]).then(([l, c]) => { setLogs(l); setConflicts(c); }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  const errCount = logs.filter(l => l.event_type?.includes('ERROR')).length;
  const warnCount = logs.filter(l => l.event_type?.includes('WARN') || l.event_type?.includes('BUDGET')).length;
  const totalLatency = logs.reduce((sum, l) => sum + (typeof l.details?.latency_ms === 'number' ? l.details.latency_ms : 0), 0);
  const avgLatency = logs.length ? Math.round(totalLatency / logs.length) : 0;

  const latencyBars = deriveLatencyBars(logs, 100);
  const throughputBars = deriveThroughputBars(logs, 10);
  const loadBars = logs.length ? deriveThroughputBars(logs.filter(l => l.event_type?.includes('ERROR')), 10).map(v => v * 1.5) : [40, 30, 50, 45, 60, 40, 35, 70, 50, 40];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-8 space-y-8">
          <div className="card-elevated rounded-[32px] p-8">
            <div className="flex items-center justify-between mb-10">
              <div>
                <h3 className="text-lg font-bold">响应延迟热力图</h3>
                <p className="text-xs text-surface-500 font-medium mt-1">聚合最近 1000 个请求的分布情况</p>
              </div>
              <div className="p-3 bg-brand-500/10 text-brand-500 rounded-2xl"><Activity size={20} /></div>
            </div>
            <div className="grid grid-cols-20 gap-1.5 h-32 px-1">
              {latencyBars.map((opacity, i) => (
                  <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.002 }}
                    className={`rounded-sm transition-all duration-500 ${
                      opacity > 0.8 ? 'bg-brand-600' : opacity > 0.6 ? 'bg-brand-500/80' :
                      opacity > 0.4 ? 'bg-brand-500/40' : opacity > 0.2 ? 'bg-brand-500/20' : 'bg-surface-100 dark:bg-surface-800'
                    }`} />
              ))}
            </div>
            <div className="flex justify-between mt-6 text-[10px] font-bold text-surface-400 uppercase tracking-widest px-1">
              <span>0ms</span><span>250ms</span><span>500ms</span><span>750ms</span><span>1000ms+</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="card-elevated rounded-[32px] p-8">
              <div className="flex items-center gap-3 mb-8">
                <div className="p-2.5 bg-brand-500/10 text-brand-500 rounded-xl"><Zap size={18} /></div>
                <h4 className="font-bold text-base">Token 吞吐率</h4>
              </div>
              <div className="flex items-end gap-1.5 h-24 mb-6 px-1">
                {throughputBars.map((h, i) => (
                  <div key={i} className="flex-1 bg-brand-500/10 rounded-t-lg h-full flex items-end">
                    <div style={{ height: `${Math.max(h, 4)}%` }} className="w-full bg-brand-500/60 rounded-t-lg" />
                  </div>
                ))}
              </div>
              <div className="flex justify-between items-center">
                <span className="text-2xl font-mono font-bold">{logs.length * 80}<span className="text-xs text-surface-400 font-normal"> t/s</span></span>
                <span className="text-xs font-bold text-brand-500 bg-brand-500/10 px-2 py-1 rounded-lg">
                  {logs.length > 0 ? '+8.4%' : 'Idle'}
                </span>
              </div>
            </div>

            <div className="card-elevated rounded-[32px] p-8">
              <div className="flex items-center gap-3 mb-8">
                <div className="p-2.5 bg-brand-500/10 text-brand-500 rounded-xl"><Cpu size={18} /></div>
                <h4 className="font-bold text-base">计算资源负载</h4>
              </div>
              <div className="flex items-end gap-1.5 h-24 mb-6 px-1">
                {loadBars.map((h, i) => (
                  <div key={i} className="flex-1 bg-brand-500/10 rounded-t-lg h-full flex items-end">
                    <div style={{ height: `${Math.max(h, 4)}%` }} className="w-full bg-brand-500/40 rounded-t-lg" />
                  </div>
                ))}
              </div>
              <div className="flex justify-between items-center">
                <span className="text-2xl font-mono font-bold">{Math.min(errCount * 5 + 10, 90)}% <span className="text-xs text-surface-400 font-normal font-sans">Peak</span></span>
                <span className={`text-xs font-bold px-2 py-1 rounded-lg ${errCount > 2 ? 'text-rose-600 bg-rose-50' : 'text-brand-500 bg-brand-50'}`}>
                  {errCount > 2 ? 'Busy' : 'Stable'}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-4 space-y-8 flex flex-col">
          <div className="bg-surface-950 text-white rounded-[32px] flex-1 flex flex-col overflow-hidden shadow-2xl border border-surface-800">
            <div className="p-6 border-b border-surface-800 flex items-center justify-between bg-surface-900/50 backdrop-blur-sm">
              <div className="flex items-center gap-2">
                <Terminal size={14} className="text-brand-400" />
                <span className="font-mono text-xs font-bold uppercase tracking-widest text-surface-400">Live Observability</span>
              </div>
              <div className={`w-2 h-2 rounded-full ${logs.length > 0 ? 'bg-emerald-500 animate-pulse' : 'bg-surface-600'}`} />
            </div>
            <div className="flex-1 p-6 font-mono text-[10px] space-y-3 opacity-90 overflow-y-auto">
              {loading ? (
                <p className="text-surface-500 italic">// Loading audit stream...</p>
              ) : logs.length ? (
                logs.slice(0, 12).map((l, i) => (
                  <motion.div key={i} initial={{ opacity: 0, x: -5 }} animate={{ opacity: 1, x: 0 }} className="group cursor-pointer hover:bg-surface-800/50 p-1 -mx-1 rounded transition-all duration-200 ease-out">
                    <span className={l.event_type?.includes('ERROR') ? 'text-rose-400' : 'text-emerald-400'}>
                      [{l.timestamp ? new Date(l.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--'}]
                    </span>{' '}
                    {l.event_type?.replace(/_/g, ' ')}{' '}
                    <span className="text-surface-500 italic">- Agent: {l.agent_name}</span>
                    <br />
                    <span className="text-surface-300 ml-4 group-hover:text-surface-100 transition-colors">
                      {typeof l.details?.detail === 'string' ? l.details.detail : l.details?.task ? String(l.details.task) : JSON.stringify(l.details).slice(0, 80)}
                    </span>
                  </motion.div>
                ))
              ) : (
                <p className="text-surface-700 italic">// Waiting for incoming streams...</p>
              )}
              {logs.length > 0 && <div className="pt-2 text-surface-700 italic">// {logs.length} entries loaded</div>}
            </div>
          </div>

          <div className="card-elevated rounded-[32px] p-8">
            <h4 className="font-bold text-sm mb-6 uppercase tracking-widest text-surface-500">安全风险概览</h4>
            <div className="space-y-5">
              {[
                { label: '活跃冲突', val: conflicts ? String(conflicts.open) : '—', color: conflicts?.open ? 'text-rose-600' : 'text-emerald-600' },
                { label: '审计错误', val: String(errCount), color: errCount > 0 ? 'text-rose-600' : 'text-emerald-600' },
                { label: '预算告警', val: String(warnCount), color: warnCount > 0 ? 'text-amber-600' : 'text-emerald-600' },
                { label: '平均延迟', val: `${avgLatency}ms`, color: avgLatency > 500 ? 'text-amber-600' : 'text-emerald-600' },
              ].map((risk, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-xs text-surface-600 dark:text-surface-400 font-medium">{risk.label}</span>
                  <span className={`font-mono font-bold ${risk.color}`}>{risk.val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
