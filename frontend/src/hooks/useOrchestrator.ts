"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = "http://localhost:8000/api/v1/orchestrator";

export interface OrchestratorAgent {
  agent_id: string;
  name: string;
  role: string;
  status: string;
  assigned_repo: string | null;
  repo_path: string | null;
  desk_slot: number | null;
  pid: number | null;
  is_alive: boolean;
}

interface SpawnParams {
  name: string;
  repo?: string;
  repo_path?: string;
  personality?: string;
  initial_prompt?: string;
}

export function useOrchestrator() {
  const [agents, setAgents] = useState<OrchestratorAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/agents`);
      if (resp.ok) {
        const data = await resp.json();
        setAgents(data);
      }
    } catch {
      // Silently fail - sidecar may not be running
    }
  }, []);

  useEffect(() => {
    fetchAgents();
    const interval = setInterval(fetchAgents, 5000);
    return () => clearInterval(interval);
  }, [fetchAgents]);

  const spawnAgent = useCallback(async (params: SpawnParams) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Spawn failed");
      }
      const agent = await resp.json();
      setAgents((prev) => [...prev, agent]);
      return agent;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  const killAgent = useCallback(async (agentId: string) => {
    try {
      await fetch(`${API_BASE}/agents/${agentId}`, { method: "DELETE" });
      setAgents((prev) =>
        prev.map((a) =>
          a.agent_id === agentId ? { ...a, status: "offline", is_alive: false } : a,
        ),
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
    }
  }, []);

  const chatAgent = useCallback(async (agentId: string, message: string) => {
    try {
      const resp = await fetch(`${API_BASE}/agents/${agentId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Chat failed");
      }
      return await resp.json();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
      throw e;
    }
  }, []);

  const removeAgent = useCallback(async (agentId: string) => {
    try {
      await fetch(`${API_BASE}/agents/${agentId}/record`, { method: "DELETE" });
      setAgents((prev) => prev.filter((a) => a.agent_id !== agentId));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
    }
  }, []);

  return {
    agents,
    loading,
    error,
    spawnAgent,
    killAgent,
    chatAgent,
    removeAgent,
    refreshAgents: fetchAgents,
  };
}
