"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Inbox,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Circle,
  Loader2,
} from "lucide-react";
import type { OrchestratorAgent } from "@/hooks/useOrchestrator";

const API_BASE = "http://localhost:8000/api/v1/linear";

interface LinearIssue {
  id: string;
  identifier: string;
  title: string;
  description: string | null;
  priority: number;
  state: { id: string; name: string };
  assignee: { id: string; name: string } | null;
  labels: { nodes: { id: string; name: string }[] };
  url: string;
  createdAt: string;
  updatedAt: string;
}

interface LinearBoardProps {
  agents: OrchestratorAgent[];
  onAssign: (issueId: string, agentId: string) => Promise<void>;
}

const priorityColors: Record<number, string> = {
  0: "text-slate-500",  // No priority
  1: "text-red-500",    // Urgent
  2: "text-orange-500", // High
  3: "text-yellow-500", // Medium
  4: "text-blue-400",   // Low
};

const priorityLabels: Record<number, string> = {
  0: "None",
  1: "Urgent",
  2: "High",
  3: "Medium",
  4: "Low",
};

function IssueCard({
  issue,
  agents,
  onAssign,
}: {
  issue: LinearIssue;
  agents: OrchestratorAgent[];
  onAssign: (issueId: string, agentId: string) => void;
}) {
  const [showAssign, setShowAssign] = useState(false);
  const aliveAgents = agents.filter((a) => a.is_alive);

  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 space-y-2">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-slate-500">
              {issue.identifier}
            </span>
            <Circle
              size={8}
              className={`fill-current ${priorityColors[issue.priority] || "text-slate-500"}`}
            />
            <span className="text-[10px] text-slate-500">
              {priorityLabels[issue.priority] || ""}
            </span>
          </div>
          <p className="text-sm text-white font-medium truncate">
            {issue.title}
          </p>
        </div>
        <span className="text-[10px] px-1.5 py-0.5 bg-slate-700 text-slate-400 rounded whitespace-nowrap">
          {issue.state.name}
        </span>
      </div>

      {/* Labels */}
      {issue.labels.nodes.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {issue.labels.nodes.map((label) => (
            <span
              key={label.id}
              className="text-[10px] px-1.5 py-0.5 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded"
            >
              {label.name}
            </span>
          ))}
        </div>
      )}

      {/* Description preview */}
      {issue.description && (
        <p className="text-xs text-slate-500 line-clamp-2">
          {issue.description.slice(0, 200)}
        </p>
      )}

      {/* Assign button */}
      <div className="flex items-center justify-between pt-1">
        {issue.assignee && (
          <span className="text-[10px] text-slate-500">
            Linear: {issue.assignee.name}
          </span>
        )}
        <div className="ml-auto relative">
          <button
            onClick={() => setShowAssign(!showAssign)}
            className="flex items-center gap-1 px-2 py-1 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded text-[10px] font-bold transition-colors"
          >
            <ArrowRight size={10} />
            ASSIGN TO AGENT
          </button>

          {showAssign && (
            <div className="absolute right-0 top-full mt-1 z-10 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden">
              {aliveAgents.length === 0 ? (
                <div className="p-3 text-xs text-slate-500 italic text-center">
                  No active agents
                </div>
              ) : (
                aliveAgents.map((agent) => (
                  <button
                    key={agent.agent_id}
                    onClick={() => {
                      onAssign(issue.id, agent.agent_id);
                      setShowAssign(false);
                    }}
                    className="w-full px-3 py-2 text-left text-xs text-slate-300 hover:bg-slate-700 transition-colors flex items-center gap-2"
                  >
                    <Circle
                      size={6}
                      className="fill-current text-green-500"
                    />
                    <span className="font-bold">{agent.name}</span>
                    <span className="text-slate-500 ml-auto">
                      {agent.assigned_repo}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function LinearBoard({ agents, onAssign }: LinearBoardProps) {
  const [issues, setIssues] = useState<LinearIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(true);
  const [stateFilter, setStateFilter] = useState("");

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/status`);
      if (resp.ok) {
        const data = await resp.json();
        setEnabled(data.enabled);
      }
    } catch {
      setEnabled(false);
    }
  }, []);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (stateFilter) params.set("state", stateFilter);
      const resp = await fetch(`${API_BASE}/issues?${params}`);
      if (resp.ok) {
        setIssues(await resp.json());
      } else {
        const err = await resp.json();
        setError(err.detail || "Failed to fetch issues");
      }
    } catch {
      setError("Cannot connect to backend");
    } finally {
      setLoading(false);
    }
  }, [stateFilter]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (enabled) fetchIssues();
  }, [enabled, fetchIssues]);

  if (enabled === false) {
    return (
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 text-center">
        <AlertCircle size={20} className="text-slate-600 mx-auto mb-2" />
        <p className="text-xs text-slate-500">
          Linear not configured. Set LINEAR_API_KEY in .env
        </p>
      </div>
    );
  }

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden">
      {/* Header */}
      <div
        className="bg-slate-900 px-3 py-2 border-b border-slate-800 flex items-center justify-between cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <Inbox size={14} className="text-violet-500" />
          <span className="text-slate-300 font-bold uppercase tracking-wider text-xs">
            Linear Issues
          </span>
          <span className="text-slate-600 text-xs">({issues.length})</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              fetchIssues();
            }}
            disabled={loading}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
          {isOpen ? (
            <ChevronUp size={14} className="text-slate-500" />
          ) : (
            <ChevronDown size={14} className="text-slate-500" />
          )}
        </div>
      </div>

      {isOpen && (
        <div className="p-2 space-y-2">
          {/* Filter */}
          <div className="flex gap-1">
            {["", "Todo", "In Progress", "Done"].map((state) => (
              <button
                key={state}
                onClick={() => setStateFilter(state)}
                className={`px-2 py-1 rounded text-[10px] font-bold transition-colors ${
                  stateFilter === state
                    ? "bg-violet-500/20 text-violet-400 border border-violet-500/30"
                    : "text-slate-500 hover:text-slate-300 border border-transparent"
                }`}
              >
                {state || "All"}
              </button>
            ))}
          </div>

          {/* Issues list */}
          <div className="space-y-1.5 max-h-96 overflow-y-auto">
            {loading && issues.length === 0 ? (
              <div className="p-4 text-center">
                <Loader2 size={16} className="animate-spin text-slate-500 mx-auto" />
              </div>
            ) : error ? (
              <div className="p-4 text-center text-rose-400 text-xs">{error}</div>
            ) : issues.length === 0 ? (
              <div className="p-4 text-center text-slate-600 text-xs italic">
                {stateFilter ? `No "${stateFilter}" issues` : "No issues found"}
              </div>
            ) : (
              issues.map((issue) => (
                <IssueCard
                  key={issue.id}
                  issue={issue}
                  agents={agents}
                  onAssign={onAssign}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
