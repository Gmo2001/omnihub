import React, { useEffect, useRef, useState } from 'react';
import { useOmniHub } from '../context/OmniHubContext'; // We might still use token from here
import { BackendAPI } from '../services/dataService'; // Import API
import { Terminal, AlertCircle, Info, AlertTriangle, Bug, RefreshCw } from 'lucide-react';

interface SystemError {
  id: string;
  timestamp: string;
  error_code: string;
  message: string;
  path: string;
  user_id?: string;
}

const EventLogPanel: React.FC = () => {
  const { logs: contextLogs } = useOmniHub(); // Keep local logs mixed in? Or just replace? User asked for "System Error Lookup API". Let's prioritize API logs.
  const [systemErrors, setSystemErrors] = useState<SystemError[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Use a ref to prevent infinite loops if we were using context for auth, 
  // but simpler to just use localStorage for now or get token from context if stable
  const token = localStorage.getItem('omnihub_token');

  const fetchErrors = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const data = await BackendAPI.getSystemErrors(token, 100);
      setSystemErrors(data);
    } catch (e) {
      console.error("Failed to fetch system logs", e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchErrors();
    // Optional: Poll every 10s
    const interval = setInterval(fetchErrors, 10000);
    return () => clearInterval(interval);
  }, []);

  const getIcon = (code: string) => {
    if (['AUTH_MISSING', 'PERM_DENIED'].includes(code)) return <AlertCircle size={12} className="text-red-500" />;
    if (['TIMEOUT', 'SERVICE_DOWN'].includes(code)) return <AlertTriangle size={12} className="text-amber-500" />;
    return <Bug size={12} className="text-slate-500" />;
  };

  return (
    <div className="h-full bg-[#050508] border border-white/5 rounded-2xl flex flex-col overflow-hidden shadow-xl font-mono">
      <div className="flex items-center gap-2 px-4 py-3 bg-[#09090b] border-b border-white/5">
        <Terminal size={14} className="text-indigo-400" />
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">System Kernel Panic Log</span>
        <div className="ml-auto flex items-center gap-3">
          <button onClick={fetchErrors} className="hover:bg-white/5 p-1 rounded transition-colors">
            <RefreshCw size={12} className={`text-slate-500 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></div>
            <span className="text-[10px] text-red-500 font-bold">ERROR STREAM</span>
          </div>
          <span className="text-[10px] text-slate-600 border px-1.5 rounded border-white/10">{systemErrors.length} events</span>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-0 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent"
      >
        {systemErrors.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-700 space-y-2 p-8">
            <Terminal size={24} className="opacity-20" />
            <span className="text-xs italic">System stable. No anomalies detected.</span>
          </div>
        ) : (
          systemErrors.map((log) => (
            <div key={log.id} className="flex items-start gap-3 px-4 py-2 text-[10px] border-b border-white/5 hover:bg-white/5 transition-colors group">
              <span className="text-slate-500 opacity-60 min-w-[70px] tabular-nums">
                {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '--:--:--'}
              </span>
              <span className="mt-0.5">{getIcon(log.error_code)}</span>
              <div className="flex-1 space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-red-400 opacity-90">[{log.error_code}]</span>
                  <span className="text-slate-500 text-[9px] border border-white/10 px-1 rounded">{log.path}</span>
                </div>
                <div className="text-slate-300 opacity-90 leading-relaxed">{log.message}</div>
                {log.user_id && log.user_id !== 'system' && (
                  <div className="text-indigo-400/60 text-[9px]">User: {log.user_id}</div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default EventLogPanel;