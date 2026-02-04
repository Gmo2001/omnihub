import React, { useState, useEffect } from 'react';
import { AIService } from '../../services/aiService';
import { TreeResponse, FolderNode, FileNode } from '../../types';
import { Folder, FileText, ChevronRight, ChevronDown, FolderOpen } from 'lucide-react';

interface Props {
    onFileClick: (docId: string) => void;
}

const TreeNode: React.FC<{
    path: string;
    name: string;
    type: 'folder' | 'file';
    docId?: string;
    level: number;
    onFileClick: (id: string) => void;
}> = ({ path, name, type, docId, level, onFileClick }) => {
    const [expanded, setExpanded] = useState(false);
    const [data, setData] = useState<TreeResponse | null>(null);
    const [loading, setLoading] = useState(false);

    const handleExpand = async (e: React.MouseEvent) => {
        e.stopPropagation();
        if (type === 'file') {
            if (docId) onFileClick(docId);
            return;
        }

        if (expanded) {
            setExpanded(false);
        } else {
            setExpanded(true);
            if (!data) {
                setLoading(true);
                try {
                    const res = await AIService.getTreeStructure(path);
                    setData(res);
                } catch (err) {
                    console.error(err);
                } finally {
                    setLoading(false);
                }
            }
        }
    };

    return (
        <div className="select-none">
            <div
                className={`flex items-center gap-2 py-1.5 px-2 hover:bg-white/5 rounded-lg cursor-pointer transition-colors ${expanded ? 'text-white' : 'text-slate-400 hover:text-slate-200'}`}
                style={{ paddingLeft: `${level * 12 + 8}px` }}
                onClick={handleExpand}
            >
                {type === 'folder' && (
                    <span className="text-slate-600">
                        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </span>
                )}
                {type === 'folder' ? (
                    expanded ? <FolderOpen size={16} className="text-indigo-400" /> : <Folder size={16} className="text-indigo-500/80" />
                ) : (
                    <FileText size={16} className="text-emerald-500/80" />
                )}
                <span className="text-sm truncate">{name}</span>
            </div>

            {expanded && data && (
                <div className="animate-in slide-in-from-top-1 duration-200">
                    {data.folders.map(f => (
                        <TreeNode
                            key={f.path}
                            path={f.path}
                            name={f.name}
                            type="folder"
                            level={level + 1}
                            onFileClick={onFileClick}
                        />
                    ))}
                    {data.files.map(f => (
                        <TreeNode
                            key={f.doc_id}
                            path=""
                            name={f.name}
                            type="file"
                            docId={f.doc_id}
                            level={level + 1}
                            onFileClick={onFileClick}
                        />
                    ))}
                    {data.folders.length === 0 && data.files.length === 0 && (
                        <div className="py-1 px-4 text-xs text-slate-600 italic" style={{ paddingLeft: `${(level + 1) * 12 + 20}px` }}>
                            (Empty)
                        </div>
                    )}
                </div>
            )}
            {expanded && loading && (
                <div className="py-1 px-4 text-xs text-slate-600 animate-pulse" style={{ paddingLeft: `${(level + 1) * 12 + 20}px` }}>
                    Loading...
                </div>
            )}
        </div>
    );
};

const DocTreeBrowser: React.FC<Props> = ({ onFileClick }) => {
    // Root level
    return (
        <div className="h-full bg-[#09090b] border-r border-white/5 flex flex-col">
            <div className="p-4 border-b border-white/5 font-bold text-slate-300 text-sm flex items-center gap-2">
                <FolderOpen size={18} className="text-indigo-500" />
                문서 탐색기
            </div>
            <div className="flex-1 overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-white/10">
                <TreeNode
                    path="/"
                    name="Root"
                    type="folder"
                    onFileClick={onFileClick}
                    level={0}
                />
            </div>
        </div>
    );
};

export default DocTreeBrowser;
