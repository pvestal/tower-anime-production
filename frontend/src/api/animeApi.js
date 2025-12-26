import axios from "axios";

const api = axios.create({
  baseURL: "/api/anime",
  timeout: 30000,
});

export default {
  // Characters
  getCharacters: () => api.get("/characters"),
  getCharacter: (key) => api.get(`/characters/${key}`),
  updateCharacter: (key, data) => api.post(`/characters/${key}`, data),
  deleteCharacter: (key) => api.delete(`/characters/${key}`),

  // Generation
  generate: (data) => api.post("/generate", data),
  getQueue: () => api.get("/queue"),
  getHistory: (limit = 20) => api.get(`/history?limit=${limit}`),

  // Images
  getCharacterImages: (key, limit = 20) =>
    api.get(`/images/list/${key}?limit=${limit}`),

  // Settings
  getSettings: () => api.get("/settings"),
  updateSettings: (data) => api.post("/settings", data),
  getStyles: () => api.get("/styles"),
  saveStyles: (data) => api.post("/styles", data),
  getModels: () => api.get("/models"),

  // V2 API endpoints for job tracking
  v2: {
    getSystemHealth: () =>
      axios.get("/video/v2/system/health", { timeout: 5000 }),
    getJobs: (limit = 10, status = null) => {
      const params = new URLSearchParams();
      params.append("limit", limit);
      if (status) params.append("status", status);
      return axios.get(`/video/v2/jobs?${params.toString()}`);
    },
    getJobDetails: (jobId) => axios.get(`/video/v2/jobs/${jobId}`),
    getStats: () => axios.get("/video/v2/stats/summary"),
    getQueueStatus: () => axios.get("/video/v2/queue/status"),
  },
};
