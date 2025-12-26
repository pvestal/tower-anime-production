<template>
  <div class="scene-generator">
    <div class="header mb-6">
      <h2 class="text-3xl font-bold text-white">AI Scene Generator</h2>
      <p class="text-gray-400 mt-2">
        Single-click generation with semantic search and real-time progress
      </p>
    </div>

    <!-- Main Generation Panel -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Left Column: Scene Input -->
      <div class="lg:col-span-2 space-y-6">
        <!-- Quick Scene Input -->
        <div class="bg-gray-800 rounded-lg p-6">
          <h3 class="text-xl font-semibold mb-4">Scene Description</h3>

          <div class="space-y-4">
            <textarea
              v-model="sceneText"
              placeholder="Describe your scene... (e.g., 'A samurai warrior standing in a cherry blossom garden at sunset, anime style')"
              class="w-full h-32 px-4 py-3 bg-gray-700 rounded-lg border border-gray-600 focus:border-blue-500 focus:outline-none resize-none"
              @keydown.ctrl.enter="generateScene"
            ></textarea>

            <div class="flex gap-4">
              <select
                v-model="outputFormat"
                class="px-4 py-2 bg-gray-700 rounded border border-gray-600"
              >
                <option value="image">Single Image</option>
                <option value="video">Video (2s)</option>
                <option value="image_sequence">Image Sequence</option>
              </select>

              <select
                v-model="stylePreset"
                class="px-4 py-2 bg-gray-700 rounded border border-gray-600"
              >
                <option value="">No Style</option>
                <option value="anime">Anime</option>
                <option value="realistic">Realistic</option>
                <option value="cinematic">Cinematic</option>
                <option value="fantasy">Fantasy</option>
                <option value="cyberpunk">Cyberpunk</option>
              </select>

              <button
                :disabled="!sceneText || store.isGenerating"
                class="flex-1 px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors"
                @click="generateScene"
              >
                <span v-if="!store.isGenerating"> 🎬 Generate Scene </span>
                <span v-else class="flex items-center justify-center">
                  <svg class="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
                    <circle
                      class="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      stroke-width="4"
                      fill="none"
                    ></circle>
                    <path
                      class="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    ></path>
                  </svg>
                  Generating...
                </span>
              </button>
            </div>
          </div>
        </div>

        <!-- Character Search & Selection -->
        <div class="bg-gray-800 rounded-lg p-6">
          <h3 class="text-xl font-semibold mb-4">Character Selection</h3>

          <div class="space-y-4">
            <!-- Semantic Search -->
            <div class="flex gap-2">
              <input
                v-model="searchQuery"
                placeholder="Search characters by description..."
                class="flex-1 px-4 py-2 bg-gray-700 rounded border border-gray-600 focus:border-purple-500"
                @keyup.enter="searchCharacters"
              />
              <button
                :disabled="!searchQuery || store.isSearching"
                class="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded"
                @click="searchCharacters"
              >
                Search
              </button>
            </div>

            <!-- Search Results -->
            <div
              v-if="store.searchResults.length > 0"
              class="grid grid-cols-2 md:grid-cols-3 gap-3"
            >
              <div
                v-for="result in store.searchResults"
                :key="result.id"
                :class="[
                  'p-3 bg-gray-700 rounded-lg cursor-pointer transition-all',
                  store.selectedCharacter?.character_id === result.id
                    ? 'ring-2 ring-blue-500'
                    : 'hover:bg-gray-600',
                ]"
                @click="selectCharacter(result.id)"
              >
                <img
                  v-if="result.preview_url"
                  :src="result.preview_url"
                  :alt="result.metadata.character_name"
                  class="w-full h-24 object-cover rounded mb-2"
                />
                <p class="text-sm font-medium truncate">
                  {{ result.metadata.character_name }}
                </p>
                <p class="text-xs text-gray-400">
                  Score: {{ (result.score * 100).toFixed(1) }}%
                </p>
              </div>
            </div>

            <!-- Selected Character -->
            <div
              v-if="store.selectedCharacter"
              class="p-4 bg-gray-700 rounded-lg"
            >
              <div class="flex justify-between items-center">
                <div>
                  <p class="font-semibold">
                    {{ store.selectedCharacter.name }}
                  </p>
                  <p class="text-sm text-gray-400">
                    {{
                      store.selectedCharacter.description.substring(0, 100)
                    }}...
                  </p>
                </div>
                <button
                  class="text-red-400 hover:text-red-300"
                  @click="store.selectedCharacter = null"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Generation Conditions -->
        <div class="bg-gray-800 rounded-lg p-6">
          <h3 class="text-xl font-semibold mb-4">Generation Conditions</h3>

          <div class="grid grid-cols-2 gap-3">
            <button
              v-for="condition in availableConditions"
              :key="condition.type"
              :class="[
                'px-4 py-2 rounded-lg transition-all',
                hasCondition(condition.type)
                  ? 'bg-blue-600 hover:bg-blue-700'
                  : 'bg-gray-700 hover:bg-gray-600',
              ]"
              @click="toggleCondition(condition)"
            >
              {{ condition.name }}
            </button>
          </div>

          <!-- Active Conditions -->
          <div
            v-if="store.selectedConditions.length > 0"
            class="mt-4 space-y-2"
          >
            <div
              v-for="condition in store.selectedConditions"
              :key="condition.type"
              class="flex justify-between items-center p-3 bg-gray-700 rounded"
            >
              <span>{{ getConditionName(condition.type) }}</span>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="condition.weight"
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  class="w-24"
                />
                <span class="text-sm">{{
                  condition.weight?.toFixed(1) || "1.0"
                }}</span>
                <button
                  class="text-red-400 hover:text-red-300 ml-2"
                  @click="store.removeCondition(condition.type)"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Column: Progress & Queue -->
      <div class="space-y-6">
        <!-- Current Generation Progress -->
        <div v-if="store.currentJob" class="bg-gray-800 rounded-lg p-6">
          <h3 class="text-xl font-semibold mb-4">Generation Progress</h3>

          <div class="space-y-4">
            <!-- Progress Bar -->
            <div class="relative">
              <div class="flex justify-between text-sm mb-2">
                <span>{{ store.currentJob.status }}</span>
                <span>{{ store.currentJob.progress }}%</span>
              </div>
              <div class="w-full bg-gray-700 rounded-full h-3">
                <div
                  :class="[
                    'h-3 rounded-full transition-all duration-300',
                    store.currentJob.status === 'failed'
                      ? 'bg-red-500'
                      : store.currentJob.status === 'completed'
                        ? 'bg-green-500'
                        : 'bg-blue-500',
                  ]"
                  :style="{ width: `${store.currentJob.progress}%` }"
                ></div>
              </div>
            </div>

            <!-- Current Step -->
            <div
              v-if="store.currentJob.current_step"
              class="p-3 bg-gray-700 rounded"
            >
              <p class="text-sm">{{ store.currentJob.current_step }}</p>
            </div>

            <!-- Actions -->
            <div class="flex gap-2">
              <button
                v-if="
                  store.currentJob.status !== 'completed' &&
                  store.currentJob.status !== 'failed'
                "
                class="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded"
                @click="cancelGeneration"
              >
                Cancel
              </button>
              <button
                v-if="
                  store.currentJob.status === 'completed' &&
                  store.currentJob.result
                "
                class="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 rounded"
                @click="viewResult"
              >
                View Result
              </button>
            </div>
          </div>
        </div>

        <!-- Queue Status -->
        <div class="bg-gray-800 rounded-lg p-6">
          <h3 class="text-xl font-semibold mb-4">Queue Status</h3>

          <div class="space-y-3">
            <div class="flex justify-between">
              <span class="text-gray-400">Queued:</span>
              <span class="font-semibold">{{
                store.queueStatus.queue_size
              }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-400">Processing:</span>
              <span class="font-semibold"
                >{{ store.queueStatus.processing_count }} /
                {{ store.queueStatus.max_concurrent }}</span
              >
            </div>
            <div class="flex justify-between">
              <span class="text-gray-400">Workers:</span>
              <span class="font-semibold">{{
                store.queueStatus.worker_count
              }}</span>
            </div>
          </div>

          <button
            class="w-full mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            @click="store.updateQueueStatus"
          >
            Refresh Status
          </button>
        </div>

        <!-- Recent Jobs -->
        <div class="bg-gray-800 rounded-lg p-6">
          <h3 class="text-xl font-semibold mb-4">Recent Jobs</h3>

          <div class="space-y-2 max-h-64 overflow-y-auto">
            <div
              v-for="job in recentJobs"
              :key="job.job_id"
              :class="[
                'p-3 bg-gray-700 rounded cursor-pointer transition-all',
                store.currentJobId === job.job_id
                  ? 'ring-2 ring-blue-500'
                  : 'hover:bg-gray-600',
              ]"
              @click="selectJob(job.job_id)"
            >
              <div class="flex justify-between items-start">
                <div class="flex-1">
                  <p class="text-sm truncate">
                    {{ job.scene_request?.storyline_text || "No description" }}
                  </p>
                  <p class="text-xs text-gray-400 mt-1">
                    {{ formatTime(job.created_at) }}
                  </p>
                </div>
                <span
                  :class="[
                    'px-2 py-1 text-xs rounded',
                    job.status === 'completed'
                      ? 'bg-green-600'
                      : job.status === 'failed'
                        ? 'bg-red-600'
                        : job.status === 'processing'
                          ? 'bg-blue-600'
                          : 'bg-gray-600',
                  ]"
                >
                  {{ job.status }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div
      v-if="store.error"
      class="mt-6 p-4 bg-red-900/20 border border-red-600 rounded-lg"
    >
      <div class="flex justify-between items-center">
        <p class="text-red-400">{{ store.error }}</p>
        <button
          class="text-red-400 hover:text-red-300"
          @click="store.clearError"
        >
          ✕
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import {
  useOrchestrationStore,
  ConditionType,
} from "../stores/useOrchestrationStore";

// Store
const store = useOrchestrationStore();

// State
const sceneText = ref("");
const searchQuery = ref("");
const outputFormat = ref<"image" | "video" | "image_sequence">("image");
const stylePreset = ref("");

// Available conditions configuration
const availableConditions = [
  { type: ConditionType.POSE_CONTROL, name: "Pose Control" },
  { type: ConditionType.CAMERA_MOTION, name: "Camera Motion" },
  { type: ConditionType.EMOTION_EXPRESSION, name: "Emotion" },
  { type: ConditionType.SCENE_CONTEXT, name: "Scene Context" },
  { type: ConditionType.TEMPORAL_CONSISTENCY, name: "Temporal" },
];

// Computed
const recentJobs = computed(() => {
  const all = [...store.activeJobsList, ...store.completedJobs];
  return all.slice(0, 10);
});

// Methods
async function generateScene() {
  if (!sceneText.value) return;

  try {
    const jobId = await store.generateScene({
      storyline_text: sceneText.value,
      output_format: outputFormat.value,
      style_preset: stylePreset.value || undefined,
      conditions: [
        {
          type: ConditionType.TEXT_PROMPT,
          data: { prompt: sceneText.value },
          weight: 1.0,
        },
      ],
      resolution: outputFormat.value === "video" ? [512, 768] : [512, 768],
      duration_seconds: outputFormat.value === "video" ? 2.0 : 0,
      fps: outputFormat.value === "video" ? 8 : 0,
    });

    console.log("Generation started:", jobId);
  } catch (error) {
    console.error("Generation failed:", error);
  }
}

async function searchCharacters() {
  if (!searchQuery.value) return;
  await store.searchBySemantic(searchQuery.value);
}

function selectCharacter(resultId) {
  store.selectCharacterBySearch(resultId);
}

function toggleCondition(condition) {
  if (hasCondition(condition.type)) {
    store.removeCondition(condition.type);
  } else {
    // Add with default data based on type
    const conditionData = {
      type: condition.type,
      data: getDefaultConditionData(condition.type),
      weight: 1.0,
    };
    store.addCondition(conditionData);
  }
}

function hasCondition(type) {
  return store.selectedConditions.some((c) => c.type === type);
}

function getConditionName(type) {
  return availableConditions.find((c) => c.type === type)?.name || type;
}

function getDefaultConditionData(type) {
  switch (type) {
    case ConditionType.CAMERA_MOTION:
      return { motion_type: "pan_right", motion_strength: 1.0 };
    case ConditionType.EMOTION_EXPRESSION:
      return { expression: "happy", intensity: 1.0 };
    case ConditionType.SCENE_CONTEXT:
      return { context: "outdoor", time_of_day: "sunset" };
    case ConditionType.TEMPORAL_CONSISTENCY:
      return { consistency_strength: 1.0 };
    default:
      return {};
  }
}

async function cancelGeneration() {
  if (store.currentJobId) {
    await store.cancelJob(store.currentJobId);
  }
}

function viewResult() {
  if (store.currentJob?.result) {
    // Open result in new tab or modal
    console.log("View result:", store.currentJob.result);
  }
}

function selectJob(jobId) {
  // Could reconnect to job WebSocket here if needed
  store.currentJobId = jobId;
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleTimeString();
}

// Lifecycle
onMounted(async () => {
  await store.loadCharacterLibrary();
  await store.updateQueueStatus();

  // Poll queue status every 5 seconds
  const interval = setInterval(() => {
    store.updateQueueStatus();
  }, 5000);

  // Store interval ID for cleanup
  window.__queueInterval = interval;
});

onUnmounted(() => {
  store.cleanup();

  // Clear queue polling
  if (window.__queueInterval) {
    clearInterval(window.__queueInterval);
  }
});
</script>

<style scoped>
.scene-generator {
  @apply text-white;
}

/* Custom scrollbar for dark theme */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  @apply bg-gray-800;
}

::-webkit-scrollbar-thumb {
  @apply bg-gray-600 rounded;
}

::-webkit-scrollbar-thumb:hover {
  @apply bg-gray-500;
}
</style>
