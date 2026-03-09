import { useEffect, useState, useCallback } from "react";
import {
  Radio, RefreshCw, Plus, Trash2, Play, Pause, Zap,
  Clock, AlertCircle, Globe, MessageSquare, Users, X
} from "lucide-react";
import { sourcesApi, actionsApi } from "../lib/api";

interface Source {
  id: number;
  name: string;
  url: string;
  source_type: string;
  check_interval_seconds: number;
  is_active: number;
  last_checked_at: string | null;
  last_content_hash: string | null;
  error_count: number;
  last_error: string | null;
  created_at: string;
}

const typeIcons: Record<string, React.ReactNode> = {
  webpage: <Globe className="w-4 h-4" />,
  social: <MessageSquare className="w-4 h-4" />,
  partner: <Users className="w-4 h-4" />,
};

const typeColors: Record<string, string> = {
  webpage: "text-blue-400",
  social: "text-purple-400",
  partner: "text-green-400",
};

export default function Sources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSource, setNewSource] = useState({
    name: "", url: "", source_type: "webpage", check_interval_seconds: 60,
  });
  const [checkingId, setCheckingId] = useState<number | null>(null);

  const fetchSources = useCallback(async () => {
    try {
      const result = await sourcesApi.list();
      setSources(result.sources || []);
    } catch (err) {
      console.error("Failed to fetch sources:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
    const interval = setInterval(fetchSources, 10000);
    return () => clearInterval(interval);
  }, [fetchSources]);

  const handleToggle = async (source: Source) => {
    try {
      await sourcesApi.update(source.id, { is_active: source.is_active ? 0 : 1 });
      fetchSources();
    } catch (err) {
      console.error("Toggle failed:", err);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm("Delete this source?")) return;
    try {
      await sourcesApi.delete(id);
      fetchSources();
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  const handleCheck = async (id: number) => {
    setCheckingId(id);
    try {
      await actionsApi.checkSource(id);
      setTimeout(fetchSources, 1000);
    } catch (err) {
      console.error("Check failed:", err);
    } finally {
      setCheckingId(null);
    }
  };

  const handleAdd = async () => {
    if (!newSource.name || !newSource.url) return;
    try {
      await sourcesApi.create(newSource);
      setNewSource({ name: "", url: "", source_type: "webpage", check_interval_seconds: 60 });
      setShowAddForm(false);
      fetchSources();
    } catch (err) {
      console.error("Add failed:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Radio className="w-6 h-6 text-cyan-400" />
            Monitored Sources
          </h1>
          <p className="text-sm text-gray-400">
            {sources.length} sources configured, {sources.filter((s) => s.is_active).length} active
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
        >
          {showAddForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showAddForm ? "Cancel" : "Add Source"}
        </button>
      </div>

      {/* Add Source Form */}
      {showAddForm && (
        <div className="bg-gray-900 rounded-xl border border-cyan-500/30 p-5">
          <h2 className="text-lg font-semibold text-white mb-4">Add New Source</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={newSource.name}
                onChange={(e) => setNewSource({ ...newSource, name: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-cyan-500 focus:outline-none"
                placeholder="Source name"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">URL</label>
              <input
                type="url"
                value={newSource.url}
                onChange={(e) => setNewSource({ ...newSource, url: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-cyan-500 focus:outline-none"
                placeholder="https://..."
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Type</label>
              <select
                value={newSource.source_type}
                onChange={(e) => setNewSource({ ...newSource, source_type: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-cyan-500 focus:outline-none"
              >
                <option value="webpage">Webpage</option>
                <option value="social">Social</option>
                <option value="partner">Partner</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Check Interval (seconds)</label>
              <input
                type="number"
                min={10}
                value={newSource.check_interval_seconds}
                onChange={(e) =>
                  setNewSource({ ...newSource, check_interval_seconds: parseInt(e.target.value) || 60 })
                }
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>
          <button
            onClick={handleAdd}
            disabled={!newSource.name || !newSource.url}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Source
          </button>
        </div>
      )}

      {/* Sources List */}
      <div className="space-y-3">
        {sources.map((source) => (
          <div
            key={source.id}
            className={`bg-gray-900 rounded-xl border p-4 transition-all ${
              source.error_count > 0
                ? "border-red-500/30 hover:border-red-500/50"
                : source.is_active
                ? "border-gray-800 hover:border-cyan-500/30"
                : "border-gray-800/50 opacity-60"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3 flex-1 min-w-0">
                {/* Status indicator */}
                <div className="mt-1">
                  <span className={`block w-3 h-3 rounded-full ${
                    source.error_count > 0 ? "bg-red-500" :
                    source.is_active ? "bg-green-500 animate-pulse" : "bg-gray-600"
                  }`} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-white font-medium">{source.name}</h3>
                    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-gray-800 ${typeColors[source.source_type] || "text-gray-400"}`}>
                      {typeIcons[source.source_type]}
                      {source.source_type}
                    </span>
                  </div>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-cyan-400/70 hover:text-cyan-400 truncate block"
                  >
                    {source.url}
                  </a>
                  <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Every {source.check_interval_seconds}s
                    </span>
                    {source.last_checked_at && (
                      <span>
                        Last checked: {new Date(source.last_checked_at).toLocaleTimeString()}
                      </span>
                    )}
                    {source.error_count > 0 && (
                      <span className="flex items-center gap-1 text-red-400">
                        <AlertCircle className="w-3 h-3" />
                        {source.error_count} errors
                      </span>
                    )}
                  </div>
                  {source.last_error && (
                    <p className="text-xs text-red-400/70 mt-1 truncate">
                      {source.last_error}
                    </p>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={() => handleCheck(source.id)}
                  disabled={checkingId === source.id}
                  className="p-2 text-gray-400 hover:text-cyan-400 hover:bg-gray-800 rounded-lg transition-colors"
                  title="Check now"
                >
                  {checkingId === source.id ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Zap className="w-4 h-4" />
                  )}
                </button>
                <button
                  onClick={() => handleToggle(source)}
                  className={`p-2 rounded-lg transition-colors ${
                    source.is_active
                      ? "text-green-400 hover:text-red-400 hover:bg-gray-800"
                      : "text-gray-500 hover:text-green-400 hover:bg-gray-800"
                  }`}
                  title={source.is_active ? "Pause" : "Resume"}
                >
                  {source.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                </button>
                <button
                  onClick={() => handleDelete(source.id)}
                  className="p-2 text-gray-500 hover:text-red-400 hover:bg-gray-800 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
