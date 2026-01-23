import React from 'react';
import { TABS, APP_TITLE } from '../constants';
import EventLogPanel from './EventLogPanel';
import OmniHubTab from './OmniHubTab';
import SecurityTab from './SecurityTab';
import { OmniHubProvider, useOmniHub } from '../context/OmniHubContext';
import { Network, Settings, UserCircle, ShieldCheck, Loader2, AlertCircle, X } from 'lucide-react';
import { Role } from '../types';

const GlobalLoader = () => (
    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-[100] flex flex-col items-center justify-center animate-in fade-in duration-300">
        <Loader2 size={48} className="text-indigo-500 animate-spin" />
        <span className="mt-4 text-sm font-bold text-slate-300 tracking-widest animate-pulse">PROCESSING...</span>
    </div>
);

const ErrorModal = ({ message, onClose }: { message: string, onClose: () => void }) => (
    <div className="absolute inset-0 bg-black/80 backdrop-blur-md z-[110] flex items-center justify-center animate-in fade-in zoom-in-95 duration-200 p-6">
        <div className="bg-[#1E1F2E] border border-red-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl relative">
            <button onClick={onClose} className="absolute top-4 right-4 text-slate-500 hover:text-white transition-colors">
                <X size={20} />
            </button>
            <div className="flex items-start gap-4">
                <div className="p-3 bg-red-500/10 rounded-full shrink-0">
                    <AlertCircle size={24} className="text-red-500" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-white mb-2">System Error</h3>
                    <p className="text-sm text-slate-300 leading-relaxed mb-4">{message}</p>
                    <button 
                        onClick={onClose}
                        className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-bold shadow-lg shadow-red-900/20 transition-all active:scale-95"
                    >
                        Dismiss
                    </button>
                </div>
            </div>
        </div>
    </div>
);

const MainLayout: React.FC = () => {
  const { 
    activeTab, setActiveTab, 
    currentRole, setCurrentRole, 
    addLog, isDataReady, logs,
    isGlobalLoading, globalError, dismissError
  } = useOmniHub();

  const handleRoleChange = (newRole: Role) => {
    setCurrentRole(newRole);
    addLog(`권한 변경됨 -> ${newRole}`, 'INFO', 'SYSTEM', newRole);
  };

  if (!isDataReady) {
    return (
      <div className="h-screen bg-[#09090b] flex flex-col items-center justify-center text-slate-400 gap-4">
         <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
         <span className="font-mono text-sm tracking-widest uppercase">System Initializing...</span>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[#09090b] text-slate-200 overflow-hidden font-sans selection:bg-indigo-500/30 selection:text-indigo-200 relative">
      
      {isGlobalLoading && <GlobalLoader />}
      {globalError && <ErrorModal message={globalError} onClose={dismissError} />}

      {/* --- Top Navigation Bar --- */}
      <header className="h-16 flex items-center px-6 justify-between shrink-0 z-30 border-b border-white/5 bg-[#09090b]/80 backdrop-blur-md">
        <div className="flex items-center gap-8">
          {/* Logo Area */}
          <div className="flex items-center gap-3 group cursor-default">
            <div className="w-8 h-8 bg-gradient-to-tr from-indigo-600 to-violet-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:shadow-indigo-500/40 transition-shadow">
               <Network size={18} className="text-white" />
            </div>
            <div>
                <h1 className="text-lg font-bold tracking-tight text-white leading-none">{APP_TITLE}</h1>
                <span className="text-[10px] text-slate-500 font-medium tracking-wider uppercase">Prototype v1.0</span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-white/5 p-1 rounded-xl border border-white/5">
            <button
              onClick={() => setActiveTab(TABS.OMNIHUB)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
                activeTab === TABS.OMNIHUB 
                  ? 'bg-[#1E1F2E] text-white shadow-inner shadow-black/50 border border-white/5' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <Network size={16} className={activeTab === TABS.OMNIHUB ? "text-indigo-400" : ""} />
              옴니허브
            </button>
            <button
              onClick={() => setActiveTab(TABS.SECURITY)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
                activeTab === TABS.SECURITY 
                  ? 'bg-[#1E1F2E] text-white shadow-inner shadow-black/50 border border-white/5' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <ShieldCheck size={16} className={activeTab === TABS.SECURITY ? "text-emerald-400" : ""} />
              보안 대시보드
            </button>
          </nav>
        </div>

        {/* User Role & Settings */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 pl-4 pr-2 py-1.5 rounded-full border border-white/10 bg-white/5 hover:border-white/20 transition-colors">
            <div className={`w-2 h-2 rounded-full animate-pulse ${currentRole === 'admin' ? 'bg-indigo-500' : 'bg-slate-500'}`}></div>
            <select
              value={currentRole}
              onChange={(e) => handleRoleChange(e.target.value as Role)}
              className="bg-transparent text-sm text-slate-200 focus:outline-none cursor-pointer font-medium min-w-[100px]"
            >
              <option value="admin">Admin</option>
              <option value="manager">Manager</option>
              <option value="viewer">Viewer</option>
            </select>
            <div className="w-7 h-7 bg-slate-700 rounded-full flex items-center justify-center text-slate-300">
                <UserCircle size={16} />
            </div>
          </div>
          <button className="p-2 text-slate-500 hover:text-slate-300 hover:bg-white/5 rounded-full transition-colors">
            <Settings size={20} />
          </button>
        </div>
      </header>

      {/* --- Main Content Area --- */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/20 via-[#09090b] to-[#09090b] pointer-events-none z-0"></div>
        <div className="relative z-10 flex-1 flex flex-col overflow-hidden">
            {activeTab === TABS.OMNIHUB && (
                <OmniHubTab />
            )}
            {activeTab === TABS.SECURITY && (
                <SecurityTab />
            )}
        </div>
      </main>

      {/* --- Persistent Event Log Panel --- */}
      <EventLogPanel logs={logs} />
    </div>
  );
};

const App: React.FC = () => {
    return (
        <OmniHubProvider>
            <MainLayout />
        </OmniHubProvider>
    );
};

export default App;