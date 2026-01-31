import React, { useEffect, useState } from 'react';
import { BackendAPI, DriveFile } from '../services/dataService';
import { Cloud, Folder, File, RefreshCw, LogIn, Lock, CheckCircle, AlertTriangle, CloudUpload, LogOut } from 'lucide-react';

declare global {
    interface Window {
        google: any;
    }
}

const DriveSyncPanel: React.FC = () => {
    const [token, setToken] = useState<string | null>(localStorage.getItem('omnihub_token'));
    const [currentFolderId, setCurrentFolderId] = useState<string>("root");
    const [files, setFiles] = useState<DriveFile[]>([]);
    const [loading, setLoading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [selectedFolder, setSelectedFolder] = useState<{ id: string, name: string } | null>(null);

    // 1. Init Google Auth (Code Flow)
    useEffect(() => {
        if (!token && window.google) {
            // New Code Flow Client
            const client = window.google.accounts.oauth2.initCodeClient({
                client_id: "707724932002-kkd8u9df0bfsc5lv0q4lssfmu3abbpko.apps.googleusercontent.com",
                scope: "https://www.googleapis.com/auth/drive.readonly openid email profile",
                ux_mode: "popup",
                callback: (response: any) => {
                    if (response.code) {
                        handleAuthCode(response.code);
                    }
                },
            });

            // Expose logic to button
            (window as any).googleLogin = () => client.requestCode();
        } else if (token) {
            loadFolder("root");
        }
    }, [token]);

    const handleAuthCode = async (code: string) => {
        try {
            setLoading(true);
            const data = await BackendAPI.exchangeToken(code);
            if (data.access_token) {
                setToken(data.access_token);
                localStorage.setItem('omnihub_token', data.access_token);
            }
        } catch (e) {
            alert("Login Failed");
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const loadFolder = async (folderId: string) => {
        setLoading(true);
        try {
            const list = await BackendAPI.getDriveProxy(folderId, token);
            setFiles(list);
            setCurrentFolderId(folderId);
        } catch (e) {
            alert("Failed to load folder");
        } finally {
            setLoading(false);
        }
    };

    // --- Sync Polling Logic ---
    const [syncStatus, setSyncStatus] = useState<any>(null);
    const [showSyncModal, setShowSyncModal] = useState(false);

    const handleSync = async () => {
        const targetId = selectedFolder ? selectedFolder.id : currentFolderId;
        const targetName = selectedFolder ? selectedFolder.name : (currentFolderId === 'root' ? "My Drive" : "Current Folder");

        if (!token) return;

        setShowSyncModal(true);
        setSyncStatus({ status: 'starting', message: 'Initiating Sync...' });

        try {
            await BackendAPI.syncFolder(targetId, token);

            const pollInterval = setInterval(async () => {
                try {
                    const status = await BackendAPI.getSyncStatus(targetId, token);
                    setSyncStatus(status);

                    if (status.status === 'completed' || status.status === 'failed') {
                        clearInterval(pollInterval);
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }, 2000);
        } catch (e: any) {
            setSyncStatus({ status: 'failed', error: e.message });
        }
    };

    const handleLogout = () => {
        setToken(null);
        localStorage.removeItem('omnihub_token');
        setFiles([]);
        setCurrentFolderId("root");
    };

    if (!token) {
        return (
            <div className="flex flex-col items-center justify-center h-full p-8 text-center space-y-6 animate-in fade-in zoom-in-95 duration-300">
                <div className="w-20 h-20 bg-indigo-500/10 rounded-full flex items-center justify-center animate-pulse">
                    <Lock size={40} className="text-indigo-400" />
                </div>
                <div>
                    <h2 className="text-2xl font-bold text-white mb-2">Login Required</h2>
                    <p className="text-slate-400 max-w-sm mx-auto">
                        Please sign in with your Google Workspace account to access Cloud Drive integration.
                    </p>
                </div>
                <button
                    onClick={() => (window as any).googleLogin && (window as any).googleLogin()}
                    className="flex items-center gap-3 bg-white text-slate-900 px-6 py-3 rounded-lg font-bold shadow-lg hover:bg-slate-100 transition-all active:scale-95"
                >
                    <img src="https://www.svgrepo.com/show/475656/google-color.svg" className="w-5 h-5" alt="G" />
                    Sign in with Google
                </button>
                {/* Fallback if script not loaded yet */}
                {!window.google && <p className="text-xs text-red-400">Google Script not loaded. Check network.</p>}
            </div>
        );
    }

    return (
        <div className="flex flex-1 h-full overflow-hidden bg-[#09090b] relative">
            {/* Sync Progress Modal */}
            {showSyncModal && (
                <div className="absolute inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
                    <div className="bg-[#1E1F2E] border border-white/10 p-8 rounded-2xl shadow-2xl max-w-md w-full space-y-6 text-center relative">
                        {['completed', 'failed'].includes(syncStatus?.status) && (
                            <button
                                onClick={() => setShowSyncModal(false)}
                                className="absolute top-4 right-4 text-slate-500 hover:text-white"
                            >
                                <Cloud size={20} />
                            </button>
                        )}

                        <div className="flex justify-center">
                            {syncStatus?.status === 'completed' ? (
                                <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center">
                                    <CheckCircle size={32} className="text-emerald-500" />
                                </div>
                            ) : syncStatus?.status === 'failed' ? (
                                <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center">
                                    <AlertTriangle size={32} className="text-red-500" />
                                </div>
                            ) : (
                                <div className="w-16 h-16 bg-indigo-500/20 rounded-full flex items-center justify-center animate-pulse">
                                    <RefreshCw size={32} className="text-indigo-500 animate-spin" />
                                </div>
                            )}
                        </div>

                        <div>
                            <h3 className="text-xl font-bold text-white mb-2">
                                {syncStatus?.status === 'completed' ? 'Sync Completed!' :
                                    syncStatus?.status === 'failed' ? 'Sync Failed' : 'Synchronizing...'}
                            </h3>
                            <p className="text-slate-400 text-sm">
                                {syncStatus?.status === 'running' ? `Processing files... (${syncStatus.processed} / ${syncStatus.total_files || '?'})` :
                                    syncStatus?.status === 'completed' ? `Successfully processed ${syncStatus.processed} files.` :
                                        syncStatus?.error || "Please wait while we fetch your files from Google Drive."}
                            </p>
                        </div>

                        {syncStatus?.status === 'running' && syncStatus.total_files > 0 && (
                            <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                                <div
                                    className="bg-indigo-500 h-full transition-all duration-500"
                                    style={{ width: `${(syncStatus.processed / syncStatus.total_files) * 100}%` }}
                                ></div>
                            </div>
                        )}

                        {syncStatus?.status === 'completed' && (
                            <div className="grid grid-cols-3 gap-2 text-xs bg-black/20 p-4 rounded-xl">
                                <div className="p-2">
                                    <div className="text-slate-500 mb-1">Total</div>
                                    <div className="text-white font-bold text-lg">{syncStatus.total_files || 0}</div>
                                </div>
                                <div className="p-2 border-x border-white/5">
                                    <div className="text-slate-500 mb-1">Skipped</div>
                                    <div className="text-amber-400 font-bold text-lg">{syncStatus.skipped || 0}</div>
                                </div>
                                <div className="p-2">
                                    <div className="text-slate-500 mb-1">Failed</div>
                                    <div className="text-red-400 font-bold text-lg">{syncStatus.failed || 0}</div>
                                </div>
                            </div>
                        )}

                        {['completed', 'failed'].includes(syncStatus?.status) && (
                            <button
                                onClick={() => setShowSyncModal(false)}
                                className="w-full py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl font-bold transition-all"
                            >
                                Close
                            </button>
                        )}
                    </div>
                </div>
            )}
            {/* Sync Progress Modal */}
            {showSyncModal && (
                <div className="absolute inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
                    <div className="bg-[#1E1F2E] border border-white/10 p-8 rounded-2xl shadow-2xl max-w-md w-full space-y-6 text-center relative">
                        {/* Close Button (Only when done) */}
                        {['completed', 'failed'].includes(syncStatus?.status) && (
                            <button
                                onClick={() => setShowSyncModal(false)}
                                className="absolute top-4 right-4 text-slate-500 hover:text-white"
                            >
                                <Cloud size={20} />
                            </button>
                        )}

                        <div className="flex justify-center">
                            {syncStatus?.status === 'completed' ? (
                                <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center">
                                    <CheckCircle size={32} className="text-emerald-500" />
                                </div>
                            ) : syncStatus?.status === 'failed' ? (
                                <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center">
                                    <AlertTriangle size={32} className="text-red-500" />
                                </div>
                            ) : (
                                <div className="w-16 h-16 bg-indigo-500/20 rounded-full flex items-center justify-center animate-pulse">
                                    <RefreshCw size={32} className="text-indigo-500 animate-spin" />
                                </div>
                            )}
                        </div>

                        <div>
                            <h3 className="text-xl font-bold text-white mb-2">
                                {syncStatus?.status === 'completed' ? 'Sync Completed!' :
                                    syncStatus?.status === 'failed' ? 'Sync Failed' : 'Synchronizing...'}
                            </h3>
                            <p className="text-slate-400 text-sm">
                                {syncStatus?.status === 'running' ? `Processing files... (${syncStatus.processed} / ${syncStatus.total_files || '?'})` :
                                    syncStatus?.status === 'completed' ? `Successfully processed ${syncStatus.processed} files.` :
                                        syncStatus?.error || "Please wait while we fetch your files from Google Drive."}
                            </p>
                        </div>

                        {/* Progress Bar (if running) */}
                        {syncStatus?.status === 'running' && syncStatus.total_files > 0 && (
                            <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                                <div
                                    className="bg-indigo-500 h-full transition-all duration-500"
                                    style={{ width: `${(syncStatus.processed / syncStatus.total_files) * 100}%` }}
                                ></div>
                            </div>
                        )}

                        {/* Stats Grid */}
                        {syncStatus?.status === 'completed' && (
                            <div className="grid grid-cols-3 gap-2 text-xs bg-black/20 p-4 rounded-xl">
                                <div className="p-2">
                                    <div className="text-slate-500 mb-1">Total</div>
                                    <div className="text-white font-bold text-lg">{syncStatus.total_files || 0}</div>
                                </div>
                                <div className="p-2 border-x border-white/5">
                                    <div className="text-slate-500 mb-1">Skipped</div>
                                    <div className="text-amber-400 font-bold text-lg">{syncStatus.skipped || 0}</div>
                                </div>
                                <div className="p-2">
                                    <div className="text-slate-500 mb-1">Failed</div>
                                    <div className="text-red-400 font-bold text-lg">{syncStatus.failed || 0}</div>
                                </div>
                            </div>
                        )}

                        {['completed', 'failed'].includes(syncStatus?.status) && (
                            <button
                                onClick={() => setShowSyncModal(false)}
                                className="w-full py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl font-bold transition-all"
                            >
                                Close
                            </button>
                        )}
                    </div>
                </div>
            )}

            {/* Left: Browser */}
            <div className="w-1/2 border-r border-white/5 flex flex-col">
                <div className="p-4 border-b border-white/5 bg-[#13141F] space-y-3">
                    <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2 font-bold text-slate-200">
                            <Cloud size={16} className="text-indigo-400" />
                            <span>Drive Explorer</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <button
                                onClick={handleLogout}
                                className="p-1.5 hover:bg-white/5 rounded-lg text-slate-400 hover:text-red-400 transition-colors"
                                title="Sign out"
                            >
                                <LogOut size={14} />
                            </button>
                            <button onClick={() => loadFolder(currentFolderId)} className="p-1.5 hover:bg-white/5 rounded-lg text-slate-400 transition-colors">
                                <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                            </button>
                        </div>
                    </div>
                    {/* Manual ID Input */}
                    <div className="flex gap-2">
                        <input
                            type="text"
                            placeholder="Paste Folder ID directly..."
                            className="flex-1 bg-black/20 border border-white/10 rounded px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500 transition-colors"
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    loadFolder(e.currentTarget.value);
                                    e.currentTarget.value = '';
                                }
                            }}
                        />
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin">
                    {currentFolderId !== 'root' && (
                        <div
                            onClick={() => loadFolder('root')}
                            className="flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 cursor-pointer text-slate-400 hover:text-indigo-300 transition-colors"
                        >
                            <span className="text-lg">↩️</span>
                            <span className="text-sm font-medium">Back to Root</span>
                        </div>
                    )}

                    {files.map(file => {
                        const isFolder = file.mimeType.includes("folder");
                        if (!isFolder) return null; // Only show folders

                        const isSelected = selectedFolder?.id === file.id;

                        return (
                            <div
                                key={file.id}
                                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border border-transparent transition-all group ${isSelected
                                    ? "bg-indigo-500/20 border-indigo-500/50 text-white"
                                    : "hover:bg-white/5 text-slate-300"
                                    }`}
                                onClick={() => setSelectedFolder({ id: file.id, name: file.name })}
                                onDoubleClick={() => loadFolder(file.id)}
                            >
                                <Folder size={18} className={isSelected ? "text-indigo-300 fill-indigo-500/20" : "text-slate-500 group-hover:text-amber-400"} />
                                <span className="text-sm truncate flex-1">{file.name}</span>
                                {isSelected && <CheckCircle size={14} className="text-indigo-400" />}
                            </div>
                        );
                    })}

                    {files.length === 0 && !loading && (
                        <div className="text-center py-10 text-slate-600 text-xs italic">
                            Empty folder
                        </div>
                    )}
                </div>
            </div>

            {/* Right: Action Panel */}
            <div className="w-1/2 bg-[#050508] flex items-center justify-center p-8 relative overflow-hidden">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-indigo-900/10 via-transparent to-transparent pointer-events-none"></div>

                <div className="w-full max-w-sm bg-[#1E1F2E] border border-white/5 p-8 rounded-2xl shadow-2xl space-y-6 relative z-10 animate-in fade-in slide-in-from-bottom-4">
                    <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/20 mx-auto transform -translate-y-2">
                        <Folder size={32} className="text-white" />
                    </div>

                    <div className="text-center space-y-1">
                        <h2 className="text-xl font-bold text-white truncate">
                            {selectedFolder ? selectedFolder.name : (currentFolderId === 'root' ? "My Drive (Root)" : "Current Folder")}
                        </h2>
                        <p className="text-xs font-mono text-slate-500 bg-black/30 py-1 px-2 rounded inline-block">
                            ID: {(selectedFolder ? selectedFolder.id : currentFolderId).slice(0, 15)}...
                        </p>
                    </div>

                    <div className="bg-amber-500/5 border border-amber-500/10 rounded-lg p-3 flex gap-3 text-left">
                        <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
                        <div className="space-y-1">
                            <p className="text-xs font-bold text-amber-500">Privacy Guard™ Active</p>
                            <p className="text-[10px] text-amber-200/60 leading-relaxed">
                                Only files within this folder will be synced. Personal files outside this scope are ignored.
                            </p>
                        </div>
                    </div>

                    <button
                        onClick={handleSync}
                        disabled={syncing}
                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold transition-all shadow-lg hover:shadow-indigo-500/25 active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {syncing ? <RefreshCw className="animate-spin" /> : <CloudUpload size={18} />}
                        {syncing ? "Starting..." : "Start Cloud Sync"}
                    </button>

                    {!selectedFolder && (
                        <p className="text-[10px] text-center text-slate-500">
                            * No subfolder selected. Syncing default/current location.
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
};

export default DriveSyncPanel;
