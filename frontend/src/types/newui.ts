import type { ChatResponse, GraphNode, GraphEdge } from '../api';

export interface EntityMentionData {
  entityId: string;
  entityType: string;
  name: string;
  startIndex: number;
  endIndex: number;
}

export interface V2Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  loading?: boolean;
  entityMentions?: EntityMentionData[];
  followupSuggestions?: string[];
  chatResponse?: ChatResponse;
}

export interface WorkspaceState {
  messages: V2Message[];
  graphData: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
  selectedEntity: GraphNode | null;
  isLoading: boolean;
  queryStatus: string | null;
  error: string | null;
}

export interface InspectorState {
  detail: unknown | null;  // CatalogEntityDetail
  isLoading: boolean;
  error: string | null;
}

export type Lens = 'explore' | 'curate';
