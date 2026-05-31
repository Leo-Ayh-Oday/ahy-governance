import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import { ShieldCheck, Lock, Clock, EyeOff, DollarSign, Zap, Bell, AlertTriangle } from 'lucide-react';
import type { PolicyRule, BudgetStatus } from '../../types';
import { fetchPolicies, updatePolicy, fetchBudget } from '../../api';

const TRIGGER_LABELS: Record<string, string> = {
  cost_spike: '成本异常',
  budget_warning: '预算告警',
  conflict_detected: '冲突检测',
  agent_offline: 'Agent 离线',
  prompt_injection: '注入攻击',
  compliance_violation: '合规违规',
  agent_error: 'Agent 错误',
};

const TRIGGER_ICONS: Record<string, typeof ShieldCheck> = {
  cost_spike: DollarSign,
  budget_warning: Bell,
  conflict_detected: AlertTriangle,
  agent_offline: Clock,
  prompt_injection: Lock,
  compliance_violation: ShieldCheck,
  agent_error: Zap,
};

const TRIGGER_COLORS: Record<string, string> = {
  cost_spike: 'emerald',
  budget_warning: 'amber',
  conflict_detected: 'rose',
  agent_offline: 'slate',
  prompt_injection: 'rose',
  compliance_violation: 'brand',
  agent_error: 'orange',
};

const ACTION_LABELS: Record<string, string> = {
  alert: '通知',
  block: '阻断',
  log: '记录',
  throttle: '限流',
};

function colorClasses(color: string) {
  const map: Record<string, { bg: string; text: string; border: string }> = {
    emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600', border: 'border-emerald-100' },
    amber: { bg: 'bg-amber-50', text: 'text-amber-600', border: 'border-amber-100' },
    rose: { bg: 'bg-rose-50', text: 'text-rose-600', border: 'border-rose-100' },
    slate: { bg: 'bg-slate-50', text: 'text-slate-600', border: 'border-slate-100' },
    brand: { bg: 'bg-brand-50', text: 'text-brand-600', border: 'border-brand-100' },
    orange: { bg: 'bg-orange-50', text: 'text-orange-600', border: 'border-orange-100' },
  };
  return map[color] ?? map.slate;
}

