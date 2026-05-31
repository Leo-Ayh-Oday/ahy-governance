import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Key, Trash2, Plus, Globe, Bell, AlertTriangle, Wallet, Activity, Users, ArrowRight } from 'lucide-react';
import {
  fetchBudget, fetchApiKeys, createApiKey, deleteApiKey,
  saveBudgetSettings, fetchWebhookChannels, addWebhookChannel, deleteWebhookChannel,
  fetchDashboard,
} from '../../api';
import { useApp } from '../../context/AppContext';
import type { BudgetStatus, DashboardData } from '../../types';

interface ApiKey {
  key_id?: string;
  id?: number;
  name: string;
  role: string;
  prefix?: string;
  created_at?: string;
}

export function SettingsPanel() {
  const { setCurrentView } = useApp();
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [channels, setChannels] = useState<Array<{ group_name?: string; channel?: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyRole, setNewKeyRole] = useState('viewer');
  const [newChannel, setNewChannel] = useState('');
  const [budgetLimit, setBudgetLimit] = useState('');
  const [budgetThreshold, setBudgetThreshold] = useState('');
  const [autoBlock, setAutoBlock] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      fetchBudget().catch(() => null),
      fetchApiKeys().catch(() => ({ keys: [] })),
      fetchWebhookChannels().catch(() => []),
      fetchDashboard().catch(() => null),
    ]).then(([b, k, c, d]) => {
      setBudget(b);
      setApiKeys(k.keys ?? []);
      setChannels(Array.isArray(c) ? c : []);
      setDashboard(d);
      if (b) {
        setBudgetLimit(String(b.limit_usd));
        setBudgetThreshold(String((b.alert_threshold * 100).toFixed(0)));
        setAutoBlock(b.auto_block);
      }
    }).finally(() => setLoading(false));
  }, []);

  const handleCreateKey = async () => { if (!newKeyName.trim()) return; try { setError(''); await createApiKey(newKeyName.trim(), newKeyRole); const r = await fetchApiKeys(); setApiKeys(r.keys ?? []); setNewKeyName(''); } catch (e: unknown) { setError((e as Error).message); } };
  const handleDeleteKey = async (id: string) => { try { setError(''); await deleteApiKey(id); setApiKeys(prev => prev.filter(k => k.key_id !== id)); } catch (e: unknown) { setError((e as Error).message); } };
  const handleSaveBudget = async () => { try { setError(''); await saveBudgetSettings({ limit_usd: parseFloat(budgetLimit), period: 'monthly', alert_threshold: parseFloat(budgetThreshold) / 100, auto_block: autoBlock }); } catch (e: unknown) { setError((e as Error).message); } };
  const handleAddChannel = async () => { if (!newChannel.trim()) return; try { setError(''); await addWebhookChannel({ channel: newChannel.trim(), group_name: 'default' }); setChannels(prev => [...prev, { channel: newChannel, group_name: 'default' }]); setNewChannel(''); } catch (e: unknown) { setError((e as Error).message); } };
  const handleDeleteChannel = async (group: string) => { try { setError(''); await deleteWebhookChannel(group); setChannels(prev => prev.filter(c => (c.group_name ?? 'default') !== group)); } catch (e: unknown) { setError((e as Error).message); } };

  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-pulse">
        <div className="lg:col-span-2 space-y-6">
          {[1, 2, 3].map(i => <div key={i} className="card-elevated rounded-[2rem] p-8 h-48" />)}
        </div>
        <div className="card-elevated rounded-[2rem] p-8 h-64" />
      </div>
    );
  }

  const sectionCls = "card-elevated rounded-[2rem] p-8";
  const labelCls = "text-xs font-bold text-surface-500 uppercase tracking-widest mb-2";
  const inputCls = "w-full px-4 py-3 bg-surface-50 dark:bg-surface-800 border-none rounded-xl text-sm focus:ring-2 focus:ring-brand-500 transition-all outline-none [&::-webkit-inner-spin-button]:opacity-40 [&::-webkit-outer-spin-button]:opacity-40 hover:[&::-webkit-inner-spin-button]:opacity-100";
  const btnCls = "flex items-center gap-2 px-5 py-2.5 bg-brand-500 text-white rounded-xl font-semibold text-sm hover:bg-brand-600 disabled:opacity-40 transition-all";
  const iconBoxCls = "p-3 rounded-2xl border";
  // Backend uses healthy_count/degraded_count/unhealthy_count
  const s = dashboard?.summary as Record<string, any> | undefined;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left: Forms */}
      <div className="lg:col-span-2 space-y-6">
        {error && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-2xl p-4 flex items-center gap-3 text-rose-700 dark:text-rose-400 text-sm">
            <AlertTriangle size={16} /> {error}
            <button onClick={() => setError('')} className="ml-auto text-rose-500 hover:text-rose-700">✕</button>
          </motion.div>
        )}

        {/* Budget */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={sectionCls}>
          <div className="flex items-center gap-3 mb-6">
            <div className={`${iconBoxCls} bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 border-emerald-100 dark:border-emerald-500/20`}><Wallet size={20} /></div>
            <div><h3 className="text-lg font-bold">预算配置</h3><p className="text-xs text-surface-400">月度成本上限和自动熔断规则</p></div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div><label className={labelCls}>月度预算上限 (USD)</label><input type="number" value={budgetLimit} onChange={e => setBudgetLimit(e.target.value)} className={inputCls} /></div>
            <div><label className={labelCls}>告警阈值 (%)</label><input type="number" value={budgetThreshold} onChange={e => setBudgetThreshold(e.target.value)} className={inputCls} /></div>
          </div>
          <div className="flex items-center justify-between p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl border border-surface-100 dark:border-surface-700 mb-6">
            <div><p className="font-semibold text-sm">自动熔断</p><p className="text-xs text-surface-400">超限时自动阻断所有 Agent API 调用</p></div>
            <button onClick={() => setAutoBlock(!autoBlock)} className={`w-12 h-6 rounded-full transition-colors ${autoBlock ? 'bg-brand-500' : 'bg-surface-300 dark:bg-surface-600'}`}><div className={`w-4 h-4 bg-white rounded-full transition-all mx-1 ${autoBlock ? 'ml-7' : 'ml-1'}`} /></button>
          </div>
          {budget && <div className="text-sm text-surface-500 mb-4">本月已用: <span className="font-bold text-surface-700 dark:text-surface-300">${budget.total_cost?.toFixed(2) ?? '0'}</span> / ${budgetLimit}<span className="text-xs ml-2">({budget.usage_pct?.toFixed(1) ?? '0'}%)</span></div>}
          <button onClick={handleSaveBudget} className="px-6 py-2.5 bg-brand-500 text-white rounded-full font-semibold text-sm hover:bg-brand-600 transition-all shadow-sm">保存预算设置</button>
        </motion.div>

        {/* API Keys */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className={sectionCls}>
          <div className="flex items-center gap-3 mb-6">
            <div className={`${iconBoxCls} bg-amber-50 dark:bg-amber-500/10 text-amber-600 border-amber-100 dark:border-amber-500/20`}><Key size={20} /></div>
            <div><h3 className="text-lg font-bold">API Keys</h3><p className="text-xs text-surface-400">管理 Agent 和 API 访问密钥</p></div>
          </div>
          <div className="space-y-2 mb-6">
            {apiKeys.length === 0 && <p className="text-surface-400 text-sm text-center py-8">暂无 API Keys</p>}
            {apiKeys.map(k => (
              <div key={k.key_id ?? k.id} className="flex items-center justify-between p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl border border-surface-100 dark:border-surface-700">
                <div><p className="font-semibold text-sm">{k.name}</p><p className="text-xs text-surface-400">{k.prefix ?? '****'} · {k.role} · {k.created_at?.slice(0, 10) ?? ''}</p></div>
                <button onClick={() => handleDeleteKey(k.key_id ?? '')} className="p-2 text-surface-400 hover:text-rose-600 transition-colors rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10"><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
          <div className="flex gap-3 items-end">
            <div className="flex-1"><label className={labelCls}>名称</label><input value={newKeyName} onChange={e => setNewKeyName(e.target.value)} placeholder="Key 名称..." className={inputCls} /></div>
            <div><label className={labelCls}>角色</label><select value={newKeyRole} onChange={e => setNewKeyRole(e.target.value)} className="px-4 py-3 bg-surface-50 dark:bg-surface-800 border-none rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500"><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="admin">Admin</option></select></div>
            <button onClick={handleCreateKey} disabled={!newKeyName.trim()} className={btnCls}><Plus size={16} /> 创建</button>
          </div>
        </motion.div>

        {/* Webhooks */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className={sectionCls}>
          <div className="flex items-center gap-3 mb-6">
            <div className={`${iconBoxCls} bg-brand-50 dark:bg-brand-500/10 text-brand-600 border-brand-100 dark:border-brand-500/20`}><Bell size={20} /></div>
            <div><h3 className="text-lg font-bold">通知频道</h3><p className="text-xs text-surface-400">Alert Webhook 和通知接收地址</p></div>
          </div>
          <div className="space-y-2 mb-6">
            {channels.length === 0 && <p className="text-surface-400 text-sm text-center py-8">暂无通知频道</p>}
            {channels.map((c, i) => (
              <div key={i} className="flex items-center justify-between p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl border border-surface-100 dark:border-surface-700">
                <div className="flex items-center gap-3"><Globe size={16} className="text-surface-400" /><div><p className="text-sm font-semibold">{c.group_name ?? c.channel ?? '未知'}</p>{c.channel && <p className="text-xs text-surface-400 truncate max-w-[300px]">{c.channel}</p>}</div></div>
                <button onClick={() => handleDeleteChannel(c.group_name ?? 'default')} className="p-2 text-surface-400 hover:text-rose-600 transition-colors rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10"><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
          <div className="flex gap-3 items-end">
            <div className="flex-1"><label className={labelCls}>Webhook URL</label><input value={newChannel} onChange={e => setNewChannel(e.target.value)} placeholder="https://hooks.slack.com/..." className={inputCls} /></div>
            <button onClick={handleAddChannel} disabled={!newChannel.trim()} className={btnCls}><Plus size={16} /> 添加</button>
          </div>
        </motion.div>
      </div>

      {/* Right: System Overview */}
      <div className="space-y-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          className="card-elevated rounded-[2rem] p-8 lg:sticky lg:top-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-3 rounded-2xl bg-brand-50 dark:bg-brand-500/10 text-brand-600 border border-brand-100 dark:border-brand-500/20"><Activity size={20} /></div>
            <div><h3 className="text-lg font-bold">系统概览</h3><p className="text-xs text-surface-400">实时状态摘要</p></div>
          </div>

          <button onClick={() => setCurrentView('registry')} className="w-full text-left mb-5 p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors group">
            <div className="flex items-center gap-2 mb-2"><Users size={14} className="text-surface-400" /><span className="text-xs font-bold text-surface-500 uppercase tracking-wider">Agent</span><ArrowRight size={12} className="ml-auto text-surface-300 group-hover:text-brand-500 transition-colors" /></div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold">{s?.total_agents ?? 0}</span>
              <span className="text-xs text-surface-400">已注册</span>
              {s && (
                <div className="flex gap-1.5 ml-2">
                  {(s.healthy_count ?? 0) > 0 && <span className="px-1.5 py-0.5 bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded text-[10px] font-bold">{s.healthy_count} 健康</span>}
                  {(s.degraded_count ?? 0) > 0 && <span className="px-1.5 py-0.5 bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 rounded text-[10px] font-bold">{s.degraded_count} 降级</span>}
                  {(s.unhealthy_count ?? 0) > 0 && <span className="px-1.5 py-0.5 bg-rose-100 dark:bg-rose-500/10 text-rose-700 dark:text-rose-400 rounded text-[10px] font-bold">{s.unhealthy_count} 异常</span>}
                </div>
              )}
            </div>
            {!s && <p className="text-xs text-surface-400 mt-1">暂无 Agent——前往注册</p>}
          </button>

          <button onClick={() => setCurrentView('dashboard')} className="w-full text-left mb-5 p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors group">
            <div className="flex items-center gap-2 mb-2"><Wallet size={14} className="text-surface-400" /><span className="text-xs font-bold text-surface-500 uppercase tracking-wider">预算</span><ArrowRight size={12} className="ml-auto text-surface-300 group-hover:text-brand-500 transition-colors" /></div>
            {budget ? (
              <>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-2xl font-bold">${budget.total_cost.toFixed(0)}</span>
                  <span className="text-xs text-surface-400">/ ${budget.limit_usd}</span>
                  <span className={`text-xs font-bold ml-auto ${budget.usage_pct > 80 ? 'text-rose-500' : 'text-emerald-500'}`}>{budget.usage_pct.toFixed(0)}%</span>
                </div>
                <div className="h-2 w-full bg-surface-200 dark:bg-surface-700 rounded-full overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(budget.usage_pct, 100)}%` }} className={`h-full rounded-full ${budget.usage_pct > 80 ? 'bg-rose-500' : 'bg-brand-500'}`} />
                </div>
                {budget.auto_block && <p className="text-[10px] text-amber-500 font-medium mt-2">自动熔断已启用</p>}
              </>
            ) : (
              <p className="text-xs text-surface-400">未配置——上方设置预算上限</p>
            )}
          </button>

          <button onClick={() => setCurrentView('observability')} className="w-full text-left p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors group">
            <div className="flex items-center gap-2 mb-2"><Activity size={14} className="text-surface-400" /><span className="text-xs font-bold text-surface-500 uppercase tracking-wider">调用</span><ArrowRight size={12} className="ml-auto text-surface-300 group-hover:text-brand-500 transition-colors" /></div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold">{s?.total_calls ?? '—'}</span>
              <span className="text-xs text-surface-400">次调用</span>
            </div>
          </button>
        </motion.div>
      </div>
    </div>
  );
}
