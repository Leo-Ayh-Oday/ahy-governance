import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  History,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import type { AnomalyFinding, AnomalyHealResult, RecoveryLedgerEntry } from '../../types';
import { fetchAnomalyScan, fetchRecoveryHistory, scanAndHealAnomalies } from '../../api';

function compactEvidence(value: unknown): string {
  if (value == null) return 'None';
  if (typeof value === 'string') return value.length > 80 ? `${value.slice(0, 80)}...` : value;
  try {
    const text = JSON.stringify(value);
    return text.length > 80 ? `${text.slice(0, 80)}...` : text;
  } catch {
    return 'Unreadable';
  }
}

function statusTone(status?: string): string {
  if (status === 'succeeded' || status === 'attempted') return 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10';
  if (status === 'escalated') return 'text-amber-600 bg-amber-50 dark:bg-amber-500/10';
  if (status === 'failed') return 'text-rose-600 bg-rose-50 dark:bg-rose-500/10';
  return 'text-surface-600 bg-surface-100 dark:bg-surface-800';
}

function severityTone(severity?: string): string {
  const s = severity?.toLowerCase();
  if (s === 'critical' || s === 'high') return 'text-rose-600 bg-rose-50 dark:bg-rose-500/10';
  if (s === 'medium') return 'text-amber-600 bg-amber-50 dark:bg-amber-500/10';
  return 'text-brand-600 bg-brand-50 dark:bg-brand-500/10';
}