export function PolicyControl() {
  const [rules, setRules] = useState<PolicyRule[]>([]);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    Promise.all([
      fetchPolicies().catch(() => ({ policies: [] })),
      fetchBudget().catch(() => null),
    ]).then(([p, b]) => {
      setRules(p.policies ?? []);
      setBudget(b);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function toggleRule(rule: PolicyRule) {
    if (toggling.has(rule.id)) return;
    setToggling(new Set(toggling).add(rule.id));
    try {
      await updatePolicy(rule.id, { enabled: !rule.enabled });
      await load();
    } catch {} finally {
      const next = new Set(toggling);
      next.delete(rule.id);
      setToggling(next);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="bg-brand-500/20 rounded-[32px] p-8 h-40" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1,2,3,4].map(i => <div key={i} className="card-elevated rounded-[32px] p-8 h-56" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center bg-brand-500 rounded-[32px] p-8 text-white shadow-xl shadow-brand-500/10 overflow-hidden relative">
        <div className="relative z-10">
          <h2 className="text-2xl font-bold mb-2 tracking-tight">防护策略</h2>
          <p className="text-brand-50/80 max-w-lg text-sm font-medium">
            Trigger → Match → Action 规则引擎。每条规则定义触发条件、匹配逻辑和响应动作，实时生效。
          </p>
          <div className="flex gap-4 mt-8">
            <button onClick={load}
              className="px-6 py-2.5 bg-white text-brand-600 rounded-full font-bold text-sm hover:bg-brand-50 transition-colors shadow-sm">
              刷新策略状态
            </button>
            <span className="px-4 py-2.5 text-brand-200 text-sm font-medium self-center">
              {rules.filter(r => r.enabled).length}/{rules.length} 条已启用
            </span>
          </div>
        </div>
        <div className="absolute right-0 top-0 bottom-0 w-1/3 opacity-10 pointer-events-none">
          <ShieldCheck size={280} className="-mr-20 -mt-10 text-white" />
        </div>
      </div>

      {rules.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {rules.map((rule, i) => {
            const icon = TRIGGER_ICONS[rule.trigger] ?? Zap;
            const color = TRIGGER_COLORS[rule.trigger] ?? 'slate';
            const cls = colorClasses(color);
            const isToggling = toggling.has(rule.id);

            return (
              <motion.div key={rule.id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.08 }}
                className={`card-elevated rounded-[32px] p-8 relative overflow-hidden ${!rule.enabled ? 'opacity-60' : ''}`}>
                <div className="flex justify-between items-start mb-6">
                  <div className="flex items-center gap-3">
                    <div className={`p-3 rounded-2xl border ${cls.bg} ${cls.text} ${cls.border}`}>
                      {<icon size={20} />}
                    </div>
                    <div>
                      <h4 className="font-bold text-base text-surface-800 dark:text-surface-50">{rule.name}</h4>
                      <p className="text-[10px] font-bold text-surface-400 uppercase tracking-widest">
                        {TRIGGER_LABELS[rule.trigger] ?? rule.trigger}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => toggleRule(rule)}
                    disabled={isToggling}
                    className={`relative w-12 h-7 rounded-full transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] cursor-pointer hover:scale-105 active:scale-95 ${
                      rule.enabled ? 'bg-brand-500 shadow-[0_0_12px_rgba(90,90,64,0.3)]' : 'bg-surface-300'
                    }`}
                  >
                    <motion.div
                      layout
                      transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                      className={`absolute top-1 w-5 h-5 bg-white rounded-full shadow-md ${isToggling ? 'animate-pulse' : ''}`}
                      style={{ left: rule.enabled ? 'calc(100% - 1.375rem)' : '0.25rem' }}
                    />
                  </button>
                </div>

                <p className="text-[14px] text-surface-600 dark:text-surface-400 mb-4 leading-relaxed">
                  {rule.description}
                </p>

                {rule.match.length > 0 && (
                  <div className="mb-3">
                    <p className="text-[10px] font-bold text-surface-400 uppercase tracking-widest mb-2">匹配条件</p>
                    <div className="flex flex-wrap gap-1.5">
                      {rule.match.map((m, j) => (
                        <span key={j} className="px-2 py-0.5 bg-surface-100 dark:bg-surface-800 rounded-md text-[11px] font-mono text-surface-600 dark:text-surface-400">
                          {m.field} {m.operator} {String(m.value)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mb-6">
                  <p className="text-[10px] font-bold text-surface-400 uppercase tracking-widest mb-2">响应动作</p>
                  <div className="flex flex-wrap gap-1.5">
                    {rule.actions.map((a, j) => (
                      <span key={j} className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                        a === 'block' ? 'bg-rose-100 text-rose-700' :
                        a === 'alert' ? 'bg-amber-100 text-amber-700' :
                        a === 'throttle' ? 'bg-orange-100 text-orange-700' : 'bg-slate-100 text-slate-700'
                      }`}>
                        {ACTION_LABELS[a] ?? a}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between pt-6 border-t border-surface-100 dark:border-surface-800">
                  <span className="text-[10px] font-bold text-surface-400 uppercase tracking-widest">状态</span>
                  <span className={`text-xs font-bold ${rule.enabled ? 'text-emerald-600' : 'text-surface-500'}`}>
                    {rule.enabled ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>
      ) : (
        /* Open-source teaser — policies activate when agents register */
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="card-elevated rounded-[32px] p-12 text-center"
        >
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.3 }}
            className="w-20 h-20 bg-brand-50 dark:bg-brand-500/10 rounded-3xl flex items-center justify-center mx-auto mb-6"
          >
            <ShieldCheck size={36} className="text-brand-500" />
          </motion.div>
          <h3 className="text-xl font-bold mb-3 text-surface-800 dark:text-surface-50">策略引擎</h3>
          <p className="text-surface-500 max-w-md mx-auto text-sm leading-relaxed mb-8">
            接入 Agent 并配置预算后，策略引擎将自动根据实时系统状态生成防护规则。
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-xl mx-auto mb-8">
            {[
              { icon: Bell, label: '实时告警', desc: '预算超标、Agent 离线、冲突检测' },
              { icon: Lock, label: '自动阻断', desc: 'Prompt 注入、成本异常、合规违规' },
              { icon: Activity, label: '动态阈值', desc: '基于历史数据自适应调整触发条件' },
            ].map((f, i) => (
              <div key={i} className="p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl">
                <f.icon size={20} className="text-brand-500 mb-2 mx-auto" />
                <p className="font-bold text-sm mb-1">{f.label}</p>
                <p className="text-[11px] text-surface-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-surface-400">
            策略规则由系统实时状态动态生成，非硬编码。接入 Agent 即可看到实际策略。
          </p>
        </motion.div>
      )}

      {/* Budget status summary */}
      {budget && (
        <div className="card-elevated rounded-[32px] p-6 text-sm text-surface-500">
          当前预算: ${budget.total_cost?.toFixed(2) ?? '0'} / ${budget.limit_usd}
          ({budget.usage_pct?.toFixed(0) ?? '0'}%)
          {budget.auto_block ? ' · 自动熔断已启用' : ' · 自动熔断未启用'}
          {budget.near_limit ? ' · ⚠ 接近预算上限' : ''}
        </div>
      )}
    </div>
  );
}
