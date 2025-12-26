<template>
  <div class="status-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <h3>System Status</h3>
      <div class="header-center">
        <!-- Echo Brain Connection Status -->
        <div
          class="echo-brain-status"
          :class="
            connectionIndicator.status.connected ? 'connected' : 'disconnected'
          "
        >
          <i
            :class="
              connectionIndicator.status.connected
                ? 'pi pi-wifi'
                : 'pi pi-wifi-slash'
            "
          ></i>
          <span class="status-text">
            Echo Brain: {{ connectionIndicator.echoBrain }}
          </span>
          <span class="connection-text">
            {{
              connectionIndicator.status.connected
                ? "Connected"
                : "Disconnected"
            }}
          </span>
        </div>
      </div>
      <div class="status-controls">
        <button
          class="control-button secondary"
          :disabled="loading"
          @click="refreshStatus"
        >
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
          Refresh
        </button>
        <button class="control-button secondary" @click="clearCompleted">
          <i class="pi pi-trash"></i>
          Clear Completed
        </button>
        <button
          v-if="echoAlerts.length > 0"
          class="control-button secondary"
          @click="clearAlerts"
        >
          <i class="pi pi-bell-slash"></i>
          Clear Alerts ({{ echoAlerts.length }})
        </button>
        <div class="auto-refresh-toggle">
          <input
            id="auto-refresh"
            v-model="autoRefresh"
            type="checkbox"
            class="toggle-checkbox"
          />
          <label for="auto-refresh" class="toggle-label">Real-time</label>
        </div>
      </div>
    </div>

    <!-- Pre-flight System Check -->
    <div v-if="showPreFlight" class="status-section pre-flight-section">
      <div class="section-header">
        <h4>🚀 Pre-flight System Check</h4>
        <button
          :disabled="runningPreFlight"
          class="control-button primary"
          @click="runPreFlightCheck"
        >
          {{ runningPreFlight ? "Checking..." : "Run System Check" }}
        </button>
      </div>

      <div v-if="preFlightResults" class="pre-flight-results">
        <div
          v-for="(result, key) in preFlightResults"
          :key="key"
          :class="['check-item', result.passed ? 'passed' : 'failed']"
        >
          <span class="check-icon">{{ result.passed ? "✅" : "❌" }}</span>
          <span class="check-name">{{ result.name }}</span>
          <span class="check-message">{{ result.message }}</span>
        </div>

        <div v-if="preFlightWarnings.length > 0" class="warnings-section">
          <h5>⚠️ Warnings:</h5>
          <div
            v-for="warning in preFlightWarnings"
            :key="warning"
            class="warning-item"
          >
            {{ warning }}
          </div>
        </div>
      </div>
    </div>

    <!-- Failed Job Analysis -->
    <div v-if="failedJobs.length > 0" class="status-section failed-analysis">
      <div class="section-header">
        <h4>🔍 Failed Job Analysis (Recent)</h4>
        <button class="control-button secondary" @click="loadFailedJobs">
          Refresh
        </button>
      </div>

      <div class="failed-jobs-grid">
        <div
          v-for="job in failedJobs.slice(0, 5)"
          :key="job.job_id || job.id"
          class="failed-job-card"
        >
          <div class="job-header">
            <span class="job-id"
              >{{ (job.job_id || job.id).toString().substring(0, 8) }}...</span
            >
            <span class="job-type">{{ job.type }}</span>
            <span class="job-time">{{ formatTime(job.created_at) }}</span>
          </div>
          <div class="job-prompt">{{ job.prompt.substring(0, 50) }}...</div>
          <button class="analyze-btn" @click="analyzeFailure(job)">
            Analyze
          </button>
        </div>
      </div>

      <div class="failure-stats">
        <span>Video Failure Rate: {{ Math.round(videoFailureRate) }}%</span>
        <span>Total Failed: {{ failedJobs.length }}</span>
      </div>
    </div>

    <!-- System Health Overview -->
    <div class="status-section">
      <div class="section-header">
        <h4>System Health</h4>
        <span :class="['health-indicator', systemHealth.status]">
          <i :class="getHealthIcon(systemHealth.status)"></i>
          {{ systemHealth.status.toUpperCase() }}
        </span>
      </div>

      <div class="health-grid">
        <!-- VRAM Usage -->
        <div class="health-card">
          <div class="card-header">
            <span class="card-title">VRAM Usage</span>
            <span class="card-value"
              >{{ formatBytes(vramStats.used) }} /
              {{ formatBytes(vramStats.total) }}</span
            >
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill vram"
              :style="{ width: vramStats.percentage + '%' }"
              :class="{
                warning: vramStats.percentage > 80,
                critical: vramStats.percentage > 95,
              }"
            ></div>
          </div>
          <div class="card-details">
            <span>{{ vramStats.percentage.toFixed(1) }}% used</span>
            <span class="gpu-name">{{ vramStats.gpuName }}</span>
          </div>
        </div>

        <!-- CPU Usage -->
        <div class="health-card">
          <div class="card-header">
            <span class="card-title">CPU Usage</span>
            <span class="card-value"
              >{{ cpuStats.percentage.toFixed(1) }}%</span
            >
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill cpu"
              :style="{ width: cpuStats.percentage + '%' }"
              :class="{
                warning: cpuStats.percentage > 80,
                critical: cpuStats.percentage > 95,
              }"
            ></div>
          </div>
          <div class="card-details">
            <span>{{ cpuStats.cores }} cores</span>
            <span>Load: {{ cpuStats.loadAverage.toFixed(2) }}</span>
          </div>
        </div>

        <!-- Memory Usage -->
        <div class="health-card">
          <div class="card-header">
            <span class="card-title">Memory Usage</span>
            <span class="card-value"
              >{{ formatBytes(memoryStats.used) }} /
              {{ formatBytes(memoryStats.total) }}</span
            >
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill memory"
              :style="{ width: memoryStats.percentage + '%' }"
              :class="{
                warning: memoryStats.percentage > 80,
                critical: memoryStats.percentage > 95,
              }"
            ></div>
          </div>
          <div class="card-details">
            <span>{{ memoryStats.percentage.toFixed(1) }}% used</span>
            <span>Available: {{ formatBytes(memoryStats.available) }}</span>
          </div>
        </div>

        <!-- Disk Usage -->
        <div class="health-card">
          <div class="card-header">
            <span class="card-title">Disk Usage</span>
            <span class="card-value"
              >{{ formatBytes(diskStats.used) }} /
              {{ formatBytes(diskStats.total) }}</span
            >
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill disk"
              :style="{ width: diskStats.percentage + '%' }"
              :class="{
                warning: diskStats.percentage > 80,
                critical: diskStats.percentage > 95,
              }"
            ></div>
          </div>
          <div class="card-details">
            <span>{{ diskStats.percentage.toFixed(1) }}% used</span>
            <span>Free: {{ formatBytes(diskStats.free) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Generation Queue -->
    <div class="status-section">
      <div class="section-header">
        <h4>Generation Queue</h4>
        <div class="queue-stats">
          <span class="queue-stat">
            <i class="pi pi-clock"></i>
            {{ queueStats.pending }} pending
          </span>
          <span class="queue-stat">
            <i class="pi pi-play"></i>
            {{ queueStats.running }} running
          </span>
          <span class="queue-stat">
            <i class="pi pi-check"></i>
            {{ queueStats.completed }} completed
          </span>
        </div>
      </div>

      <div class="queue-container">
        <!-- Active Generation -->
        <div v-if="activeGeneration" class="active-generation">
          <div class="generation-header">
            <div class="generation-info">
              <span class="generation-title">{{
                activeGeneration.title || activeGeneration.id
              }}</span>
              <span class="generation-type">{{
                activeGeneration.type || "Anime Generation"
              }}</span>
              <div class="generation-meta">
                <span class="generation-id">ID: {{ activeGeneration.id }}</span>
                <span
                  class="generation-status"
                  :class="activeGeneration.status"
                >
                  {{ (activeGeneration.status || "running").toUpperCase() }}
                </span>
              </div>
            </div>
            <div class="generation-actions">
              <button
                v-if="
                  activeGeneration.status === 'running' &&
                  !activeGeneration.paused
                "
                class="action-button"
                title="Pause Generation"
                @click="pauseGeneration"
              >
                <i class="pi pi-pause"></i>
              </button>
              <button
                v-if="
                  activeGeneration.paused ||
                  activeGeneration.status === 'paused'
                "
                class="action-button"
                title="Resume Generation"
                @click="resumeGeneration"
              >
                <i class="pi pi-play"></i>
              </button>
              <button
                v-if="['running', 'paused'].includes(activeGeneration.status)"
                class="action-button danger"
                title="Cancel Generation"
                @click="cancelGeneration"
              >
                <i class="pi pi-times"></i>
              </button>
            </div>
          </div>

          <div class="generation-progress">
            <div class="progress-info">
              <div class="progress-left">
                <span
                  >Step {{ activeGeneration.currentStep || 0 }} of
                  {{ activeGeneration.totalSteps || 0 }}</span
                >
                <span class="current-stage">{{
                  activeGeneration.stage || "Processing"
                }}</span>
              </div>
              <div class="progress-right">
                <span class="progress-percentage"
                  >{{ (activeGeneration.progress || 0).toFixed(1) }}%</span
                >
                <span v-if="activeGeneration.speed" class="generation-speed">
                  {{ activeGeneration.speed.toFixed(2) }} steps/sec
                </span>
              </div>
            </div>

            <div class="progress-bar large">
              <div
                class="progress-fill active"
                :style="{ width: (activeGeneration.progress || 0) + '%' }"
                :class="{
                  'progress-paused': activeGeneration.paused,
                  'progress-error': activeGeneration.status === 'failed',
                }"
              ></div>
            </div>

            <div class="progress-details">
              <div class="time-info">
                <span>ETA: {{ formatTime(activeGeneration.eta || 0) }}</span>
                <span
                  >Elapsed:
                  {{ formatTime(activeGeneration.elapsed || 0) }}</span
                >
              </div>
              <div class="technical-info">
                <span v-if="activeGeneration.model"
                  >Model: {{ activeGeneration.model }}</span
                >
                <span v-if="activeGeneration.resolution"
                  >Size: {{ activeGeneration.resolution }}</span
                >
              </div>
            </div>
          </div>

          <div v-if="activeGeneration.stages" class="generation-stages">
            <div
              v-for="stage in activeGeneration.stages"
              :key="stage.name"
              :class="['stage-item', stage.status]"
            >
              <i :class="getStageIcon(stage.status)"></i>
              <span class="stage-name">{{ stage.name }}</span>
              <span v-if="stage.progress" class="stage-progress"
                >{{ stage.progress }}%</span
              >
              <span v-if="stage.duration" class="stage-time">{{
                formatTime(stage.duration)
              }}</span>
            </div>
          </div>

          <!-- Real-time Generation Output Preview -->
          <div v-if="activeGeneration.previewUrl" class="generation-preview">
            <div class="preview-header">
              <span>Live Preview</span>
              <button class="mini-button" @click="refreshPreview">
                <i class="pi pi-refresh"></i>
              </button>
            </div>
            <img
              :src="activeGeneration.previewUrl"
              alt="Generation Preview"
              class="preview-image"
            />
          </div>
        </div>

        <!-- Queue List -->
        <div class="queue-list">
          <div
            v-for="item in queueItems"
            :key="item.id"
            :class="['queue-item', item.status]"
            @click="selectQueueItem(item)"
          >
            <div class="queue-item-info">
              <div class="item-header">
                <span class="item-title">{{ item.title }}</span>
                <span :class="['item-status', item.status]">{{
                  item.status.toUpperCase()
                }}</span>
              </div>
              <div class="item-details">
                <span class="item-type">{{ item.type }}</span>
                <span class="item-priority">Priority: {{ item.priority }}</span>
                <span class="item-time">{{
                  formatRelativeTime(item.createdAt)
                }}</span>
              </div>
            </div>

            <div class="queue-item-actions">
              <button
                v-if="item.status === 'pending'"
                class="mini-action"
                @click.stop="moveQueueItem(item, 'up')"
              >
                <i class="pi pi-arrow-up"></i>
              </button>
              <button
                v-if="item.status === 'pending'"
                class="mini-action"
                @click.stop="moveQueueItem(item, 'down')"
              >
                <i class="pi pi-arrow-down"></i>
              </button>
              <button
                class="mini-action danger"
                @click.stop="removeQueueItem(item)"
              >
                <i class="pi pi-trash"></i>
              </button>
            </div>
          </div>

          <div v-if="queueItems.length === 0" class="empty-queue">
            <i class="pi pi-inbox"></i>
            <span>No items in queue</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Real-time Logs -->
    <div class="status-section">
      <div class="section-header">
        <h4>Real-time Logs</h4>
        <div class="log-controls">
          <select v-model="selectedLogLevel" class="log-level-select">
            <option value="all">All Levels</option>
            <option value="error">Errors</option>
            <option value="warning">Warnings</option>
            <option value="info">Info</option>
            <option value="debug">Debug</option>
          </select>
          <button class="control-button secondary" @click="clearLogs">
            <i class="pi pi-trash"></i>
            Clear
          </button>
          <button class="control-button secondary" @click="downloadLogs">
            <i class="pi pi-download"></i>
            Download
          </button>
        </div>
      </div>

      <div ref="logsContainer" class="logs-container">
        <div
          v-for="log in filteredLogs"
          :key="log.id"
          :class="['log-entry', log.level]"
        >
          <span class="log-timestamp">{{ formatLogTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level.toUpperCase() }}</span>
          <span class="log-source">{{ log.source }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>

        <div v-if="filteredLogs.length === 0" class="empty-logs">
          <i class="pi pi-info-circle"></i>
          <span>No logs available</span>
        </div>
      </div>
    </div>

    <!-- Performance Metrics -->
    <div class="status-section">
      <div class="section-header">
        <h4>Performance Metrics</h4>
        <div class="metric-timeframe">
          <select v-model="metricsTimeframe" class="timeframe-select">
            <option value="1h">Last Hour</option>
            <option value="6h">Last 6 Hours</option>
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
          </select>
        </div>
      </div>

      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-header">
            <span class="metric-title">Generations/Hour</span>
            <span class="metric-value">{{
              performanceMetrics.generationsPerHour
            }}</span>
          </div>
          <div class="metric-trend" :class="performanceMetrics.generationTrend">
            <i :class="getTrendIcon(performanceMetrics.generationTrend)"></i>
            {{ performanceMetrics.generationChange }}%
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-header">
            <span class="metric-title">Avg. Generation Time</span>
            <span class="metric-value">{{
              formatTime(performanceMetrics.avgGenerationTime)
            }}</span>
          </div>
          <div class="metric-trend" :class="performanceMetrics.timeTrend">
            <i :class="getTrendIcon(performanceMetrics.timeTrend)"></i>
            {{ performanceMetrics.timeChange }}%
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-header">
            <span class="metric-title">Success Rate</span>
            <span class="metric-value"
              >{{ performanceMetrics.successRate }}%</span
            >
          </div>
          <div class="metric-trend" :class="performanceMetrics.successTrend">
            <i :class="getTrendIcon(performanceMetrics.successTrend)"></i>
            {{ performanceMetrics.successChange }}%
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-header">
            <span class="metric-title">Error Rate</span>
            <span class="metric-value"
              >{{ performanceMetrics.errorRate }}%</span
            >
          </div>
          <div class="metric-trend" :class="performanceMetrics.errorTrend">
            <i :class="getTrendIcon(performanceMetrics.errorTrend)"></i>
            {{ performanceMetrics.errorChange }}%
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import {
  ref,
  reactive,
  computed,
  onMounted,
  onUnmounted,
  nextTick,
  watch,
} from "vue";
import { useWebSocket } from "@/composables/useWebSocket.js";

export default {
  name: "StatusDashboard",
  setup() {
    const loading = ref(false);
    const autoRefresh = ref(true);
    const selectedLogLevel = ref("all");
    const metricsTimeframe = ref("1h");
    const refreshInterval = ref(null);

    // Initialize WebSocket connection to Echo Brain
    const {
      connectionStatus,
      isConnected,
      systemStatus: echoSystemStatus,
      generationState: echoGenerationState,
      metrics: echoMetrics,
      logs: echoLogs,
      alerts: echoAlerts,
      communications: echoCommunications,
      requestSystemStatus,
      requestQueueStatus,
      subscribeToGeneration,
      sendGenerationCommand,
      clearAlerts,
      clearLogs: clearEchoLogs,
    } = useWebSocket();

    // System health - now connected to Echo Brain
    const systemHealth = computed(() => ({
      status: isConnected.value
        ? echoSystemStatus.healthy
          ? "healthy"
          : "warning"
        : "error",
    }));

    // VRAM stats from Echo Brain metrics
    const vramStats = computed(() => ({
      used: echoMetrics.vram?.nvidia_used || 0,
      total: echoMetrics.vram?.nvidia_total || 12000000000,
      percentage: echoMetrics.vram?.nvidia || 0,
      gpuName: "NVIDIA RTX 3060",
    }));

    const cpuStats = computed(() => ({
      percentage: echoMetrics.cpu || 0,
      cores: echoMetrics.cpu_cores || 8,
      loadAverage: echoMetrics.load_average || 0,
    }));

    const memoryStats = computed(() => ({
      used: echoMetrics.memory_used || 0,
      total: echoMetrics.memory_total || 16000000000,
      available: echoMetrics.memory_available || 0,
      percentage: echoMetrics.memory || 0,
    }));

    const diskStats = computed(() => ({
      used: echoMetrics.disk_used || 0,
      total: echoMetrics.disk_total || 1000000000000,
      free: echoMetrics.disk_free || 0,
      percentage: echoMetrics.disk || 0,
    }));

    // Queue management - connected to Echo Brain
    const activeGeneration = computed(() => echoGenerationState.active);
    const queueItems = computed(() => echoGenerationState.queue);
    const queueStats = computed(() => echoGenerationState.queueStats);

    // Logs - combined local and Echo Brain
    const logs = ref([]);
    const logsContainer = ref(null);

    // Pre-flight check state
    const showPreFlight = ref(true);
    const runningPreFlight = ref(false);
    const preFlightResults = ref(null);
    const preFlightWarnings = ref([]);

    // Failed job analysis state
    const failedJobs = ref([]);
    const videoFailureRate = ref(0);

    // Performance metrics from Echo Brain
    const performanceMetrics = computed(() => ({
      generationsPerHour: echoMetrics.generationsPerHour || 0,
      generationTrend: getTrendFromValue(echoMetrics.generationChange || 0),
      generationChange: Math.abs(echoMetrics.generationChange || 0),
      avgGenerationTime: echoMetrics.avgGenerationTime || 0,
      timeTrend: getTrendFromValue(-(echoMetrics.timeChange || 0)), // Negative because less time is better
      timeChange: Math.abs(echoMetrics.timeChange || 0),
      successRate: echoMetrics.successRate || 0,
      successTrend: getTrendFromValue(echoMetrics.successChange || 0),
      successChange: Math.abs(echoMetrics.successChange || 0),
      errorRate: echoMetrics.errorRate || 0,
      errorTrend: getTrendFromValue(-(echoMetrics.errorChange || 0)), // Negative because less error is better
      errorChange: Math.abs(echoMetrics.errorChange || 0),
    }));

    // Helper function for trend calculation
    const getTrendFromValue = (value) => {
      if (value > 0.5) return "up";
      if (value < -0.5) return "down";
      return "neutral";
    };

    // Computed properties
    const filteredLogs = computed(() => {
      // Combine Echo logs with local logs
      const allLogs = [
        ...echoLogs.value.map((log) => ({
          ...log,
          source: log.source || "Echo Brain",
        })),
        ...logs.value,
      ];

      if (selectedLogLevel.value === "all") {
        return allLogs;
      }
      return allLogs.filter((log) => log.level === selectedLogLevel.value);
    });

    // Connection status indicator
    const connectionIndicator = computed(() => ({
      connected: isConnected.value,
      status: connectionStatus.value,
      echoBrain: echoSystemStatus.consciousness || "inactive",
    }));

    // Methods
    const loadSystemHealth = async () => {
      // Now handled by Echo Brain WebSocket
      if (isConnected.value) {
        requestSystemStatus();
      } else {
        // Fallback to REST API if WebSocket not connected
        try {
          const response = await fetch("/api/status/system-health");
          if (response.ok) {
            const data = await response.json();
            // Update local reactive data as fallback
            console.log("Fallback system health data:", data);
          }
        } catch (error) {
          console.error("Failed to load system health:", error);
        }
      }
    };

    const loadGenerationQueue = async () => {
      // Now handled by Echo Brain WebSocket
      if (isConnected.value) {
        requestQueueStatus();
      } else {
        // Fallback to REST API if WebSocket not connected
        try {
          const response = await fetch("/api/generations/queue");
          if (response.ok) {
            const data = await response.json();
            console.log("Fallback queue data:", data);
          }
        } catch (error) {
          console.error("Failed to load generation queue:", error);
        }
      }
    };

    const loadPerformanceMetrics = async () => {
      try {
        const response = await fetch(
          `/api/status/metrics?timeframe=${metricsTimeframe.value}`,
        );
        if (response.ok) {
          const data = await response.json();
          Object.assign(performanceMetrics, data);
        }
      } catch (error) {
        console.error("Failed to load performance metrics:", error);
      }
    };

    const loadLogs = async () => {
      try {
        const response = await fetch("/api/status/logs?limit=100");
        if (response.ok) {
          const data = await response.json();
          logs.value = data.logs;

          // Auto-scroll to bottom
          await nextTick();
          if (logsContainer.value) {
            logsContainer.value.scrollTop = logsContainer.value.scrollHeight;
          }
        }
      } catch (error) {
        console.error("Failed to load logs:", error);
      }
    };

    const refreshStatus = async () => {
      loading.value = true;
      try {
        await Promise.all([
          loadSystemHealth(),
          loadGenerationQueue(),
          loadPerformanceMetrics(),
          loadLogs(),
          loadFailedJobs(),
        ]);
      } finally {
        loading.value = false;
      }
    };

    // Pre-flight check functions
    const runPreFlightCheck = async () => {
      runningPreFlight.value = true;
      preFlightWarnings.value = [];

      try {
        // Run comprehensive pre-flight check for video generation
        const response = await fetch("/api/anime/verification/pre-flight", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workflow_type: "video" }),
        });

        const data = await response.json();

        // Transform check results into display format
        const results = {};
        Object.entries(data.checks || {}).forEach(([key, passed]) => {
          results[key] = {
            name: formatCheckName(key),
            passed: passed,
            message: passed ? "OK" : "Failed",
          };
        });

        preFlightResults.value = results;
        preFlightWarnings.value = data.warnings || [];

        console.log("Pre-flight check completed:", data);
      } catch (error) {
        console.error("Pre-flight check failed:", error);
        preFlightResults.value = {
          error: {
            name: "System Check",
            passed: false,
            message: "Failed to run check",
          },
        };
      } finally {
        runningPreFlight.value = false;
      }
    };

    // Load failed jobs for analysis
    const loadFailedJobs = async () => {
      try {
        const response = await fetch("/api/anime/jobs?status=failed&limit=20");
        const data = await response.json();
        const jobs = data.jobs || data;

        failedJobs.value = jobs.filter((job) => job.status === "failed");

        // Calculate video failure rate
        const videoJobs = jobs.filter((job) => job.type === "video");
        const failedVideoJobs = videoJobs.filter(
          (job) => job.status === "failed",
        );
        videoFailureRate.value =
          videoJobs.length > 0
            ? (failedVideoJobs.length / videoJobs.length) * 100
            : 0;
      } catch (error) {
        console.error("Failed to load failed jobs:", error);
        failedJobs.value = [];
      }
    };

    // Analyze specific failure
    const analyzeFailure = async (job) => {
      try {
        const response = await fetch(
          "/api/anime/verification/analyze-failure",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ job_id: job.job_id || job.id }),
          },
        );

        const analysis = await response.json();

        // Show analysis in console for now - could be expanded to modal
        console.log(
          "Failure analysis for job:",
          job.job_id || job.id,
          analysis,
        );

        // Could add toast notification here
        alert(
          `Analysis complete for job ${(job.job_id || job.id).toString().substring(0, 8)}...\n\nLikely causes:\n${analysis.likely_causes?.join("\n") || "Unknown"}\n\nRecommendations:\n${analysis.recommendations?.join("\n") || "None"}`,
        );
      } catch (error) {
        console.error("Failure analysis error:", error);
        alert("Failed to analyze job failure");
      }
    };

    // Utility function to format check names
    const formatCheckName = (checkKey) => {
      const names = {
        backend: "Backend API",
        gpu: "GPU Availability",
        models: "Required Models",
        video_models: "Video Models",
        comfyui: "ComfyUI Service",
        video_nodes: "Video Nodes",
        disk_space: "Disk Space",
        memory: "System Memory",
        queue_available: "Queue Capacity",
      };
      return names[checkKey] || checkKey.replace(/_/g, " ").toUpperCase();
    };

    const pauseGeneration = async () => {
      if (!activeGeneration.value?.id) {
        console.warn("No active generation to pause");
        return;
      }

      try {
        if (isConnected.value) {
          // Use Echo Brain WebSocket for real-time control
          const success = sendGenerationCommand(
            activeGeneration.value.id,
            "pause",
          );
          if (!success) {
            throw new Error("WebSocket command failed");
          }
        } else {
          // Fallback to REST API
          await fetch(`/api/generations/${activeGeneration.value.id}/pause`, {
            method: "POST",
          });
          await loadGenerationQueue();
        }
      } catch (error) {
        console.error("Failed to pause generation:", error);
      }
    };

    const resumeGeneration = async () => {
      if (!activeGeneration.value?.id) {
        console.warn("No active generation to resume");
        return;
      }

      try {
        if (isConnected.value) {
          // Use Echo Brain WebSocket for real-time control
          const success = sendGenerationCommand(
            activeGeneration.value.id,
            "resume",
          );
          if (!success) {
            throw new Error("WebSocket command failed");
          }
        } else {
          // Fallback to REST API
          await fetch(`/api/generations/${activeGeneration.value.id}/resume`, {
            method: "POST",
          });
          await loadGenerationQueue();
        }
      } catch (error) {
        console.error("Failed to resume generation:", error);
      }
    };

    const cancelGeneration = async () => {
      if (!activeGeneration.value?.id) {
        console.warn("No active generation to cancel");
        return;
      }

      if (!confirm("Cancel the current generation?")) return;

      try {
        if (isConnected.value) {
          // Use Echo Brain WebSocket for real-time control
          const success = sendGenerationCommand(
            activeGeneration.value.id,
            "cancel",
          );
          if (!success) {
            throw new Error("WebSocket command failed");
          }
        } else {
          // Fallback to REST API
          await fetch(`/api/generations/${activeGeneration.value.id}/cancel`, {
            method: "POST",
          });
          await loadGenerationQueue();
        }
      } catch (error) {
        console.error("Failed to cancel generation:", error);
      }
    };

    const selectQueueItem = (item) => {
      // Handle queue item selection
      console.log("Selected queue item:", item);
    };

    const moveQueueItem = async (item, direction) => {
      try {
        await fetch(`/api/generations/queue/${item.id}/move`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ direction }),
        });
        await loadGenerationQueue();
      } catch (error) {
        console.error("Failed to move queue item:", error);
      }
    };

    const removeQueueItem = async (item) => {
      if (!confirm(`Remove "${item.title}" from queue?`)) return;

      try {
        await fetch(`/api/generations/queue/${item.id}`, {
          method: "DELETE",
        });
        await loadGenerationQueue();
      } catch (error) {
        console.error("Failed to remove queue item:", error);
      }
    };

    const clearCompleted = async () => {
      try {
        await fetch("/api/generations/queue/clear-completed", {
          method: "POST",
        });
        await loadGenerationQueue();
      } catch (error) {
        console.error("Failed to clear completed items:", error);
      }
    };

    const clearLogs = () => {
      logs.value = [];
    };

    const downloadLogs = () => {
      const logText = logs.value
        .map(
          (log) =>
            `[${log.timestamp}] ${log.level.toUpperCase()} ${log.source}: ${log.message}`,
        )
        .join("\n");

      const blob = new Blob([logText], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `anime-logs-${new Date().toISOString().split("T")[0]}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    };

    // Utility functions
    const formatBytes = (bytes) => {
      if (!bytes) return "0 B";
      const k = 1024;
      const sizes = ["B", "KB", "MB", "GB", "TB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    };

    const formatTime = (seconds) => {
      if (!seconds) return "0s";
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      const secs = Math.floor(seconds % 60);

      if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
      } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
      } else {
        return `${secs}s`;
      }
    };

    const formatRelativeTime = (dateString) => {
      const date = new Date(dateString);
      const now = new Date();
      const diffMs = now - date;
      const diffMinutes = Math.floor(diffMs / (1000 * 60));

      if (diffMinutes < 1) return "Just now";
      if (diffMinutes < 60) return `${diffMinutes}m ago`;
      const diffHours = Math.floor(diffMinutes / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays}d ago`;
    };

    const formatLogTime = (timestamp) => {
      return new Date(timestamp).toLocaleTimeString();
    };

    const getHealthIcon = (status) => {
      const icons = {
        healthy: "pi pi-check-circle",
        warning: "pi pi-exclamation-triangle",
        error: "pi pi-times-circle",
        unknown: "pi pi-question-circle",
      };
      return icons[status] || icons.unknown;
    };

    const getStageIcon = (status) => {
      const icons = {
        pending: "pi pi-clock",
        running: "pi pi-spin pi-spinner",
        completed: "pi pi-check",
        failed: "pi pi-times",
        skipped: "pi pi-forward",
      };
      return icons[status] || icons.pending;
    };

    const getTrendIcon = (trend) => {
      const icons = {
        up: "pi pi-arrow-up",
        down: "pi pi-arrow-down",
        neutral: "pi pi-minus",
      };
      return icons[trend] || icons.neutral;
    };

    // Auto-refresh setup
    const setupAutoRefresh = () => {
      if (refreshInterval.value) {
        clearInterval(refreshInterval.value);
      }

      if (autoRefresh.value) {
        refreshInterval.value = setInterval(refreshStatus, 5000); // 5 seconds
      }
    };

    // WebSocket event handlers and watchers
    watch(isConnected, (newValue) => {
      console.log(
        `[StatusDashboard] WebSocket connection status changed: ${newValue}`,
      );
      if (newValue) {
        // Connected to Echo Brain - request initial data
        requestSystemStatus();
        requestQueueStatus();
      }
    });

    watch(
      echoAlerts,
      (newAlerts) => {
        // Show browser notifications for critical alerts
        if (newAlerts.length > 0) {
          const latestAlert = newAlerts[0];
          if (
            latestAlert.level === "error" ||
            latestAlert.level === "critical"
          ) {
            showNotification(latestAlert.title, latestAlert.message, "error");
          }
        }
      },
      { deep: true },
    );

    // Auto-subscribe to active generation updates
    watch(activeGeneration, (newGeneration, oldGeneration) => {
      if (oldGeneration?.id && oldGeneration.id !== newGeneration?.id) {
        console.log(
          `[StatusDashboard] Active generation changed from ${oldGeneration.id} to ${newGeneration?.id}`,
        );
      }

      if (newGeneration?.id && isConnected.value) {
        subscribeToGeneration(newGeneration.id);
        console.log(
          `[StatusDashboard] Subscribed to generation updates: ${newGeneration.id}`,
        );
      }
    });

    // Notification system
    const showNotification = (title, message, type = "info") => {
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification(title, {
          body: message,
          icon: "/favicon.ico",
        });
      } else if (
        "Notification" in window &&
        Notification.permission !== "denied"
      ) {
        Notification.requestPermission().then((permission) => {
          if (permission === "granted") {
            new Notification(title, {
              body: message,
              icon: "/favicon.ico",
            });
          }
        });
      }

      // Also add to local alerts if it's an error
      if (type === "error") {
        logs.value.unshift({
          id: Date.now().toString(),
          timestamp: new Date().toISOString(),
          level: "error",
          source: "StatusDashboard",
          message: `${title}: ${message}`,
        });
      }
    };

    // Enhanced refresh function
    const refreshPreview = () => {
      if (activeGeneration.value?.id) {
        // Request updated preview from Echo Brain
        const timestamp = Date.now();
        if (activeGeneration.value.previewUrl) {
          activeGeneration.value.previewUrl =
            activeGeneration.value.previewUrl.split("?")[0] + "?t=" + timestamp;
        }
      }
    };

    // Add method to return to setup
    const addRefreshPreview = () => refreshPreview;

    // Lifecycle
    onMounted(() => {
      refreshStatus();
      setupAutoRefresh();

      // Request notification permission
      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
      }

      console.log(
        "[StatusDashboard] Component mounted, WebSocket integration active",
      );
    });

    onUnmounted(() => {
      if (refreshInterval.value) {
        clearInterval(refreshInterval.value);
      }
      console.log("[StatusDashboard] Component unmounted");
    });

    return {
      // Basic component state
      loading,
      autoRefresh,
      selectedLogLevel,
      metricsTimeframe,

      // WebSocket connection data
      isConnected,
      connectionIndicator,
      connectionStatus,

      // Echo Brain data
      echoAlerts,
      echoCommunications,
      echoLogs,

      // System health (computed from Echo Brain)
      systemHealth,
      vramStats,
      cpuStats,
      memoryStats,
      diskStats,

      // Generation state (computed from Echo Brain)
      activeGeneration,
      queueItems,
      queueStats,

      // Local logs and container ref
      logs,
      logsContainer,

      // Performance metrics (computed from Echo Brain)
      performanceMetrics,
      filteredLogs,

      // Pre-flight check state
      showPreFlight,
      runningPreFlight,
      preFlightResults,
      preFlightWarnings,

      // Failed job analysis state
      failedJobs,
      videoFailureRate,

      // Methods
      refreshStatus,
      runPreFlightCheck,
      loadFailedJobs,
      analyzeFailure,
      pauseGeneration,
      resumeGeneration,
      cancelGeneration,
      selectQueueItem,
      moveQueueItem,
      removeQueueItem,
      clearCompleted,
      clearLogs,
      downloadLogs,
      refreshPreview,

      // Utility functions
      formatBytes,
      formatTime,
      formatRelativeTime,
      formatLogTime,
      getHealthIcon,
      getStageIcon,
      getTrendIcon,

      // WebSocket methods
      requestSystemStatus,
      requestQueueStatus,
      subscribeToGeneration,
      sendGenerationCommand,
      clearAlerts,
      showNotification,
    };
  },
};
</script>

