"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import Modal from "./Modal";

// Predefined repos from the AI Textura workspace
const REPOS = [
  { name: "main-server", path: "/Users/drcode/Documents/work/aitextura/main-server" },
  { name: "frontend_v2", path: "/Users/drcode/Documents/work/aitextura/frontend_v2" },
  { name: "telegram-channel", path: "/Users/drcode/Documents/work/aitextura/telegram-channel" },
  { name: "omni-channel", path: "/Users/drcode/Documents/work/aitextura/omni-channel" },
  { name: "widget-go", path: "/Users/drcode/Documents/work/aitextura/widget-go" },
  { name: "oauth", path: "/Users/drcode/Documents/work/aitextura/oauth" },
  { name: "oauth-ui", path: "/Users/drcode/Documents/work/aitextura/oauth-ui" },
  { name: "nginx", path: "/Users/drcode/Documents/work/aitextura/nginx" },
  { name: "cdn", path: "/Users/drcode/Documents/work/aitextura/cdn" },
  { name: "textura", path: "/Users/drcode/Documents/work/aitextura/textura" },
  { name: "pipedream", path: "/Users/drcode/Documents/work/aitextura/pipedream" },
  { name: "langchain", path: "/Users/drcode/Documents/work/aitextura/langchain" },
  { name: "llm", path: "/Users/drcode/Documents/work/aitextura/llm" },
  { name: "revelton-revenue", path: "/Users/drcode/Documents/work/aitextura/revelton-revenue" },
  { name: "mcp-hub", path: "/Users/drcode/Documents/work/aitextura/mcp-hub" },
  { name: "mcp-scrapingbee", path: "/Users/drcode/Documents/work/aitextura/mcp-scrapingbee" },
  { name: "mcp-travelline", path: "/Users/drcode/Documents/work/aitextura/mcp-travelline" },
  { name: "keycloak-russian-providers", path: "/Users/drcode/Documents/work/aitextura/keycloak-russian-providers" },
  { name: "docs", path: "/Users/drcode/Documents/work/aitextura/docs" },
];

interface SpawnPanelProps {
  onSpawn: (params: {
    name: string;
    repo: string;
    repo_path: string;
    initial_prompt?: string;
  }) => Promise<void>;
  loading: boolean;
}

export default function SpawnPanel({ onSpawn, loading }: SpawnPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [selectedRepo, setSelectedRepo] = useState("");
  const [initialPrompt, setInitialPrompt] = useState("");

  const handleSpawn = async () => {
    const repo = REPOS.find((r) => r.name === selectedRepo);
    if (!repo || !name.trim()) return;

    await onSpawn({
      name: name.trim(),
      repo: repo.name,
      repo_path: repo.path,
      initial_prompt: initialPrompt.trim() || undefined,
    });

    // Reset form
    setName("");
    setSelectedRepo("");
    setInitialPrompt("");
    setIsOpen(false);
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded text-xs font-bold transition-colors"
        title="Spawn new agent"
      >
        <Plus size={14} />
        SPAWN AGENT
      </button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Spawn New Agent"
        footer={
          <>
            <button
              onClick={() => setIsOpen(false)}
              className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSpawn}
              disabled={!name.trim() || !selectedRepo || loading}
              className="px-4 py-2 text-sm font-bold bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors"
            >
              {loading ? "Spawning..." : "Spawn"}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          {/* Agent Name */}
          <div>
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Agent Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Backend Bot"
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Repository */}
          <div>
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Repository
            </label>
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">Select repository...</option>
              {REPOS.map((repo) => (
                <option key={repo.name} value={repo.name}>
                  {repo.name}
                </option>
              ))}
            </select>
          </div>

          {/* Initial Prompt */}
          <div>
            <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Initial Prompt (optional)
            </label>
            <textarea
              value={initialPrompt}
              onChange={(e) => setInitialPrompt(e.target.value)}
              placeholder="Fix the login redirect bug..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none resize-none"
            />
          </div>
        </div>
      </Modal>
    </>
  );
}
