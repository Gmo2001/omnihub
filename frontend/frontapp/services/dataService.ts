
import { ConceptNode, DocRecord, Role, SecurityLevel } from '../types';

// --- Constants ---
const API_BASE_URL = 'http://localhost:8000'; // Helper for dev

export interface VersionMeta {
    versionNumber?: number;
    versionStatus?: 'final' | 'approved' | 'revised' | 'draft' | null;
    rawTokens: string[];
}

// --- Version Regex & Logic ---
const REGEX_VER_NUM = /\b(v|ver|version|rev|re|r)[\s._-]*(\d{1,3})\b/gi;
const REGEX_STATUS_FINAL = /(final|finalized|definitive|최종(본|안)?|확정(본|안)?|완료본|제출본)/gi;
const REGEX_STATUS_APPROVED = /(approved|signed|executed|승인(본)?|서명(본)?|날인(본)?|결재(완료)?)/gi;
const REGEX_STATUS_REVISED = /(update(d)?|revis(ed|ion)?|수정(본|안)?|재수정(본)?|변경(본)?|개정(본)?)/gi;
const REGEX_STATUS_DRAFT = /(draft|tmp|temp|초안|초본|임시(본)?|작업본|검토본|내부용)/gi;
const REGEX_DATE_PREFIX = /^\d{4}([._-]?\d{2}){0,2}[._-]?/;
const REGEX_BRACKET_PREFIX = /^\s*[\[\(].*?[\]\)]\s*/;

export const extractVersionMeta = (fileName: string): VersionMeta => {
    const rawTokens: string[] = [];
    let versionNumber: number | undefined;
    let versionStatus: VersionMeta['versionStatus'] = null;

    const verMatch = Array.from(fileName.matchAll(REGEX_VER_NUM));
    if (verMatch.length > 0) {
        const lastMatch = verMatch[verMatch.length - 1];
        versionNumber = parseInt(lastMatch[2], 10);
        rawTokens.push(lastMatch[0]);
    }

    if (fileName.match(REGEX_STATUS_FINAL)) versionStatus = 'final';
    else if (fileName.match(REGEX_STATUS_APPROVED)) versionStatus = 'approved';
    else if (fileName.match(REGEX_STATUS_REVISED)) versionStatus = 'revised';
    else if (fileName.match(REGEX_STATUS_DRAFT)) versionStatus = 'draft';

    return { versionNumber, versionStatus, rawTokens };
};

export const computeGroupKey = (fileName: string): string => {
    let base = fileName.replace(/\.[^/.]+$/, "");
    base = base.replace(REGEX_BRACKET_PREFIX, "");
    base = base.replace(REGEX_DATE_PREFIX, "");
    base = base.replace(REGEX_VER_NUM, "");
    base = base.replace(REGEX_STATUS_FINAL, "");
    base = base.replace(REGEX_STATUS_APPROVED, "");
    base = base.replace(REGEX_STATUS_REVISED, "");
    base = base.replace(REGEX_STATUS_DRAFT, "");
    base = base.replace(/[._\-]+/g, " ");
    return base.trim().toLowerCase();
};

const versionSort = (a: DocRecord, b: DocRecord) => {
    const metaA = extractVersionMeta(a.name);
    const metaB = extractVersionMeta(b.name);
    const statusScore = (s: string | null | undefined) => {
        if (s === 'final') return 4;
        if (s === 'approved') return 3;
        if (s === 'revised') return 2;
        if (s === 'draft') return 1;
        return 0;
    };
    const sA = statusScore(metaA.versionStatus);
    const sB = statusScore(metaB.versionStatus);
    if (sA !== sB) return sB - sA;
    const vA = metaA.versionNumber || 0;
    const vB = metaB.versionNumber || 0;
    if (vA !== vB) return vB - vA;
    return b.updatedAt - a.updatedAt;
};

export const getVersionRangeText = (docs: DocRecord[]): string => {
    if (docs.length === 0) return '';
    const sorted = [...docs].sort(versionSort);
    const representative = sorted[0];
    const repMeta = extractVersionMeta(representative.name);
    const repText = repMeta.versionStatus ? repMeta.versionStatus.toUpperCase() : (repMeta.versionNumber ? `v${repMeta.versionNumber}` : 'Latest');
    const others = sorted.slice(1);
    const oldest = others[others.length - 1];
    if (!oldest) return repText;
    const oldMeta = extractVersionMeta(oldest.name);
    const oldText = oldMeta.versionNumber ? `v${oldMeta.versionNumber}` : (oldMeta.versionStatus || 'v1');
    return `${oldText} ~ ${repText}`;
};

export interface GroupedDocs {
    groups: Record<string, DocRecord[]>;
    singles: DocRecord[];
}

export const groupDocsByVersion = (docs: DocRecord[]): GroupedDocs => {
    const groups: Record<string, DocRecord[]> = {};
    const singles: DocRecord[] = [];
    const tempMap: Record<string, DocRecord[]> = {};
    docs.forEach(doc => {
        const base = computeGroupKey(doc.name);
        if (base.length < 2) {
            singles.push(doc);
            return;
        }
        if (!tempMap[base]) tempMap[base] = [];
        tempMap[base].push(doc);
    });
    Object.entries(tempMap).forEach(([key, list]) => {
        if (list.length >= 2) {
            groups[key] = list.sort(versionSort);
        } else {
            singles.push(...list);
        }
    });
    return { groups, singles };
};

