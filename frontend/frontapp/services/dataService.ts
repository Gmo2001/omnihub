
import { ConceptNode, DocRecord, Role, SecurityLevel } from '../types';

// --- Constants for Random Generation ---
const CONCEPT_LABELS = [
    "비품관리", "구매요청", "회계감사", "비용정산", "계약검토", "법무지원", "인재채용",
    "면접평가", "사내규정", "정보보안", "프로젝트A", "프로젝트B", "차세대구축", "마케팅",
    "영업실적", "R&D", "물류관리", "재고현황", "급여대장", "컴플라이언스", "내부감사", "경영전략",
    "1분기목표", "2분기목표", "예산편성", "법인카드", "출장규정", "IT지원", "클라우드운영",
    "API연동", "프론트엔드", "백엔드", "DB설계", "UX디자인", "고객센터", "VOC분석"
];

const VIRTUAL_ROOTS = ["경영지원본부", "전략기획실", "인사팀", "재무팀", "법무팀", "IT개발실"];

// 50 Actual Folders for "Actual Tree"
const ACTUAL_FOLDERS = [
    "01_인사_급여_2024", "01_인사_채용_이력서", "01_인사_퇴직자관리", "01_인사_증명서발급", "01_인사_조직도",
    "02_재무_법인카드", "02_재무_부가세신고", "02_재무_결산서_2023", "02_재무_결산서_2024", "02_재무_지출결의서",
    "03_총무_비품관리", "03_총무_임대차계약", "03_총무_차량일지", "03_총무_행사지원", "03_총무_우편발송",
    "04_법무_NDA", "04_법무_용역계약", "04_법무_소송관련", "04_법무_자문의견서", "04_법무_등기부등본",
    "05_IT_서버로그", "05_IT_장애보고서", "05_IT_라이선스", "05_IT_보안점검", "05_IT_계정관리",
    "06_영업_수주계약", "06_영업_제안서_A팀", "06_영업_제안서_B팀", "06_영업_고객리스트", "06_영업_매출집계",
    "07_마케팅_브랜드", "07_마케팅_SNS운영", "07_마케팅_행사기획", "07_마케팅_보도자료", "07_마케팅_광고비",
    "08_연구소_특허", "08_연구소_프로젝트A", "08_연구소_프로젝트B", "08_연구소_프로젝트C", "08_연구소_논문",
    "09_감사_내부회계", "09_감사_정기감사", "09_감사_제보접수", "09_감사_조치결과", "09_감사_규정집",
    "10_CEO_보고자료", "10_CEO_이사회", "10_CEO_주주총회", "10_CEO_신년사", "10_CEO_비서실"
];

const OWNERS = ["김철수@corp.com", "이영희@corp.com", "박지성@corp.com", "최민수@corp.com", "security_bot", "admin@corp.com"];
const TAGS_POOL = ["대외비", "초안", "확정", "긴급", "보관용", "검토필요", "외부발송", "사내용", "결재완료", "보안"];
const TEXT_SNIPPETS = [
    "본 문서는 2026년도 회계연도의 주요 목표를 포함하고 있습니다.",
    "감사 기간 동안 보안 수칙을 엄격히 준수해야 합니다.",
    "새로운 규제 요건을 반영하여 프로젝트 일정이 조정되었습니다.",
    "해당 후보자의 면접 결과, 기술적 역량이 매우 뛰어난 것으로 평가되었습니다.",
    "1분기 하드웨어 구매 요청에 대한 영수증 내역입니다."
];

// --- Version Regex & Logic ---
const REGEX_VER_NUM = /\b(v|ver|version|rev|re|r)[\s._-]*(\d{1,3})\b/gi;
const REGEX_STATUS_FINAL = /(final|finalized|definitive|최종(본|안)?|확정(본|안)?|완료본|제출본)/gi;
const REGEX_STATUS_APPROVED = /(approved|signed|executed|승인(본)?|서명(본)?|날인(본)?|결재(완료)?)/gi;
const REGEX_STATUS_REVISED = /(update(d)?|revis(ed|ion)?|수정(본|안)?|재수정(본)?|변경(본)?|개정(본)?)/gi;
const REGEX_STATUS_DRAFT = /(draft|tmp|temp|초안|초본|임시(본)?|작업본|검토본|내부용)/gi;
const REGEX_DATE_PREFIX = /^\d{4}([._-]?\d{2}){0,2}[._-]?/;
const REGEX_BRACKET_PREFIX = /^\s*[\[\(].*?[\]\)]\s*/;

export interface VersionMeta {
    versionNumber?: number;
    versionStatus?: 'final' | 'approved' | 'revised' | 'draft' | null;
    rawTokens: string[];
}

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

// --- Helpers ---
function getRandomInt(min: number, max: number) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}
function getRandomItem<T>(arr: T[]): T {
    return arr[Math.floor(Math.random() * arr.length)];
}
function getRandomDate(start: Date, end: Date): number {
    return new Date(start.getTime() + Math.random() * (end.getTime() - start.getTime())).getTime();
}

