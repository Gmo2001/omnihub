import React, { useState, useEffect, useCallback, memo } from 'react';
import { ConceptNode, DocRecord } from '../types';
import { ActualFolderNode } from '../services/dataService';
import GraphVisualizer from './GraphVisualizer';
import DocDetailDrawer from './DocDetailDrawer';
import { useOmniHub } from '../context/OmniHubContext';
import { Search, Sparkles, ArrowRight, History, CloudUpload, FileSearch, Bot, Loader2, MessageSquare, FolderTree, ChevronRight, ChevronDown, Filter, Database, FileText, Star } from 'lucide-react';

interface RagResponse {
  conclusion: string;
  evidenceSummary: string;
  action: string;
}

export interface VirtualFilterState {
    security: string[];
    status: string[];
    years: string[];
    tags: string[];
}

type LeftTab = 'chat' | 'explorer';

const INITIAL_FOLDER_LIMIT = 8;
const LOAD_MORE_STEP = 20;

// --- MEMOIZED TREE COMPONENTS ---

const TreeDocItem = memo(({ 
    doc, 
    isSelected, 
    onClick 
}: { 
    doc: DocRecord; 
    isSelected: boolean; 
    onClick: (doc: DocRecord) => void;
}) => (
    <div 
        id={`tree-doc-${doc.id}`}
        onClick={() => onClick(doc)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer text-xs transition-all group/doc border border-transparent ${
            isSelected
            ? 'bg-indigo-500/30 text-white border-indigo-500/50 shadow-[0_0_15px_rgba(99,102,241,0.3)] font-bold translate-x-1' 
            : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
        }`}
    >
        <FileText size={12} className={`shrink-0 ${isSelected ? 'text-indigo-300' : 'opacity-40 group-hover/doc:opacity-100'}`} />
        <span className="truncate">{doc.name}</span>
    </div>
));

const TreeFolderItem = memo(({ 
    node, 
    isExpanded, 
    limit, 
    selectedDocId, 
    onToggle, 
    onLoadMore, 
    onDocClick 
}: { 
    node: ActualFolderNode; 
    isExpanded: boolean; 
    limit: number; 
    selectedDocId: string | undefined; 
    onToggle: (name: string, e: React.MouseEvent) => void;
    onLoadMore: (name: string, e: React.MouseEvent) => void;
    onDocClick: (doc: DocRecord) => void;
}) => {
    const visibleDocs = node.docs.slice(0, limit);
    const hasMore = node.docs.length > limit;
    const remaining = node.docs.length - limit;

    return (
        <div className="animate-in fade-in slide-in-from-left-2 duration-200">
            <div 
                onClick={(e) => onToggle(node.folderName, e)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all border border-transparent group ${
                    isExpanded 
                    ? 'bg-amber-500/10 border-amber-500/20 text-amber-100' 
                    : 'hover:bg-white/5 text-slate-300'
                }`}
            >
                <button className="p-0.5 text-slate-500 hover:text-white transition-colors">
                    {isExpanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
                </button>
                
                <Database size={14} className={isExpanded ? "text-amber-400" : "text-slate-600 group-hover:text-amber-500/50"} />
                
                <span className="text-xs font-bold truncate flex-1">{node.folderName}</span>
                <span className="text-[9px] bg-white/10 px-1.5 rounded-full text-slate-400">{node.totalDocs}</span>
            </div>

            {isExpanded && (
                <div className="ml-4 pl-3 border-l border-white/5 mt-1 mb-2 space-y-0.5">
                    {visibleDocs.map(doc => (
                        <TreeDocItem 
                            key={doc.id} 
                            doc={doc} 
                            isSelected={selectedDocId === doc.id} 
                            onClick={onDocClick} 
                        />
                    ))}
                    
                    {hasMore && (
                        <button 
                            onClick={(e) => onLoadMore(node.folderName, e)}
                            className="w-full text-left px-3 py-1.5 text-[10px] text-amber-500/70 hover:text-amber-400 hover:bg-white/5 rounded transition-colors italic font-medium"
                        >
                            + {remaining} more files...
                        </button>
                    )}
                    
                    {node.docs.length === 0 && (
                        <div className="px-3 py-1.5 text-[10px] text-slate-600 italic">Empty folder</div>
                    )}
                </div>
            )}
        </div>
    );
});

