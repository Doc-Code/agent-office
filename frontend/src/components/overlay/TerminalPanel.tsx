"use client";

import { useEffect, useRef, useState } from "react";
import { X, Maximize2, Minimize2 } from "lucide-react";
import "@xterm/xterm/css/xterm.css";

const PTY_SIDECAR_WS = "ws://localhost:8001";

interface TerminalPanelProps {
  agentId: string;
  agentName: string;
  onClose: () => void;
}

export default function TerminalPanel({
  agentId,
  agentName,
  onClose,
}: TerminalPanelProps) {
  const termRef = useRef<HTMLDivElement>(null);
  const termInstance = useRef<import("@xterm/xterm").Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function initTerminal() {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");

      if (cancelled || !termRef.current) return;

      const fitAddon = new FitAddon();
      const term = new Terminal({
        cursorBlink: true,
        fontSize: 12,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        theme: {
          background: "#0f172a",
          foreground: "#e2e8f0",
          cursor: "#60a5fa",
          selectionBackground: "#334155",
        },
        convertEol: true,
      });

      term.loadAddon(fitAddon);
      term.open(termRef.current);
      fitAddon.fit();
      termInstance.current = term;

      term.writeln(`\x1b[1;34m--- Terminal: ${agentName} (${agentId}) ---\x1b[0m`);
      term.writeln(`\x1b[90mConnecting to PTY sidecar...\x1b[0m`);

      // Connect to terminal WebSocket
      const ws = new WebSocket(`${PTY_SIDECAR_WS}/ws/terminal/${agentId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        term.writeln(`\x1b[32mConnected.\x1b[0m\n`);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "output" && typeof msg.data === "string") {
            term.write(msg.data);
          } else if (msg.type === "exit") {
            term.writeln(`\n\x1b[1;31m--- Process exited (code ${msg.code}) ---\x1b[0m`);
            setConnected(false);
          }
        } catch {
          // Non-JSON data, write raw
          term.write(event.data);
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        term.writeln(`\n\x1b[90m--- Disconnected ---\x1b[0m`);
      };

      ws.onerror = () => {
        term.writeln(`\x1b[31mWebSocket error. Is the PTY sidecar running?\x1b[0m`);
      };

      // Forward terminal input to WebSocket
      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "input", data }));
        }
      });

      // Handle resize
      const handleResize = () => {
        requestAnimationFrame(() => fitAddon.fit());
      };
      window.addEventListener("resize", handleResize);

      return () => {
        window.removeEventListener("resize", handleResize);
      };
    }

    initTerminal();

    return () => {
      cancelled = true;
      wsRef.current?.close();
      termInstance.current?.dispose();
    };
  }, [agentId, agentName]);

  return (
    <div
      className={`fixed z-50 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl flex flex-col overflow-hidden ${
        isMaximized
          ? "inset-4"
          : "bottom-4 right-4 w-[640px] h-[400px]"
      }`}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700 select-none">
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${connected ? "bg-green-500" : "bg-slate-500"}`}
          />
          <span className="text-sm font-bold text-white">{agentName}</span>
          <span className="text-xs text-slate-500 font-mono">{agentId.slice(-8)}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsMaximized(!isMaximized)}
            className="p-1.5 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors"
          >
            {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-rose-500/20 rounded text-slate-400 hover:text-rose-400 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Terminal */}
      <div ref={termRef} className="flex-grow min-h-0" />
    </div>
  );
}
