import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

export const dashboardApi = {
  getDashboard: () => api.get("/api/dashboard").then((r) => r.data),
  getStatus: () => api.get("/api/status").then((r) => r.data),
};

export const settingsApi = {
  getSettings: () => api.get("/api/settings").then((r) => r.data),
  getSettingsRaw: () => api.get("/api/settings/raw").then((r) => r.data),
  updateSetting: (key: string, value: string) =>
    api.put("/api/settings", { key, value }).then((r) => r.data),
  updateBatch: (settings: Record<string, string>) =>
    api.put("/api/settings/batch", { settings }).then((r) => r.data),
};

export const sourcesApi = {
  list: (activeOnly = false) =>
    api.get(`/api/sources?active_only=${activeOnly}`).then((r) => r.data),
  get: (id: number) => api.get(`/api/sources/${id}`).then((r) => r.data),
  create: (data: {
    name: string;
    url: string;
    source_type?: string;
    check_interval_seconds?: number;
    is_active?: boolean;
  }) => api.post("/api/sources", data).then((r) => r.data),
  update: (id: number, data: Record<string, unknown>) =>
    api.put(`/api/sources/${id}`, data).then((r) => r.data),
  delete: (id: number) => api.delete(`/api/sources/${id}`).then((r) => r.data),
};

export const detectionsApi = {
  list: (params?: {
    limit?: number;
    offset?: number;
    priority?: string;
    source_id?: number;
  }) => api.get("/api/detections", { params }).then((r) => r.data),
  stats: () => api.get("/api/detections/stats").then((r) => r.data),
};

export const schedulerApi = {
  status: () => api.get("/api/scheduler/status").then((r) => r.data),
  start: () => api.post("/api/scheduler/start").then((r) => r.data),
  stop: () => api.post("/api/scheduler/stop").then((r) => r.data),
};

export const actionsApi = {
  checkSource: (id: number) =>
    api.post(`/api/actions/check/${id}`).then((r) => r.data),
  checkAll: () => api.post("/api/actions/check-all").then((r) => r.data),
  sendNotifications: () =>
    api.post("/api/actions/send-notifications").then((r) => r.data),
  testTelegram: () =>
    api.post("/api/actions/test-telegram").then((r) => r.data),
};

export default api;
