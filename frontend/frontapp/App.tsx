import React from 'react';
import { TABS, APP_TITLE } from './constants';
import EventLogPanel from './components/EventLogPanel';
import OmniHubTab from './components/OmniHubTab';
import SecurityTab from './components/SecurityTab';
import DriveSyncPanel from './components/DriveSyncPanel';
import { OmniHubProvider, useOmniHub } from './context/OmniHubContext';
import { Network, Settings, UserCircle, ShieldCheck, Loader2, AlertCircle, X, LogOut } from 'lucide-react';
import { Role } from './types';
import AdminUserManagement from './components/AdminUserManagement'; // New Component
import ErrorBoundary from './components/ErrorBoundary';

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
    isGlobalLoading, globalError, dismissError,
    isAuthenticated, logout,
    userProfile, isAdmin, refreshUserProfile
  } = useOmniHub();

  const [showAdminPanel, setShowAdminPanel] = React.useState(false);

  // Force default tab to CONNECT if no token
  // [DEV BYPASS] Temporarily disabled to allow access to OmniHub tab for UI development
  // Auto-Redirect to OmniHub on Login
  // Force default tab to CONNECT if no token
  // [DEV BYPASS] Temporarily disabled to allow access to OmniHub tab for UI development
  // Auto-Redirect logic moved to OmniHubContext.login() to allow manual access to Connect tab later.

  /* Role change simulation logic removed */

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
      {showAdminPanel && <AdminUserManagement onClose={() => setShowAdminPanel(false)} />}

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
              onClick={() => setActiveTab(TABS.CONNECT)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${activeTab === TABS.CONNECT
                ? 'bg-[#1E1F2E] text-white shadow-inner shadow-black/50 border border-white/5'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                }`}
            >
              <div className={`w-2 h-2 rounded-full ${activeTab === TABS.CONNECT ? 'bg-indigo-500 animate-pulse' : 'bg-slate-600'}`}></div>
              데이터 연동
            </button>
            <div className="w-px h-6 bg-white/10 mx-2"></div>

            <button
              onClick={() => setActiveTab(TABS.OMNIHUB)}
              disabled={!isAuthenticated}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${activeTab === TABS.OMNIHUB
                ? 'bg-[#1E1F2E] text-white shadow-inner shadow-black/50 border border-white/5'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed'
                }`}
            >
              <Network size={16} className={activeTab === TABS.OMNIHUB ? "text-indigo-400" : ""} />
              옴니허브
            </button>
            <button
              onClick={() => setActiveTab(TABS.SECURITY)}
              disabled={!isAuthenticated}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${activeTab === TABS.SECURITY
                ? 'bg-[#1E1F2E] text-white shadow-inner shadow-black/50 border border-white/5'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed'
                }`}
            >
              <ShieldCheck size={16} className={activeTab === TABS.SECURITY ? "text-emerald-400" : ""} />
              보안 대시보드
            </button>
          </nav>
        </div>

        {/* User Role & Settings */}
        <div className="flex items-center gap-4">
          {userProfile ? (
            <div className="flex items-center gap-3 pl-1 pr-3 py-1 bg-white/5 border border-white/10 rounded-full hover:bg-white/10 transition-colors">
              <div className="w-8 h-8 rounded-full bg-indigo-500 overflow-hidden shrink-0 border border-white/20">
                {userProfile.photoUrl ? (
                  <img src={userProfile.photoUrl} alt="User" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white"><UserCircle size={20} /></div>
                )}
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-white leading-tight">{userProfile.displayName}</span>
                <span className="text-[10px] text-indigo-300 font-medium tracking-wide uppercase">{userProfile.role}</span>
              </div>
            </div>
          ) : (
            <div className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-slate-400">
              Not Logged In
            </div>
          )}

          {isAdmin && (
            <button
              onClick={() => setShowAdminPanel(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-lg shadow-lg shadow-indigo-500/20 transition-all active:scale-95"
            >
              <Network size={14} />
              Admin Panel
            </button>
          )}

          <div className="relative group z-50">
            <button className="p-2 text-slate-500 hover:text-slate-300 hover:bg-white/5 rounded-full transition-colors">
              <Settings size={20} />
            </button>
            {/* Settings Dropdown - Added pt-2 as invisible bridge to prevent mouseleave */}
            <div className="absolute right-0 top-full w-48 pt-2 hidden group-hover:block hover:block animate-in fade-in slide-in-from-top-2">
              <div className="bg-[#1E1F2E] border border-white/10 rounded-xl shadow-2xl p-2">
                <div className="text-[10px] text-slate-500 font-bold px-3 py-2 uppercase tracking-wider">Settings</div>
                <button
                  disabled
                  className="w-full text-left px-3 py-2 rounded-lg text-slate-400 text-sm hover:bg-white/5 disabled:opacity-50"
                >
                  Theme (Dark)
                </button>
                <div className="h-px bg-white/5 my-1"></div>
                {isAuthenticated && (
                  <button
                    onClick={logout}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-red-400 text-sm hover:bg-red-500/10 font-medium transition-colors"
                  >
                    <LogOut size={14} />
                    Log Out
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* --- Main Content Area --- */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/20 via-[#09090b] to-[#09090b] pointer-events-none z-0"></div>
        <div className="relative z-10 flex-1 flex flex-col overflow-hidden">
          {activeTab === TABS.CONNECT && (
            <ErrorBoundary fallbackTitle="Drive Sync Failed">
              <DriveSyncPanel />
            </ErrorBoundary>
          )}
          {activeTab === TABS.OMNIHUB && (
            <ErrorBoundary fallbackTitle="OmniHub Missing">
              <OmniHubTab />
            </ErrorBoundary>
          )}
          {activeTab === TABS.SECURITY && (
            <ErrorBoundary fallbackTitle="Security Dashboard Failed">
              <SecurityTab />
            </ErrorBoundary>
          )}
        </div>
      </main>

      {/* --- Persistent Event Log Panel removed as requested --- */}
    </div>
  );
};

import { ToastProvider } from './context/ToastContext';

const App: React.FC = () => {
  return (
    <ToastProvider>
      <OmniHubProvider>
        <MainLayout />
      </OmniHubProvider>
    </ToastProvider>
  );
};

export default App;