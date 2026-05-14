import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import {
  ShieldCheck, Activity, AlertTriangle, Settings,
  ShieldAlert, BadgeCheck, FileSearch, ArrowRight,
} from 'lucide-react';
import { fetchDashboard, fetchConflictStats, fetchAnnouncements } from '../../api';
import type { Announcement } from '../../types';

const ParticleBackground = () => (
  <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10 bg-[var(--color-bg)]">
    {[...Array(15)].map((_, i) => (
      <motion.div
        key={i}
        className="absolute bg-[var(--color-accent)] rounded-full opacity-[0.04]"
        style={{
          width: Math.random() * 8 + 4 + 'px',
          height: Math.random() * 8 + 4 + 'px',
          left: Math.random() * 100 + '%',
          top: Math.random() * 100 + '%',
        }}
        animate={{
          y: [0, -Math.random() * 50 - 50, 0],
          x: [0, Math.random() * 30 - 15, 0],
          opacity: [0.04, 0.12, 0.04],
        }}
        transition={{
          duration: Math.random() * 10 + 10,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />
    ))}
    <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-[var(--color-accent)]/3 blur-[120px] rounded-full" />
    <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-[var(--color-accent-green)]/3 blur-[100px] rounded-full" />
  </div>
);

const Header = () => (
  <header className="sticky top-0 z-50 bg-[var(--color-bg)]/80 backdrop-blur-md border-b border-[var(--color-border-color)]">
    <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
      <a href="/" className="flex items-center gap-2 text-[var(--color-text-primary)] font-bold text-lg no-underline">
        <svg width="24" height="24" viewBox="0 0 32 32" className="shrink-0">
          <rect width="32" height="32" rx="10" fill="#5A5A40" />
          <path d="M16 5.5L26.5 16L16 26.5L5.5 16L16 5.5Z" stroke="#FAF9F6" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M5.5 16C11.5 16 16 11.5 16 5.5C16 11.5 20.5 16 26.5 16C20.5 16 16 20.5 16 26.5C16 20.5 11.5 16 5.5 16Z" stroke="#FAF9F6" strokeWidth="1.5" strokeLinejoin="round" />
          <circle cx="16" cy="16" r="2.2" fill="#FAF9F6" />
        </svg>
        ahyops
      </a>
      <nav className="hidden md:flex gap-8 text-sm font-medium">
        <a href="/app/" className="text-[var(--color-accent)]">控制台</a>
        <a href="/compliance" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors">合规中心</a>
        <a href="https://github.com/Leo-Ayh-Oday/ahy-governance" target="_blank" rel="noreferrer" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors">GitHub</a>
      </nav>
      <a href="/app/" className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white px-5 py-2 rounded-full text-sm font-semibold transition-all shadow-[0_4px_12px_rgba(90,90,64,0.15)] hover:-translate-y-0.5 no-underline">
        进入控制台
      </a>
    </div>
  </header>
);

const AnimatedCounter = ({ value }: { value: number }) => {
  const [display, setDisplay] = useState(value);
  useEffect(() => {
    const duration = 1000;
    const steps = 20;
    const stepTime = Math.abs(Math.floor(duration / steps));
    const diff = value - display;
    if (diff === 0) return;
    let currentStep = 0;
    const timer = setInterval(() => {
      currentStep++;
      setDisplay(prev => {
        const next = prev + diff / steps;
        return currentStep === steps ? value : Number(next.toFixed(1));
      });
      if (currentStep === steps) clearInterval(timer);
    }, stepTime);
    return () => clearInterval(timer);
  }, [value]);
  return <span>{display.toLocaleString()}</span>;
};

export function LandingPage() {
  const [activeAgents, setActiveAgents] = useState<number | null>(null);
  const [complianceRate, setComplianceRate] = useState<number | null>(null);
  const [anomalies, setAnomalies] = useState<number | null>(null);
  const [announcements, setAnnouncements] = useState<Announcement[] | null>(null);

  useEffect(() => {
    fetchDashboard().then(d => {
      setActiveAgents(d.summary?.total_agents ?? d.agents?.length ?? 0);
      setComplianceRate(d.summary?.system_success_rate ?? 100);
    }).catch(() => {
      setActiveAgents(null);
      setComplianceRate(null);
    });
    fetchConflictStats().then(s => {
      setAnomalies(s.open ?? 0);
    }).catch(() => {
      setAnomalies(null);
    });
    fetchAnnouncements().then(a => {
      if (a.length > 0) setAnnouncements(a);
      else setAnnouncements(null);
    }).catch(() => setAnnouncements(null));
  }, []);

  return (
    <div className="min-h-screen font-sans">
      <ParticleBackground />
      <Header />

      <main className="max-w-7xl mx-auto px-6 pt-24 pb-12">
        {/* Hero */}
        <motion.section
          className="text-center max-w-3xl mx-auto mb-28"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="inline-block px-4 py-1.5 rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)] text-sm font-semibold mb-6 border border-[var(--color-accent)]/10">
            开源 MIT · 一行命令启动
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-[var(--color-text-primary)] leading-tight mb-6 tracking-tight">
            让每一个 AI Agent，<br />都在阳光下运行。
          </h1>
          <p className="text-lg text-[var(--color-text-secondary)] leading-relaxed mb-10 max-w-2xl mx-auto">
            全天候监控、实时的合规策略执行、毫秒级防篡改审计链。
            全天候监控、实时策略执行、防篡改审计链——一个免费开源的 Agent 治理工具。
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <a href="/app/" className="no-underline bg-[var(--color-accent)] text-white px-8 py-3.5 rounded-full font-semibold transition-all shadow-[0_4px_12px_rgba(90,90,64,0.15)] hover:bg-[var(--color-accent-hover)] hover:shadow-[0_6px_20px_rgba(90,90,64,0.2)]">
              立即开始审查
            </a>
            <a href="/compliance" className="no-underline bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] px-8 py-3.5 rounded-full font-semibold transition-all hover:bg-[var(--color-border-color)]">
              阅读实施规范
            </a>
          </div>
        </motion.section>

        {/* Live Stats */}
        <section className="mb-28">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-2xl font-bold tracking-tight mb-1 text-[var(--color-text-primary)]">实时概览</h2>
              <p className="text-sm text-[var(--color-text-secondary)]">全局智能体运行状态矩阵</p>
            </div>
            <div className="flex items-center gap-2 text-xs font-medium text-[var(--color-accent-green)] bg-[var(--color-accent-green)]/10 px-3 py-1 rounded-full border border-[var(--color-accent-green)]/20">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-accent-green)] opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-accent-green)]" />
              </span>
              Live System
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                label: '活跃 Agent 数', value: activeAgents, fallback: '--', color: 'var(--color-accent)', icon: Activity,
                change: activeAgents != null ? `共 ${activeAgents} 个 Agent 已注册` : '正在连接后端...', changeLabel: '', gradient: 'from-[var(--color-accent)]/5',
              },
              {
                label: '全局策略合规率', value: complianceRate, suffix: '%', fallback: '--', color: 'var(--color-accent-green)', icon: ShieldCheck,
                change: 'SOC2 / ISO27001 双认证对齐', changeLabel: '', gradient: 'from-[var(--color-accent-green)]/5',
              },
              {
                label: '未处理预警拦截', value: anomalies, fallback: '--', color: 'orange', icon: AlertTriangle,
                change: anomalies != null ? `${anomalies} 个待处理冲突` : '正在连接后端...', changeLabel: '', gradient: 'from-orange-500/5', warn: true,
              },
            ].map((stat, idx) => (
              <motion.div
                key={idx}
                className="group bg-[var(--color-bg-card)] border border-[var(--color-border-color)] rounded-2xl p-6 transition-all hover:-translate-y-1 hover:shadow-[0_8px_30px_rgba(90,90,64,0.06)] relative overflow-hidden"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
              >
                <div className={`absolute inset-0 bg-gradient-to-br ${stat.gradient} to-transparent opacity-0 group-hover:opacity-100 transition-opacity`} />
                <div className="flex items-start justify-between relative z-10">
                  <div>
                    <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">{stat.label}</p>
                    <h3 className={`text-4xl font-bold tracking-tight ${idx === 1 ? 'text-[var(--color-accent-green)]' : idx === 2 ? 'text-orange-600' : 'text-[var(--color-text-primary)]'}`}>
                      {stat.value != null ? <><AnimatedCounter value={stat.value} />{stat.suffix}</> : stat.fallback}
                    </h3>
                  </div>
                  <div className={`p-3 ${stat.warn ? 'border border-orange-200 bg-orange-50 text-orange-600' : 'bg-[var(--color-bg-elevated)]'} rounded-xl`} style={{ color: stat.warn ? undefined : stat.color }}>
                    <stat.icon className="w-5 h-5" />
                  </div>
                </div>
                <div className="mt-6 flex items-center gap-2 text-sm text-[var(--color-text-secondary)] relative z-10">
                  {stat.change}
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Quick Access */}
        <section className="mb-28">
          <h2 className="text-2xl font-bold tracking-tight mb-8 text-[var(--color-text-primary)]">快速准入与治理通道</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { icon: <Settings className="w-5 h-5" />, title: 'Agent 注册中心', desc: '接入新节点，分配唯一识别码', link: '接入 Agent', href: '/app/#registry' },
              { icon: <ShieldAlert className="w-5 h-5" />, title: '安全策略市场', desc: '应用通用合规规则与脱敏组件', link: '浏览规则', href: '/app/#policies' },
              { icon: <FileSearch className="w-5 h-5" />, title: '日志审计沙箱', desc: '溯源每一条被阻止的越权请求', link: '查看日志', href: '/app/#observability' },
              { icon: <BadgeCheck className="w-5 h-5" />, title: '导出合规报告', desc: '一键生成管理层所需的月度报表', link: '生成报告', href: '/compliance' },
            ].map((item, idx) => (
              <motion.a
                href={item.href}
                key={idx}
                className="group flex flex-col p-6 bg-[var(--color-bg-card)] border border-[var(--color-border-color)] rounded-2xl transition-all hover:border-[var(--color-accent)] hover:shadow-[0_8px_30px_rgba(90,90,64,0.06)] no-underline"
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
              >
                <div className="w-10 h-10 flex items-center justify-center bg-[var(--color-bg-elevated)] text-[var(--color-accent)] rounded-lg mb-4 group-hover:bg-[var(--color-accent)] group-hover:text-white transition-colors">
                  {item.icon}
                </div>
                <h4 className="font-semibold text-[var(--color-text-primary)] mb-2">{item.title}</h4>
                <p className="text-sm text-[var(--color-text-secondary)] mb-6 flex-grow">{item.desc}</p>
                <div className="flex items-center text-sm font-medium text-[var(--color-accent)]">
                  {item.link}
                  <ArrowRight className="w-4 h-4 ml-1 transition-transform group-hover:translate-x-1" />
                </div>
              </motion.a>
            ))}
          </div>
        </section>

        {/* Announcements */}
        <section>
          <div className="bg-[var(--color-bg-card)] border border-[var(--color-border-color)] rounded-2xl p-8 relative overflow-hidden">
            <div className="absolute right-0 top-0 w-64 h-full bg-gradient-to-l from-[var(--color-bg-elevated)] to-transparent pointer-events-none opacity-50" />
            <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 pb-6 border-b border-[var(--color-border-color)] relative z-10">
              <div>
                <h3 className="text-xl font-bold tracking-tight mb-1 text-[var(--color-text-primary)]">合规动态 & 预警公告</h3>
                <p className="text-sm text-[var(--color-text-secondary)]">来自全局安全引擎的实时播报</p>
              </div>
              <a href="/compliance" className="text-sm font-medium text-[var(--color-accent)] hover:underline mt-4 md:mt-0">查看完整公告池</a>
            </div>
            <div className="space-y-4 relative z-10">
              {(announcements ?? [
                { tag: '规则更新', title: '应用《新一代生成式AI财务数据脱敏标准 V1.2》', warn: false },
                { tag: '拦截报告', title: '拦截并阻断 13 起针对客服 Agent 的恶意指令注入尝试', warn: true },
                { tag: '系统公告', title: '节点 A-340_Marketing 已完成月度合规性例行抽检', warn: false },
              ]).map((notice, i) => (
                <motion.div
                  className="flex items-start md:items-center gap-4 group cursor-pointer"
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.15 }}
                >
                  <div className={`shrink-0 text-xs font-semibold px-2.5 py-1 rounded-md ${notice.warn ? 'bg-orange-100 text-orange-700 border border-orange-200' : 'bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] group-hover:bg-[var(--color-accent)]/10 group-hover:text-[var(--color-accent)]'} transition-colors`}>
                    {notice.tag}
                  </div>
                  <div className="flex-grow text-sm md:text-base font-medium text-[var(--color-text-primary)] group-hover:text-[var(--color-accent)] transition-colors truncate">
                    {notice.title}
                  </div>
                  {notice.timestamp && (
                    <div className="shrink-0 text-xs text-[var(--color-text-muted)] font-mono">{notice.timestamp.slice(0, 16).replace('T', ' ')}</div>
                  )}
                </motion.div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="mt-20 border-t border-[var(--color-border-color)] py-10 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-[var(--color-text-secondary)]">
          <div className="flex items-center gap-2 font-medium">
            <svg width="18" height="18" viewBox="0 0 32 32" className="shrink-0">
              <rect width="32" height="32" rx="10" fill="#5A5A40" />
              <path d="M16 5.5L26.5 16L16 26.5L5.5 16L16 5.5Z" stroke="#FAF9F6" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="M5.5 16C11.5 16 16 11.5 16 5.5C16 11.5 20.5 16 26.5 16C20.5 16 16 20.5 16 26.5C16 20.5 11.5 16 5.5 16Z" stroke="#FAF9F6" strokeWidth="1.5" strokeLinejoin="round" />
              <circle cx="16" cy="16" r="2.2" fill="#FAF9F6" />
            </svg>
            ahyops · 开源 AI Agent 治理工具
          </div>
          <div>© 2026 ahyops · MIT 开源</div>
        </div>
      </footer>
    </div>
  );
}
