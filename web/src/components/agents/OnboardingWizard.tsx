import { useState } from 'react';
import { motion } from 'motion/react';
import { Check, Sparkles, Upload } from 'lucide-react';
import { registerAgents } from '../../api';

interface Props {
  onDone: () => void;
}

type Mode = 'single' | 'batch';

export function OnboardingWizard({ onDone }: Props) {
  const [mode, setMode] = useState<Mode>('single');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [discovered, setDiscovered] = useState<Record<string, any> | null>(null);
  const [batchJson, setBatchJson] = useState('');
  const [batchError, setBatchError] = useState('');

  const canSubmit = name.trim() && url.trim();

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const payload = { agent_name: name.trim(), upstream_url: url.trim() };
      const result = await registerAgents([payload]);
      const agent = result.agents?.[0];
      if (agent?.discovered && Object.keys(agent.discovered).length > 0) {
        setDiscovered(agent.discovered);
      }
      setDone(true);
      setTimeout(() => onDone(), 2500);
    } catch (e: any) {
      setError(e.message || '注册失败，请检查网络连接');
      setSubmitting(false);
    }
  };

  const parsedBatch = (() => {
    if (!batchJson.trim()) return [];
    try {
      const arr = JSON.parse(batchJson);
      if (!Array.isArray(arr)) throw new Error('必须是 JSON 数组');
      return arr.map((item: any, i: number) => ({
        agent_name: item.agent_name || item.name || `agent-${i + 1}`,
        upstream_url: item.upstream_url || item.url || item.endpoint || '',
      }));
    } catch {
      return [];
    }
  })();

  const handleBatchSubmit = async () => {
    const valid = parsedBatch.filter((e: any) => e.agent_name && e.upstream_url);
    if (!valid.length) return;
    setSubmitting(true);
    try {
      await registerAgents(valid);
      setDone(true);
      setTimeout(() => onDone(), 2000);
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        className="absolute inset-0 bg-surface-950/40 backdrop-blur-sm" onClick={onDone}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        className="bg-white dark:bg-surface-900 rounded-[2rem] p-10 max-w-lg w-full shadow-2xl relative z-10 border border-surface-200 dark:border-surface-800 max-h-[85vh] overflow-y-auto"
      >
        {done ? (
          <div className="flex flex-col items-center py-12 text-center">
            <motion.div
              initial={{ scale: 0 }} animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 200, damping: 12 }}
              className="w-20 h-20 bg-emerald-100 dark:bg-emerald-500/10 rounded-3xl flex items-center justify-center mb-6"
            >
              <Check size={36} className="text-emerald-600" />
            </motion.div>
            <h3 className="text-xl font-bold mb-2">Agent 注册成功</h3>
            {discovered ? (
              <div className="text-sm space-y-2 mt-3">
                {discovered.reachable && <p className="text-emerald-600 font-medium">✓ 已成功连接</p>}
                {discovered.agent_type && discovered.agent_type !== 'unknown' && (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 rounded-full text-xs font-bold">
                    {discovered.agent_type === 'openai_compatible' ? 'OpenAI 兼容' :
                     discovered.agent_type === 'ahy_agent' ? 'Ahy Agent' :
                     discovered.agent_type === 'custom_http' ? '自定义 HTTP' : discovered.agent_type}
                  </div>
                )}
                {discovered.integration_note && (
                  <p className="text-surface-500 text-xs leading-relaxed">{discovered.integration_note}</p>
                )}
                <div className="border-t border-surface-100 dark:border-surface-800 pt-2 mt-2 space-y-1 text-surface-500">
                  {discovered.model && discovered.model !== 'unknown' && <p>模型: {discovered.model}</p>}
                  {discovered.version && discovered.version !== 'unknown' && <p>版本: {discovered.version}</p>}
                  <p>状态: {discovered.status || 'unknown'}</p>
                  {discovered.probe_latency_ms != null && <p>延迟: {discovered.probe_latency_ms}ms</p>}
                </div>
              </div>
            ) : (
              <p className="text-sm text-surface-500">正在后台探测 Agent 信息...</p>
            )}
          </div>
        ) : (
          <>
            <div className="flex mb-8 bg-surface-100 dark:bg-surface-800 rounded-2xl p-1.5">
              {([
                { id: 'single' as Mode, label: '单个注册', icon: Sparkles },
                { id: 'batch' as Mode, label: '批量导入', icon: Upload },
              ]).map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setMode(tab.id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold transition-all ${
                    mode === tab.id
                      ? 'bg-white dark:bg-surface-700 text-brand-600 shadow-sm'
                      : 'text-surface-500 hover:text-surface-700'
                  }`}
                >
                  <tab.icon size={16} />{tab.label}
                </button>
              ))}
            </div>

            {mode === 'single' && (
              <div className="space-y-5">
                <div>
                  <label className="block text-xs font-bold text-surface-500 uppercase tracking-widest mb-2 px-1">
                    Agent 名称
                  </label>
                  <input
                    type="text" value={name}
                    onChange={e => { setName(e.target.value); setError(''); }}
                    placeholder="例如：财务数据分析专家"
                    autoFocus
                    className="w-full px-4 py-3.5 bg-surface-50 dark:bg-surface-800 border-none rounded-xl text-sm focus:ring-2 focus:ring-brand-500 transition-all outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-surface-500 uppercase tracking-widest mb-2 px-1">
                    Agent URL
                  </label>
                  <input
                    type="text" value={url}
                    onChange={e => setUrl(e.target.value)}
                    placeholder="https://your-agent.example.com"
                    className="w-full px-4 py-3.5 bg-surface-50 dark:bg-surface-800 border-none rounded-xl font-mono text-xs focus:ring-2 focus:ring-brand-500 transition-all outline-none"
                  />
                  <p className="text-xs text-surface-400 mt-1.5 px-1">
                    模型和状态将自动探测
                  </p>
                </div>

                {error && (
                  <div className="p-3 bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-xl text-sm text-rose-600">
                    {error}
                  </div>
                )}
                <button
                  onClick={handleSubmit}
                  disabled={!canSubmit || submitting}
                  className="w-full py-3.5 bg-brand-600 text-white font-bold rounded-2xl shadow-lg shadow-brand-500/20 hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submitting ? '正在探测并注册...' : '注册 Agent'}
                </button>
              </div>
            )}

            {mode === 'batch' && (
              <div className="space-y-5">
                <div>
                  <label className="block text-xs font-bold text-surface-500 uppercase tracking-widest mb-2 px-1">
                    JSON 批量导入（只需名称和 URL）
                  </label>
                  <textarea
                    value={batchJson}
                    onChange={e => { setBatchJson(e.target.value); setBatchError(''); }}
                    placeholder={`[\n  {"agent_name": "Planner", "upstream_url": "https://api.openai.com/v1"},\n  {"agent_name": "Coder", "upstream_url": "https://api.anthropic.com/v1"}\n]`}
                    rows={8}
                    className="w-full px-4 py-3.5 bg-surface-50 dark:bg-surface-800 border-none rounded-xl font-mono text-xs focus:ring-2 focus:ring-brand-500 transition-all outline-none resize-y"
                  />
                </div>
                {parsedBatch.length > 0 && (
                  <div className="bg-surface-50 dark:bg-surface-800 rounded-xl p-3 text-xs text-surface-500">
                    已解析 {parsedBatch.length} 个 Agent
                  </div>
                )}
                <button
                  onClick={handleBatchSubmit}
                  disabled={parsedBatch.length === 0 || submitting}
                  className="w-full py-3.5 bg-brand-600 text-white font-bold rounded-2xl shadow-lg shadow-brand-500/20 hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submitting ? '正在注册...' : `批量注册 ${parsedBatch.length} 个 Agent`}
                </button>
              </div>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}
