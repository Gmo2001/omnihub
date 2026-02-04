import React, { useEffect, useState } from 'react';
import { BackendAPI } from '../../services/dataService';
import { useOmniHub } from '../../context/OmniHubContext';
import { Folder, Trash2, ExternalLink, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';

interface MonitoredFolder {
    id: string;
    name: string;
    link?: string;
    status: string;
    error?: string;
    last_synced?: string;
}

const SyncManager = () => {
    const { token } = useOmniHub();
    const [folders, setFolders] = useState<MonitoredFolder[]>([]);
    const [loading, setLoading] = useState(false);
    const [removingId, setRemovingId] = useState<string | null>(null);

    const loadFolders = async () => {
        setLoading(true);
        try {
            const list = await BackendAPI.getMonitoredFolders(token);
            setFolders(list);
        } catch (e) {
            console.error("Failed to load synced folders", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadFolders();
    }, []);

    const handleUnsync = async (folderId: string) => {
        if (!confirm("Are you sure you want to stop syncing this folder? Files already ingested will remain.")) return;

        setRemovingId(folderId);
        try {
            await BackendAPI.unsyncFolder(folderId, token);
            await loadFolders(); // Refresh
        } catch (e) {
            alert("Failed to unsync folder");
        } finally {
            setRemovingId(null);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <Folder size={18} className="text-blue-400" />
                        Synced Folders Management
                    </h3>
                    <p className="text-xs text-slate-500 mt-1">
                        Folders listed here are actively watched for changes.
                    </p>
                </div>
                <button
                    onClick={loadFolders}
                    disabled={loading}
                    className="p-2 hover:bg-white/5 rounded-lg text-slate-400 transition-colors"
                >
                    <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                </button>
            </div>

            <div className="space-y-3">
                {folders.length === 0 && !loading && (
                    <div className="text-center py-8 text-slate-500 bg-white/5 rounded-xl border border-white/5 border-dashed">
                        No folders are currently being synced.
                    </div>
                )}

                {folders.map(folder => (
                    <div key={folder.id} className="bg-[#13141F] border border-white/5 rounded-xl p-4 flex items-center justify-between group hover:border-white/10 transition-colors">
                        <div className="flex items-center gap-4">
                            <div className={`p-3 rounded-lg ${folder.status === 'active' ? 'bg-blue-500/10 text-blue-400' : 'bg-red-500/10 text-red-400'}`}>
                                <Folder size={20} />
                            </div>
                            <div>
                                <div className="flex items-center gap-2">
                                    <span className="font-bold text-slate-200">{folder.name}</span>
                                    {folder.link && (
                                        <a href={folder.link} target="_blank" rel="noreferrer" className="text-slate-500 hover:text-blue-400 transition-colors">
                                            <ExternalLink size={12} />
                                        </a>
                                    )}
                                </div>
                                <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                                    <span className="font-mono bg-white/5 px-1.5 py-0.5 rounded text-[10px]">{folder.id}</span>
                                    {folder.status === 'active' ? (
                                        <span className="text-emerald-500 flex items-center gap-1">
                                            <CheckCircle size={10} /> Active
                                        </span>
                                    ) : (
                                        <span className="text-red-500 flex items-center gap-1">
                                            <AlertCircle size={10} /> {folder.status}
                                        </span>
                                    )}
                                </div>
                                {folder.error && (
                                    <div className="text-[10px] text-red-500 mt-1">{folder.error}</div>
                                )}
                            </div>
                        </div>

                        <button
                            onClick={() => handleUnsync(folder.id)}
                            disabled={removingId === folder.id}
                            className="p-2 bg-white/5 hover:bg-red-500/20 text-slate-400 hover:text-red-400 rounded-lg transition-all opacity-0 group-hover:opacity-100 disabled:opacity-50"
                            title="Stop Syncing"
                        >
                            {removingId === folder.id ? <div className="w-4 h-4 border-2 border-red-500/30 border-t-red-500 rounded-full animate-spin"></div> : <Trash2 size={18} />}
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default SyncManager;