<style scoped>
.status-dashboard {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  color: #e0e0e0;
  font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #333;
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.echo-brain-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  border: 1px solid;
  transition: all 0.3s ease;
}

.echo-brain-status.connected {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
  border-color: #10b981;
}

.echo-brain-status.connected .pi-wifi {
  animation: pulse 2s infinite;
}

.echo-brain-status.disconnected {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  border-color: #ef4444;
}

.status-text {
  font-weight: 600;
}

.connection-text {
  font-size: 0.8rem;
  opacity: 0.8;
}

@keyframes pulse {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}

.dashboard-header h3 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.2rem;
}

.status-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.control-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.control-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.control-button.secondary:hover {
  background: #333;
}

.control-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.auto-refresh-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.toggle-checkbox {
  width: 16px;
  height: 16px;
}

.toggle-label {
  font-size: 0.9rem;
  color: #e0e0e0;
}

.status-section {
  padding: 1rem;
  border-bottom: 1px solid #222;
}

.status-section:last-child {
  border-bottom: none;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h4 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.1rem;
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 600;
}

.health-indicator.healthy {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
  border: 1px solid #10b981;
}

.health-indicator.warning {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
  border: 1px solid #f59e0b;
}

.health-indicator.error {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  border: 1px solid #ef4444;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.health-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.card-title {
  font-weight: 600;
  color: #3b82f6;
}

