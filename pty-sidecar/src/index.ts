import express from "express";
import { createServer } from "node:http";
import { WebSocketServer, WebSocket } from "ws";
import { z } from "zod";
import {
  agentPtys,
  createAgentPty,
  bridgeChatToPty,
  killAgentPty,
  resetAgentPty,
  getAgentStatus,
  setEventCallback,
} from "./pty-manager.js";

const PORT = Number(process.env.PTY_SIDECAR_PORT ?? 8001);

const app = express();
app.use(express.json());

const server = createServer(app);

// --- Main event WebSocket (broadcasts agent lifecycle events) ---
const mainWss = new WebSocketServer({ noServer: true });
const mainClients = new Set<WebSocket>();

mainWss.on("connection", (ws) => {
  mainClients.add(ws);
  ws.on("close", () => mainClients.delete(ws));
});

function broadcastEvent(agentId: string, type: string, data: Record<string, unknown>) {
  const msg = JSON.stringify({
    type,
    agentId,
    timestamp: new Date().toISOString(),
    payload: data,
  });
  for (const ws of mainClients) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(msg);
    }
  }
}

setEventCallback(broadcastEvent);

// --- Terminal WebSocket (per-agent raw PTY data) ---
const terminalWss = new WebSocketServer({ noServer: true });

terminalWss.on("connection", (ws, req) => {
  const url = new URL(req.url!, `http://localhost:${PORT}`);
  const match = url.pathname.match(/^\/ws\/terminal\/(.+)$/);
  if (!match) {
    ws.close(1008, "Invalid path");
    return;
  }

  const agentId = match[1];
  const session = agentPtys.get(agentId);

  if (!session) {
    ws.close(1008, "Agent not found");
    return;
  }

  // Register as terminal viewer
  session.clients.add(ws);

  // Send scrollback
  for (const data of session.scrollback) {
    ws.send(JSON.stringify({ type: "output", data }));
  }

  // Handle input from terminal
  ws.on("message", (rawMsg) => {
    try {
      const msg = JSON.parse(rawMsg.toString());
      if (msg.type === "input" && typeof msg.data === "string") {
        session.process.stdin?.write(msg.data);
      }
    } catch {
      // Ignore malformed messages
    }
  });

  ws.on("close", () => {
    session.clients.delete(ws);
  });
});

// --- HTTP upgrade routing ---
server.on("upgrade", (req, socket, head) => {
  const url = new URL(req.url!, `http://localhost:${PORT}`);

  if (url.pathname === "/ws") {
    mainWss.handleUpgrade(req, socket, head, (ws) => {
      mainWss.emit("connection", ws, req);
    });
  } else if (url.pathname.startsWith("/ws/terminal/")) {
    terminalWss.handleUpgrade(req, socket, head, (ws) => {
      terminalWss.emit("connection", ws, req);
    });
  } else {
    socket.destroy();
  }
});

// --- Validation schemas ---
const SpawnSchema = z.object({
  workingDirectory: z.string().min(1),
  continueConversation: z.boolean().optional().default(false),
  personality: z.string().optional(),
  initialPrompt: z.string().optional(),
});

const ChatSchema = z.object({
  message: z.string().min(1),
});

// --- REST API ---

/** Health check */
app.get("/health", (_req, res) => {
  res.json({ status: "ok", agents: agentPtys.size });
});

/** List all active agents */
app.get("/agents", (_req, res) => {
  const agents: Record<string, ReturnType<typeof getAgentStatus> & { agentId: string }> = {};
  for (const [agentId] of agentPtys) {
    agents[agentId] = { agentId, ...getAgentStatus(agentId) };
  }
  res.json(agents);
});

/** Get agent status */
app.get("/agents/:agentId/status", (req, res) => {
  const { agentId } = req.params;
  const status = getAgentStatus(agentId);
  res.json({ agentId, ...status });
});

/** Spawn a new agent */
app.post("/agents/:agentId/spawn", (req, res) => {
  const { agentId } = req.params;

  // Don't spawn if already exists
  if (agentPtys.has(agentId)) {
    res.status(409).json({ error: "Agent already running", agentId });
    return;
  }

  const parsed = SpawnSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid request", details: parsed.error.errors });
    return;
  }

  try {
    const session = createAgentPty(agentId, parsed.data);

    // If initialPrompt provided, send it after agent starts
    if (parsed.data.initialPrompt) {
      const prompt = parsed.data.initialPrompt;
      // Wait for Claude Code to initialize, then send prompt
      const checkReady = setInterval(() => {
        if (session.scrollback.length > 0) {
          clearInterval(checkReady);
          setTimeout(() => {
            bridgeChatToPty(agentId, prompt);
          }, 1000);
        }
      }, 500);
      // Fallback: send after 8s regardless
      setTimeout(() => {
        clearInterval(checkReady);
        if (!session.isBusy) {
          bridgeChatToPty(agentId, prompt);
        }
      }, 8000);
    }

    res.status(201).json({
      agentId,
      pid: session.process.pid,
      workingDirectory: parsed.data.workingDirectory,
    });
  } catch (err) {
    res.status(500).json({ error: "Failed to spawn agent", details: String(err) });
  }
});

/** Send a chat message to an agent */
app.post("/agents/:agentId/chat", (req, res) => {
  const { agentId } = req.params;
  const parsed = ChatSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid request", details: parsed.error.errors });
    return;
  }

  const sent = bridgeChatToPty(agentId, parsed.data.message);
  if (!sent) {
    const session = agentPtys.get(agentId);
    if (!session) {
      res.status(404).json({ error: "Agent not found" });
    } else {
      res.status(429).json({ error: "Agent is busy" });
    }
    return;
  }

  res.json({ status: "sent", agentId });
});

/** Kill an agent */
app.delete("/agents/:agentId", (req, res) => {
  const { agentId } = req.params;
  const killed = killAgentPty(agentId);
  if (!killed) {
    res.status(404).json({ error: "Agent not found" });
    return;
  }
  res.json({ status: "killed", agentId });
});

/** Reset an agent (kill + respawn fresh) */
app.post("/agents/:agentId/reset", (req, res) => {
  const { agentId } = req.params;
  const session = resetAgentPty(agentId);
  if (!session) {
    res.status(404).json({ error: "Agent not found" });
    return;
  }
  res.json({ status: "reset", agentId, pid: session.ptyProcess.pid });
});

// --- Start server ---
server.listen(PORT, () => {
  console.log(`PTY Sidecar running on http://localhost:${PORT}`);
  console.log(`  REST API:     http://localhost:${PORT}/agents`);
  console.log(`  Event WS:     ws://localhost:${PORT}/ws`);
  console.log(`  Terminal WS:  ws://localhost:${PORT}/ws/terminal/:agentId`);
});
