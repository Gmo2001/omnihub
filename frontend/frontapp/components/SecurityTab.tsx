import React, { useMemo } from 'react';
import { useOmniHub } from '../context/OmniHubContext';
import { ShieldAlert, ShieldCheck, Lock, Activity, BarChart3, AlertTriangle, Zap, RefreshCcw, FileText, Ban } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import EventLogPanel from './EventLogPanel';

const SecurityTab: React.FC = () => {
    // [FUTURE_WORK] This tab should only be visible to users with 'admin' role.
    // Implement RBAC check here or in the parent router.
    const {
        resetSecurity, docs,
        securityState, logs, riskHistory
    } = useOmniHub();

    const { approvedCount, pendingCount } = useMemo(() => {
        return {
            approvedCount: docs.filter(d => d.status === 'approved').length,
            pendingCount: docs.filter(d => d.status === 'pending').length
        };
    }, [docs]);

    const securityLogs = useMemo(() => {
        return logs.filter(l => l.category === 'SECURITY' || ['WARN', 'ERROR'].includes(l.level)).slice().reverse();
    }, [logs]);

    const modeStyles = {
        SAFE: 'from-emerald-500/10 to-emerald-900/5 border-emerald-500/30 text-emerald-400',
        WATCH: 'from-amber-500/10 to-amber-900/5 border-amber-500/30 text-amber-400',
        ALERT: 'from-red-500/10 to-red-900/5 border-red-500/30 text-red-400'
    };

    const chartColor = securityState.mode === 'ALERT' ? '#f43f5e' : (securityState.mode === 'WATCH' ? '#fbbf24' : '#10b981');

    return (
        <div className="flex-1 overflow-y-auto p-8 bg-[#09090b] scrollbar-thin">
            <div className="max-w-[1600px] mx-auto space-y-8">

                {/* Header */}
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                    <div>
                        <h2 className="text-3xl font-bold text-white flex items-center gap-3">
                            <ShieldCheck className="text-indigo-400" size={32} />
                            Security Ops Center
                        </h2>
                        <p className="text-sm text-slate-400 mt-1">Real-time threat monitoring and access control visualization</p>
                    </div>

                    {securityState.mode === 'ALERT' && (
                        <button
                            onClick={resetSecurity}
                            className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-bold shadow-lg shadow-emerald-900/50 transition-all active:scale-95"
                        >
                            <RefreshCcw size={18} />
                            SYSTEM RESET
                        </button>
                    )}
                </div>

                {/* Alert Banner */}
                {securityState.mode === 'ALERT' && (
                    <div className="bg-red-500/10 border border-red-500/50 text-red-200 px-8 py-6 rounded-2xl flex items-center gap-6 animate-pulse shadow-[0_0_30px_rgba(239,68,68,0.2)]">
                        <div className="p-3 bg-red-500/20 rounded-full">
                            <AlertTriangle size={32} className="text-red-500" />
                        </div>
                        <div className="flex-1">
                            <h3 className="font-bold text-xl text-red-400 tracking-wide">CRITICAL THREAT DETECTED</h3>
                            <p className="text-base opacity-80 mt-1">Automated defense protocols activated. Traffic throttling in effect.</p>
                        </div>
                    </div>
                )}

                {/* KPI Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {/* Risk Score */}
                    <div className={`p-6 rounded-2xl border bg-gradient-to-br ${modeStyles[securityState.mode]} backdrop-blur-sm relative overflow-hidden group`}>
                        <div className="absolute top-0 right-0 p-4 opacity-20 group-hover:scale-110 transition-transform">
                            <Activity size={48} />
                        </div>
                        <div className="text-xs uppercase font-bold tracking-widest opacity-70 mb-2">Current Risk Level</div>
                        <div className="flex items-baseline gap-2">
                            <span className="text-5xl font-black tracking-tighter">
                                {securityState.riskScore}
                            </span>
                            <span className="text-sm opacity-60">/ 100</span>
                        </div>
                        <div className="mt-4 inline-flex items-center px-3 py-1 rounded-lg text-xs font-black uppercase bg-black/20 border border-white/10">
                            STATUS: {securityState.mode}
                        </div>
                    </div>

                    {/* Other Stats - Glass Cards */}
                    <div className="bg-[#1E1F2E]/60 backdrop-blur border border-white/5 p-6 rounded-2xl hover:border-white/10 transition-colors group">
                        <div className="flex justify-between items-start mb-4">
                            <span className="text-slate-400 text-xs uppercase font-bold tracking-widest">Total Approved</span>
                            <FileText className="text-indigo-400 group-hover:text-indigo-300 transition-colors" size={20} />
                        </div>
                        <div className="text-4xl font-bold text-white">{approvedCount}</div>
                        <div className="mt-2 text-xs text-indigo-400/80">Docs Processed</div>
                    </div>

                    <div className="bg-[#1E1F2E]/60 backdrop-blur border border-white/5 p-6 rounded-2xl hover:border-white/10 transition-colors group">
                        <div className="flex justify-between items-start mb-4">
                            <span className="text-slate-400 text-xs uppercase font-bold tracking-widest">Threats Blocked</span>
                            <ShieldAlert className="text-amber-400 group-hover:text-amber-300 transition-colors" size={20} />
                        </div>
                        <div className="text-4xl font-bold text-white">{securityState.blockedCount}</div>
                        <div className="mt-2 text-xs text-amber-400/80">Active Defense</div>
                    </div>

                    <div className="bg-[#1E1F2E]/60 backdrop-blur border border-white/5 p-6 rounded-2xl hover:border-white/10 transition-colors group">
                        <div className="flex justify-between items-start mb-4">
                            <span className="text-slate-400 text-xs uppercase font-bold tracking-widest">Pending Review</span>
                            <Lock className="text-blue-400 group-hover:text-blue-300 transition-colors" size={20} />
                        </div>
                        <div className="text-4xl font-bold text-white">{pendingCount}</div>
                        <div className="mt-2 text-xs text-blue-400/80">Awaiting Action</div>
                    </div>
                </div>

                {/* Charts & Logs */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[500px]">

                    {/* Chart */}
                    <div className="lg:col-span-2 bg-[#1E1F2E]/60 backdrop-blur border border-white/5 p-6 rounded-2xl flex flex-col">
                        <div className="flex items-center gap-3 mb-6">
                            <div className="p-2 bg-white/5 rounded-lg">
                                <BarChart3 className="text-slate-400" size={20} />
                            </div>
                            <h3 className="text-base font-bold text-slate-200">Risk Velocity Timeline</h3>
                        </div>
                        <div className="flex-1 w-full min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={riskHistory}>
                                    <defs>
                                        <linearGradient id="colorRisk" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor={chartColor} stopOpacity={0.3} />
                                            <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} opacity={0.3} />
                                    <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} tickMargin={10} minTickGap={30} axisLine={false} tickLine={false} />
                                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={[0, 100]} axisLine={false} tickLine={false} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', color: '#f1f5f9' }}
                                        itemStyle={{ color: '#f1f5f9' }}
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="score"
                                        stroke={chartColor}
                                        fillOpacity={1}
                                        fill="url(#colorRisk)"
                                        strokeWidth={3}
                                        isAnimationActive={false}
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Logs */}
                    <div className="bg-[#1E1F2E]/60 backdrop-blur border border-white/5 rounded-2xl flex flex-col overflow-hidden h-full">
                        <EventLogPanel />
                    </div>
                </div>

            </div>
        </div>
    );
};

export default SecurityTab;