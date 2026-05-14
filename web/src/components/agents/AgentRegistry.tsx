import { motion, AnimatePresence } from 'motion/react';
import {
  Search, Plus, ExternalLink, Globe, Sparkles, ArrowRight,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import type { AgentHealth, RegisteredAgent } from '../../types';
import { fetchAgentList, fetchAgents } from '../../api';
import { OnboardingWizard } from './OnboardingWizard';

interface DisplayAgent {
  id: string;
  name: string;
  model: string;
  status: string;
  tasks: number;
  uptime: string;
  description: string;
}

export function AgentRegistry() {
  const [showWizard, setShowWizard] = useState(false);
  const [agents, setAgents] = useState<DisplayAgent[]>([]);
  const [loading, setLoading] = useState(true);

  const loadAgents = async () => {
    const [list, health] = await Promise.all([
      fetchAgentList().catch(() => ({ agents: [] as RegisteredAgent[] })),
      fetchAgents().catch(() => [] as AgentHealth[]),
    ]);
    const healthMap = new Map(health.map(h => [h.agent_name, h]));
    const display: DisplayAgent[] = (list.agents ?? []).map(a => {
      const h = healthMap.get(a.agent_name);
      return {
        id: a.agent_id,
        name: a.agent_name,
        model: a.model || 'Unknown',
        status: h?.status ?? 'offline',
        tasks: h?.total_calls ?? 0,
        uptime: h?.success_rate != null ? `${(h.success_rate * 100).toFixed(0)}%` : '0%',
        description: `Agent ID: ${a.agent_id.slice(0, 8)}... | Endpoint: ${a.upstream_url || 'N/A'}`,
      };
    });
    setAgents(display);
  };

  useEffect(() => { loadAgents().finally(() => setLoading(false)); }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight mb-1">Agent 注册与发现</h2>
          <p className="text-surface-500 text-sm font-medium">注册和管理你的 AI Agent</p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" size={18} />
            <input
              type="text"
              placeholder="搜索 Agent 名称或型号..."
              className="pl-10 pr-4 py-2.5 bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 rounded-xl text-sm w-64 focus:ring-2 focus:ring-brand-500 transition-all outline-none"
            />
          </div>
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 px-6 py-2.5 bg-brand-500 text-white rounded-full font-semibold text-sm shadow-sm hover:bg-brand-600 active:scale-95 transition-all"
          >
            <Plus size={18} />
            Register New Agent
          </button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-8">
          {[1,2,3].map(i => (
            <div key={i} className="card-elevated rounded-[32px] p-8 h-72 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-8">
          <AnimatePresence>
            {agents.map((agent, i) => (
              <motion.div
                key={agent.id}
                layout
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ delay: i * 0.05 }}
                className="card-elevated rounded-[32px] p-8 group flex flex-col"
              >
                <div className="flex items-start justify-between mb-6">
                  <div className="w-12 h-12 rounded-xl border border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-800 flex items-center justify-center font-bold text-brand-500">
                    {agent.name.substring(0, 2).toUpperCase()}
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-right">
                      <p className="text-[10px] font-bold text-surface-400 uppercase tracking-widest">Status</p>
                      <div className="flex items-center gap-1.5 justify-end mt-0.5">
                        <div className={`w-2 h-2 rounded-full ${
                          agent.status === 'healthy' || agent.status === 'online' ? 'bg-emerald-500' :
                          agent.status === 'offline' ? 'bg-rose-500' : 'bg-orange-400'
                        }`} />
                        <span className={`text-xs font-bold ${
                          agent.status === 'healthy' || agent.status === 'online' ? 'text-emerald-700' :
                          agent.status === 'offline' ? 'text-rose-700' : 'text-orange-700'
                        }`}>{agent.status.charAt(0).toUpperCase() + agent.status.slice(1)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <h3 className="font-bold text-base mb-1">{agent.name}</h3>
                <p className="text-xs text-surface-500 font-medium mb-4">Model: {agent.model} • Internal Knowledge Base</p>

                <p className="text-[13px] text-surface-600 dark:text-surface-400 mb-6 flex-1 line-clamp-2 leading-relaxed">
                  {agent.description}
                </p>

                <div className="flex items-center justify-between pt-6 border-t border-surface-100 dark:border-surface-800">
                   <div className="w-full bg-surface-200 dark:bg-surface-800 h-1 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-500"
                        style={{ width: `${agent.uptime === '0%' ? 0 : parseFloat(agent.uptime)}%` }}
                      />
                   </div>
                </div>

                <button className="mt-6 flex items-center justify-center gap-2 w-full py-3 bg-brand-500 text-white rounded-full text-sm font-bold hover:bg-brand-600 transition-all shadow-sm">
                  监控面板 <ExternalLink size={14} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
          {agents.length === 0 && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="col-span-full"
            >
              <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 200, damping: 12, delay: 0.1 }}
                  className="w-24 h-24 bg-brand-50 dark:bg-brand-500/10 rounded-[2rem] flex items-center justify-center mb-8"
                >
                  <Globe size={40} className="text-brand-500" />
                </motion.div>
                <h3 className="text-2xl font-bold mb-3 text-surface-800 dark:text-surface-50">接入你的第一个 Agent</h3>
                <p className="text-surface-500 max-w-md text-sm mb-3 leading-relaxed">
                  30 秒完成接入，系统自动开始监控健康状态、延迟和成本。
                </p>
                <div className="flex items-center gap-6 mb-8 text-xs text-surface-400">
                  <span className="flex items-center gap-1.5"><span className="w-5 h-5 rounded-full bg-brand-100 dark:bg-brand-500/10 flex items-center justify-center text-[10px] font-bold text-brand-500">1</span> 命名</span>
                  <span className="flex items-center gap-1.5"><span className="w-5 h-5 rounded-full bg-brand-100 dark:bg-brand-500/10 flex items-center justify-center text-[10px] font-bold text-brand-500">2</span> 配 Endpoint</span>
                  <span className="flex items-center gap-1.5"><span className="w-5 h-5 rounded-full bg-brand-100 dark:bg-brand-500/10 flex items-center justify-center text-[10px] font-bold text-brand-500">3</span> 完成</span>
                </div>
                <button
                  onClick={() => setShowWizard(true)}
                  className="flex items-center gap-2 px-8 py-3.5 bg-brand-500 text-white rounded-full font-bold text-sm shadow-lg shadow-brand-500/20 hover:bg-brand-600 active:scale-95 transition-all"
                >
                  <Sparkles size={18} />
                  开始接入 <ArrowRight size={16} />
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}

      <AnimatePresence>
        {showWizard && (
          <OnboardingWizard onDone={() => { setShowWizard(false); loadAgents(); }} />
        )}
      </AnimatePresence>
    </div>
  );
}
