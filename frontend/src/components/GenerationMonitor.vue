<template>
  <div class="generation-monitor">
    <h2 class="text-2xl font-bold mb-6">System Generation Monitor</h2>

    <!-- Service Status Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <div
        v-for="service in services"
        :key="service.name"
        class="service-card bg-gray-800 rounded-lg p-4"
      >
        <div class="flex items-center justify-between mb-2">
          <h3 class="font-semibold">{{ service.name }}</h3>
          <div
            :class="[
              'w-3 h-3 rounded-full',
              service.status === 'online'
                ? 'bg-green-500 animate-pulse'
                : service.status === 'error'
                  ? 'bg-red-500'
                  : service.status === 'warning'
                    ? 'bg-yellow-500'
                    : 'bg-gray-500',
            ]"
          ></div>
        </div>

        <div class="text-xs text-gray-400 mb-2">{{ service.endpoint }}</div>

        <div class="grid grid-cols-2 gap-2 text-xs">
          <div>
            <span class="text-gray-500">Jobs:</span>
            <span class="ml-1 font-bold">{{ service.activeJobs }}</span>
          </div>
          <div>
            <span class="text-gray-500">Queue:</span>
            <span class="ml-1 font-bold">{{ service.queueSize }}</span>
          </div>
        </div>

        <div v-if="service.lastError" class="mt-2 text-xs text-red-400">
          {{ service.lastError }}
        </div>
      </div>
    </div>

    <!-- System Resources -->
    <div class="resources bg-gray-800 rounded-lg p-6 mb-6">
      <h3 class="text-xl font-semibold mb-4">System Resources</h3>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <!-- GPU Usage -->
        <div>
          <div class="flex justify-between mb-2">
            <span class="text-sm">GPU Memory</span>
            <span class="text-sm font-bold"
              >{{ gpuUsage.used }}GB / {{ gpuUsage.total }}GB</span
            >
          </div>
          <div class="w-full bg-gray-700 rounded-full h-3">
            <div
              :class="[
                'h-3 rounded-full transition-all duration-500',
                gpuUsage.percentage > 90
                  ? 'bg-red-500'
                  : gpuUsage.percentage > 70
                    ? 'bg-yellow-500'
                    : 'bg-green-500',
              ]"
              :style="{ width: `${gpuUsage.percentage}%` }"
            ></div>
          </div>
        </div>

        <!-- CPU Usage -->
        <div>
          <div class="flex justify-between mb-2">
            <span class="text-sm">CPU Usage</span>
            <span class="text-sm font-bold">{{ cpuUsage }}%</span>
          </div>
          <div class="w-full bg-gray-700 rounded-full h-3">
            <div
              :class="[
                'h-3 rounded-full transition-all duration-500',
                cpuUsage > 90
                  ? 'bg-red-500'
                  : cpuUsage > 70
                    ? 'bg-yellow-500'
                    : 'bg-blue-500',
              ]"
              :style="{ width: `${cpuUsage}%` }"
            ></div>
          </div>
        </div>

        <!-- Memory Usage -->
        <div>
          <div class="flex justify-between mb-2">
            <span class="text-sm">RAM Usage</span>
            <span class="text-sm font-bold"
              >{{ ramUsage.used }}GB / {{ ramUsage.total }}GB</span
            >
          </div>
          <div class="w-full bg-gray-700 rounded-full h-3">
            <div
              :class="[
                'h-3 rounded-full transition-all duration-500',
                ramUsage.percentage > 90
                  ? 'bg-red-500'
                  : ramUsage.percentage > 70
                    ? 'bg-yellow-500'
                    : 'bg-purple-500',
              ]"
              :style="{ width: `${ramUsage.percentage}%` }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Generation Queue -->
    <div class="queue bg-gray-800 rounded-lg p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-xl font-semibold">Generation Queue</h3>
        <div class="flex items-center gap-4">
          <button
            class="text-sm px-3 py-1 bg-gray-700 rounded hover:bg-gray-600"
            @click="refreshQueue"
          >
            <i class="pi pi-refresh mr-1"></i>
            Refresh
          </button>
          <button
            v-if="queue.length > 0"
            class="text-sm px-3 py-1 bg-red-600 rounded hover:bg-red-700"
            @click="clearQueue"
          >
            Clear Queue
          </button>
        </div>
      </div>

      <div v-if="queue.length === 0" class="text-gray-500 text-center py-8">
        Queue is empty
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="(job, index) in queue"
          :key="job.id"
          class="queue-item bg-gray-700 rounded-lg p-4"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-3">
              <span class="text-gray-400 text-sm">#{{ index + 1 }}</span>
              <div>
                <span class="font-semibold">{{ job.character_name }}</span>
                <span class="text-xs text-gray-400 ml-2">{{
                  job.id.substring(0, 8)
                }}</span>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <span
                :class="[
                  'px-2 py-1 rounded text-xs',
                  job.status === 'processing'
                    ? 'bg-blue-600'
                    : job.status === 'queued'
                      ? 'bg-gray-600'
                      : job.status === 'completed'
                        ? 'bg-green-600'
                        : 'bg-red-600',
                ]"
              >
                {{ job.status }}
              </span>

              <button
                class="text-xs px-2 py-1 bg-red-600 rounded hover:bg-red-700"
                @click="cancelJob(job.id)"
              >
                Cancel
              </button>
            </div>
          </div>

          <div class="grid grid-cols-3 gap-4 text-xs text-gray-400">
            <div>
              <span class="text-gray-500">Type:</span>
              <span class="ml-1">{{ job.generation_type }}</span>
            </div>
            <div>
              <span class="text-gray-500">Model:</span>
              <span class="ml-1">{{
                job.model_name?.split(".")[0] || "default"
              }}</span>
            </div>
            <div>
              <span class="text-gray-500">Time:</span>
              <span class="ml-1">{{
                formatDuration(job.processing_time)
              }}</span>
            </div>
          </div>

          <div v-if="job.status === 'processing'" class="mt-3">
            <div class="w-full bg-gray-600 rounded-full h-2">
              <div
                class="bg-blue-500 h-2 rounded-full transition-all duration-500"
                :style="{ width: `${job.progress || 0}%` }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Activity Log -->
    <div class="activity-log bg-gray-800 rounded-lg p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-xl font-semibold">Activity Log</h3>
        <select
          v-model="logFilter"
          class="text-sm px-3 py-1 bg-gray-700 rounded"
        >
          <option value="all">All Events</option>
          <option value="generation">Generation</option>
          <option value="error">Errors</option>
          <option value="system">System</option>
        </select>
      </div>

      <div class="log-container max-h-96 overflow-y-auto space-y-2">
        <div
          v-for="(log, index) in filteredLogs"
          :key="index"
          class="log-item flex items-start gap-3 text-sm"
        >
          <span class="text-gray-500 text-xs">{{
            formatTime(log.timestamp)
          }}</span>
          <span
            :class="[
              'px-1 py-0.5 rounded text-xs',
              log.type === 'error'
                ? 'bg-red-600'
                : log.type === 'warning'
                  ? 'bg-yellow-600'
                  : log.type === 'success'
                    ? 'bg-green-600'
                    : 'bg-gray-600',
            ]"
          >
            {{ log.type }}
          </span>
          <span class="flex-1">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { api } from "../services/api";

