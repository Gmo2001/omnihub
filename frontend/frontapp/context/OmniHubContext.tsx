import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { Role, EventLog, SecurityState, DocRecord, ConceptNode } from '../types';
import { OmniHubAPI, getActualTreeStructure, generateUniqueName, ActualFolderNode } from '../services/dataService';
import { TABS } from '../constants';

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

  // Data
  docs: DocRecord[];
  concepts: ConceptNode[];
  logs: EventLog[];
  securityState: SecurityState;
  riskHistory: { time: string, score: number }[];

  // Tree & Graph State
  selectedDoc: DocRecord | null;
  setSelectedDoc: (doc: DocRecord | null) => void;
  activeCenterId: string | null;
  setActiveCenterId: (id: string | null) => void;
  expandedFolders: Set<string>;
  setExpandedFolders: React.Dispatch<React.SetStateAction<Set<string>>>;
  folderLimits: Record<string, number>;
  setFolderLimits: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  treeSearchQuery: string;
  setTreeSearchQuery: (query: string) => void;
  actualTreeData: ActualFolderNode[];
  scrollToTreeItem: (docId: string, folderName: string) => void;

  // Actions
  addLog: (message: string, level?: EventLog['level'], category?: 'SYSTEM' | 'SECURITY', actorRole?: Role) => void;
  updateDoc: (id: string, updates: Partial<DocRecord>) => void;
  addDoc: (doc: DocRecord) => void;
  setSecurityState: React.Dispatch<React.SetStateAction<SecurityState>>;
  reportSecurityEvent: (action: 'DOWNLOAD' | 'APPROVE' | 'MOVE' | 'ACCESS_DENIED' | 'BLOCK_ATTEMPT' | 'ACCESS_ATTEMPT' | 'MFA_SUCCESS', details?: string) => void;
  simulateAttack: () => void;
  resetSecurity: () => void;
  handleUpload: (onComplete?: (doc: DocRecord) => void) => void;
  isUploading: boolean;
  uploadProgress: number;
}

const OmniHubContext = createContext<OmniHubContextType | undefined>(undefined);

