import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import {
  LayoutDashboard, Search, ShieldCheck, Activity, Settings, ChevronRight,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { fetchDashboard, fetchBudget } from '../../api';

const navItems = [
  { id: 'dashboard', label: '控制台', icon: LayoutDashboard },
  { id: 'registry', label: 'Agent 注册与发现', icon: Search },
  { id: 'policies', label: '策略控制', icon: ShieldCheck },
  { id: 'observability', label: '可观测性', icon: Activity },
  { id: 'settings', label: '系统设置', icon: Settings },
] as const;

export function Sidebar() {
  const { currentView, setCurrentView } = useApp();
  const [agentCount, setAgentCount] = useState<number | null>(null);
  const [quotaPct, setQuotaPct] = useState<number>(0);
  const [quotaLabel, setQuotaLabel] = useState('加载中...');

  useEffect(() => {
    fetchDashboard().then(d => {
      const total = d.summary?.total_agents ?? d.agents?.length ?? 0;
      setAgentCount(total);
    }).catch(() => {});
    fetchBudget().then(b => {
      const pct = Math.min(b.usage_pct, 100);
      setQuotaPct(pct);
      setQuotaLabel(`$${b.total_cost.toFixed(0)} / $${b.limit_usd} (${pct.toFixed(0)}%)`);
    }).catch(() => {
      setQuotaLabel('后端未连接');
    });
  }, []);

  return (
    <aside className="w-68 h-screen bg-surface-100 dark:bg-surface-950 border-r border-surface-200 dark:border-surface-800 flex flex-col pt-8">
      <div className="px-6 mb-10 flex items-center gap-3">
        <svg width="32" height="32" viewBox="0 0 32 32" className="shrink-0">
          <rect width="32" height="32" rx="10" fill="#5A5A40" />
          <path d="M16 5.5L26.5 16L16 26.5L5.5 16L16 5.5Z" stroke="#FAF9F6" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M5.5 16C11.5 16 16 11.5 16 5.5C16 11.5 20.5 16 26.5 16C20.5 16 16 20.5 16 26.5C16 20.5 11.5 16 5.5 16Z" stroke="#FAF9F6" strokeWidth="1.5" strokeLinejoin="round" />
          <circle cx="16" cy="16" r="2.2" fill="#FAF9F6" />
        </svg>
        <div>
          <h1 className="font-bold text-lg tracking-tight text-surface-800 dark:text-surface-50">Ahy Governance</h1>
          <p className="text-[10px] text-surface-500 font-medium uppercase tracking-widest">Community v0.8</p>
        </div>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={`w-full group flex items-center justify-between px-4 py-2.5 rounded-xl transition-all duration-300 ease-out hover:scale-[1.02] ${
                isActive
                  ? 'bg-brand-500/10 text-brand-500 dark:bg-brand-500/20 dark:text-brand-400 font-semibold'
                  : 'text-surface-500 dark:text-surface-400 hover:bg-brand-500/5 dark:hover:bg-surface-800'
              }`}
            >
              <div className="flex items-center gap-3">
                <item.icon size={18} className={isActive ? 'text-brand-500' : 'text-surface-400'} />
                <span className="text-[14px]">{item.label}</span>
              </div>
              {isActive && (
                <motion.div layoutId="active-indicator">
                  <ChevronRight size={14} />
                </motion.div>
              )}
            </button>
          );
        })}
      </nav>

      <div className="p-6">
        <div className="bg-brand-100/50 dark:bg-surface-900 rounded-2xl p-4 border border-surface-200 dark:border-surface-800 transition-all duration-300 ease-out hover:scale-[1.02] hover:shadow-md cursor-pointer">
          <p className="text-xs font-bold text-surface-500 mb-2 uppercase tracking-wider">配额限制</p>
          <div className="h-1.5 w-full bg-surface-200 dark:bg-surface-800 rounded-full overflow-hidden mb-2">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(quotaPct, 2)}%` }}
              className={`h-full rounded-full ${quotaPct > 80 ? 'bg-rose-500' : 'bg-brand-500'}`}
            />
          </div>
          <p className="text-[11px] text-surface-600 dark:text-surface-400 font-medium">
            {agentCount != null ? `${agentCount} 活跃智能体` : quotaLabel}
          </p>
        </div>
      </div>
    </aside>
  );
}