// --- Normalization Logic (SSOT) ---

const normalizeDoc = (raw: any): DocRecord => {
    // If raw is already normalized-ish or comes from Firestore directly
    const sizeKB = raw.size ? parseInt(raw.size) / 1024 : 0;
    const tags = Array.isArray(raw.tags) ? raw.tags : [];

    // Concept IDs mapping
    const conceptIds = Array.isArray(raw.concept_ids) ? raw.concept_ids : (Array.isArray(raw.conceptIds) ? raw.conceptIds : []);

    // Security Level Mapping
    let sec: SecurityLevel = 'medium';
    if (raw.securityLevel || raw.security_level) {
        const lower = (raw.securityLevel || raw.security_level).toLowerCase();
        if (lower === 'high' || lower === 'critical') sec = 'high';
        else if (lower === 'low' || lower === 'public') sec = 'low';
    }

    // Name Resolution (Critical for "unknown.pdf" fix)
    // Backend might return: title, name, or filename
    const name = raw.title || raw.name || raw.filename || "Untitled Doc.pdf";

    return {
        id: String(raw.id || `unknown-${Math.random().toString(36).substr(2, 9)}`),
        name: name,
        driveUrl: raw.webViewLink || raw.drive_url || "#",
        folderPath: raw.virtual_path || raw.folderPath || "Unclassified/General",
        actualPath: raw.actual_path || raw.actualPath || "99_Unsorted",
        tags: tags,
        period: raw.period || "2024-Q1",
        owner: (raw.owners && raw.owners[0] && (raw.owners[0].displayName || raw.owners[0].email)) || raw.owner || "Unknown",
        updatedAt: raw.modifiedTime ? new Date(raw.modifiedTime).getTime() : (raw.updated_at ? new Date(raw.updated_at).getTime() : Date.now()),
        sizeKB: sizeKB,
        ext: raw.ext || 'pdf',
        security: sec,
        aiSummary3: raw.aiSummary || raw.ai_summary || ["AI 요약 정보가 없습니다."],
        textExcerpt: raw.snippet || raw.textExcerpt || "내용 미리보기가 없습니다.",
        conceptIds: conceptIds,
        status: raw.status || 'idle',
        relatedFolderPaths: []
    };
};

const normalizeConcept = (raw: any): ConceptNode => {
    return {
        id: raw.id,
        label: raw.label || raw.name || "Unknown Concept",
        createdAt: raw.created_at ? new Date(raw.created_at).getTime() : Date.now()
    };
};

// --- API Implementation ---

export interface ChatRequest {
    question: string;
    filters?: any;
    topK?: number;
}

export interface ChatResponse {
    answer: string;
    citations: any[];
    action_item?: string;
}

export const OmniHubAPI = {
    // 1. Initial Data Load
    fetchInitialData: async () => {
        try {
            console.log("Fetching /api/initial-data...");
            // Use relative path to let proxy or same-origin handle it, or use absolute if needed.
            // Assuming localhost:8000 for dev based on user prompt.
            const res = await fetch(`${API_BASE_URL}/api/initial-data`);
            if (!res.ok) throw new Error(`API Error: ${res.status}`);
            const data = await res.json();

            // Expected schema: { docs: [], concepts: [] }
            const docs = (data.docs || []).map(normalizeDoc);
            const concepts = (data.concepts || []).map(normalizeConcept);

            return { docs, concepts, logMsg: `Loaded ${docs.length} docs & ${concepts.length} concepts from Firestore` };
        } catch (e) {
            console.warn("Initial data fetch failed, using minimal fallback", e);
            // Fallback for Dev/Offline
            const fallbackConcepts: ConceptNode[] = [{ id: 'c1', label: '오프라인_모드', createdAt: Date.now() }];
            const fallbackDocs: DocRecord[] = [{
                id: 'd1', name: 'Please_Check_Backend.pdf', driveUrl: '#', folderPath: 'System', actualPath: '00_System',
                tags: ['Error'], period: '2026', owner: 'system', updatedAt: Date.now(), sizeKB: 0, ext: 'pdf',
                security: 'low', aiSummary3: ['백엔드 연결 실패', 'API 서버 확인 필요'], textExcerpt: 'Failed to connect to API.',
                conceptIds: ['c1'], status: 'idle', relatedFolderPaths: []
            }];
            return { docs: fallbackDocs, concepts: fallbackConcepts, logMsg: "API Error: Switched to Fallback Mode" };
        }
    },

    // 2. Chat
    chat: async (question: string, topK: number = 8): Promise<ChatResponse | null> => {
        try {
            const body: ChatRequest = { question, topK };
            const res = await fetch(`${API_BASE_URL}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error(`Chat API Error: ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error("Chat API failed", e);
            return null;
        }
    },

    // 3. Evidence Graph
    searchEvidence: async (question: string, topK: number = 8) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/graph/evidence?question=${encodeURIComponent(question)}&topK=${topK}`);
            if (!res.ok) throw new Error(`Evidence API Error: ${res.status}`);
            const data = await res.json();

            const docs = (data.docs || []).map(normalizeDoc);
            const concepts = (data.concepts || []).map(normalizeConcept);

            // Backend citations: { doc_id, page, snippet, score, ... }
            return {
                docs,
                concepts,
                citations: data.citations || []
            };

        } catch (e) {
            console.error("Evidence search failed", e);
            return null;
        }
    },

    // 4. Chunk Retrieval
    getDocChunks: async (docId: string) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/docs/${docId}/chunks`);
            if (!res.ok) throw new Error(`Chunk API Error: ${res.status}`);
            return await res.json(); // Returns { chunks: [] }
        } catch (e) {
            console.error("Chunk fetch failed", e);
            // Fallback for demo
            return {
                chunks: [
                    { id: 'ch1', page: 1, snippet: "This is a fallback snippet because backend is not reachable.", tags: ['Fallback'], security: 'low' },
                    { id: 'ch2', page: 3, snippet: "Another snippet showing where this concept appears.", tags: ['Evidence'], security: 'medium' }
                ]
            };
        }
    },

    uploadDocument: async (doc: DocRecord) => {
        // Still Mock or implement actual upload if backend supports
        // const res = await fetch(`${API_BASE_URL}/api/docs`, { method: 'POST', body: ... });
        await new Promise(r => setTimeout(r, 1000));
        return { success: true, doc };
    },

    updateDocumentStatus: async (id: string, status: string) => {
        // E.g. PATCH /api/docs/:id
        try {
            // await fetch(`${API_BASE_URL}/api/docs/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
            console.log(`[TODO] Backend Patch: Doc ${id} -> ${status}`);
            await new Promise(r => setTimeout(r, 500));
            return { success: true, id, status };
        } catch (e) {
            console.warn("Update failed", e);
            throw e;
        }
    }
};

