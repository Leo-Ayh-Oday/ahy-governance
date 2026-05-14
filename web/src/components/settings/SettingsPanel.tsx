import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Key, Trash2, Plus, Save, Globe, Bell, AlertTriangle } from 'lucide-react';
import { fetchBudget } from '../../api';
import type { BudgetStatus } from '../../types';

interface ApiKey {
  id?: number;
  key_id?: string;
  name: string;
  role: string;
  created_at?: string;
  prefix?: string;
}

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

export function SettingsPanel() {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
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
      request<{ keys: ApiKey[] }>('/auth/keys').catch(() => ({ keys: [] })),
      fetchBudget().catch(() => null),
      request<Array<{ group_name?: string; channel?: string }>>('/webhooks/channels').catch(() => []),
    ]).then(([k, b, c]) => {
      setApiKeys(k.keys ?? []);
      setBudget(b);
      setChannels(Array.isArray(c) ? c : []);
      if (b) {
        setBudgetLimit(String(b.limit_usd));
        setBudgetThreshold(String((b.alert_threshold * 100).toFixed(0)));
        setAutoBlock(b.auto_block);
      }
    }).finally(() => setLoading(false));
  }, []);

  async function createKey() {
    if (!newKeyName.trim()) return;
    try {
      setError('');
      const r = await request<{ key?: ApiKey }>('/auth/keys', {
        method: 'POST',
        body: JSON.stringify({ name: newKeyName.trim(), role: newKeyRole }),
      });
      const newKey: ApiKey = r.key ?? { name: newKeyName, role: newKeyRole, key_id: 'created' };
      setApiKeys([...apiKeys, newKey]);
      setNewKeyName('');
    } catch (e: unknown) { setError((e as Error).message); }
  }

  async function deleteKey(id: string) {
    try {
      setError('');
      await request(`/auth/keys/${id}`, { method: 'DELETE' });
      setApiKeys(apiKeys.filter(k => k.key_id !== id));
    } catch (e: unknown) { setError((e as Error).message); }
  }

  async function saveBudget() {
    try {
      setError('');
      const body = {
        limit_usd: parseFloat(budgetLimit),
        period: 'monthly',
        alert_threshold: parseFloat(budgetThreshold) / 100,
        auto_block: autoBlock,
      };
      await request('/cost/budget', { method: 'POST', body: JSON.stringify(body) });
      setBudget({ ...budget!, limit_usd: body.limit_usd, alert_threshold: body.alert_threshold, auto_block: body.auto_block, usage_pct: budget?.usage_pct ?? 0, near_limit: false, total_cost: budget?.total_cost ?? 0, period: budget?.period ?? 'monthly' });
    } catch (e: unknown) { setError((e as Error).message); }
  }

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="bg-brand-500/20 rounded-3xl p-8 h-40" />
        {[1, 2, 3].map(i => <div key={i} className="card-elevated rounded-3xl p-8 h-48" />)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 flex items-center gap-3 text-rose-700 text-sm">
          <AlertTriangle size={16} />
          {error}
          <button onClick={() => setError('')} className="ml-auto text-rose-500 hover:text-rose-700">✕</button>
        </div>
      )}

      {/* API Keys */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card-elevated rounded-3xl p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 rounded-2xl bg-amber-50 text-amber-600 border border-amber-100"><Key size={20} /></div>
          <div>
            <h3 className="text-lg font-bold">API Keys</h3>
            <p className="text-xs text-surface-400">管理 Agent 和 API 访问密钥</p>
          </div>
        </div>

        <div className="space-y-3 mb-6">
          {apiKeys.length === 0 && <p className="text-surface-400 text-sm text-center py-4">暂无 API Keys</p>}
          {apiKeys.map(k => (
            <div key={k.key_id ?? k.id} className="flex items-center justify-between p-4 bg-surface-50 rounded-2xl border border-surface-100">
              <div>
                <p className="font-semibold text-sm">{k.name}</p>
                <p className="text-xs text-surface-400">{k.prefix ?? '****'} · {k.role} · {k.created_at?.slice(0, 10) ?? ''}</p>
              </div>
              <button onClick={() => deleteKey(k.key_id ?? '')} className="p-2 text-surface-400 hover:text-rose-600 transition-colors rounded-xl hover:bg-rose-50">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-xs font-semibold text-surface-400 block mb-1">名称</label>
            <input value={newKeyName} onChange={e => setNewKeyName(e.target.value)} placeholder="Key 名称..."
              className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500 transition-all" />
          </div>
          <div>
            <label className="text-xs font-semibold text-surface-400 block mb-1">角色</label>
            <select value={newKeyRole} onChange={e => setNewKeyRole(e.target.value)}
              className="px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500">
              <option value="viewer">Viewer</option>
              <option value="operator">Operator</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button onClick={createKey} disabled={!newKeyName.trim()}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 text-white rounded-xl font-semibold text-sm hover:bg-brand-600 disabled:opacity-40 transition-all">
            <Plus size={16} /> 创建
          </button>
        </div>
      </motion.div>

      {/* Budget Settings */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card-elevated rounded-3xl p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-100"><Save size={20} /></div>
          <div>
            <h3 className="text-lg font-bold">预算配置</h3>
            <p className="text-xs text-surface-400">设置成本上限和异常熔断</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div>
            <label className="text-xs font-semibold text-surface-400 block mb-1">月度预算上限 (USD)</label>
            <input type="number" value={budgetLimit} onChange={e => setBudgetLimit(e.target.value)}
              className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500" />
          </div>
          <div>
            <label className="text-xs font-semibold text-surface-400 block mb-1">告警阈值 (%)</label>
            <input type="number" value={budgetThreshold} onChange={e => setBudgetThreshold(e.target.value)}
              className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500" />
          </div>
        </div>

        <div className="flex items-center justify-between p-4 bg-surface-50 rounded-2xl border border-surface-100 mb-6">
          <div>
            <p className="font-semibold text-sm">自动熔断</p>
            <p className="text-xs text-surface-400">超限时自动阻断所有 Agent API 调用</p>
          </div>
          <button onClick={() => setAutoBlock(!autoBlock)}
            className={`w-12 h-6 rounded-full transition-colors ${autoBlock ? 'bg-brand-500' : 'bg-surface-300'}`}>
            <div className={`w-4 h-4 bg-white rounded-full transition-all mx-1 ${autoBlock ? 'ml-7' : 'ml-1'}`} />
          </button>
        </div>

        {budget && (
          <div className="text-xs text-surface-400 mb-4">
            当前: ${budget.total_cost?.toFixed(2) ?? '0'} / ${budgetLimit} ({budget.usage_pct?.toFixed(1) ?? '0'}%)
          </div>
        )}

        <button onClick={saveBudget} className="px-6 py-2.5 bg-brand-500 text-white rounded-full font-semibold text-sm hover:bg-brand-600 transition-all">
          保存预算设置
        </button>
      </motion.div>

      {/* Webhook Channels */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card-elevated rounded-3xl p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 border border-brand-100"><Bell size={20} /></div>
          <div>
            <h3 className="text-lg font-bold">通知频道</h3>
            <p className="text-xs text-surface-400">配置 Alert Webhook 和通知接收地址</p>
          </div>
        </div>

        <div className="space-y-3 mb-6">
          {channels.length === 0 && <p className="text-surface-400 text-sm text-center py-4">暂无通知频道</p>}
          {channels.map((c, i) => (
            <div key={i} className="flex items-center justify-between p-4 bg-surface-50 rounded-2xl border border-surface-100">
              <div className="flex items-center gap-3">
                <Globe size={16} className="text-surface-400" />
                <div>
                  <p className="text-sm font-semibold">{c.group_name ?? c.channel ?? '未知'}</p>
                  {c.channel && <p className="text-xs text-surface-400 truncate max-w-[300px]">{c.channel}</p>}
                </div>
              </div>
              <button onClick={() => {
                const group = c.group_name ?? 'default';
                request(`/webhooks/channels/${group}`, { method: 'DELETE' })
                  .then(() => setChannels(channels.filter(ch => (ch.group_name ?? 'default') !== group)))
                  .catch((e: unknown) => setError((e as Error).message));
              }} className="p-2 text-surface-400 hover:text-rose-600 transition-colors rounded-xl hover:bg-rose-50">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-xs font-semibold text-surface-400 block mb-1">Webhook URL</label>
            <input value={newChannel} onChange={e => setNewChannel(e.target.value)} placeholder="https://hooks.slack.com/..."
              className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500" />
          </div>
          <button onClick={() => {
            if (newChannel.trim()) {
              request('/webhooks/channels', { method: 'POST', body: JSON.stringify({ channel: newChannel.trim(), group_name: 'default' }) })
                .then(() => setChannels([...channels, { channel: newChannel, group_name: 'default' }]))
                .catch((e: unknown) => setError((e as Error).message));
              setNewChannel('');
            }
          }} disabled={!newChannel.trim()}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 text-white rounded-xl font-semibold text-sm hover:bg-brand-600 disabled:opacity-40 transition-all">
            <Plus size={16} /> 添加
          </button>
        </div>
      </motion.div>
    </div>
  );
}
