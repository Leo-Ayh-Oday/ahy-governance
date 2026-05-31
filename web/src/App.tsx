import { AppProvider, useApp } from './context/AppContext';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { Dashboard } from './components/dashboard/Overview';
import { AgentRegistry } from './components/agents/AgentRegistry';
import { PolicyControl } from './components/policy/PolicyControl';
import { Observability } from './components/observability/ObservabilityConsole';
import { RunReplay } from './components/observability/RunReplay';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { LandingPage } from './components/landing/LandingPage';
import { motion, AnimatePresence } from 'motion/react';

function ViewRenderer() {
  const { currentView } = useApp();

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={currentView}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className="w-full"
      >
        {currentView === 'dashboard' && <Dashboard />}
        {currentView === 'registry' && <AgentRegistry />}
        {currentView === 'policies' && <PolicyControl />}
        {currentView === 'observability' && <Observability />}
        {currentView === 'replay' && <RunReplay />}
        {currentView === 'settings' && <SettingsPanel />}
      </motion.div>
    </AnimatePresence>
  );
}

function DashboardLayout() {
  return (
    <AppProvider>
      <div className="flex min-h-screen bg-surface-50 dark:bg-surface-950">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <main className="flex-1 overflow-y-auto p-8 content-wrap">
            <div className="max-w-7xl mx-auto">
              <ViewRenderer />
            </div>
          </main>
        </div>
      </div>
    </AppProvider>
  );
}

export default function App() {
  const isDashboard = window.location.pathname.startsWith('/app');

  if (isDashboard) {
    return <DashboardLayout />;
  }

  return <LandingPage />;
}