export const OmniHubProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeTab, setActiveTab] = useState<string>(TABS.OMNIHUB);
  const [currentRole, setCurrentRole] = useState<Role>('admin');
  const [isDataReady, setIsDataReady] = useState(false);
  const [isGlobalLoading, setIsGlobalLoading] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

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
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

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

  // Async Initialization
  useEffect(() => {
    const init = async () => {
        try {
            const { concepts: c, docs: d, logMsg } = await OmniHubAPI.fetchInitialData();
            setConcepts(c);
            setDocs(d);
            setIsDataReady(true);
            addLog(`초기 데이터 생성됨: 개념노드=${c.length}, 문서노드=${d.length}`, 'INFO', 'SYSTEM', 'admin');
            if (logMsg) addLog(logMsg, 'INFO', 'SYSTEM', 'admin');
            addLog(`초기 권한 설정: 관리자(Admin)`, 'INFO', 'SYSTEM', 'admin');

            const now = new Date();
            const initHistory = Array.from({ length: 20 }, (_, i) => ({
                time: new Date(now.getTime() - (19 - i) * 2000).toLocaleTimeString([], { hour12: false, minute:'2-digit', second:'2-digit' }),
                score: 10 + Math.floor(Math.random() * 5)
            }));
            setRiskHistory(initHistory);
        } catch (e) {
            setGlobalError("Failed to initialize system data. Please refresh.");
        }
    };
    init();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const actualTreeData = useMemo(() => {
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
               setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute:'2-digit', second:'2-digit' }), score: newScore }]);
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
        switch(action) {
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

        setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute:'2-digit', second:'2-digit' }), score: newScore }]);

        return { ...prev, riskScore: newScore, mode: newMode, softBlocked: newSoftBlocked };
    });
  }, [currentRole, addLog]);

  const simulateAttack = useCallback(() => {
    addLog("이상 징후 감지: DDOS 패턴 트래픽 발생", 'WARN', 'SECURITY');
    const ips = ['192.168.1.105', '10.0.0.55', '172.16.0.23'];
    let count = 0;
    const burstInterval = setInterval(() => {
        count++;
        addLog(`의심스러운 접근 시도 차단됨 IP:${ips[count % 3]}`, 'WARN', 'SECURITY', 'unknown' as Role);
        if (count > 10) {
            clearInterval(burstInterval);
            setSecurityState(prev => {
                const newScore = 98;
                setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute:'2-digit', second:'2-digit' }), score: newScore }]);
                return { ...prev, riskScore: newScore, mode: 'ALERT', softBlocked: true };
            });
        }
    }, 100);
  }, [addLog]);

  const resetSecurity = useCallback(() => {
    setSecurityState(prev => {
        const newScore = 20;
        setRiskHistory(h => [...h.slice(-59), { time: new Date().toLocaleTimeString([], { hour12: false, minute:'2-digit', second:'2-digit' }), score: newScore }]);
        return { ...prev, riskScore: newScore, mode: 'SAFE', softBlocked: false };
    });
    addLog("보안 상태 초기화 -> SAFE(안전)", 'INFO', 'SECURITY');
  }, [addLog]);

  const handleUpload = useCallback(async (onComplete?: (doc: DocRecord) => void) => {
    if (isUploading) return;
    if (securityState.softBlocked) {
        reportSecurityEvent('BLOCK_ATTEMPT');
        addLog('보안 정책에 의해 업로드 차단됨', 'WARN', 'SECURITY');
        return;
    }

    setIsUploading(true);
    // Note: uploadProgress is still simulated locally for UI feedback
    setUploadProgress(0);
    const fileName = generateUniqueName("2026_업무일지_3월.pdf", docs);
    addLog(`업로드 시작 -> ${fileName}`, 'INFO');

    const interval = setInterval(() => {
        setUploadProgress(prev => {
            if (prev >= 95) return prev;
            return prev + 5;
        });
    }, 150);

    const randomConcepts = [concepts[0], concepts[1]]; 
    const newDoc: DocRecord = {
        id: crypto.randomUUID(),
        name: fileName,
        driveUrl: 'https://drive.google.com/simulated',
        folderPath: 'Projects/2026/DailyReports',
        actualPath: '03_총무_비품관리',
        tags: ['사내용', '초안', '일일보고'],
        period: '2026-Q1',
        owner: 'demo_user@corp.com',
        updatedAt: Date.now(),
        sizeKB: 1204,
        ext: 'pdf',
        security: 'medium',
        aiSummary3: ["자동으로 추출된 일일 업무 요약입니다.", "주요 안건: 프로젝트A 타임라인 조정.", "AI 제안: 매니저의 결재가 필요합니다."],
        textExcerpt: "금일 프로젝트A 관련 회의록 요약입니다.",
        conceptIds: randomConcepts.map(c => c.id),
        status: 'pending',
        relatedFolderPaths: []
    };

    try {
        await OmniHubAPI.uploadDocument(newDoc); // Actual Async Call
        
        clearInterval(interval);
        setUploadProgress(100);
        addDoc(newDoc);
        addLog(`AI 분류 제안 생성됨 -> 승인 대기`, 'INFO');
        
        setTimeout(() => {
            setIsUploading(false);
            setUploadProgress(0);
            if (onComplete) onComplete(newDoc);
            setSelectedDoc(newDoc);
            addLog(`상세 패널 열림 -> 분류 제안 확인`, 'INFO');
        }, 500);

    } catch (e) {
        clearInterval(interval);
        setIsUploading(false);
        setUploadProgress(0);
        setGlobalError("업로드 실패. 네트워크 연결을 확인해주세요.");
        addLog("업로드 실패: API Error", 'ERROR');
    }

  }, [isUploading, securityState.softBlocked, docs, concepts, addDoc, addLog, reportSecurityEvent, setSelectedDoc]);

  const value = useMemo(() => ({
    activeTab, setActiveTab,
    currentRole, setCurrentRole,
    isDataReady, isGlobalLoading, globalError, dismissError: () => setGlobalError(null),
    docs, concepts, logs, securityState, riskHistory,
    selectedDoc, setSelectedDoc,
    activeCenterId, setActiveCenterId,
    expandedFolders, setExpandedFolders,
    folderLimits, setFolderLimits,
    treeSearchQuery, setTreeSearchQuery,
    actualTreeData, scrollToTreeItem,
    addLog, updateDoc, addDoc,
    setSecurityState, reportSecurityEvent, simulateAttack, resetSecurity,
    handleUpload, isUploading, uploadProgress
  }), [
    activeTab, currentRole, isDataReady, isGlobalLoading, globalError,
    docs, concepts, logs, securityState, riskHistory,
    selectedDoc, activeCenterId, expandedFolders, folderLimits, treeSearchQuery, actualTreeData, scrollToTreeItem,
    addLog, updateDoc, addDoc, reportSecurityEvent, simulateAttack, resetSecurity,
    handleUpload, isUploading, uploadProgress
  ]);

  return <OmniHubContext.Provider value={value}>{children}</OmniHubContext.Provider>;
};

export const useOmniHub = () => {
  const context = useContext(OmniHubContext);
  if (!context) throw new Error("useOmniHub must be used within OmniHubProvider");
  return context;
};