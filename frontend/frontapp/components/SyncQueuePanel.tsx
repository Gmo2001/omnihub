import React from 'react';
import { Loader2, CheckCircle2, XCircle, FastForward } from 'lucide-react';

interface SyncQueuePanelProps {
    statusData: any; // Raw system_status data from polling
}

const SyncQueuePanel: React.FC<SyncQueuePanelProps> = ({ statusData }) => {
    if (!statusData || statusData.status !== 'running') return null;

    const { processed, total_files, queue_preview, recent_completed } = statusData;
    const progressPercent = Math.min(100, Math.round((processed / total_files) * 100));

    // Derive Active Task (Fake it using the first item of queue or specific logic)
    // Since queue_preview[0] is technically "next", let's say "Processing..."
    const activeTaskName = queue_preview && queue_preview.length > 0 ? queue_preview[0] : "Finishing up...";

    return (
        <div className="mt-6 mx-6 p-4 bg-white/5 border border-white/5 rounded-xl space-y-4 animate-in fade-in slide-in-from-bottom-2">

            {/* Header & Progress */}
            <div className="space-y-2">
                <div className="flex justify-between items-center text-xs font-bold text-slate-300">
                    <span className="flex items-center gap-2">
                        <Loader2 size={12} className="animate-spin text-indigo-400" />
                        SYNC IN PROGRESS
                    </span>
                    <span className="font-mono text-indigo-300">{progressPercent}%</span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                        className="h-full bg-indigo-500 transition-all duration-500 ease-out"
                        style={{ width: `${progressPercent}%` }}
                    ></div>
                </div>
                <div className="text-[10px] text-slate-500 text-right">
                    {processed} / {total_files} files processed
                </div>
            </div>

            {/* Active Task */}
            <div className="bg-indigo-500/10 border border-indigo-500/20 p-3 rounded-lg">
                <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider mb-1">Currently Processing</div>
                <div className="text-xs text-white truncate font-mono">
                    {activeTaskName}
                </div>
            </div>

            {/* Up Next (Queue) */}
            {queue_preview && queue_preview.length > 1 && (
                <div className="space-y-2">
                    <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Up Next</div>
                    <div className="space-y-1">
                        {queue_preview.slice(1, 4).map((name: string, idx: number) => (
                            <div key={idx} className="flex items-center gap-2 text-[10px] text-slate-400 pl-2 border-l border-white/10">
                                <div className="w-1 h-1 rounded-full bg-slate-600"></div>
                                <span className="truncate">{name}</span>
                            </div>
                        ))}
                        {queue_preview.length > 4 && (
                            <div className="text-[9px] text-slate-600 pl-4 italic">
                                + {queue_preview.length - 4} more...
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Recent History */}
            {recent_completed && recent_completed.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-white/5">
                    <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Recent Activity</div>
                    <div className="space-y-1.5">
                        {recent_completed.slice(0, 3).map((item: any, idx: number) => (
                            <div key={idx} className="flex items-center justify-between text-[10px]">
                                <span className="text-slate-400 truncate max-w-[120px]">{item.name}</span>
                                {item.status === 'success' && <span className="text-emerald-500 flex items-center gap-1"><CheckCircle2 size={10} /> Done</span>}
                                {item.status === 'skipped' && <span className="text-slate-500 flex items-center gap-1"><FastForward size={10} /> Skip</span>}
                                {item.status === 'failed' && <span className="text-red-500 flex items-center gap-1"><XCircle size={10} /> Fail</span>}
                            </div>
                        ))}
                    </div>
                </div>
            )}

        </div>
    );
};

export default SyncQueuePanel;
