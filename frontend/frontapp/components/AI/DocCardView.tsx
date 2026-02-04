import React, { useEffect, useState } from 'react';
import { AIService } from '../../services/aiService';
import { DocCard } from '../../types';
import { X, FileText, Calendar, Shield, ExternalLink, Network } from 'lucide-react';

interface Props {
    docId: string;
    onClose: () => void;
}

const DocCardView: React.FC<Props> = ({ docId, onClose }) => {
    const [doc, setDoc] = useState<DocCard | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        loadDoc();
    }, [docId]);

    const loadDoc = async () => {
        setLoading(true);
        try {
            const data = await AIService.getDocCard(docId);
            setDoc(data);
        } catch (err) {
            setError("Failed to load document card.");
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center text-indigo-400">
                <div className="animate-spin w-8 h-8 border-2 border-current border-t-transparent rounded-full"></div>
            </div>
        );
    }

    if (error || !doc) {
        return (
            <div className="p-6 text-center text-red-400">
                <p>{error || "Document not found"}</p>
                <button onClick={onClose} className="mt-4 text-sm underline">Close</button>
            </div>
        );
    }

    return (
        <div className="h-full bg-[#09090b] flex flex-col overflow-hidden relative animate-in slide-in-from-right duration-300">
            {/* Header */}
            <div className="p-6 border-b border-white/10 flex items-start justify-between bg-white/5">
                <div>
                    <div className="flex items-center gap-2 text-indigo-400 mb-2 text-xs font-mono uppercase tracking-wider">
                        <FileText size={14} /> DOCUMENT CARD
                    </div>
                    <h2 className="text-xl font-bold text-white leading-tight">{doc.title || "Untitled Document"}</h2>
                </div>
                <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full text-slate-400 hover:text-white transition-colors">
                    <X size={20} />
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-8 scrollbar-thin scrollbar-thumb-white/10">

                {/* Meta Grid */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-1">
                        <span className="text-slate-500 text-xs block">Last Revised</span>
                        <div className="text-slate-200 flex items-center gap-2">
                            <Calendar size={14} className="text-slate-400" />
                            {doc.modified_time?.substring(0, 10) || 'Unknown'}
                        </div>
                    </div>
                    <div className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-1">
                        <span className="text-slate-500 text-xs block">Security Level</span>
                        <div className="text-slate-200 flex items-center gap-2">
                            <Shield size={14} className={doc.policy?.security_level === 'high' ? 'text-red-400' : 'text-emerald-400'} />
                            <span className="capitalize">{doc.policy?.security_level || 'Normal'}</span>
                        </div>
                    </div>
                </div>

                {/* AI Summary Card (L1/L2/L3) */}
                {doc.card && (
                    <div className="space-y-4">
                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider">AI Summary</h3>
                        <div className="bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 rounded-2xl p-5 space-y-4">
                            {doc.card.l1 && (
                                <div>
                                    <span className="text-indigo-400 text-xs font-bold mb-1 block">ONE LINE</span>
                                    <p className="text-lg font-medium text-white">{doc.card.l1}</p>
                                </div>
                            )}
                            {doc.card.l2 && (
                                <div>
                                    <span className="text-indigo-400 text-xs font-bold mb-1 block">KEY POINTS</span>
                                    <p className="text-slate-300 leading-relaxed">{doc.card.l2}</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Concepts */}
                {doc.concepts && doc.concepts.length > 0 && (
                    <div className="space-y-3">
                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                            <Network size={16} /> Related Concepts
                        </h3>
                        <div className="flex flex-wrap gap-2">
                            {doc.concepts.map((c, i) => (
                                <span key={i} className="px-3 py-1 bg-slate-800 rounded-full text-sm text-slate-300 border border-white/5">
                                    #{c}
                                </span>
                            ))}
                        </div>
                    </div>
                )}

                {/* Evidence / Excerpts */}
                {doc.evidence && doc.evidence.length > 0 && (
                    <div className="space-y-3">
                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider">Key Evidence</h3>
                        <div className="space-y-3">
                            {doc.evidence.map((ev, i) => (
                                <div key={i} className="p-4 bg-[#1E1F2E] rounded-xl border-l-2 border-indigo-500">
                                    <p className="text-slate-300 text-sm italic">"{ev.snippet}"</p>
                                    <div className="mt-2 text-xs text-slate-500 flex justify-end">
                                        Page {ev.page}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Footer Actions */}
                {doc.source_link && (
                    <div className="pt-6 border-t border-white/10">
                        <a
                            href={doc.source_link}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center justify-center gap-2 w-full py-3 bg-white/5 hover:bg-white/10 text-white rounded-xl font-medium transition-colors"
                        >
                            <ExternalLink size={18} /> Open Original Document
                        </a>
                    </div>
                )}

            </div>
        </div>
    );
};

export default DocCardView;