const ActualTree = memo(({ 
    treeData, 
    expandedFolders, 
    folderLimits, 
    selectedDocId, 
    onToggleFolder, 
    onLoadMore, 
    onDocClick, 
    searchQuery 
}: {
    treeData: ActualFolderNode[];
    expandedFolders: Set<string>;
    folderLimits: Record<string, number>;
    selectedDocId: string | undefined;
    onToggleFolder: (name: string, e: React.MouseEvent) => void;
    onLoadMore: (name: string, e: React.MouseEvent) => void;
    onDocClick: (doc: DocRecord) => void;
    searchQuery: string;
}) => (
    <div className="space-y-1">
        {treeData.length === 0 && (
            <div className="text-center text-slate-500 text-xs py-8">
                No folders matching "{searchQuery}"
            </div>
        )}
        {treeData.map((node) => (
            <TreeFolderItem
                key={node.folderName}
                node={node}
                isExpanded={expandedFolders.has(node.folderName) || searchQuery.length > 0}
                limit={folderLimits[node.folderName] || INITIAL_FOLDER_LIMIT}
                selectedDocId={selectedDocId}
                onToggle={onToggleFolder}
                onLoadMore={onLoadMore}
                onDocClick={onDocClick}
            />
        ))}
    </div>
));

// --- MAIN COMPONENT ---

