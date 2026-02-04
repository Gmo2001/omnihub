import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { Role, EventLog, SecurityState, DocRecord, ConceptNode } from '../types';
import { OmniHubAPI, getActualTreeStructure, generateUniqueName, ActualFolderNode, BackendAPI } from '../services/dataService';
import { TABS } from '../constants';

export interface UserProfile {
    userId: string;
    email: string;
    displayName: string;
    photoUrl?: string;
    department?: string;
    position?: string;
    role: string;
    monitored_folder_ids?: string[];
}

interface OmniHubContextType {
    // App State
    activeTab: string;
    setActiveTab: (tab: string) => void;
    currentRole: Role;
    setCurrentRole: (role: Role) => void;
    isDataReady: boolean;
    isGlobalLoading: boolean;
    globalError: string | null;
    dismissError: () => void;
    isAuthenticated: boolean;
    login: (token: string) => void;
    logout: () => void;
    userProfile: UserProfile | null;
    token: string | null;

    // Added Missing Properties
    isAdmin: boolean;
    refreshUserProfile: () => Promise<void>;
    addLog: (message: string, level?: EventLog['level'], category?: 'SYSTEM' | 'SECURITY', actorRole?: Role) => void;
    logs: EventLog[];

    // Data 
    docs: DocRecord[];
    concepts: ConceptNode[];

    // AI Loading
    aiStatus: 'idle' | 'syncing' | 'analyzing' | 'completed' | 'error';
    setPollingFolderId: (id: string | null) => void;
    syncStatusData: any; // Added

    // Security
    securityState: SecurityState;
    riskHistory: { time: string, score: number }[];
    resetSecurity: () => void;
}

const OmniHubContext = createContext<OmniHubContextType | undefined>(undefined);

