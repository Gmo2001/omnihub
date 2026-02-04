import React, { useEffect, useState } from 'react';
import { BackendAPI } from '../services/dataService';
import { AIService } from '../services/aiService';
import { useOmniHub } from '../context/OmniHubContext';
import { DriveFile } from '../types';
import { Cloud, Folder, File, RefreshCw, LogIn, Lock, CheckCircle, AlertTriangle, CloudUpload, LogOut, Search, XCircle, Trash2 } from 'lucide-react';
import SyncQueuePanel from './SyncQueuePanel';

declare global {
    interface Window {
        google: any;
    }
}

const DriveSyncPanel = () => {
    // Assuming setStep is a local state based on usage context found in typical React components
    // Assuming setStep is a local state based on usage context found in typical React components
    const [step, setStep] = useState('connect');
    const {
        isAuthenticated, login, logout, userProfile, token
    } = useOmniHub();
    const [currentFolderId, setCurrentFolderId] = useState<string>("root");
    const [files, setFiles] = useState<DriveFile[]>([]);
    const [loading, setLoading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [selectedItem, setSelectedItem] = useState<{ id: string, name: string, mimeType: string } | null>(null);
    const [searchQuery, setSearchQuery] = useState("");

    // 1. Init Google Auth (Code Flow)
    useEffect(() => {
        if (!isAuthenticated && window.google) {
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
            (window as any).googleLogin = () => client.requestCode();
        } else if (isAuthenticated && token) {
            loadFolder("root");
            setStep('sync');
        }
    }, [isAuthenticated, token]);

    // 2. Sync: If global auth is lost, clear local state
    useEffect(() => {
        if (!isAuthenticated) {
            setFiles([]);
            setCurrentFolderId("root");
        }
    }, [isAuthenticated]);

    const handleAuthCode = async (code: string) => {
        try {
            setLoading(true);
            const data = await BackendAPI.exchangeToken(code);
            if (data.access_token) {
                login(data.access_token);
                setStep('sync');
            }
        } catch (e: any) {
            console.error("Login Error Details:", e);
            alert(`Login Failed: ${e.message || "Unknown Error"}`);
        } finally {
            setLoading(false);
        }
    };

    const loadFolder = async (folderId: string, query?: string) => {
        setLoading(true);
        try {
            // If query is present, we might want to clear folderId context if it was "root" 
            // but backend handles q priority.
            const list = await BackendAPI.getDriveProxy(folderId, token, query);
            setFiles(list);
            setSelectedItem(null); // Deselect on folder change
            if (!query) {
                setCurrentFolderId(folderId);
                setSearchQuery(""); // Clear search if folder nav
            }
        } catch (e) {
            alert("Failed to load folder");
        } finally {
            setLoading(false);
        }
    };

    const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            const q = e.currentTarget.value.trim();
            if (q) {
                loadFolder("root", q); // Global search
            } else {
                loadFolder("root"); // Reset
            }
        }
    };

    // --- Sync Polling Logic ---
    const [syncStatus, setSyncStatus] = useState<any>(null);
    const [showSyncModal, setShowSyncModal] = useState(false);

    const handleSync = async () => {
        // Only for folders
        if (!selectedItem || selectedItem.mimeType !== "application/vnd.google-apps.folder") {
            // Fallback to current folder if nothing selected (legacy logic support)
            if (selectedItem) return; // Should not happen based on UI
        }

        const targetId = selectedItem ? selectedItem.id : currentFolderId;

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

    const handleUnsync = async () => {
        const targetId = selectedItem ? selectedItem.id : currentFolderId;
        if (!token) return;

        // [UX] Clearer warning
        if (!confirm("Stop Syncing?\n\n- Existing files will remain.\n- Ongoing transfer will verify current file then stop.\n- Queue will be cleared.")) return;

        try {
            setSyncing(true);
            // [Feature] Send Abort Signal
            await BackendAPI.unsyncFolder(targetId, token, true);
            alert("Sync cancellation requested.\nThe process will stop after the current file finishes.");

            // [UX] Reset Status Preview immediately (Optimistic UI)
            setSyncStatus({ status: 'cancelled', message: 'Stopping...' });

        } catch (e: any) {
            alert(e.message);
        } finally {
            setSyncing(false);
        }
    };

    // --- Single File Ingest Logic ---
    const handleIngestFile = async () => {
        if (!selectedItem || selectedItem.mimeType === "application/vnd.google-apps.folder") return;
        if (!token) return;

        try {
            setSyncing(true);
            await BackendAPI.ingestFile(selectedItem.id, token);
            alert(`File '${selectedItem.name}' has been queued for ingestion.`);
        } catch (e: any) {
            alert(`Ingest failed: ${e.message}`);
        } finally {
            setSyncing(false);
        }
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

    // Unsync Check
    const targetFolderId = selectedItem ? selectedItem.id : currentFolderId;
    const isMonitored = userProfile?.monitored_folder_ids?.includes(targetFolderId);

    // Determine UI Mode
    const isFolderSelected = selectedItem?.mimeType === "application/vnd.google-apps.folder";
    const isFileSelected = selectedItem && !isFolderSelected;

    return (
        <div className="flex flex-1 h-full overflow-hidden bg-[#09090b] relative">
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
            <div className="w-1/2 border-r border-white/5 flex flex-col relative">
                <div className="p-4 border-b border-white/5 bg-[#13141F] space-y-3">
                    <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2 font-bold text-slate-200">
                            <Cloud size={16} className="text-indigo-400" />
                            <span>Drive Explorer</span>
                        </div>
                        <div className="flex items-center gap-1">
                            {/* Search Bar */}
                            <div className="relative group mr-2">
                                <Search size={14} className="absolute left-2.5 top-2 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
                                <input
                                    type="text"
                                    placeholder="Search Drive..."
                                    className="bg-black/20 border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500 focus:bg-white/5 w-32 focus:w-48 transition-all"
                                    onKeyDown={handleSearch}
                                />
                            </div>
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

                <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin pb-48">
                    {/* Embedded Sync Queue Panel (Bottom of Left Column) */}
                    <div className="absolute bottom-6 left-6 right-6 z-20">
                        <SyncQueuePanel statusData={syncStatus} />
                    </div>
                    {currentFolderId !== 'root' && !searchQuery ? (
                        <div
                            onClick={() => loadFolder('root')}
                            className="flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 cursor-pointer text-slate-400 hover:text-indigo-300 transition-colors"
                        >
                            <span className="text-lg">↩️</span>
                            <span className="text-sm font-medium">Back to Root</span>
                        </div>
                    ) : null}

                    {/* Search Result Mode Warning */}
                    {searchQuery && (
                        <div className="p-3 text-xs text-slate-400 border-b border-white/5 mb-2">
                            Searching for: <span className="text-indigo-300">"{searchQuery}"</span>
                        </div>
                    )}

                    {files?.map(file => {
                        const isFolder = file.mimeType === "application/vnd.google-apps.folder";

                        // Was filtered, now showing all
                        const isSelected = selectedItem?.id === file.id;

                        return (
                            <div
                                key={file.id}
                                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border border-transparent transition-all group ${isSelected
                                    ? "bg-indigo-500/20 border-indigo-500/50 text-white"
                                    : "hover:bg-white/5 text-slate-300"
                                    }`}
                                onClick={() => setSelectedItem({ id: file.id, name: file.name, mimeType: file.mimeType })}
                                onDoubleClick={() => isFolder ? loadFolder(file.id) : null}
                            >
                                {isFolder ? (
                                    <Folder size={18} className={isSelected ? "text-indigo-300 fill-indigo-500/20" : "text-slate-500 group-hover:text-amber-400"} />
                                ) : (
                                    <File size={18} className="text-slate-600 group-hover:text-slate-400" />
                                )}
                                <span className="text-sm truncate flex-1">{file.name}</span>
                                {isSelected && <CheckCircle size={14} className="text-indigo-400" />}
                            </div>
                        );
                    })}

                    {files?.length === 0 && !loading && (
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
                        {isFileSelected ? <File size={32} className="text-white" /> : <Folder size={32} className="text-white" />}
                    </div>

                    <div className="text-center space-y-1">
                        <h2 className="text-xl font-bold text-white truncate">
                            {selectedItem ? selectedItem.name : (currentFolderId === 'root' ? "My Drive (Root)" : "Current Folder")}
                        </h2>
                        <p className="text-xs font-mono text-slate-500 bg-black/30 py-1 px-2 rounded inline-block">
                            ID: {(selectedItem ? selectedItem.id : currentFolderId)?.slice(0, 15)}...
                        </p>
                    </div>

                    {isFolderSelected && (
                        <div className="bg-amber-500/5 border border-amber-500/10 rounded-lg p-3 flex gap-3 text-left">
                            <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
                            <div className="space-y-1">
                                <p className="text-xs font-bold text-amber-500">Privacy Guard™ Active</p>
                                <p className="text-[10px] text-amber-200/60 leading-relaxed">
                                    Only files within this folder will be synced. Personal files outside this scope are ignored.
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Action Buttons based on Type */}
                    {isFileSelected ? (
                        <button
                            onClick={handleIngestFile}
                            disabled={syncing}
                            className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold transition-all shadow-lg hover:shadow-indigo-500/25 active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {syncing ? <RefreshCw className="animate-spin" /> : <CloudUpload size={18} />}
                            {syncing ? "Ingesting..." : "Ingest Single File"}
                        </button>
                    ) : (
                        // Folder Actions
                        <>
                            {isMonitored ? (
                                <button
                                    onClick={handleUnsync}
                                    disabled={syncing}
                                    className="w-full py-3 bg-red-600 hover:bg-red-500 text-white rounded-xl font-bold transition-all shadow-lg hover:shadow-red-500/25 active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed group"
                                >
                                    {syncing ? <RefreshCw className="animate-spin" /> : <Trash2 size={18} className="group-hover:text-red-200" />}
                                    {syncing ? "Stopping..." : "Stop Cloud Sync"}
                                </button>
                            ) : (
                                <button
                                    onClick={handleSync}
                                    disabled={syncing}
                                    className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold transition-all shadow-lg hover:shadow-indigo-500/25 active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {syncing ? <RefreshCw className="animate-spin" /> : <CloudUpload size={18} />}
                                    {syncing ? "Starting..." : "Start Cloud Sync"}
                                </button>
                            )}
                        </>
                    )}

                    {!selectedItem && (
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