export function SelfHealingConsole() {
  const [findings, setFindings] = useState<AnomalyFinding[]>([]);
  const [history, setHistory] = useState<RecoveryLedgerEntry[]>([]);
  const [healResults, setHealResults] = useState<AnomalyHealResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      fetchAnomalyScan().catch((): AnomalyFinding[] => []),
      fetchRecoveryHistory(12).catch((): RecoveryLedgerEntry[] => []),
    ])
      .then(([nextFindings, nextHistory]) => {
        setFindings(nextFindings);
        setHistory(nextHistory);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const runSelfHealing = useCallback(() => {
    setRunning(true);
    setError('');
    scanAndHealAnomalies()
      .then(results => {
        setHealResults(results);
        return Promise.all([
          fetchAnomalyScan().catch((): AnomalyFinding[] => []),
          fetchRecoveryHistory(12).catch((): RecoveryLedgerEntry[] => []),
        ]);
      })
      .then(([nextFindings, nextHistory]) => {
        setFindings(nextFindings);
        setHistory(nextHistory);
      })
      .catch(err => {
        const message = err instanceof Error ? err.message : String(err);
        setError(message.includes('disabled') || message.includes('403')
          ? '自动修复未开启'
          : '自动修复请求失败');
      })
      .finally(() => setRunning(false));
  }, []);

  const latestRestore = useMemo(() => {
    return healResults.find(r => r.healing.restore_context)?.healing.restore_context ?? null;
  }, [healResults]);

  const summary = [
    { label: '异常', value: findings.length, icon: AlertTriangle },
    { label: '修复', value: healResults.length, icon: ShieldCheck },
    { label: '恢复点', value: latestRestore?.checkpoint_id ?? 'None', icon: Database },
    { label: '记录', value: history.length, icon: History },
  ];

  return (
    <div className="card-elevated rounded-[32px] p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h3 className="text-lg font-bold text-surface-900 dark:text-surface-50">Self-Healing 闭环</h3>
          <p className="text-xs text-surface-500 font-medium mt-1">异常检测、恢复上下文和 ledger 审计</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={loadData}
            disabled={loading || running}
            className="w-10 h-10 rounded-2xl border border-surface-200 dark:border-surface-800 flex items-center justify-center text-surface-600 hover:text-brand-600 hover:border-brand-200 disabled:opacity-50"
            title="刷新"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={runSelfHealing}
            disabled={running}
            className="h-10 px-4 rounded-2xl bg-surface-950 text-white dark:bg-brand-500 text-xs font-bold flex items-center gap-2 disabled:opacity-60"
          >
            <ShieldCheck size={15} />
            {running ? '运行中' : '扫描并修复'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {summary.map(item => (
          <div key={item.label} className="rounded-2xl border border-surface-100 dark:border-surface-800 p-4 bg-surface-50/70 dark:bg-surface-900/40">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-surface-500">{item.label}</span>
              <item.icon size={16} className="text-brand-500" />
            </div>
            <div className="font-mono text-xl font-bold text-surface-900 dark:text-surface-50 truncate">{item.value}</div>
          </div>
        ))}
      </div>

      {error && (
        <div className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 text-amber-700 px-4 py-3 text-xs font-semibold dark:bg-amber-500/10 dark:border-amber-500/20">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 rounded-2xl border border-surface-100 dark:border-surface-800 overflow-hidden">
          <div className="px-5 py-4 border-b border-surface-100 dark:border-surface-800 flex items-center justify-between">
            <h4 className="text-sm font-bold text-surface-800 dark:text-surface-100">当前异常</h4>
            <span className="text-[10px] font-bold text-surface-400 uppercase tracking-widest">scan</span>
          </div>
          <div className="divide-y divide-surface-100 dark:divide-surface-800">
            {findings.length ? findings.slice(0, 5).map((finding, index) => (
              <motion.div
                key={`${finding.agent}-${finding.type}-${index}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-5"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`text-[10px] font-bold px-2 py-1 rounded-lg ${severityTone(finding.severity)}`}>
                        {finding.severity}
                      </span>
                      <span className="text-xs font-mono text-surface-500 truncate">{finding.type}</span>
                    </div>
                    <p className="text-sm font-bold text-surface-900 dark:text-surface-50 truncate">{finding.agent}</p>
                    <p className="text-xs text-surface-500 mt-1 line-clamp-2">{finding.description}</p>
                  </div>
                  <div className="font-mono text-xs text-right text-surface-500">
                    <div>{finding.current_value.toFixed(2)}</div>
                    <div className="text-[10px]">threshold {finding.threshold.toFixed(2)}</div>
                  </div>
                </div>
              </motion.div>
            )) : (
              <div className="p-6 text-sm text-surface-500 flex items-center gap-2">
                <CheckCircle2 size={16} className="text-emerald-500" />
                当前没有异常
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-surface-100 dark:border-surface-800 p-5">
          <h4 className="text-sm font-bold text-surface-800 dark:text-surface-100 mb-4">恢复上下文</h4>
          {latestRestore ? (
            <div className="space-y-4">
              {[
                ['Agent', latestRestore.agent_name],
                ['Session', latestRestore.session_id],
                ['Checkpoint', latestRestore.checkpoint_id],
                ['Step', latestRestore.step],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-4">
                  <span className="text-xs text-surface-500">{label}</span>
                  <span className="text-xs font-mono font-bold text-surface-800 dark:text-surface-100 truncate">{String(value ?? 'None')}</span>
                </div>
              ))}
              <div className="rounded-xl bg-surface-950 text-surface-100 p-4 text-[10px] font-mono overflow-hidden">
                {compactEvidence(latestRestore.state)}
              </div>
            </div>
          ) : (
            <p className="text-sm text-surface-500">暂无恢复上下文</p>
          )}
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-surface-100 dark:border-surface-800 overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-100 dark:border-surface-800 flex items-center justify-between">
          <h4 className="text-sm font-bold text-surface-800 dark:text-surface-100">Recovery Ledger</h4>
          <span className="text-[10px] font-bold text-surface-400 uppercase tracking-widest">audit</span>
        </div>
        <div className="divide-y divide-surface-100 dark:divide-surface-800">
          {history.length ? history.slice(0, 6).map((entry, index) => (
            <div key={`${entry.agent_name}-${entry.timestamp ?? index}`} className="p-4 grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
              <div className="md:col-span-3 min-w-0">
                <p className="text-sm font-bold text-surface-900 dark:text-surface-50 truncate">{entry.agent_name}</p>
                <p className="text-[10px] font-mono text-surface-400 truncate">{entry.incident_type}</p>
              </div>
              <div className="md:col-span-3 text-xs text-surface-600 dark:text-surface-300 truncate">{entry.recovery_action}</div>
              <div className="md:col-span-2">
                <span className={`text-[10px] font-bold px-2 py-1 rounded-lg ${statusTone(entry.success ? 'attempted' : 'escalated')}`}>
                  {entry.success ? 'recorded' : 'review'}
                </span>
              </div>
              <div className="md:col-span-4 text-[10px] font-mono text-surface-400 truncate">
                {compactEvidence(entry.evidence)}
              </div>
            </div>
          )) : (
            <div className="p-6 text-sm text-surface-500">暂无恢复记录</div>
          )}
        </div>
      </div>
    </div>
  );
}
