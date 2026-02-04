import React, { useEffect, useState } from 'react';
import { BackendAPI } from '../../services/dataService';
import { useOmniHub } from '../../context/OmniHubContext';
import { CheckCircle, AlertTriangle, RefreshCw, Server, Database, Activity } from 'lucide-react';

const SystemStatus = () => {
    const { token } = useOmniHub();
    const [loading, setLoading] = useState(false);
    const [health, setHealth] = useState<any>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const checkHealth = async () => {
        setLoading(true);
        try {
            const data = await BackendAPI.getSystemHealth(token);
            setHealth(data);
            setLastUpdated(new Date());
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        checkHealth();
    }, []);

    const StatusCard = ({ title, icon: Icon, status, latency }: any) => (
        <div className="bg-[#13141F] border border-white/5 rounded-xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${status === 'ok' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
                    <Icon size={20} />
                </div>
                <div>
                    <div className="text-sm font-bold text-slate-200">{title}</div>
                    <div className="text-xs text-slate-500">
                        {status === 'ok' ? 'Connected' : 'Error'}
                    </div>
                </div>
            </div>
            <div className="text-right">
                <div className={`text-sm font-bold ${status === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {status === 'ok' ? 'Active' : 'Down'}
                </div>
                {latency > 0 && (
                    <div className="text-[10px] text-slate-500 font-mono">
                        {latency}ms
                    </div>
                )}
            </div>
        </div>
    );

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    <Activity size={18} className="text-indigo-400" />
                    System Status
                </h3>
                <button
                    onClick={checkHealth}
                    disabled={loading}
                    className="p-2 hover:bg-white/5 rounded-lg text-slate-400 transition-colors"
                >
                    <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                </button>
            </div>

            <div className="grid grid-cols-1 gap-3">
                <StatusCard
                    title="Firestore Database"
                    icon={Database}
                    status={health?.firestore?.status}
                    latency={health?.firestore?.latency_ms}
                />
                <StatusCard
                    title="BigQuery Analytics"
                    icon={Server}
                    status={health?.bigquery?.status}
                    latency={health?.bigquery?.latency_ms}
                />
            </div>

            <div className="bg-[#13141F] border border-white/5 rounded-xl p-4">
                <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wider">Diagnostic Log</div>
                <div className="space-y-1 max-h-32 overflow-y-auto scrollbar-thin">
                    {health?.details?.map((log: string, i: number) => (
                        <div key={i} className="text-[10px] text-slate-500 font-mono flex gap-2">
                            <span className="text-indigo-500/50">[{lastUpdated?.toLocaleTimeString()}]</span>
                            {log}
                        </div>
                    ))}
                    {!health && <div className="text-[10px] text-slate-600 italic">No logs available.</div>}
                </div>
            </div>
        </div>
    );
};

export default SystemStatus;
