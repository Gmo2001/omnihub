
export type Role = 'admin' | 'manager' | 'viewer';

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
