import { spawn, type ChildProcess } from "node:child_process";
import { WebSocket } from "ws";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import type { AgentPtySession, SpawnRequest } from "./types.js";

const MAX_SCROLLBACK = 5000;
const JSONL_POLL_MS = 500;
const SETTLE_TIMER_MS = 3000;

/** All active PTY sessions */
export const agentPtys = new Map<string, AgentPtySession>();

/** Event callback for broadcasting state changes */
let onAgentEvent: ((agentId: string, type: string, data: Record<string, unknown>) => void) | null = null;

export function setEventCallback(cb: typeof onAgentEvent) {
  onAgentEvent = cb;
}

function emitEvent(agentId: string, type: string, data: Record<string, unknown> = {}) {
  onAgentEvent?.(agentId, type, data);
}

/**
 * Get the Claude JSONL project directory for a given working directory.
 * Claude Code stores transcripts at ~/.claude/projects/<encoded-path>/
 */
function getClaudeProjectDir(workDir: string): string {
  const encoded = workDir.replace(/\//g, "-").replace(/ /g, "-");
  return path.join(os.homedir(), ".claude", "projects", encoded);
}

/**
 * Start watching JSONL files for agent responses.
 */
function startJsonlWatcher(agentId: string, session: AgentPtySession): void {
  const projectDir = getClaudeProjectDir(session.workingDirectory);

  const existingFiles = new Map<string, number>();
  try {
    const files = fs.readdirSync(projectDir).filter((f) => f.endsWith(".jsonl"));
    for (const f of files) {
      const stat = fs.statSync(path.join(projectDir, f));
      existingFiles.set(f, stat.size);
    }
  } catch {
    // Directory may not exist yet
  }

  session.jsonlWatcher = setInterval(() => {
    try {
      if (!fs.existsSync(projectDir)) return;

      const files = fs.readdirSync(projectDir).filter((f) => f.endsWith(".jsonl"));

      for (const f of files) {
        const fullPath = path.join(projectDir, f);
        const stat = fs.statSync(fullPath);
        const prevSize = existingFiles.get(f) ?? 0;

        if (stat.size > prevSize) {
          if (!session.jsonlPath) {
            session.jsonlPath = fullPath;
            session.lastJsonlSize = prevSize;
          }
          if (fullPath === session.jsonlPath) {
            readNewJsonlContent(agentId, session);
          }
        }
        existingFiles.set(f, stat.size);
      }
    } catch {
      // Ignore transient filesystem errors
    }
  }, JSONL_POLL_MS);
}

function readNewJsonlContent(agentId: string, session: AgentPtySession): void {
  if (!session.jsonlPath) return;

  try {
    const fd = fs.openSync(session.jsonlPath, "r");
    const stat = fs.fstatSync(fd);
    const bytesToRead = stat.size - session.lastJsonlSize;

    if (bytesToRead <= 0) {
      fs.closeSync(fd);
      return;
    }

    const buffer = Buffer.alloc(bytesToRead);
    fs.readSync(fd, buffer, 0, bytesToRead, session.lastJsonlSize);
    fs.closeSync(fd);

    session.lastJsonlSize = stat.size;

    const text = buffer.toString("utf-8");
    const lines = text.split("\n").filter((l) => l.trim());

    for (const line of lines) {
      try {
        processJsonlLine(agentId, session, JSON.parse(line));
      } catch {
        // Skip malformed lines
      }
    }
  } catch {
    // File may be locked or deleted
  }
}

function processJsonlLine(agentId: string, session: AgentPtySession, obj: Record<string, unknown>): void {
  if (obj.type === "user") {
    session.isBusy = true;
    emitEvent(agentId, "agent.status", { status: "thinking" });
  } else if (obj.type === "assistant") {
    const message = obj.message as Record<string, unknown> | undefined;
    if (message?.content && Array.isArray(message.content)) {
      const textBlocks = message.content.filter(
        (b: Record<string, unknown>) => b.type === "text"
      );
      for (const block of textBlocks) {
        const text = (block as Record<string, unknown>).text as string;
        if (text) session.pendingText += text;
      }

      if (session.settleTimer) clearTimeout(session.settleTimer);
      session.settleTimer = setTimeout(() => {
        flushPendingResponse(agentId, session);
      }, SETTLE_TIMER_MS);
    }
  }
}

function flushPendingResponse(agentId: string, session: AgentPtySession): void {
  if (!session.pendingText) return;

  const text = session.pendingText
    .replace(/[\x00-\x09\x0B\x0C\x0E-\x1F]/g, "")
    .trim();

  if (text && text !== session.lastChatMessage) {
    emitEvent(agentId, "agent.message", { text, channel: "reply" });
    emitEvent(agentId, "agent.status", { status: "replied" });
    session.lastChatMessage = text;
  }

  session.pendingText = "";
  session.isBusy = false;
  session.settleTimer = null;
}

/**
 * Spawn a new Claude Code process for an agent.
 * Uses child_process.spawn with pipe stdio for cross-platform compatibility.
 */
export function createAgentPty(agentId: string, opts: SpawnRequest): AgentPtySession {
  const { workingDirectory, continueConversation, personality } = opts;

  // Find claude binary
  const claudePath = process.env.CLAUDE_PATH || "/opt/homebrew/bin/claude";

  // Build args
  const args: string[] = [];
  if (continueConversation) {
    args.push("--continue");
  }
  args.push("--dangerously-skip-permissions");

  // Strip CLAUDECODE env var to prevent nesting detection
  const env = { ...process.env };
  delete env.CLAUDECODE;
  if (env.PATH && !env.PATH.includes("/opt/homebrew/bin")) {
    env.PATH = `/opt/homebrew/bin:${env.PATH}`;
  }

  const childProcess = spawn(claudePath, args, {
    cwd: workingDirectory,
    env,
    stdio: ["pipe", "pipe", "pipe"],
  });

  const session: AgentPtySession = {
    process: childProcess,
    clients: new Set(),
    scrollback: [],
    workingDirectory,
    isBusy: false,
    settleTimer: null,
    pendingText: "",
    lastChatMessage: "",
    jsonlWatcher: null,
    jsonlPath: null,
    lastJsonlSize: 0,
    isFirstMessage: true,
    personality: personality ?? "",
  };

  // Capture stdout
  childProcess.stdout?.on("data", (data: Buffer) => {
    const text = data.toString();
    session.scrollback.push(text);
    if (session.scrollback.length > MAX_SCROLLBACK) {
      session.scrollback.shift();
    }

    for (const ws of session.clients) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "output", data: text }));
      }
    }
  });

  // Capture stderr
  childProcess.stderr?.on("data", (data: Buffer) => {
    const text = data.toString();
    session.scrollback.push(text);
    if (session.scrollback.length > MAX_SCROLLBACK) {
      session.scrollback.shift();
    }

    for (const ws of session.clients) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "output", data: text }));
      }
    }
  });

  // Handle exit
  childProcess.on("close", (exitCode) => {
    for (const ws of session.clients) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "exit", code: exitCode }));
      }
    }

    if (session.jsonlWatcher) clearInterval(session.jsonlWatcher);
    if (session.settleTimer) clearTimeout(session.settleTimer);

    if (agentPtys.get(agentId) === session) {
      agentPtys.delete(agentId);
    }

    emitEvent(agentId, "agent.exited", { exitCode: exitCode ?? -1 });
  });

  childProcess.on("error", (err) => {
    emitEvent(agentId, "agent.error", { error: err.message });
  });

  agentPtys.set(agentId, session);
  startJsonlWatcher(agentId, session);
  emitEvent(agentId, "agent.spawned", { pid: childProcess.pid, workingDirectory });

  return session;
}

