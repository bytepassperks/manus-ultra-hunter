import { useEffect, useState, useCallback } from "react";
import {
  Activity, AlertTriangle, Bell, CheckCircle, Clock,
  Radio, RefreshCw, Zap, Eye, Server
} from "lucide-react";
import { dashboardApi, actionsApi } from "../lib/api";

interface DashboardData {
  system: { name: string; version: string; status: string };
  stats: Record<string, number>;
  sources: {
    total: number; active: number; with_errors: number;
    list: Array<{
      id: number; name: string; url: string; source_type: string;
      is_active: number; last_checked_at: string | null;
      error_count: number; last_error: string | null;
      check_interval_seconds: number;
    }>;
  };
  recent_detections: Array<{
    id: number; title: string; priority: string; detection_type: string;
    summary: string; url: string; source_name: string; created_at: string;
    detected_rewards: string; action: string;
  }>;
  pending_notifications: number;
  scheduler: { running: boolean; active_source_tasks: number; total_checks: number };
  timestamp: string;
}

const priorityColors: Record<string, string> = {
  CRITICAL: "bg-red-500/20 text-red-400 border-red-500/30",
  HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  MEDIUM: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  LOW: "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

const priorityDots: Record<string, string> = {
  CRITICAL: "bg-red-500", HIGH: "bg-orange-500",
  MEDIUM: "bg-yellow-500", LOW: "bg-blue-500",
};

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const result = await dashboardApi.getDashboard();
      setData(result);
    } catch (err) {
      console.error("Failed to fetch dashboard:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleCheckAll = async () => {
    try {
      await actionsApi.checkAll();
      setTimeout(fetchData, 2000);
    } catch (err) {
      console.error("Check all failed:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center text-gray-400 py-20">
        <Server className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>Failed to connect to backend</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-400">
            Real-time monitoring overview
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg border border-gray-700 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={handleCheckAll}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
          >
            <Zap className="w-4 h-4" />
            Check All Sources
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={<Radio className="w-5 h-5" />}
          label="Active Sources"
          value={data.sources.active}
          sub={`${data.sources.total} total`}
          color="text-cyan-400"
        />
        <StatCard
          icon={<Eye className="w-5 h-5" />}
          label="Total Checks"
          value={data.scheduler.total_checks}
          sub={data.scheduler.running ? "Scheduler running" : "Scheduler stopped"}
          color="text-green-400"
        />
        <StatCard
          icon={<AlertTriangle className="w-5 h-5" />}
          label="Detections"
          value={data.stats.total || 0}
          sub={`${data.stats.CRITICAL || 0} critical`}
          color="text-orange-400"
        />
        <StatCard
          icon={<Bell className="w-5 h-5" />}
          label="Pending Alerts"
          value={data.pending_notifications}
          sub={`${data.stats.unnotified || 0} unnotified`}
          color="text-yellow-400"
        />
      </div>

      {/* System Status */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            System Status
          </h2>
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
              data.system.status === "running"
                ? "bg-green-500/20 text-green-400 border border-green-500/30"
                : "bg-red-500/20 text-red-400 border border-red-500/30"
            }`}>
              <span className={`w-2 h-2 rounded-full ${data.system.status === "running" ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
              {data.system.status === "running" ? "Running" : "Stopped"}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-400">Version</span>
            <p className="text-white font-medium">{data.system.version}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-400">Active Tasks</span>
            <p className="text-white font-medium">{data.scheduler.active_source_tasks}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-400">Error Sources</span>
            <p className={`font-medium ${data.sources.with_errors > 0 ? "text-red-400" : "text-green-400"}`}>
              {data.sources.with_errors}
            </p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3">
            <span className="text-gray-400">Last Updated</span>
            <p className="text-white font-medium text-xs">
              {new Date(data.timestamp).toLocaleTimeString()}
            </p>
          </div>
        </div>
      </div>

      {/* Sources Overview */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <Radio className="w-5 h-5 text-cyan-400" />
          Monitored Sources
        </h2>
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {data.sources.list.map((source) => (
            <div
              key={source.id}
              className="flex items-center justify-between bg-gray-800/50 rounded-lg p-3 hover:bg-gray-800 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                  source.error_count > 0 ? "bg-red-500" :
                  source.is_active ? "bg-green-500 animate-pulse" : "bg-gray-500"
                }`} />
                <div className="min-w-0">
                  <p className="text-white text-sm font-medium truncate">{source.name}</p>
                  <p className="text-gray-500 text-xs truncate">{source.url}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0 text-xs">
                <span className="text-gray-500">
                  {source.check_interval_seconds}s
                </span>
                <span className={`px-2 py-0.5 rounded ${
                  source.source_type === "webpage" ? "bg-blue-500/20 text-blue-400" :
                  source.source_type === "social" ? "bg-purple-500/20 text-purple-400" :
                  "bg-green-500/20 text-green-400"
                }`}>
                  {source.source_type}
                </span>
                {source.last_checked_at && (
                  <span className="text-gray-500 hidden md:inline">
                    <Clock className="w-3 h-3 inline mr-1" />
                    {new Date(source.last_checked_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Detections */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-orange-400" />
          Recent Detections
        </h2>
        {data.recent_detections.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            <CheckCircle className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>No detections yet. System is monitoring...</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {data.recent_detections.map((det) => (
              <div
                key={det.id}
                className={`rounded-lg p-3 border ${priorityColors[det.priority] || priorityColors.LOW}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`w-2 h-2 rounded-full ${priorityDots[det.priority] || "bg-gray-500"}`} />
                      <span className="text-xs font-bold uppercase">{det.priority}</span>
                      <span className="text-xs opacity-60">{det.detection_type}</span>
                    </div>
                    <p className="text-sm font-medium truncate">{det.title}</p>
                    <p className="text-xs opacity-70 mt-1 line-clamp-2">{det.summary}</p>
                    {det.detected_rewards && (
                      <p className="text-xs mt-1">
                        <span className="opacity-60">Rewards: </span>
                        <span className="font-medium">{det.detected_rewards}</span>
                      </p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0 text-xs opacity-60">
                    <p>{det.source_name}</p>
                    <p>{new Date(det.created_at).toLocaleTimeString()}</p>
                  </div>
                </div>
                {det.url && (
                  <a
                    href={det.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-cyan-400 hover:text-cyan-300 mt-1 inline-block truncate max-w-full"
                  >
                    {det.url}
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon, label, value, sub, color,
}: {
  icon: React.ReactNode; label: string; value: number | string;
  sub: string; color: string;
}) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className={`${color} mb-2`}>{icon}</div>
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-sm text-gray-400">{label}</p>
      <p className="text-xs text-gray-500 mt-1">{sub}</p>
    </div>
  );
}
