import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Play, Pause, SkipBack, SkipForward, Clock, Cpu, AlertTriangle, CheckCircle, XCircle, Zap, ChevronDown, type LucideIcon } from 'lucide-react';
const BASE = '/api';

async function apiRequest<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

interface AuditEvent {
  index: number;
  timestamp: string;
  event_type: string;
  agent_name: string;
  details: Record<string, any>;
  session_id: string;
  hash: string;
}

interface Session {
  session_id: string;
  event_count: number;
  start_time: string;
  end_time: string;
  agents: string[];
}

const EVENT_COLORS: Record<string, string> = {
  PIPELINE_START: 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
  PIPELINE_COMPLETE: 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
  AGENT_START: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  AGENT_COMPLETE: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  AGENT_ERROR: 'bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400',
  CONFLICT_DETECTED: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  HUMAN_REVIEW: 'bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400',
  BUDGET_WARNING: 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400',
  TOOL_CALL: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-400',
  GOVERNOR_LOG: 'bg-slate-100 text-slate-700 dark:bg-slate-500/10 dark:text-slate-400',
};

const EVENT_ICONS: Record<string, LucideIcon> = {
  PIPELINE_START: Zap,
  PIPELINE_COMPLETE: CheckCircle,
  AGENT_START: Play,
  AGENT_COMPLETE: CheckCircle,
  AGENT_ERROR: XCircle,
  CONFLICT_DETECTED: AlertTriangle,
  HUMAN_REVIEW: Clock,
  BUDGET_WARNING: AlertTriangle,
  TOOL_CALL: Cpu,
};

const SPEEDS = [0.5, 1, 2, 5];

