import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

type View = 'dashboard' | 'registry' | 'policies' | 'observability' | 'replay' | 'settings';

const VIEWS: View[] = ['dashboard', 'registry', 'policies', 'observability', 'replay', 'settings'];

function viewFromHash(): View | null {
  const raw = window.location.hash.replace('#', '');
  return VIEWS.includes(raw as View) ? (raw as View) : null;
}

interface AppContextType {
  currentView: View;
  setCurrentView: (view: View) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [currentView, setCurrentView] = useState<View>(() => viewFromHash() ?? 'dashboard');

  useEffect(() => {
    const onHashChange = () => {
      const v = viewFromHash();
      if (v) setCurrentView(v);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = (view: View) => {
    window.location.hash = view;
    setCurrentView(view);
  };

  return (
    <AppContext.Provider value={{ currentView, setCurrentView: navigate }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used within AppProvider');
  return context;
}