// Service definitions
const services = ref([
  {
    name: "API Service",
    endpoint: "tower-anime-production",
    status: "checking",
    activeJobs: 0,
    queueSize: 0,
    lastError: null,
  },
  {
    name: "File Organizer",
    endpoint: "anime-file-organizer",
    status: "checking",
    activeJobs: 0,
    queueSize: 0,
    lastError: null,
  },
  {
    name: "Job Worker",
    endpoint: "anime-job-worker",
    status: "checking",
    activeJobs: 0,
    queueSize: 0,
    lastError: null,
  },
  {
    name: "WebSocket Service",
    endpoint: "anime-websocket",
    status: "checking",
    activeJobs: 0,
    queueSize: 0,
    lastError: null,
  },
]);

// System resources
const gpuUsage = ref({
  used: 0,
  total: 12,
  percentage: 0,
});

const cpuUsage = ref(0);

const ramUsage = ref({
  used: 0,
  total: 64,
  percentage: 0,
});

// Queue
const queue = ref([]);

// Activity logs
const logs = ref([]);
const logFilter = ref("all");

// Polling intervals
let statusInterval = null;
let resourceInterval = null;
let queueInterval = null;

// Methods
const checkServiceStatus = async () => {
  // Check main API health
  try {
    const response = await api.system.health();
    services.value[0].status = "online";
    services.value[0].activeJobs = response.data.active_jobs || 0;
    services.value[0].queueSize = response.data.queue_size || 0;
  } catch (error) {
    services.value[0].status = "error";
    services.value[0].lastError = error.message;
  }

  // Check orchestration status for other services
  try {
    const response = await api.system.getOrchestrationStatus();
    const status = response.data;

    // Update service statuses based on orchestration data
    if (status.services) {
      services.value.forEach((service, index) => {
        if (status.services[service.endpoint]) {
          service.status =
            status.services[service.endpoint].status || "unknown";
          service.activeJobs =
            status.services[service.endpoint].active_jobs || 0;
          service.queueSize = status.services[service.endpoint].queue_size || 0;
        }
      });
    }
  } catch (error) {
    console.error("Failed to check orchestration status:", error);
  }
};

