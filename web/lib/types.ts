/**
 * Types mirroring CONTRACTS.md — "HTTP API surface consumed by web".
 * IDs are UUIDv4 strings in JSON. Do not widen these shapes casually;
 * where the contract is silent, fields are optional and rendering is
 * defensive.
 */

export type MeetingStatus = "scheduled" | "live" | "processing" | "ready";
export type OrgRole = "admin" | "member";
export type ProjectRole = "manager" | "member";
export type ActionStatus = "open" | "in_progress" | "done" | string;

export interface CurrentUser {
  id: string;
  email: string;
  name?: string | null;
}

export interface OrgMembership {
  org_id: string;
  role: OrgRole;
  /** Not promised by the contract; used when the API provides it. */
  name?: string;
}

export interface ProjectMembership {
  project_id: string;
  role: ProjectRole;
  /** Not promised by the contract; used when the API provides it. */
  name?: string;
  org_id?: string;
}

export interface Me {
  user: CurrentUser;
  orgs: OrgMembership[];
  projects: ProjectMembership[];
}

export interface Meeting {
  id: string;
  project_id: string;
  title: string;
  livekit_room?: string;
  status: MeetingStatus;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface MeetingTokenResponse {
  token: string;
  livekit_url: string;
}

/** Canonical utterance shape from transcripts.json_utterances. */
export interface Utterance {
  speaker_identity: string;
  speaker_name: string;
  start: number;
  end: number;
  text: string;
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  project_id?: string;
  text: string;
  owner_user_id?: string | null;
  owner_name?: string | null;
  deadline?: string | null;
  status: ActionStatus;
}

export interface Citation {
  /** Shape is backend-defined; render whatever identifies the source. */
  meeting_id?: string;
  meeting_title?: string;
  text?: string;
  snippet?: string;
  source?: string;
  date?: string;
  [key: string]: unknown;
}

export interface SearchRequest {
  org_id: string;
  project_id?: string;
  query: string;
  search_type?: string;
}

export interface SearchResponse {
  answer: string;
  citations: (Citation | string)[];
}

export interface AuditRow {
  id: string;
  org_id: string;
  user_id: string;
  op: "search" | "add" | "cognify" | "forget" | "export" | string;
  dataset: string;
  meeting_id?: string | null;
  ts: string;
}
