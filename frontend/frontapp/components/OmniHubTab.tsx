import React, { useState } from 'react';
import { useOmniHub } from '../context/OmniHubContext'; // Keep for Upload/Global status
import { MessageSquare, FolderTree } from 'lucide-react';

// New AI Components
import RAGSearchPanel from './AI/RAGSearchPanel';
import DocTreeBrowser from './AI/DocTreeBrowser';
import KnowledgeGraph from './AI/KnowledgeGraph';
import DocCardView from './AI/DocCardView';
import SyncQueuePanel from './SyncQueuePanel';

type LeftTab = 'chat' | 'explorer';

const OmniHubTab: React.FC = () => {
    const [leftTab, setLeftTab] = useState<LeftTab>('chat');
    const { aiStatus, syncStatusData } = useOmniHub();
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

    return (
        <div className="flex flex-1 overflow-hidden relative">
            {/* Left Panel */}
            <div className="w-[360px] shrink-0 bg-[#13141F] border-r border-white/5 flex flex-col z-10 shadow-2xl relative">

                {/* Tab Navigation */}
                <div className="px-4 pt-4 pb-2 bg-[#13141F]">
                    <div className="flex bg-white/5 p-1 rounded-xl border border-white/5">
                        <button
                            onClick={() => setLeftTab('chat')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${leftTab === 'chat'
                                ? 'bg-[#1E1F2E] text-white shadow-lg border border-white/5'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                                }`}
                        >
                            <MessageSquare size={14} /> AI Chat
                        </button>
                        <button
                            onClick={() => setLeftTab('explorer')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${leftTab === 'explorer'
                                ? 'bg-[#1E1F2E] text-white shadow-lg border border-white/5'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                                }`}
                        >
                            <FolderTree size={14} /> Docs Tree
                        </button>
                    </div>
                </div>

                {/* Left Content */}
                <div className="flex-1 overflow-hidden relative">
                    {leftTab === 'chat' ? (
                        <>
                            <RAGSearchPanel onCitationClick={(id) => setSelectedDocId(id)} />

                            {/* Sync Active Queue */}
                            <SyncQueuePanel statusData={syncStatusData} />

                            {/* Status Legend */}
                            {(aiStatus === 'completed' || aiStatus === 'idle') && (
                                <div className="mx-6 mt-4 p-4 bg-white/5 rounded-xl border border-white/5 space-y-2">
                                    <h4 className="text-[10px] uppercase font-bold text-slate-400 tracking-wider mb-2">Sync Status Guide</h4>
                                    <div className="flex items-center gap-2 text-[10px] text-slate-300">
                                        <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                                        <span>Success: Processed & Analyzed</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-[10px] text-slate-300">
                                        <div className="w-2 h-2 rounded-full bg-slate-500"></div>
                                        <span>Skipped: Unchanged (Optimization)</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-[10px] text-slate-300">
                                        <div className="w-2 h-2 rounded-full bg-red-500"></div>
                                        <span>Failed: Unsupported Format (e.g. Sheet)</span>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <DocTreeBrowser onFileClick={(id) => setSelectedDocId(id)} />
                    )}
                </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 bg-[#09090b] relative overflow-hidden flex flex-col">

                {/* Loading State: Syncing */}
                {aiStatus === 'syncing' && (
                    <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-[#09090b]/90 backdrop-blur-md">
                        <div className="relative w-24 h-24 mb-6">
                            <div className="absolute inset-0 border-4 border-t-indigo-500 border-r-transparent border-b-purple-500 border-l-transparent rounded-full animate-spin"></div>
                            <div className="absolute inset-2 border-4 border-t-transparent border-r-blue-500 border-b-transparent border-l-cyan-500 rounded-full animate-spin reverse"></div>
                        </div>
                        <h3 className="text-2xl font-bold text-white tracking-widest animate-pulse">SYNCING FILES</h3>
                        <p className="text-slate-400 mt-2 font-mono text-sm">Ingesting data from Google Drive...</p>
                        <p className="text-white/20 text-[10px] mt-8 font-light tracking-wide">
                            Server continues processing strictly even if you navigate away.
                        </p>
                    </div>
                )}

                {/* Loading State: Analyzing */}
                {aiStatus === 'analyzing' && (
                    <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-[#09090b]/90 backdrop-blur-md">
                        <div className="flex items-center gap-1 mb-6">
                            <div className="w-2 h-16 bg-indigo-500 animate-[height_1s_ease-in-out_infinite]"></div>
                            <div className="w-2 h-24 bg-purple-500 animate-[height_1s_ease-in-out_infinite_0.2s]"></div>
                            <div className="w-2 h-12 bg-pink-500 animate-[height_1s_ease-in-out_infinite_0.4s]"></div>
                        </div>
                        <h3 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
                            REFINING KNOWLEDGE
                        </h3>
                        <p className="text-slate-500 mt-2 font-mono text-xs">Injecting vectors into Graph DB...</p>
                        <p className="text-white/20 text-[10px] mt-8 font-light tracking-wide">
                            Background analysis persists safely on the server.
                        </p>
                    </div>
                )}

                {/* Default State: Show Graph Only when Ready or Mocked */}
                {(aiStatus === 'completed' || aiStatus === 'idle') && (
                    <>
                        <KnowledgeGraph />
                    </>
                )}

                {/* Doc Detail Overlay */}
                {selectedDocId && (
                    <div className="absolute top-0 right-0 w-[450px] h-full shadow-2xl z-20 border-l border-white/10">
                        <DocCardView docId={selectedDocId} onClose={() => setSelectedDocId(null)} />
                    </div>
                )}
            </div>
        </div>
    );
};

export default OmniHubTab;