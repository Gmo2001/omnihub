import React, { useState } from 'react';
import { AIService } from '../../services/aiService';
import { RAGResponse, Citation } from '../../types';
import { Search, Loader2, FileText, ExternalLink } from 'lucide-react';

interface Props {
    onCitationClick: (docId: string) => void;
}

const RAGSearchPanel: React.FC<Props> = ({ onCitationClick }) => {
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<RAGResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!query.trim()) return;

        setLoading(true);
        setError(null);
        try {
            const data = await AIService.searchRAG(query);
            setResult(data);
        } catch (err: any) {
            setError(err.message || "Search failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#1E1F2E] border-l border-white/5">
            <div className="p-4 border-b border-white/5">
                <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                    <Search size={20} className="text-indigo-400" />
                    AI 기반 검색
                </h2>
                <div className="relative">
                    <textarea
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSearch(e as any);
                            }
                        }}
                        placeholder="규정이나 문서 내용을 물어보세요... (Shift+Enter for new line)"
                        className="w-full bg-[#09090b] border border-white/10 rounded-xl px-4 py-3 pr-12 text-slate-200 focus:outline-none focus:border-indigo-500 transition-colors resize-none scrollbar-thin scrollbar-thumb-white/10 min-h-[80px] max-h-[200px]"
                    />
                    <button
                        onClick={(e) => handleSearch(e as any)}
                        disabled={loading || !query.trim()}
                        className="absolute right-3 bottom-3 p-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg disabled:opacity-50 disabled:bg-transparent disabled:text-slate-500 transition-all"
                    >
                        {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-thin scrollbar-thumb-white/10">
                {error && (
                    <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                        {error}
                    </div>
                )}

                {result && (
                    <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                        {/* Answer Section */}
                        <div className="mb-6">
                            <h3 className="text-sm font-semibold text-slate-400 mb-2 uppercase tracking-wider">AI 답변</h3>
                            <div className="bg-[#09090b]/50 rounded-xl p-4 text-slate-200 leading-relaxed border border-white/5 whitespace-pre-wrap">
                                {result.answer}
                            </div>
                        </div>

                        {/* Citations Section */}
                        {result.citations.length > 0 && (
                            <div>
                                <h3 className="text-sm font-semibold text-slate-400 mb-2 uppercase tracking-wider">
                                    참조 문서 ({result.citations.length})
                                </h3>
                                <div className="space-y-2">
                                    {result.citations.map((cit) => (
                                        <div
                                            key={cit.idx}
                                            onClick={() => onCitationClick(cit.doc_id)}
                                            className="group p-3 bg-white/5 hover:bg-white/10 rounded-lg border border-white/5 hover:border-indigo-500/30 transition-all cursor-pointer"
                                        >
                                            <div className="flex items-start gap-3">
                                                <div className="w-5 h-5 rounded bg-indigo-500/20 text-indigo-400 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                                                    {cit.idx}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <h4 className="text-sm font-medium text-indigo-300 group-hover:text-indigo-200 truncate mb-1">
                                                        {cit.title || "제목 없음"}
                                                    </h4>
                                                    <p className="text-xs text-slate-400 line-clamp-2">
                                                        {cit.snippet}
                                                    </p>
                                                    <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-500">
                                                        <span className="flex items-center gap-1">
                                                            <FileText size={10} /> Page {cit.page || '?'}
                                                        </span>
                                                        {cit.source_link && (
                                                            <a
                                                                href={cit.source_link}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                onClick={(e) => e.stopPropagation()}
                                                                className="hover:text-indigo-400 flex items-center gap-0.5"
                                                            >
                                                                <ExternalLink size={10} /> 원문 보기
                                                            </a>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mt-8 pt-4 border-t border-white/5 flex gap-4 text-[10px] text-slate-600 font-mono">
                            <span>Model: {result.meta?.model_version}</span>
                            <span>Latency: {result.meta?.latency_ms}ms</span>
                        </div>
                    </div>
                )}

                {!result && !loading && !error && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-600 gap-4 opacity-50">
                        <Search size={48} strokeWidth={1} />
                        <p className="text-sm">검색어를 입력하면 AI가 답변을 생성합니다.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default RAGSearchPanel;