export function RunReplay() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [agentFilter, setAgentFilter] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    apiRequest<Session[]>('/audit/sessions').then(setSessions).catch(() => {});
  }, []);

  const loadEvents = useCallback(async (sid: string) => {
    setLoading(true);
    try {
      const data = await apiRequest<{ events: AuditEvent[] }>(`/audit/replay?session_id=${encodeURIComponent(sid)}`);
      setEvents(data.events);
      setCurrentIndex(0);
      setPlaying(false);
    } catch { /* noop */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (sessions.length > 0 && !sessionId) {
      const sid = sessions[0].session_id;
      setSessionId(sid);
      loadEvents(sid);
    }
  }, [sessions]);

  const agents = [...new Set(events.map(e => e.agent_name))].sort();

  const filtered = agentFilter.length > 0
    ? events.filter(e => agentFilter.includes(e.agent_name))
    : events;

  const visibleEvents = filtered.slice(0, currentIndex + 1);
  const currentEvent = filtered[currentIndex];

  // Auto-play
  useEffect(() => {
    if (playing && currentIndex < filtered.length - 1) {
      const interval = 1000 / speed;
      timerRef.current = setInterval(() => {
        setCurrentIndex(i => Math.min(i + 1, filtered.length - 1));
      }, interval);
      return () => { if (timerRef.current) clearInterval(timerRef.current); };
    } else {
      setPlaying(false);
    }
  }, [playing, currentIndex, filtered.length, speed]);

  const handlePlayPause = () => {
    if (currentIndex >= filtered.length - 1) {
      setCurrentIndex(0);
      setPlaying(true);
    } else {
      setPlaying(!playing);
    }
  };

  const handleStep = (dir: 1 | -1) => {
    setPlaying(false);
    setCurrentIndex(i => Math.max(0, Math.min(filtered.length - 1, i + dir)));
  };

  const formatTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return ts;
    }
  };

  const formatEventType = (t: string) => t.replace(/_/g, ' ').toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());

  const progress = filtered.length > 0 ? (currentIndex / (filtered.length - 1)) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Session selector */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-xs">
          <select
            value={sessionId}
            onChange={e => { setSessionId(e.target.value); loadEvents(e.target.value); }}
            className="w-full px-4 py-2.5 bg-surface-50 dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-xl text-sm font-medium outline-none focus:ring-2 focus:ring-brand-500 appearance-none"
          >
            {sessions.map(s => (
              <option key={s.session_id} value={s.session_id}>
                {s.session_id} ({s.event_count} events)
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 pointer-events-none" />
        </div>
        {loading && <span className="text-xs text-surface-400">Loading...</span>}
      </div>

      {/* Agent filter */}
      {agents.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {agents.map(a => (
            <button
              key={a}
              onClick={() => setAgentFilter(prev => prev.includes(a) ? prev.filter(x => x !== a) : [...prev, a])}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                agentFilter.includes(a)
                  ? 'bg-brand-500 text-white shadow-sm'
                  : 'bg-surface-100 dark:bg-surface-800 text-surface-500 hover:text-surface-700'
              }`}
            >
              {a}
            </button>
          ))}
          {agentFilter.length > 0 && (
            <button onClick={() => setAgentFilter([])} className="px-2 py-1.5 text-xs text-surface-400 hover:text-surface-600">
              Clear
            </button>
          )}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-4 p-4 bg-surface-50 dark:bg-surface-800 rounded-2xl">
        <button onClick={() => handleStep(-1)} disabled={currentIndex === 0}
          className="p-2 rounded-xl hover:bg-surface-200 dark:hover:bg-surface-700 disabled:opacity-30 transition-colors">
          <SkipBack size={18} />
        </button>
        <button onClick={handlePlayPause}
          className="p-3 rounded-xl bg-brand-500 text-white hover:bg-brand-600 shadow-lg shadow-brand-500/20 transition-all">
          {playing ? <Pause size={18} /> : <Play size={18} />}
        </button>
        <button onClick={() => handleStep(1)} disabled={currentIndex >= filtered.length - 1}
          className="p-2 rounded-xl hover:bg-surface-200 dark:hover:bg-surface-700 disabled:opacity-30 transition-colors">
          <SkipForward size={18} />
        </button>

        {/* Speed selector */}
        <div className="flex items-center gap-1 ml-4">
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                speed === s
                  ? 'bg-brand-100 dark:bg-brand-500/10 text-brand-600'
                  : 'text-surface-400 hover:text-surface-600'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        <div className="ml-auto text-sm font-mono text-surface-500">
          {currentIndex + 1} / {filtered.length}
        </div>
      </div>

      {/* Timeline scrubber */}
      <div className="relative">
        <input
          type="range"
          min={0}
          max={Math.max(0, filtered.length - 1)}
          value={currentIndex}
          onChange={e => { setPlaying(false); setCurrentIndex(Number(e.target.value)); }}
          className="w-full h-2 bg-surface-200 dark:bg-surface-700 rounded-full appearance-none cursor-pointer accent-brand-500"
          style={{
            background: `linear-gradient(to right, var(--color-brand-500, #6366f1) 0%, var(--color-brand-500, #6366f1) ${progress}%, transparent ${progress}%, transparent 100%)`,
          }}
        />
        {currentEvent && (
          <div className="absolute -top-8 left-0 text-xs text-surface-400 font-mono"
               style={{ left: `calc(${progress}% - 30px)` }}>
            {formatTime(currentEvent.timestamp)}
          </div>
        )}
      </div>

      {/* Event list */}
      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
        <AnimatePresence>
          {visibleEvents.map((evt, i) => {
            const isLatest = i === currentIndex;
            const Icon = EVENT_ICONS[evt.event_type] || Clock;
            const colorClass = EVENT_COLORS[evt.event_type] || 'bg-slate-100 text-slate-700 dark:bg-slate-500/10 dark:text-slate-400';

            return (
              <motion.div
                key={evt.index}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
                className={`flex items-start gap-3 p-3 rounded-xl transition-all ${
                  isLatest ? 'bg-brand-50 dark:bg-brand-500/5 border border-brand-200 dark:border-brand-500/20' : 'bg-white dark:bg-surface-900'
                }`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${colorClass}`}>
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-surface-700 dark:text-surface-300">
                      {formatEventType(evt.event_type)}
                    </span>
                    <span className="text-[10px] text-surface-400 font-mono">
                      {formatTime(evt.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm text-surface-500 mt-0.5">
                    <span className="font-semibold text-surface-600 dark:text-surface-400">{evt.agent_name}</span>
                    {evt.details?.task && <> — {evt.details.task}</>}
                    {evt.details?.pipeline && <> — {evt.details.pipeline}</>}
                    {evt.details?.error && <> — <span className="text-rose-500">{evt.details.error}</span></>}
                    {evt.details?.duration_ms && (
                      <> · <span className="text-surface-400">{evt.details.duration_ms}ms</span></>
                    )}
                  </p>
                  {evt.details?.model && (
                    <span className="inline-block mt-1 px-1.5 py-0.5 bg-surface-100 dark:bg-surface-800 rounded text-[10px] font-mono text-surface-400">
                      {evt.details.model}
                    </span>
                  )}
                </div>
                {isLatest && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="w-2 h-2 rounded-full bg-brand-500 shrink-0 mt-3"
                  />
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
        {visibleEvents.length === 0 && !loading && (
          <div className="text-center py-12 text-surface-400 text-sm">
            No events to replay. Seed demo data or connect an agent.
          </div>
        )}
      </div>
    </div>
  );
}
