import {
    RAGResponse,
    RAGRequest,
    GraphData,
    DocCard,
    TreeResponse
} from '../types';

const API_BASE_URL = 'http://localhost:8000'; // Or use relative path if proxied

// Helper to get headers with Auth Token
const getHeaders = () => {
    const token = localStorage.getItem('omnihub_token');
    return {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : ''
    };
};

// [DEV NOTE - AI-A 개발자 필독]
// 현재 상태: 백엔드 API 연동 전이므로 프론트엔드 테스트를 위해 "Mock Data(가짜 데이터)"를 반환하도록 설정되어 있습니다.
// 이유: Sync 로직 없이도 UI/UX를 개발하고 확인하기 위함입니다.
// 할 일: 실제 백엔드 API (/api/graph, /api/rag 등)가 준비되면, 
//       아래의 [MOCK] 주석이 달린 부분들을 실제 API 호출(fetch/axios)로 교체해주세요.

export const AIService = {
    // 1. RAG Search
    searchRAG: async (query: string, scope?: any): Promise<RAGResponse> => {
        // [REAL API CALL] Backed by Mock Data on Backend
        const res = await fetch(`${API_BASE_URL}/api/search/rag`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ query, scope })
        });
        if (!res.ok) throw new Error("RAG Search failed");
        return await res.json();
    },

    // 2. Graph Ops
    getGraphInit: async (limit: number = 30): Promise<GraphData> => {
        // [REAL API CALL] Backed by Mock Data on Backend
        const res = await fetch(`${API_BASE_URL}/api/graph/init?limit=${limit}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Graph Init failed");
        return await res.json();
    },

    expandGraph: async (nodeId: string, nodeType: 'document' | 'concept'): Promise<GraphData> => {
        // [REAL API CALL] Backed by Mock Data on Backend
        const res = await fetch(`${API_BASE_URL}/api/graph/expand?node_id=${nodeId}&node_type=${nodeType}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Graph Expand failed");
        return await res.json();
    },

    // 3. Tree Ops
    getTreeStructure: async (folderPath: string = '/'): Promise<TreeResponse> => {
        // [REAL API CALL] Backed by Mock Data on Backend
        // Encoding path parameter
        const encodedPath = encodeURIComponent(folderPath);
        const res = await fetch(`${API_BASE_URL}/api/tree?folder=${encodedPath}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Fetch Tree failed");
        return await res.json();
    },

    // 4. Doc Card
    getDocCard: async (docId: string): Promise<DocCard> => {
        // [REAL API CALL] Backed by Mock Data on Backend
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Fetch Doc Card failed");
        return await res.json();
    }
};
