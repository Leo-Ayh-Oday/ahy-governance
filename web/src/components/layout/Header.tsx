import { motion } from 'motion/react';
import { 
  Bell, 
  Moon, 
  Sun, 
  HelpCircle,
  Command,
  Search
} from 'lucide-react';
import { useApp } from '../../context/AppContext';

export function Header() {
  const { currentView } = useApp();

  return (
    <header className="glass sticky top-0 z-10 px-8 py-5 flex items-center justify-between border-b border-surface-200 dark:border-surface-800">
      <div className="flex items-center gap-8 flex-1">
        <div>
          <h2 className="font-bold text-xl tracking-tight text-surface-800 dark:text-surface-50">
            {currentView.charAt(0).toUpperCase() + currentView.slice(1)}
          </h2>
          <p className="text-xs text-surface-500 font-medium hidden md:block">正在管理 4 个区域的 12 个活跃服务</p>
        </div>
        
        <div className="relative group max-w-md w-full ml-4">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 group-focus-within:text-brand-500 transition-colors" size={16} />
          <input 
            type="text" 
            placeholder="搜索智能体..."
            className="w-full pl-11 pr-16 py-2.5 bg-surface-100 dark:bg-surface-900 border-none rounded-full text-sm focus:ring-2 focus:ring-brand-500/20 outline-none transition-all placeholder:text-surface-400"
          />
          <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-2 py-1 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-lg shadow-sm pointer-events-none">
            <Command size={10} className="text-surface-400" />
            <span className="text-[10px] font-bold text-surface-500">K</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button className="p-2.5 text-surface-500 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-900 rounded-xl relative">
          <Bell size={20} />
          <span className="absolute top-2.5 right-2.5 w-2 h-2 bg-rose-500 border-2 border-surface-50 dark:border-surface-950 rounded-full" />
        </button>
        <div className="w-[1px] h-6 bg-surface-200 dark:bg-surface-800 mx-1" />
        <div className="flex items-center gap-3 pl-2 group cursor-pointer">
          <div className="w-10 h-10 rounded-full bg-brand-100 dark:bg-surface-800 overflow-hidden border-2 border-white dark:border-surface-700 shadow-sm">
            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=Leo" alt="Avatar" />
          </div>
        </div>
      </div>
    </header>
  );
}
