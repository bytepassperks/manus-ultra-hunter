import { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle, Bell, Filter, RefreshCw, ExternalLink,
  ChevronDown, Send
} from "lucide-react";
import { detectionsApi, actionsApi } from "../lib/api";

interface Detection {
  id: number;
  source_id: number;
  source_name: string;
  title: string;
  detection_type: string;
  url: string;
  priority: string;
  summary: string;
  action: string;
  detected_rewards: string;
  notified: number;
  created_at: string;
}

const priorityColors: Record<string, string> = {
  CRITICAL: "bg-red-500/20 text-red-400 border-red-500/30",
  HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  MEDIUM: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  LOW: "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

const priorityEmoji: Record<string, string> = {
  CRITICAL: "🚨", HIGH: "⚠️", MEDIUM: "📋", LOW: "ℹ️",
};

export default function Alerts() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("ALL");
  const [sending, setSending] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const limit = 20;

  const fetchDetections = useCallback(async (reset = false) => {
    try {
      const currentOffset = reset ? 0 : offset;
      const params: Record<string, string | number> = { limit, offset: currentOffset };
      if (filter !== "ALL") params.priority = filter;

      const result = await detectionsApi.list(params as {
        limit?: number; offset?: number; priority?: string;
      });
      const newDetections = result.detections || [];
      if (reset) {
        setDetections(newDetections);
        setOffset(limit);
      } else {
        setDetections((prev) => [...prev, ...newDetections]);
        setOffset((prev) => prev + limit);
      }
      setHasMore(newDetections.length === limit);
    } catch (err) {
      console.error("Failed to fetch detections:", err);
    } finally {
      setLoading(false);
    }
  }, [filter, offset]);

  useEffect(() => {
    setLoading(true);
    setOffset(0);
    fetchDetections(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const handleSendNotifications = async () => {
    setSending(true);
    try {
      await actionsApi.sendNotifications();
    } catch (err) {
      console.error("Send notifications failed:", err);
    } finally {
      setSending(false);
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
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Bell className="w-6 h-6 text-orange-400" />
            Alert History
          </h1>
          <p className="text-sm text-gray-400">
            All detected changes and notifications
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSendNotifications}
            disabled={sending}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            <Send className="w-4 h-4" />
            {sending ? "Sending..." : "Send Pending"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => (
          <button
            key={p}
            onClick={() => setFilter(p)}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              filter === p
                ? "bg-cyan-600/30 text-cyan-400 border-cyan-500/50"
                : "bg-gray-800 text-gray-400 border-gray-700 hover:border-gray-600"
            }`}
          >
            <Filter className="w-3 h-3 inline mr-1" />
            {p}
          </button>
        ))}
      </div>

      {/* Detections List */}
      {detections.length === 0 ? (
        <div className="text-center text-gray-500 py-16 bg-gray-900 rounded-xl border border-gray-800">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg">No detections found</p>
          <p className="text-sm mt-1">The system will alert you when changes are detected</p>
        </div>
      ) : (
        <div className="space-y-3">
          {detections.map((det) => (
            <div
              key={det.id}
              className={`bg-gray-900 rounded-xl border p-4 transition-all hover:bg-gray-800/50 ${
                priorityColors[det.priority] || "border-gray-800"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="text-lg">{priorityEmoji[det.priority] || "📌"}</span>
                    <span className="text-xs font-bold uppercase px-2 py-0.5 rounded bg-gray-800">
                      {det.priority}
                    </span>
                    <span className="text-xs text-gray-500 px-2 py-0.5 rounded bg-gray-800/50">
                      {det.detection_type}
                    </span>
                    {det.notified ? (
                      <span className="text-xs text-green-400 px-2 py-0.5 rounded bg-green-500/10">
                        ✓ Notified
                      </span>
                    ) : (
                      <span className="text-xs text-yellow-400 px-2 py-0.5 rounded bg-yellow-500/10">
                        Pending
                      </span>
                    )}
                  </div>
                  <h3 className="text-white font-medium mb-1">{det.title}</h3>
                  {det.summary && (
                    <p className="text-sm text-gray-400 mb-2">{det.summary}</p>
                  )}
                  {det.detected_rewards && (
                    <p className="text-sm mb-1">
                      <span className="text-gray-500">Rewards: </span>
                      <span className="text-yellow-400">{det.detected_rewards}</span>
                    </p>
                  )}
                  {det.action && (
                    <p className="text-sm mb-1">
                      <span className="text-gray-500">Action: </span>
                      <span className="text-cyan-400">{det.action}</span>
                    </p>
                  )}
                  {det.url && (
                    <a
                      href={det.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-sm text-cyan-400 hover:text-cyan-300 mt-1"
                    >
                      <ExternalLink className="w-3 h-3" />
                      {det.url}
                    </a>
                  )}
                </div>
                <div className="text-right flex-shrink-0 text-xs text-gray-500">
                  <p className="font-medium text-gray-400">{det.source_name}</p>
                  <p className="mt-1">{new Date(det.created_at).toLocaleString()}</p>
                </div>
              </div>
            </div>
          ))}
          {hasMore && (
            <button
              onClick={() => fetchDetections(false)}
              className="w-full py-3 text-sm text-gray-400 hover:text-white bg-gray-900 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors flex items-center justify-center gap-2"
            >
              <ChevronDown className="w-4 h-4" />
              Load More
            </button>
          )}
        </div>
      )}
    </div>
  );
}