const OmniHubTab: React.FC = () => {
  const { 
    docs, concepts, addLog, securityState, reportSecurityEvent, 
    selectedDoc, setSelectedDoc, setActiveCenterId,
    expandedFolders, setExpandedFolders, folderLimits, setFolderLimits,
    treeSearchQuery, setTreeSearchQuery, actualTreeData, scrollToTreeItem,
    handleUpload, isUploading, uploadProgress
  } = useOmniHub();

  const [leftTab, setLeftTab] = useState<LeftTab>('chat');
  const [searchQuery, setSearchQuery] = useState('');
  const [ragResponse, setRagResponse] = useState<RagResponse | null>(null);
  const [viewModeState, setViewModeState] = useState<'default' | 'local' | 'evidence'>('default');
  const [evidenceData, setEvidenceData] = useState<{ docs: DocRecord[], concepts: ConceptNode[] } | null>(null);

  const [virtualFilters, setVirtualFilters] = useState<VirtualFilterState>({
      security: [], status: [], years: [], tags: []
  });

  const [recentSearches, setRecentSearches] = useState([
    "1분기 회계 감사", "2026 보안 규정", "신규 입사자 계약서", "프로젝트A 구매 요청", "컴플라이언스 준수 현황"
  ]);

  const handleLeftTabChange = useCallback((tab: LeftTab) => {
      setLeftTab(tab);
      addLog(`LeftTab changed -> ${tab}`, 'INFO');
  }, [addLog]);

  const handleOpenSampleDoc = useCallback(() => {
    if (docs.length > 0) {
        const randomDoc = docs[Math.floor(Math.random() * 100)];
        setSelectedDoc(randomDoc);
        addLog(`문서 열람 -> ${randomDoc.name}`, 'INFO');
    }
  }, [docs, setSelectedDoc, addLog]);

  const handleDocSelect = useCallback((doc: DocRecord) => {
    if (leftTab !== 'explorer') {
        setLeftTab('explorer');
    }
    setSelectedDoc(doc);
    addLog(doc.ssotRating ? `증거 문서 열람 -> ${doc.name} (${doc.ssotRating.toUpperCase()})` : `문서 선택됨 -> ${doc.name}`, 'INFO');
  }, [leftTab, setSelectedDoc, addLog]);

  // Sync Graph -> Tree
  useEffect(() => {
      if (!selectedDoc) return;
      // Use the robust scrolling mechanism from context
      scrollToTreeItem(selectedDoc.id, selectedDoc.actualPath);
  }, [selectedDoc, scrollToTreeItem]);

  const toggleFolder = useCallback((folderName: string, e?: React.MouseEvent) => {
      if (e) e.stopPropagation();
      setExpandedFolders(prev => {
          const next = new Set(prev);
          if (next.has(folderName)) next.delete(folderName);
          else next.add(folderName);
          return next;
      });
      setFolderLimits(prev => {
          if (!prev[folderName]) return { ...prev, [folderName]: INITIAL_FOLDER_LIMIT };
          return prev;
      });
  }, [setExpandedFolders, setFolderLimits]);

  const handleLoadMore = useCallback((folderName: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setFolderLimits(prev => ({
          ...prev,
          [folderName]: (prev[folderName] || INITIAL_FOLDER_LIMIT) + LOAD_MORE_STEP
      }));
      addLog(`Tree load more -> ${folderName}`, 'INFO');
  }, [setFolderLimits, addLog]);

  const handleTreeDocClick = useCallback((doc: DocRecord) => {
      handleDocSelect(doc);
      setActiveCenterId(doc.id); 
  }, [handleDocSelect, setActiveCenterId]);

  const handleSearch = (query: string) => {
    if (!query.trim()) return;
    addLog(`검색 요청 -> ${query}`, 'INFO');
    reportSecurityEvent('APPROVE'); 
    setRecentSearches(prev => [query, ...prev.filter(s => s !== query)].slice(0, 5));

    const keywords = query.toLowerCase().split(' ').filter(w => w.length > 1);
    const scoredDocs = docs.map(doc => {
        let score = 0;
        const lowerName = doc.name.toLowerCase();
        keywords.forEach(k => { if (lowerName.includes(k)) score += 10; });
        return { ...doc, _score: score + (Math.random() * 10) };
    });

    scoredDocs.sort((a, b) => b._score - a._score);
    const topDocs = scoredDocs.slice(0, 5);
    const evidenceDocs: DocRecord[] = topDocs.map((d, idx) => ({ ...d, ssotRating: idx === 0 ? 'gold' : 'silver' }));
    
    const relevantConceptIds = new Set<string>();
    evidenceDocs.forEach(d => d.conceptIds.forEach(id => relevantConceptIds.add(id)));
    const evidenceConcepts = concepts.filter(c => relevantConceptIds.has(c.id));

    setRagResponse({
        conclusion: `"${query}"에 대한 분석 결과, 가장 신뢰도 높은 문서는 '${topDocs[0].name}' 입니다.`,
        evidenceSummary: `근거 자료: '${topDocs[0].name}' (Gold 등급) 외 ${evidenceDocs.length - 1}건 식별됨.`,
        action: `권장 사항: 문서 소유자(${topDocs[0].owner})에게 최신 버전을 확인하세요.`
    });
    setEvidenceData({ docs: evidenceDocs, concepts: evidenceConcepts });
    setViewModeState('evidence');
  };

  return (
    <div className="flex flex-1 overflow-hidden relative">
      {/* Left Panel */}
      <div className="w-[360px] shrink-0 bg-[#13141F] border-r border-white/5 flex flex-col z-10 shadow-2xl relative transition-all">
        <div className="absolute top-0 right-0 w-full h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-500 opacity-20"></div>

        {/* Tab Navigation */}
        <div className="px-4 pt-4 pb-2">
            <div className="flex bg-white/5 p-1 rounded-xl border border-white/5">
                <button 
                    onClick={() => handleLeftTabChange('chat')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-bold transition-all ${
                        leftTab === 'chat' 
                        ? 'bg-[#1E1F2E] text-white shadow-lg border border-white/5' 
                        : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                    }`}
                >
                    <MessageSquare size={14} /> Chat
                </button>
                <button 
                    onClick={() => handleLeftTabChange('explorer')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-bold transition-all ${
                        leftTab === 'explorer' 
                        ? 'bg-[#1E1F2E] text-white shadow-lg border border-white/5' 
                        : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                    }`}
                >
                    <FolderTree size={14} /> Explorer
                </button>
            </div>
        </div>

        {/* CHAT TAB CONTENT */}
        {leftTab === 'chat' && (
          <>
            <div className="flex-1 p-6 overflow-y-auto flex flex-col scrollbar-thin">
                <div className="mb-6 flex items-center gap-2 text-indigo-400">
                    <Sparkles size={16} className="animate-pulse" />
                    <h2 className="font-bold uppercase tracking-wider text-xs">AI Research Assistant</h2>
                </div>

                {!ragResponse ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center opacity-60 mb-8 space-y-4">
                        <div className="w-20 h-20 bg-white/5 rounded-2xl flex items-center justify-center border border-white/5 shadow-inner">
                            <Bot className="text-slate-400" size={36} />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold text-slate-200">무엇을 도와드릴까요?</h3>
                            <p className="text-sm text-slate-500 mt-2 leading-relaxed max-w-[260px]">
                                자연어로 질문하면 OmniHub 그래프 엔진이<br/>연관된 개념과 증거 문서를 찾아줍니다.
                            </p>
                        </div>
                        <button 
                            onClick={handleOpenSampleDoc}
                            className="mt-4 px-5 py-2.5 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 rounded-lg text-sm font-medium border border-indigo-500/30 transition-all flex items-center gap-2"
                        >
                            <FileSearch size={16} /> 샘플 문서 열기
                        </button>
                    </div>
                ) : (
                    <div className="animate-in fade-in slide-in-from-bottom-2 duration-500 space-y-6">
                        {/* Bot Message */}
                        <div className="flex gap-4">
                            <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-600/20 shrink-0">
                                <Bot size={20} className="text-white" />
                            </div>
                            <div className="space-y-3">
                                <div className="bg-[#1E1F2E] border border-white/5 p-4 rounded-r-xl rounded-bl-xl text-sm text-slate-200 leading-relaxed shadow-lg">
                                    <span className="text-indigo-400 font-bold block mb-1">Conclusion</span>
                                    {ragResponse.conclusion}
                                </div>
                                <div className="bg-[#1E1F2E] border border-white/5 p-4 rounded-r-xl rounded-bl-xl text-sm text-slate-200 leading-relaxed shadow-lg">
                                    <span className="text-emerald-400 font-bold block mb-1">Action Item</span>
                                    {ragResponse.action}
                                </div>
                            </div>
                        </div>
                        
                        {/* Evidence List */}
                        <div className="pl-14">
                            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Evidence Docs</h4>
                            <ul className="space-y-2">
                                {evidenceData?.docs.map(doc => (
                                    <li key={doc.id} 
                                        onClick={() => handleDocSelect(doc)}
                                        className="flex items-center gap-3 p-3 rounded-lg bg-white/5 hover:bg-white/10 cursor-pointer border border-transparent hover:border-indigo-500/30 transition-all group"
                                    >
                                        <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center text-lg shadow-inner">
                                            {doc.ssotRating ? (
                                                <Star 
                                                    size={16} 
                                                    className={doc.ssotRating === 'gold' ? "fill-amber-400 text-amber-400" : "fill-slate-400 text-slate-400"} 
                                                />
                                            ) : (
                                                <FileText size={16} className="text-slate-500"/>
                                            )}
                                        </div>
                                        <div className="flex flex-col min-w-0">
                                            <span className="text-sm text-slate-200 truncate group-hover:text-indigo-300 font-medium transition-colors">{doc.name}</span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-[10px] text-slate-500">{new Date(doc.updatedAt).toLocaleDateString()}</span>
                                                {doc.ssotRating && <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold border ${
                                                    doc.ssotRating === 'gold' 
                                                    ? "bg-amber-500/20 text-amber-400 border-amber-500/20" 
                                                    : "bg-slate-500/20 text-slate-400 border-slate-500/20"
                                                }`}>SSOT</span>}
                                            </div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                )}

                <div className="mt-auto pt-6 border-t border-white/5">
                    <div className="flex items-center gap-2 text-[10px] font-bold text-slate-500 mb-3 uppercase tracking-widest">
                        <History size={12} /> Recent Queries
                    </div>
                    <div className="space-y-1">
                        {recentSearches.map((item, idx) => (
                            <button 
                                key={idx} 
                                onClick={() => { setSearchQuery(item); handleSearch(item); }}
                                className="w-full text-left group flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/5 transition-colors"
                            >
                                <span className="text-xs text-slate-400 group-hover:text-slate-200 truncate">{item}</span>
                                <ArrowRight size={12} className="text-indigo-400 opacity-0 group-hover:opacity-100 transition-all -translate-x-2 group-hover:translate-x-0" />
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Input Area */}
            <div className="p-5 border-t border-white/5 bg-[#13141F]/95 backdrop-blur">
                <div className="relative group">
                    <input 
                        type="text" 
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch(searchQuery)}
                        placeholder="Ask OmniHub..." 
                        className="w-full bg-[#1E1F2E] border border-white/10 text-slate-100 pl-11 pr-12 py-3.5 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all text-sm shadow-inner placeholder-slate-600 group-hover:border-white/20"
                    />
                    <Search className="absolute left-3.5 top-3.5 text-slate-500 group-focus-within:text-indigo-400 transition-colors" size={20} />
                    <button 
                        onClick={() => handleSearch(searchQuery)}
                        className="absolute right-2 top-2 bg-indigo-600 hover:bg-indigo-500 p-1.5 rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
                    >
                        <ArrowRight size={18} className="text-white"/>
                    </button>
                </div>
            </div>
          </>
        )}

        {/* EXPLORER TAB CONTENT - ACTUAL TREE */}
        {leftTab === 'explorer' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden">
                <div className="px-6 pt-6 pb-2 shrink-0">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2 text-amber-400">
                            <FolderTree size={16} />
                            <h2 className="font-bold uppercase tracking-wider text-xs">
                                Actual File System
                            </h2>
                        </div>
                    </div>
                    
                    {/* Tree Search Input */}
                    <div className="relative group mb-4">
                        <input 
                            type="text" 
                            value={treeSearchQuery}
                            onChange={(e) => setTreeSearchQuery(e.target.value)}
                            placeholder="Filter folders or files..."
                            className="w-full bg-[#050508] border border-white/10 text-slate-200 pl-8 pr-4 py-2 rounded-lg text-xs focus:outline-none focus:border-amber-500/50 transition-all placeholder-slate-600"
                        />
                        <Filter className="absolute left-2.5 top-2.5 text-slate-500" size={12} />
                    </div>
                </div>
                
                <div className="flex-1 overflow-y-auto px-4 pb-6 scrollbar-thin">
                    <ActualTree 
                        treeData={actualTreeData}
                        expandedFolders={expandedFolders}
                        folderLimits={folderLimits}
                        selectedDocId={selectedDoc?.id}
                        onToggleFolder={toggleFolder}
                        onLoadMore={handleLoadMore}
                        onDocClick={handleTreeDocClick}
                        searchQuery={treeSearchQuery}
                    />
                </div>
                
                {/* Footer Info */}
                <div className="px-6 py-3 border-t border-white/5 bg-[#0e0e12] text-[10px] text-slate-500 flex justify-between items-center shrink-0">
                    <span className="flex items-center gap-1">
                        <Database size={10} /> 
                        Total: <span className="text-slate-300 font-mono">{docs.length}</span> files
                    </span>
                    <span className="opacity-50">v1.0.0</span>
                </div>
             </div>
        )}
      </div>

      {/* Right Panel: Graph */}
      <div className="flex-1 bg-[#050508] relative overflow-hidden flex flex-col">
        {/* Upload Button */}
        <div className="absolute top-6 right-6 z-10">
            {isUploading ? (
                <div className="flex items-center gap-4 bg-[#1E1F2E]/90 backdrop-blur px-5 py-3 rounded-xl border border-indigo-500/50 shadow-2xl min-w-[240px]">
                    <Loader2 size={20} className="text-indigo-400 animate-spin" />
                    <div className="flex-1">
                         <div className="flex justify-between text-xs font-bold text-indigo-200 mb-1.5">
                            <span>INGESTING...</span>
                            <span>{uploadProgress}%</span>
                         </div>
                         <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                             <div className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-150" style={{ width: `${uploadProgress}%` }}></div>
                         </div>
                    </div>
                </div>
            ) : (
                <button 
                    onClick={() => handleUpload()}
                    className="group flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl border border-indigo-500 shadow-lg shadow-indigo-600/20 text-sm font-bold transition-all hover:scale-105 active:scale-95"
                >
                    <CloudUpload size={18} className="group-hover:animate-bounce" />
                    Upload Data
                </button>
            )}
        </div>

        {/* Graph Canvas */}
        <div className="flex-1 relative">
            <GraphVisualizer 
                viewModeState={viewModeState}
                evidenceData={evidenceData}
                virtualFilters={virtualFilters}
            />
            {selectedDoc && (
                <DocDetailDrawer />
            )}
        </div>
      </div>
    </div>
  );
};

export default OmniHubTab;