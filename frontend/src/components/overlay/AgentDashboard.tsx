"use client";

import { useState } from "react";
import {
  Users,
  Skull,
  Trash2,
  MessageCircle,
  ChevronDown,
  ChevronUp,
  Circle,
  Send,
} from "lucide-react";
import type { OrchestratorAgent } from "@/hooks/useOrchestrator";

interface AgentDashboardProps {
  agents: OrchestratorAgent[];
  onKill: (agentId: string) => Promise<void>;
  onRemove: (agentId: string) => Promise<void>;
  onChat: (agentId: string, message: string) => Promise<void>;
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    working: "text-green-500",
    idle: "text-blue-500",
    stuck: "text-amber-500",
    offline: "text-slate-500",
  };
  return <Circle size={8} className={`fill-current ${colors[status] || "text-slate-500"}`} />;
}

function AgentCard({
  agent,
  onKill,
  onRemove,
  onChat,
}: {
  agent: OrchestratorAgent;
  onKill: () => void;
  onRemove: () => void;
  onChat: (message: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [chatInput, setChatInput] = useState("");

  const handleSend = () => {
    if (!chatInput.trim()) return;
    onChat(chatInput.trim());
    setChatInput("");
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-slate-800"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <StatusDot status={agent.status} />
          <span className="text-sm font-bold text-white">{agent.name}</span>
          <span className="text-xs text-slate-500 font-mono">{agent.assigned_repo}</span>
        </div>
        <div className="flex items-center gap-2">
          {agent.is_alive && (
            <span className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-500 rounded font-mono">
              PID {agent.pid}
            </span>
          )}
          {expanded ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
        </div>
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-slate-700/50">
          {/* Info */}
          <div className="grid grid-cols-2 gap-1 pt-2 text-[10px] text-slate-400 font-mono">
            <span>Status: {agent.status}</span>
            <span>Role: {agent.role}</span>
            <span>Desk: {agent.desk_slot ?? "none"}</span>
            <span>ID: {agent.agent_id.slice(-8)}</span>
          </div>

          {/* Chat Input */}
          {agent.is_alive && (
            <div className="flex gap-1.5">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Send message..."
                className="flex-1 px-2 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={handleSend}
                disabled={!chatInput.trim()}
                className="px-2 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white rounded transition-colors"
              >
                <Send size={12} />
              </button>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-1.5 pt-1">
            {agent.is_alive && (
              <button
                onClick={(e) => { e.stopPropagation(); onKill(); }}
                className="flex items-center gap-1 px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 border border-amber-500/30 rounded text-[10px] font-bold transition-colors"
              >
                <Skull size={10} />
                KILL
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onRemove(); }}
              className="flex items-center gap-1 px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 border border-rose-500/30 rounded text-[10px] font-bold transition-colors"
            >
              <Trash2 size={10} />
              REMOVE
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentDashboard({
  agents,
  onKill,
  onRemove,
  onChat,
}: AgentDashboardProps) {
  const [isOpen, setIsOpen] = useState(true);
  const aliveCount = agents.filter((a) => a.is_alive).length;

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden">
      {/* Header */}
      <div
        className="bg-slate-900 px-3 py-2 border-b border-slate-800 flex items-center justify-between cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <Users size={14} className="text-blue-500" />
          <span className="text-slate-300 font-bold uppercase tracking-wider text-xs">
            Agents
          </span>
          <span className="text-slate-600 text-xs">({aliveCount} active)</span>
        </div>
        {isOpen ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
      </div>

      {/* Content */}
      {isOpen && (
        <div className="p-2 space-y-1.5 max-h-80 overflow-y-auto">
          {agents.length === 0 ? (
            <div className="p-4 text-center text-slate-600 text-xs italic">
              No agents spawned yet
            </div>
          ) : (
            agents.map((agent) => (
              <AgentCard
                key={agent.agent_id}
                agent={agent}
                onKill={() => onKill(agent.agent_id)}
                onRemove={() => onRemove(agent.agent_id)}
                onChat={(msg) => onChat(agent.agent_id, msg)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
