export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  sources?: string[];
  fileUrl?: string;
  intent?: string;
  verified?: boolean;
  isStreaming?: boolean;
  isError?: boolean;
}

export interface ProgressStep {
  node: string;
  label: string;
  done: boolean;
}

export interface ProgressEvent {
  type: "progress";
  node: string;
  label: string;
}

export interface ResultEvent {
  type: "result";
  answer: string;
  intent: string;
  sources: string[];
  verified: boolean;
  file_url: string;
}

export interface ErrorEvent {
  type: "error";
  detail: string;
}

export type StreamEvent = ProgressEvent | ResultEvent | ErrorEvent;

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  messageCount: number;
}
