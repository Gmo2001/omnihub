
export type Role = 'admin' | 'manager' | 'viewer' | 'user';

export interface User {
  email: string;
  displayName: string;
  photoUrl?: string;
  department?: string;
  department_id?: string; // [RBAC] Added
  position?: string;
  role: string;
  lastLoginAt?: string;
}

export type ViewMode = 'virtual' | 'actual';

export type SecurityLevel = 'low' | 'medium' | 'high';

export interface ConceptNode {
  id: string;
  label: string;
  createdAt: number;
}

export interface DocRecord {
  id: string;
  name: string;
  driveUrl: string;
  folderPath: string; // Virtual Path (AI Classification) e.g. "Projects/2026/DailyReports"
  actualPath: string; // Actual File System Path e.g. "01_HR_Contracts"
  tags: string[]; // 2~5 tags
  period: string; // e.g., "2026-H1"
  owner: string;
  updatedAt: number;
  sizeKB: number;
  ext: 'pdf';
  security: SecurityLevel;
  aiSummary3: string[]; // 3-line summary
  textExcerpt: string; // 2~4 sentence snippet
  conceptIds: string[]; // Connected concept IDs for graph
  status: 'idle' | 'pending' | 'approved' | 'rejected';
  ssotRating?: 'gold' | 'silver'; // Optional property for Research context
  relatedFolderPaths: string[]; // For Actual Mode 3-hop traversal (logical links)
}

export interface EventLog {
  id: string;
  ts: number;
  level: 'INFO' | 'WARN' | 'ERROR';
  actorRole?: Role;
  message: string;
  category?: 'SYSTEM' | 'SECURITY';
}

export interface SecurityState {
  riskScore: number; // 0~100
  mode: 'SAFE' | 'WATCH' | 'ALERT';
  softBlocked: boolean;
  blockedCount: number;
}

// --- AI-A Integration Types ---

// 1. RAG
export interface Citation {
  idx: number;
  doc_id: string;
  title?: string;
  source_link?: string;
  page?: number;
  chunk_id?: string;
  snippet?: string;
  relevance?: number;
}

export interface RAGResponse {
  answer: string;
  citations: Citation[];
  meta?: any;
  follow_up?: string[];
}

export interface RAGScope {
  doc_ids?: string[];
  concept_ids?: string[];
  folder_path?: string;
}

export interface RAGRequest {
  query: string;
  scope?: RAGScope;
  top_k?: number;
}

// 2. Graph
export interface GraphNode {
  id: string;
  label?: string;
  group?: string; // "document" or "concept"
  [key: string]: any;
}

export interface GraphLink {
  source: string;
  target: string;
  value?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

// 3. Tree
export interface FileNode {
  doc_id: string;
  name: string;
  kind?: string;
  [key: string]: any;
}

export interface FolderNode {
  path: string;
  name: string;
  type?: 'folder';
}

export interface TreeResponse {
  current_path: string;
  folders: FolderNode[];
  files: FileNode[];
}

// 4. Doc Card
export interface DocCard {
  doc_id: string;
  title: string;
  folder_path?: string;
  modified_time?: string;
  source_link?: string;
  card?: {
    l1?: string;
    l2?: string;
    l3?: string;
  };
  concepts?: string[];
  policy?: {
    security_level?: string;
    ssot_level?: string;
  };
  summary?: string;
  keywords?: string[];
  entities?: string[];
  sentiment?: string;
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  iconLink?: string;
  thumbnailLink?: string;
}
