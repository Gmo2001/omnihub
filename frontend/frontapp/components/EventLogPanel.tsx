import React, { useEffect, useRef } from 'react';
import { useOmniHub } from '../context/OmniHubContext';
import { Terminal, AlertCircle, Info, AlertTriangle } from 'lucide-react';

const EventLogPanel: React.FC = () => {
  const { logs } = useOmniHub();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const getIcon = (level: string) => {
    switch (level) {
      case 'ERROR': return <AlertCircle size={12} className="text-red-500" />;
      case 'WARN': return <AlertTriangle size={12} className="text-amber-500" />;
      default: return <Info size={12} className="text-blue-500" />;
    }
  };

  const getRowStyle = (level: string) => {
      switch(level) {
          case 'ERROR': return 'bg-red-500/5 border-l-2 border-red-500 text-red-200';
          case 'WARN': return 'bg-amber-500/5 border-l-2 border-amber-500 text-amber-200';
          default: return 'text-slate-400 border-l-2 border-transparent';
      }
  };

  return (
    <div className="h-40 bg-[#050508] border-t border-white/10 flex flex-col shrink-0 font-mono z-20 shadow-[0_-5px_15px_rgba(0,0,0,0.3)]">
      <div className="flex items-center gap-2 px-4 py-2 bg-[#09090b] border-b border-white/5">
        <Terminal size={14} className="text-indigo-400" />
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">System Kernel Log</span>
        <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
                <span className="text-[10px] text-emerald-500 font-bold">LIVE</span>
            </div>
            <span className="text-[10px] text-slate-600 border px-1.5 rounded border-white/10">{logs.length} events</span>
        </div>
      </div>
      
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-0 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent"
      >
        {logs.map((log) => (
          <div key={log.id} className={`flex items-start gap-3 px-4 py-1.5 text-[10px] transition-colors hover:bg-white/5 ${getRowStyle(log.level)}`}>
            <span className="opacity-50 min-w-[70px]">
              {new Date(log.ts).toISOString().split('T')[1].replace('Z','')}
            </span>
            <span className="mt-0.5">{getIcon(log.level)}</span>
            <div className="flex-1 flex gap-2">
              <span className="font-bold opacity-80 min-w-[40px]">[{log.level}]</span>
              {log.actorRole && <span className="text-indigo-400 opacity-90">@{log.actorRole}</span>}
              <span className="opacity-90 tracking-tight">{log.message}</span>
            </div>
          </div>
        ))}
        {logs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-slate-700 space-y-2">
              <Terminal size={24} className="opacity-20"/>
              <span className="text-xs italic">Awaiting system events...</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default EventLogPanel;