.card-value {
  font-weight: 600;
  color: #e0e0e0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #333;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-bar.large {
  height: 12px;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-fill.vram {
  background: #3b82f6;
}

.progress-fill.cpu {
  background: #10b981;
}

.progress-fill.memory {
  background: #8b5cf6;
}

.progress-fill.disk {
  background: #f59e0b;
}

.progress-fill.active {
  background: #3b82f6;
}

.progress-fill.warning {
  background: #f59e0b;
}

.progress-fill.critical {
  background: #ef4444;
}

.card-details {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  color: #999;
}

.queue-stats {
  display: flex;
  gap: 1rem;
}

.queue-stat {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.9rem;
  color: #ccc;
}

.queue-container {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  overflow: hidden;
}

.active-generation {
  padding: 1rem;
  background: rgba(59, 130, 246, 0.1);
  border-bottom: 1px solid #333;
}

.generation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.generation-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.generation-title {
  font-weight: 600;
  color: #e0e0e0;
  font-size: 1.1rem;
}

.generation-type {
  font-size: 0.8rem;
  color: #999;
}

.generation-meta {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-top: 0.25rem;
}

.generation-id {
  font-size: 0.75rem;
  color: #666;
  font-family: monospace;
}

.generation-status {
  padding: 0.125rem 0.5rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
}

.generation-status.running {
  background: #3b82f6;
  color: white;
}

.generation-status.paused {
  background: #f59e0b;
  color: white;
}

.generation-status.completed {
  background: #10b981;
  color: white;
}

.generation-status.failed {
  background: #ef4444;
  color: white;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

.progress-left,
.progress-right {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.progress-right {
  align-items: flex-end;
  text-align: right;
}

.current-stage {
  font-size: 0.8rem;
  color: #3b82f6;
  font-style: italic;
}

.progress-percentage {
  font-weight: 600;
  font-size: 1rem;
}

.generation-speed {
  font-size: 0.75rem;
  color: #10b981;
}

.progress-fill.progress-paused {
  background: #f59e0b;
  animation: blink 1s infinite;
}

.progress-fill.progress-error {
  background: #ef4444;
}

@keyframes blink {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}

.progress-details {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.8rem;
}

.time-info,
.technical-info {
  display: flex;
  gap: 1rem;
}

.technical-info {
  color: #999;
}

.stage-progress {
  color: #3b82f6;
  font-weight: 600;
}

.generation-preview {
  margin-top: 1rem;
  border: 1px solid #333;
  border-radius: 8px;
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  font-size: 0.9rem;
  font-weight: 600;
}

.preview-image {
  width: 100%;
  height: auto;
  max-height: 300px;
  object-fit: contain;
  display: block;
}

.mini-button {
  padding: 0.25rem 0.5rem;
  background: none;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-size: 0.8rem;
}

.mini-button:hover {
  background: #333;
}

.generation-actions {
  display: flex;
  gap: 0.5rem;
}

.action-button {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
}

.action-button:hover {
  background: #333;
}

.action-button.danger:hover {
  background: #ef4444;
  border-color: #ef4444;
}

.generation-progress {
  margin-bottom: 1rem;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

.progress-details {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: #999;
}

.generation-stages {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stage-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: #333;
  border-radius: 4px;
  font-size: 0.8rem;
}

.stage-item.completed {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.stage-item.running {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.stage-item.failed {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.queue-list {
  max-height: 300px;
  overflow-y: auto;
}

.queue-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #333;
  cursor: pointer;
  transition: background 0.2s ease;
}

.queue-item:hover {
  background: #333;
}

.queue-item:last-child {
  border-bottom: none;
}

.queue-item.pending {
  border-left: 3px solid #6b7280;
}

.queue-item.running {
  border-left: 3px solid #3b82f6;
}

.queue-item.completed {
  border-left: 3px solid #10b981;
  opacity: 0.7;
}

.queue-item.failed {
  border-left: 3px solid #ef4444;
}

.queue-item-info {
  flex: 1;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}

.item-title {
  font-weight: 600;
  color: #e0e0e0;
}

.item-status {
  padding: 0.125rem 0.5rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
}

.item-status.pending {
  background: #6b7280;
  color: white;
}

.item-status.running {
  background: #3b82f6;
  color: white;
}

.item-status.completed {
  background: #10b981;
  color: white;
}

.item-status.failed {
  background: #ef4444;
  color: white;
}

.item-details {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: #999;
}

.queue-item-actions {
  display: flex;
  gap: 0.25rem;
}

.mini-action {
  padding: 0.25rem;
  background: none;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
}

.mini-action:hover {
  background: #333;
}

.mini-action.danger:hover {
  background: #ef4444;
  border-color: #ef4444;
}

.empty-queue,
.empty-logs {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: #999;
  font-style: italic;
}

.log-controls {
  display: flex;
  gap: 0.75rem;
}

.log-level-select,
.timeframe-select {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.logs-container {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  height: 300px;
  overflow-y: auto;
  padding: 0.5rem;
  font-family: monospace;
}

.log-entry {
  display: grid;
  grid-template-columns: auto auto auto 1fr;
  gap: 0.75rem;
  padding: 0.25rem 0;
  font-size: 0.8rem;
  line-height: 1.4;
}

.log-entry.error {
  color: #ef4444;
}

.log-entry.warning {
  color: #f59e0b;
}

.log-entry.info {
  color: #3b82f6;
}

.log-entry.debug {
  color: #6b7280;
}

.log-timestamp {
  color: #999;
}

.log-level {
  font-weight: 600;
  min-width: 60px;
}

.log-source {
  color: #999;
  min-width: 80px;
}

.log-message {
  color: #e0e0e0;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.metric-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem;
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.metric-title {
  font-weight: 600;
  color: #3b82f6;
  font-size: 0.9rem;
}

.metric-value {
  font-weight: 600;
  color: #e0e0e0;
  font-size: 1.1rem;
}

.metric-trend {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
}

.metric-trend.up {
  color: #10b981;
}

.metric-trend.down {
  color: #ef4444;
}

.metric-trend.neutral {
  color: #6b7280;
}

/* Pre-flight Check Styles */
.pre-flight-section {
  background: rgba(30, 40, 50, 0.8);
  border: 2px solid rgba(0, 150, 255, 0.3);
  border-radius: 12px;
  margin: 1rem 0;
}

.pre-flight-results {
  margin-top: 1rem;
}

.check-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin: 5px 0;
  border-radius: 6px;
  transition: background 0.3s;
  font-size: 0.9rem;
}

.check-item.passed {
  background: rgba(0, 255, 0, 0.1);
  border-left: 3px solid #10b981;
}

.check-item.failed {
  background: rgba(255, 0, 0, 0.1);
  border-left: 3px solid #ef4444;
}

.check-icon {
  margin-right: 10px;
  font-size: 1.2em;
  width: 20px;
}

.check-name {
  font-weight: 600;
  min-width: 120px;
  color: #e0e0e0;
}

.check-message {
  color: #a0a0a0;
  font-size: 0.85em;
}

.warnings-section {
  margin-top: 15px;
  padding: 10px;
  background: rgba(255, 165, 0, 0.1);
  border-left: 3px solid #f59e0b;
  border-radius: 4px;
}

.warnings-section h5 {
  margin: 0 0 8px 0;
  color: #f59e0b;
  font-size: 0.9rem;
}

.warning-item {
  color: #fbbf24;
  font-size: 0.85rem;
  margin: 4px 0;
}

/* Failed Job Analysis Styles */
.failed-analysis {
  background: rgba(50, 30, 30, 0.8);
  border: 2px solid rgba(255, 100, 100, 0.3);
  border-radius: 12px;
  margin: 1rem 0;
}

.failed-jobs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.failed-job-card {
  background: rgba(80, 40, 40, 0.6);
  border-radius: 8px;
  padding: 15px;
  border-left: 4px solid #ef4444;
  transition: all 0.3s ease;
}

.failed-job-card:hover {
  background: rgba(80, 40, 40, 0.8);
  transform: translateY(-2px);
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 0.8rem;
}

.job-id {
  font-family: "Monaco", "Menlo", monospace;
  color: #fbbf24;
  font-weight: bold;
}

.job-type {
  background: #374151;
  color: #e0e0e0;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-size: 0.7rem;
}

.job-time {
  color: #9ca3af;
  font-size: 0.7rem;
}

.job-prompt {
  color: #d1d5db;
  font-size: 0.85rem;
  margin: 8px 0;
  line-height: 1.3;
}

.analyze-btn {
  background: #374151;
  color: #e0e0e0;
  border: 1px solid #4b5563;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.analyze-btn:hover {
  background: #4b5563;
  color: #f3f4f6;
}

.failure-stats {
  display: flex;
  gap: 2rem;
  margin-top: 1rem;
  padding: 10px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
  font-size: 0.9rem;
}

.failure-stats span {
  color: #ef4444;
  font-weight: 600;
}

.control-button.primary {
  background: #3b82f6;
  color: white;
  border: 1px solid #2563eb;
}

.control-button.primary:hover {
  background: #2563eb;
}

.control-button.primary:disabled {
  background: #374151;
  color: #6b7280;
  border-color: #374151;
}
</style>