// --- MAIN SEED GENERATOR (Internal) ---
const generateSeedData = (): { concepts: ConceptNode[], docs: DocRecord[], logMsg: string } => {
    const concepts: ConceptNode[] = [];
    for (let i = 0; i < 120; i++) {
        const labelBase = getRandomItem(CONCEPT_LABELS);
        const suffix = i % 5 === 0 ? `_${(i % 5) + 1}` : '';
        const isRecent = Math.random() > 0.6;
        const createdAt = isRecent
            ? getRandomDate(new Date('2026-01-01'), new Date())
            : getRandomDate(new Date('2024-01-01'), new Date('2025-12-31'));

        concepts.push({ id: crypto.randomUUID(), label: `${labelBase}${suffix}`, createdAt: createdAt });
    }

    const docs: DocRecord[] = [];
    const securityLevels: SecurityLevel[] = ['low', 'medium', 'high'];
    const statuses: DocRecord['status'][] = ['idle', 'pending', 'approved', 'rejected'];

    for (let i = 0; i < 1000; i++) {
        const year = getRandomInt(2024, 2026);
        const conceptLabel = getRandomItem(CONCEPT_LABELS);
        const virtualFolder = `${getRandomItem(VIRTUAL_ROOTS)}/${year}/${conceptLabel}`;
        const actualFolder = getRandomItem(ACTUAL_FOLDERS);
        const version = Math.random() > 0.7 ? `_v${getRandomInt(1, 5)}` : (Math.random() > 0.8 ? '_Final' : '');
        const name = `${year}년_${conceptLabel.replace(/\s/g, '_')}_${getRandomItem(['보고서', '계약서', '명세서', '회의록', '지출결의서'])}${version}.pdf`;

        const linkedConcepts: string[] = [];
        const numLinks = getRandomInt(1, 4);
        for (let j = 0; j < numLinks; j++) {
            const c = getRandomItem(concepts);
            if (!linkedConcepts.includes(c.id)) linkedConcepts.push(c.id);
        }

        const docTags: string[] = [];
        const numTags = getRandomInt(2, 5);
        for (let t = 0; t < numTags; t++) {
            const tag = getRandomItem(TAGS_POOL);
            if (!docTags.includes(tag)) docTags.push(tag);
        }

        docs.push({
            id: crypto.randomUUID(),
            name: name,
            driveUrl: `https://fake-drive.corp/files/${name}`,
            folderPath: virtualFolder,
            actualPath: actualFolder,
            tags: docTags,
            period: `${year}-H${getRandomInt(1, 2)}`,
            owner: getRandomItem(OWNERS),
            updatedAt: getRandomDate(new Date(`${year}-01-01`), new Date()),
            sizeKB: getRandomInt(100, 8000),
            ext: 'pdf',
            security: getRandomItem(securityLevels),
            aiSummary3: [
                `[Virtual] ${virtualFolder} 로 자동 분류됨.`,
                `[Actual] ${actualFolder} 에 저장된 파일임.`,
                `AI Insight: ${linkedConcepts.length}개의 연관 개념이 식별됨.`
            ],
            conceptIds: linkedConcepts,
            status: getRandomItem(statuses),
            relatedFolderPaths: [],
            textExcerpt: ''
        });
    }

    return { concepts, docs, logMsg: `Initialized: 50 Actual Folders, 1000 Docs` };
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

// --- API SIMULATION ---
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export const OmniHubAPI = {
    fetchInitialData: async () => {
        await delay(1200); // Simulate network
        return generateSeedData();
    },
    uploadDocument: async (doc: DocRecord) => {
        await delay(2000); // Simulate upload
        return { success: true, doc };
    },
    updateDocumentStatus: async (id: string, status: string) => {
        await delay(600);
        return { success: true, id, status };
    }
};

// --- Actual Tree Helpers ---
export interface ActualFolderNode {
    folderName: string;
    totalDocs: number;
    docs: DocRecord[];
}

export const getActualTreeStructure = (docs: DocRecord[], filterText: string = ''): ActualFolderNode[] => {
    const map: Record<string, DocRecord[]> = {};
    ACTUAL_FOLDERS.forEach(f => map[f] = []);

    docs.forEach(doc => {
        if (map[doc.actualPath]) {
            map[doc.actualPath].push(doc);
        }
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

export const getTopTags = (docs: DocRecord[]): string[] => {
    const counts: Record<string, number> = {};
    docs.forEach(d => d.tags.forEach(t => counts[t] = (counts[t] || 0) + 1));
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(e => e[0]);
};

// --- REAL BACKEND API INTEGRATION ---

export interface DriveFile {
    id: string;
    name: string;
    mimeType: string;
    iconLink?: string;
    thumbnailLink?: string;
}

export const BackendAPI = {
    // 1. Google Login (Exchange Code for Tokens)
    exchangeToken: async (googleCode: string): Promise<{ access_token: string }> => {
        const res = await fetch('https://omnihub-backend-707724932002.asia-northeast3.run.app/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: googleCode })
        });
        if (!res.ok) throw new Error("Login Failed");
        return await res.json();
    },

    // 2. Drive Proxy (List Files)
    getDriveProxy: async (folderId: string = "root", token: string | null): Promise<DriveFile[]> => {
        if (!token) return [];
        const res = await fetch(`https://omnihub-backend-707724932002.asia-northeast3.run.app/files/drive/proxy?folder_id=${folderId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return []; // Fallback empty
        const data = await res.json();
        return data.files || [];
    },

    // 3. Sync Folder Action
    syncFolder: async (folderId: string, token: string | null) => {
        if (!token) throw new Error("No Token");
        const res = await fetch('https://omnihub-backend-707724932002.asia-northeast3.run.app/drive/sync-folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ folder_id: folderId })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Sync Failed");
        }
        return await res.json();
    }
};