/**
 * Send a chat message to an agent by writing to stdin.
 */
export function bridgeChatToPty(agentId: string, message: string): boolean {
  const session = agentPtys.get(agentId);
  if (!session) return false;
  if (session.isBusy) return false;

  let fullMessage = message;

  if (session.isFirstMessage && session.personality) {
    fullMessage = `${session.personality}\n\n${message}`;
    session.isFirstMessage = false;
  }

  session.lastChatMessage = message;
  session.isBusy = true;

  emitEvent(agentId, "agent.status", { status: "thinking" });

  // Write message to stdin followed by newline
  session.process.stdin?.write(fullMessage + "\n");

  // Safety timeout: reset isBusy after 60s
  setTimeout(() => {
    if (session.isBusy) {
      session.isBusy = false;
      emitEvent(agentId, "agent.status", { status: "available" });
    }
  }, 60000);

  return true;
}

/**
 * Kill an agent's process.
 */
export function killAgentPty(agentId: string): boolean {
  const session = agentPtys.get(agentId);
  if (!session) return false;

  if (session.jsonlWatcher) clearInterval(session.jsonlWatcher);
  if (session.settleTimer) clearTimeout(session.settleTimer);

  try {
    session.process.kill("SIGTERM");
    // Force kill after 5s if still alive
    setTimeout(() => {
      try {
        session.process.kill("SIGKILL");
      } catch {
        // Already dead
      }
    }, 5000);
  } catch {
    // Process may already be dead
  }

  agentPtys.delete(agentId);
  emitEvent(agentId, "agent.killed", {});

  return true;
}

/**
 * Reset an agent: kill and respawn fresh.
 */
export function resetAgentPty(agentId: string): AgentPtySession | null {
  const oldSession = agentPtys.get(agentId);
  if (!oldSession) return null;

  const { workingDirectory, personality } = oldSession;
  killAgentPty(agentId);

  return createAgentPty(agentId, {
    workingDirectory,
    continueConversation: false,
    personality,
  });
}

/**
 * Get status of an agent's process.
 */
export function getAgentStatus(agentId: string): {
  isAlive: boolean;
  isBusy: boolean;
  pid: number | undefined;
  scrollbackLength: number;
} {
  const session = agentPtys.get(agentId);
  if (!session) {
    return { isAlive: false, isBusy: false, pid: undefined, scrollbackLength: 0 };
  }

  return {
    isAlive: !session.process.killed,
    isBusy: session.isBusy,
    pid: session.process.pid,
    scrollbackLength: session.scrollback.length,
  };
}