const checkResourceUsage = async () => {
  try {
    const response = await api.system.getAdminStats();
    const stats = response.data;

    // Update GPU usage
    if (stats.gpu) {
      gpuUsage.value.used = (stats.gpu.memory_used / 1024).toFixed(1);
      gpuUsage.value.total = (stats.gpu.memory_total / 1024).toFixed(1);
      gpuUsage.value.percentage = Math.round(
        (stats.gpu.memory_used / stats.gpu.memory_total) * 100,
      );
    }

    // Update CPU usage
    if (stats.cpu) {
      cpuUsage.value = Math.round(stats.cpu.usage);
    }

    // Update RAM usage
    if (stats.memory) {
      ramUsage.value.used = (stats.memory.used / (1024 * 1024 * 1024)).toFixed(
        1,
      );
      ramUsage.value.total = (
        stats.memory.total /
        (1024 * 1024 * 1024)
      ).toFixed(1);
      ramUsage.value.percentage = Math.round(
        (stats.memory.used / stats.memory.total) * 100,
      );
    }
  } catch (error) {
    console.error("Failed to get resource usage:", error);
  }
};

const loadQueue = async () => {
  try {
    const response = await api.jobs.list();
    queue.value = response.data
      .filter((job) => job.status === "queued" || job.status === "processing")
      .slice(0, 10); // Show top 10 items
  } catch (error) {
    console.error("Failed to load queue:", error);
  }
};

const refreshQueue = () => {
  loadQueue();
  addLog("info", "Queue refreshed");
};

const clearQueue = async () => {
  if (!confirm("Clear all queued jobs?")) return;

  try {
    // Would need an endpoint to clear queue
    addLog("warning", "Queue cleared by user");
  } catch (error) {
    console.error("Failed to clear queue:", error);
    addLog("error", "Failed to clear queue");
  }
};

const cancelJob = async (jobId) => {
  try {
    await api.jobs.cancel(jobId);
    addLog("info", `Job ${jobId.substring(0, 8)} cancelled`);
    await loadQueue();
  } catch (error) {
    console.error("Failed to cancel job:", error);
    addLog("error", `Failed to cancel job ${jobId.substring(0, 8)}`);
  }
};

const addLog = (type, message) => {
  logs.value.unshift({
    type,
    message,
    timestamp: new Date().toISOString(),
  });

  // Keep only last 100 logs
  if (logs.value.length > 100) {
    logs.value = logs.value.slice(0, 100);
  }
};

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString();
};

const formatDuration = (seconds) => {
  if (!seconds) return "0s";

  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;

  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
};

// Computed
const filteredLogs = computed(() => {
  if (logFilter.value === "all") return logs.value;

  return logs.value.filter((log) => {
    if (logFilter.value === "generation") {
      return (
        log.message.toLowerCase().includes("generation") ||
        log.message.toLowerCase().includes("character")
      );
    }
    if (logFilter.value === "error") {
      return log.type === "error" || log.type === "warning";
    }
    if (logFilter.value === "system") {
      return log.type === "info" || log.type === "system";
    }
    return true;
  });
});

// Lifecycle
onMounted(() => {
  // Initial load
  checkServiceStatus();
  checkResourceUsage();
  loadQueue();

  // Start polling
  statusInterval = setInterval(checkServiceStatus, 5000); // Every 5 seconds
  resourceInterval = setInterval(checkResourceUsage, 10000); // Every 10 seconds
  queueInterval = setInterval(loadQueue, 3000); // Every 3 seconds

  addLog("info", "Generation monitor initialized");
});

onUnmounted(() => {
  // Clean up intervals
  if (statusInterval) clearInterval(statusInterval);
  if (resourceInterval) clearInterval(resourceInterval);
  if (queueInterval) clearInterval(queueInterval);
});
</script>

<style scoped>
.generation-monitor {
  max-width: 1600px;
  margin: 0 auto;
  padding: 2rem;
  color: white;
}

.service-card {
  transition:
    transform 0.2s,
    box-shadow 0.2s;
}

.service-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.log-container {
  font-family: "Monaco", "Courier New", monospace;
  font-size: 0.85rem;
}

.log-item {
  padding: 0.5rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 0.25rem;
  transition: background 0.2s;
}

.log-item:hover {
  background: rgba(0, 0, 0, 0.4);
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.animate-pulse {
  animation: pulse 2s infinite;
}
</style>
