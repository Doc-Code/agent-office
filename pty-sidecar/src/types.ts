import type { ChildProcess } from "node:child_process";
import type { WebSocket } from "ws";

export interface AgentPtySession {
  process: ChildProcess;
  clients: Set<WebSocket>;
  scrollback: string[];
  workingDirectory: string;
  isBusy: boolean;
  settleTimer: ReturnType<typeof setTimeout> | null;
  pendingText: string;
  lastChatMessage: string;
  jsonlWatcher: ReturnType<typeof setInterval> | null;
  jsonlPath: string | null;
  lastJsonlSize: number;
  isFirstMessage: boolean;
  personality: string;
}

export interface SpawnRequest {
  workingDirectory: string;
  continueConversation?: boolean;
  personality?: string;
  initialPrompt?: string;
}

export interface ChatRequest {
  message: string;
}

export interface AgentStatus {
  agentId: string;
  isAlive: boolean;
  isBusy: boolean;
  pid: number | undefined;
  workingDirectory: string;
  scrollbackLength: number;
}