export const OmniHubProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const hasToken = !!localStorage.getItem('omnihub_token');
    const [activeTab, setActiveTab] = useState<string>(hasToken ? TABS.OMNIHUB : TABS.CONNECT);
    const [currentRole, setCurrentRole] = useState<Role>('admin');
    const [isDataReady, setIsDataReady] = useState(false);
    const [isGlobalLoading, setIsGlobalLoading] = useState(false);
    const [globalError, setGlobalError] = useState<string | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(hasToken);
    const [token, setToken] = useState<string | null>(localStorage.getItem('omnihub_token'));
    const [userProfile, setUserProfile] = useState<UserProfile | null>(null);

    const [docs, setDocs] = useState<DocRecord[]>([]);
    const [concepts, setConcepts] = useState<ConceptNode[]>([]);
    const [logs, setLogs] = useState<EventLog[]>([]);

    // Security
    const [securityState, setSecurityState] = useState<SecurityState>({
        riskScore: 12, mode: 'SAFE', softBlocked: false, blockedCount: 0
    });
    const [riskHistory, setRiskHistory] = useState<{ time: string, score: number }[]>([]);

    // Selection & Tree
    const [selectedDoc, setSelectedDoc] = useState<DocRecord | null>(null);
    const [activeCenterId, setActiveCenterId] = useState<string | null>(null);
    const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
    const [folderLimits, setFolderLimits] = useState<Record<string, number>>({});
    const [treeSearchQuery, setTreeSearchQuery] = useState('');

    // Upload


    const login = useCallback((newToken: string) => {
        setToken(newToken);
        localStorage.setItem('omnihub_token', newToken);
        setIsAuthenticated(true);
        setActiveTab(TABS.OMNIHUB); // Auto-redirect only on fresh login action
    }, []);

    const logout = useCallback(() => {
        setToken(null);
        localStorage.removeItem('omnihub_token');
        setIsAuthenticated(false);
        setUserProfile(null);
        setActiveTab(TABS.CONNECT);
    }, []);

    const addLog = useCallback((message: string, level: EventLog['level'] = 'INFO', category: 'SYSTEM' | 'SECURITY' = 'SYSTEM', actorRole: Role = currentRole) => {
        const newLog: EventLog = {
            id: crypto.randomUUID(),
            ts: Date.now(),
            level,
            actorRole,
            message,
            category
        };
        setLogs((prev) => [...prev.slice(-49), newLog]);
    }, [currentRole]);

    // --- AI Loading State Logic ---
    const [aiStatus, setAiStatus] = useState<'idle' | 'syncing' | 'analyzing' | 'completed' | 'error'>('idle');
    const [pollingFolderId, setPollingFolderId] = useState<string | null>(null);
    const [syncStatusData, setSyncStatusData] = useState<any>(null); // Raw Data for UI

    useEffect(() => {
        if (!pollingFolderId) return;

        console.log(`[Polling] Started for folder: ${pollingFolderId}`);
        const interval = setInterval(async () => {
            try {
                const statusData = await BackendAPI.getSyncStatus(pollingFolderId, token);
                console.log(`[Polling] Status:`, statusData);
                setSyncStatusData(statusData); // Update raw data

                if (statusData.status === 'running') {
                    setAiStatus('syncing');
                } else if (statusData.status === 'completed') {
                    clearInterval(interval);
                    setPollingFolderId(null);
                    setAiStatus('analyzing'); // Switch to "Refining" screen
                    setSyncStatusData(null); // Clear data

                    // Simulate AI refining time (since it's fast or mostly mock)
                    setTimeout(() => {
                        setAiStatus('completed');
                        setIsDataReady(true);
                        addLog('AI Knowledge Graph Updated', 'INFO', 'SYSTEM');
                    }, 4500);
                } else if (statusData.status === 'failed' || statusData.status === 'error') {
                    clearInterval(interval);
                    setPollingFolderId(null);
                    setAiStatus('error');
                    setSyncStatusData(null);
                    setGlobalError("Sync failed. Please check system logs.");
                }
            } catch (e) {
                console.error("Polling error", e);
            }
        }, 3000);

        return () => clearInterval(interval);
    }, [pollingFolderId, token, addLog]);

    // Async Initialization
    useEffect(() => {
        if (!isAuthenticated) return; // [FIX] Wait for login

        const init = async () => {
            try {
                // [ARCH_NOTE]: This is currently MOCK DATA for the prototype.
                // In Phase 2/3, this will be replaced by BackendAPI.fetchGraphData() / SecurityStatus
                const { concepts: c, docs: d, logMsg } = await OmniHubAPI.fetchInitialData();
                setConcepts(c);
                setDocs(d);
                setIsDataReady(true);
                addLog(`초기 데이터 생성됨: 개념노드=${c.length}, 문서노드=${d.length}`, 'INFO', 'SYSTEM', 'admin');
                if (logMsg) addLog(logMsg, 'INFO', 'SYSTEM', 'admin');

                const now = new Date();
                const initHistory = Array.from({ length: 20 }, (_, i) => ({
                    time: new Date(now.getTime() - (19 - i) * 2000).toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }),
                    score: 10 + Math.floor(Math.random() * 5)
                }));
                setRiskHistory(initHistory);
            } catch (e) {
                setGlobalError("Failed to initialize system data. Please refresh.");
            }
        };
        init();
    }, [isAuthenticated]); // eslint-disable-line react-hooks/exhaustive-deps

    const refreshUserProfile = useCallback(async () => {
        const token = localStorage.getItem('omnihub_token');
        if (!token) return;
        try {
            const profile = await BackendAPI.fetchCurrentUser(token);
            setUserProfile(profile);
            setCurrentRole(profile.role as Role); // Sync context role with DB role
            addLog(`사용자 프로필 로드됨: ${profile.email} (${profile.role})`, 'INFO', 'SYSTEM');
        } catch (e) {
            console.error("Failed to load profile", e);
            // Optional: handle auth error (logout)
        }
    }, [addLog]);

    useEffect(() => {
        if (isAuthenticated) {
            refreshUserProfile();
        }
    }, [isAuthenticated, refreshUserProfile]);

    const actualTreeData = useMemo(() => {
        // [ARCH_NOTE]: Hybrid Data - Mocks mixed with Real will happen in DocTreeBrowser
        return getActualTreeStructure(docs, treeSearchQuery);
    }, [docs, treeSearchQuery]);

    // Robust Scrolling Helper
    const scrollToTreeItem = useCallback((docId: string, folderName: string) => {
        // 1. Ensure folder is expanded
        setExpandedFolders(prev => {
            const next = new Set(prev);
            next.add(folderName);
            return next;
        });

        // 2. Ensure item is within limit
        setFolderLimits(prev => {
            const node = actualTreeData.find(n => n.folderName === folderName);
            if (node) {
                const idx = node.docs.findIndex(d => d.id === docId);
                if (idx !== -1 && idx >= (prev[folderName] || 8)) {
                    return { ...prev, [folderName]: idx + 5 };
                }
            }
            return prev;
        });

        // 3. Retry finding element (Robust)
        let attempts = 0;
        const maxAttempts = 10;
        const check = () => {
            const el = document.getElementById(`tree-doc-${docId}`);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Highlight flash effect could be added here directly to DOM if needed
            } else if (attempts < maxAttempts) {
                attempts++;
                setTimeout(check, 50); // Retry every 50ms
            }
        };

        // Defer check to next tick to allow React render
        setTimeout(check, 0);
    }, [actualTreeData]);


    const updateDoc = useCallback(async (id: string, updates: Partial<DocRecord>) => {
        // Optimistic Update
        setDocs(prev => prev.map(d => d.id === id ? { ...d, ...updates } : d));
        if (selectedDoc && selectedDoc.id === id) {
            setSelectedDoc(prev => prev ? { ...prev, ...updates } : null);
        }

        // Simulate API (Background)
        try {
            await OmniHubAPI.updateDocumentStatus(id, updates.status || 'idle');
        } catch (e) {
            addLog(`업데이트 실패: ${id}`, 'ERROR');
            setGlobalError("서버 통신 오류가 발생했습니다. 변경사항이 저장되지 않았을 수 있습니다.");
        }
    }, [selectedDoc, addLog]);

    const addDoc = useCallback((doc: DocRecord) => {
        setDocs(prev => [doc, ...prev]);
    }, []);

    const reportSecurityEvent = useCallback((action: 'DOWNLOAD' | 'APPROVE' | 'MOVE' | 'ACCESS_DENIED' | 'BLOCK_ATTEMPT' | 'ACCESS_ATTEMPT' | 'MFA_SUCCESS', details?: string) => {
        if (action === 'MFA_SUCCESS') {
            addLog("MFA 인증 성공 (데모) -> WATCH 모드로 하향", 'INFO', 'SECURITY');
            setSecurityState(prev => ({ ...prev, riskScore: 50, mode: 'WATCH', softBlocked: false }));
            return;
        }

        if (action === 'ACCESS_ATTEMPT') {
            let scoreAdd = 0;
            if (currentRole === 'viewer') {
                scoreAdd = 12;
                addLog(`뷰어(Viewer) 권한으로 높은 보안 등급 문서 접근 시도`, 'WARN', 'SECURITY');
            } else if (currentRole === 'manager') {
                scoreAdd = 6;
                addLog(`매니저(Manager) 권한으로 민감 영역 접근`, 'WARN', 'SECURITY');
            }

            if (scoreAdd > 0) {
                setSecurityState(prev => {
                    const newScore = Math.min(100, prev.riskScore + scoreAdd);
                    setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }), score: newScore }]);
                    return { ...prev, riskScore: newScore };
                });
            }
            return;
        }

        setSecurityState(prev => {
            if (action === 'BLOCK_ATTEMPT') {
                const newScore = Math.min(100, prev.riskScore + 5);
                return { ...prev, blockedCount: prev.blockedCount + 1, riskScore: newScore };
            }

            let scoreDelta = 0;
            switch (action) {
                case 'APPROVE': scoreDelta = 10; break;
                case 'DOWNLOAD': scoreDelta = 8; break;
                case 'MOVE': scoreDelta = 6; break;
                case 'ACCESS_DENIED': scoreDelta = 12; break;
            }

            const newScore = Math.min(100, prev.riskScore + scoreDelta);
            let newMode: SecurityState['mode'] = 'SAFE';
            let newSoftBlocked = false;

            if (newScore >= 80) {
                newMode = 'ALERT';
                newSoftBlocked = true;
            } else if (newScore >= 40) {
                newMode = 'WATCH';
            }

            if (newMode === 'ALERT' && prev.mode !== 'ALERT') {
                addLog('위험 임계값 초과: ALERT(경보) 모드 진입', 'WARN', 'SECURITY');
            }

            setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }), score: newScore }]);

            return { ...prev, riskScore: newScore, mode: newMode, softBlocked: newSoftBlocked };
        });
    }, [currentRole, addLog]);



    const resetSecurity = useCallback(() => {
        setSecurityState(prev => {
            const newScore = 20;
            setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }), score: newScore }]);
            return { ...prev, riskScore: newScore, mode: 'SAFE', softBlocked: false };
        });
        addLog("보안 상태 초기화 -> SAFE(안전)", 'INFO', 'SECURITY');
    }, [addLog]);

    const value = useMemo<OmniHubContextType>(() => ({
        activeTab, setActiveTab,
        currentRole, setCurrentRole,
        isDataReady, isGlobalLoading, globalError, dismissError: () => setGlobalError(null),
        isAuthenticated, login,
        userProfile, refreshUserProfile, isAdmin: userProfile?.role === 'admin',
        token,
        docs, concepts, logs, securityState, riskHistory,
        selectedDoc, setSelectedDoc,
        activeCenterId, setActiveCenterId,
        expandedFolders, setExpandedFolders,
        folderLimits, setFolderLimits,
        treeSearchQuery, setTreeSearchQuery,
        actualTreeData, scrollToTreeItem,
        addLog, updateDoc, addDoc,
        setSecurityState, reportSecurityEvent, resetSecurity,
        logout,
        // AI Loading
        // AI Loading
        aiStatus, setPollingFolderId, syncStatusData
    }), [
        activeTab, currentRole, isDataReady, isGlobalLoading, globalError, isAuthenticated, userProfile,
        token, docs, concepts, logs, securityState, riskHistory,
        selectedDoc, activeCenterId, expandedFolders, folderLimits, treeSearchQuery, actualTreeData, scrollToTreeItem,
        addLog, updateDoc, addDoc, reportSecurityEvent, resetSecurity,
        logout,
        aiStatus, setPollingFolderId, syncStatusData
    ]);

    return (
        <OmniHubContext.Provider value={value}>
            {children}
        </OmniHubContext.Provider>
    );
};

export const useOmniHub = () => {
    const context = useContext(OmniHubContext);
    if (!context) throw new Error("useOmniHub must be used within OmniHubProvider");
    return context;
};