export const generateUniqueName = (baseName: string, existingDocs: DocRecord[]): string => {
    let name = baseName;
    let counter = 2;
    while (existingDocs.some(d => d.name === name)) {
        name = baseName.replace('.pdf', `_(${counter}).pdf`);
        counter++;
    }
    return name;
};

// --- Actual Tree Helpers ---
export interface ActualFolderNode {
    folderName: string;
    totalDocs: number;
    docs: DocRecord[];
}

export const getActualTreeStructure = (docs: DocRecord[], filterText: string = ''): ActualFolderNode[] => {
    const map: Record<string, DocRecord[]> = {};
    // Dynamic folder discovery instead of hardcoded list
    docs.forEach(doc => {
        const path = doc.actualPath || "Unsorted";
        if (!map[path]) map[path] = [];
        map[path].push(doc);
    });

    const result = Object.entries(map).map(([folderName, folderDocs]) => {
        folderDocs.sort((a, b) => b.updatedAt - a.updatedAt);
        return {
            folderName,
            totalDocs: folderDocs.length,
            docs: folderDocs
        };
    });

    result.sort((a, b) => a.folderName.localeCompare(b.folderName));

    if (filterText) {
        const lowerFilter = filterText.toLowerCase();
        return result.map(node => ({
            ...node,
            docs: node.docs.filter(d =>
                d.name.toLowerCase().includes(lowerFilter) ||
                node.folderName.toLowerCase().includes(lowerFilter)
            )
        })).filter(node => node.docs.length > 0 || node.folderName.toLowerCase().includes(lowerFilter));
    }

    return result;
};

export const getVirtualTreeStructure = (docs: DocRecord[], filterText: string = ''): ActualFolderNode[] => {
    const map: Record<string, DocRecord[]> = {};
    docs.forEach(doc => {
        const path = doc.folderPath || "Unclassified";
        if (!map[path]) map[path] = [];
        map[path].push(doc);
    });

    const result = Object.entries(map).map(([folderName, folderDocs]) => {
        folderDocs.sort((a, b) => b.updatedAt - a.updatedAt);
        return {
            folderName, // Virtual Path Name
            totalDocs: folderDocs.length,
            docs: folderDocs
        };
    });

    result.sort((a, b) => a.folderName.localeCompare(b.folderName));

    if (filterText) {
        const lowerFilter = filterText.toLowerCase();
        return result.map(node => ({
            ...node,
            docs: node.docs.filter(d =>
                d.name.toLowerCase().includes(lowerFilter) ||
                node.folderName.toLowerCase().includes(lowerFilter) // Match path name
            )
        })).filter(node => node.docs.length > 0 || node.folderName.toLowerCase().includes(lowerFilter));
    }

    return result;
};

export const getTopTags = (docs: DocRecord[]): string[] => {
    const counts: Record<string, number> = {};
    docs.forEach(d => d.tags.forEach(t => counts[t] = (counts[t] || 0) + 1));
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(e => e[0]);
};

export const getRecentConcepts = (concepts: ConceptNode[]): ConceptNode[] => {
    return [...concepts].sort((a, b) => b.createdAt - a.createdAt).slice(0, 20);
};
