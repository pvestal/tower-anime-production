<template>
  <div class="character-generator-enhanced">
    <h2 class="text-2xl font-bold mb-6">
      Character Generator - Real-Time Generation
    </h2>

    <!-- Generation Form -->
    <div class="generation-form bg-gray-800 rounded-lg p-6 mb-6">
      <h3 class="text-xl font-semibold mb-4">Generate New Character</h3>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-2">Character Name</label>
          <input
            v-model="formData.character_name"
            type="text"
            class="w-full px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500"
            placeholder="e.g., Rina Suzuki"
            @input="searchSimilarDebounced"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-2">Content Type</label>
          <select
            v-model="formData.content_type"
            class="w-full px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500"
          >
            <option value="sfw">Safe for Work (SFW)</option>
            <option value="nsfw">Not Safe for Work (NSFW)</option>
            <option value="artistic">Artistic Nude</option>
          </select>
        </div>

        <div class="md:col-span-2">
          <label class="block text-sm font-medium mb-2"
            >Character Description</label
          >
          <div class="relative">
            <textarea
              v-model="formData.prompt"
              rows="4"
              class="w-full px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500"
              placeholder="Describe the character appearance, outfit, pose, style..."
              @input="getSuggestionsDebounced"
            ></textarea>

            <!-- Prompt Suggestions -->
            <div
              v-if="promptSuggestions.length > 0"
              class="absolute z-10 w-full mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto"
            >
              <div
                v-for="suggestion in promptSuggestions"
                :key="suggestion.id"
                class="px-4 py-2 hover:bg-gray-700 cursor-pointer"
                @click="applyPromptSuggestion(suggestion)"
              >
                <div class="font-semibold text-sm">
                  {{ suggestion.character_name }}
                </div>
                <div class="text-xs text-gray-400 line-clamp-2">
                  {{ suggestion.prompt }}
                </div>
                <div class="text-xs text-purple-400 mt-1">
                  Score: {{ suggestion.score.toFixed(3) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium mb-2">Generation Type</label>
          <select
            v-model="formData.generation_type"
            class="w-full px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500"
          >
            <option value="single_image">Single Image</option>
            <option value="turnaround">Character Turnaround</option>
            <option value="pose_sheet">Pose Sheet</option>
            <option value="expression_sheet">Expression Sheet</option>
            <option value="animation">Animation Sequence</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium mb-2">Model</label>
          <select
            v-model="formData.model_name"
            class="w-full px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500"
          >
            <option value="chilloutmix_NiPrunedFp32Fix.safetensors">
              ChilloutMix (Realistic)
            </option>
            <option value="AOM3A1B.safetensors">AOM3 (Anime)</option>
            <option value="dreamshaper_8.safetensors">
              DreamShaper (Fantasy)
            </option>
          </select>
        </div>
      </div>

      <!-- Generation Controls -->
      <div class="mt-6 flex gap-4 items-center">
        <button
          :disabled="
            isGenerating || !formData.character_name || !formData.prompt
          "
          class="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="generateCharacter"
        >
          {{ isGenerating ? "Generating..." : "Generate Character" }}
        </button>

        <button
          :disabled="isGenerating"
          class="px-6 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
          @click="generateBatch"
        >
          Batch Generate (x4)
        </button>

        <!-- Generation Progress -->
        <div v-if="currentGeneration" class="flex-1">
          <div class="flex items-center gap-3">
            <div class="flex-1">
              <div class="text-sm text-gray-400 mb-1">
                {{ currentGeneration.status }} - {{ currentGeneration.message }}
              </div>
              <div class="w-full bg-gray-700 rounded-full h-2">
                <div
                  class="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all duration-300"
                  :style="{ width: `${currentGeneration.progress}%` }"
                ></div>
              </div>
            </div>
            <div class="text-lg font-bold text-blue-400">
              {{ currentGeneration.progress }}%
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Real-Time Generation Monitor -->
    <div
      v-if="activeGenerations.length > 0"
      class="generation-monitor bg-gray-800 rounded-lg p-6 mb-6"
    >
      <h3 class="text-xl font-semibold mb-4">Active Generations</h3>

      <div class="space-y-3">
        <div
          v-for="gen in activeGenerations"
          :key="gen.id"
          class="bg-gray-700 rounded-lg p-4"
        >
          <div class="flex items-center justify-between mb-2">
            <div>
              <span class="font-semibold">{{ gen.character_name }}</span>
              <span class="text-sm text-gray-400 ml-2"
                >ID: {{ gen.id.substring(0, 8) }}</span
              >
            </div>
            <div class="flex items-center gap-2">
              <span
                :class="[
                  'px-2 py-1 rounded text-xs',
                  gen.status === 'completed'
                    ? 'bg-green-600'
                    : gen.status === 'failed'
                      ? 'bg-red-600'
                      : gen.status === 'processing'
                        ? 'bg-blue-600'
                        : 'bg-gray-600',
                ]"
              >
                {{ gen.status }}
              </span>
              <button
                v-if="gen.status === 'failed'"
                class="text-xs px-2 py-1 bg-orange-600 rounded hover:bg-orange-700"
                @click="retryGeneration(gen.id)"
              >
                Retry
              </button>
            </div>
          </div>

          <!-- Progress Bar -->
          <div class="mb-2">
            <div class="w-full bg-gray-600 rounded-full h-2">
              <div
                :class="[
                  'h-2 rounded-full transition-all duration-300',
                  gen.status === 'completed'
                    ? 'bg-green-500'
                    : gen.status === 'failed'
                      ? 'bg-red-500'
                      : 'bg-blue-500',
                ]"
                :style="{ width: `${gen.progress || 0}%` }"
              ></div>
            </div>
          </div>

          <!-- Generation Logs -->
          <div
            v-if="gen.logs && gen.logs.length > 0"
            class="text-xs text-gray-400 max-h-20 overflow-y-auto"
          >
            <div v-for="(log, idx) in gen.logs.slice(-3)" :key="idx">
              {{ log }}
            </div>
          </div>

          <!-- Preview -->
          <div v-if="gen.preview" class="mt-3">
            <img :src="gen.preview" alt="Preview" class="h-32 rounded" />
          </div>
        </div>
      </div>
    </div>

    <!-- Similar Characters (Vector Search) -->
    <div
      v-if="similarCharacters.length > 0"
      class="similar-characters bg-gray-800 rounded-lg p-6 mb-6"
    >
      <h3 class="text-xl font-semibold mb-4">Similar Characters</h3>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div
          v-for="char in similarCharacters"
          :key="char.id"
          class="bg-gray-700 rounded-lg p-3 cursor-pointer hover:bg-gray-600 transition"
          @click="loadSimilarCharacter(char)"
        >
          <div class="text-sm font-semibold">{{ char.character_name }}</div>
          <div class="text-xs text-gray-400 mt-1">
            Score: {{ char.score.toFixed(3) }}
          </div>
          <div class="text-xs mt-2 line-clamp-3">{{ char.prompt }}</div>
          <button
            class="mt-2 text-xs px-2 py-1 bg-purple-600 rounded hover:bg-purple-700 w-full"
            @click.stop="applyStyleTransfer(char)"
          >
            Apply Style
          </button>
        </div>
      </div>
    </div>

    <!-- Recent Completions -->
    <div class="recent-completions bg-gray-800 rounded-lg p-6">
      <h3 class="text-xl font-semibold mb-4">Recent Completions</h3>

      <div v-if="completedGenerations.length === 0" class="text-gray-500">
        No completed generations yet
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div
          v-for="gen in completedGenerations"
          :key="gen.id"
          class="bg-gray-700 rounded-lg overflow-hidden"
        >
          <div v-if="gen.output" class="h-48 bg-gray-600">
            <img
              :src="gen.output"
              alt="Generated"
              class="w-full h-full object-cover"
            />
          </div>
          <div v-else class="h-48 bg-gray-600 flex items-center justify-center">
            <span class="text-gray-400">{{ gen.character_name }}</span>
          </div>

          <div class="p-4">
            <div class="font-semibold">{{ gen.character_name }}</div>
            <div class="text-sm text-gray-400 mt-1">
              {{ gen.generation_type }}
            </div>
            <div class="text-xs text-gray-500 mt-1">
              {{ formatTime(gen.completed_at) }}
            </div>

            <div class="mt-3 flex gap-2">
              <button
                class="text-xs px-2 py-1 bg-blue-600 rounded hover:bg-blue-700 flex-1"
                @click="viewFullSize(gen)"
              >
                View
              </button>
              <button
                class="text-xs px-2 py-1 bg-purple-600 rounded hover:bg-purple-700 flex-1"
                @click="generateVariations(gen)"
              >
                Variations
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { api, WebSocketService } from "../services/api";
import { debounce } from "lodash-es";

// State
const formData = ref({
  character_name: "",
  prompt: "",
  negative_prompt: "bad anatomy, worst quality, low quality",
  content_type: "sfw",
  generation_type: "single_image",
  model_name: "chilloutmix_NiPrunedFp32Fix.safetensors",
  seed: -1,
  num_images: 1,
  width: 512,
  height: 768,
  steps: 30,
  cfg_scale: 7,
});

const isGenerating = ref(false);
const currentGeneration = ref(null);
const activeGenerations = ref([]);
const completedGenerations = ref([]);
const promptSuggestions = ref([]);
const similarCharacters = ref([]);

// WebSocket connections map
const wsConnections = new Map();

// Methods
const generateCharacter = async () => {
  isGenerating.value = true;
  currentGeneration.value = {
    status: "Starting",
    message: "Initializing generation...",
    progress: 0,
  };

  try {
    const response = await api.character.generate(formData.value);
    const { generation_id } = response.data;

    // Create WebSocket connection for real-time updates
    const ws = new WebSocketService(generation_id);
    wsConnections.set(generation_id, ws);

    // Add to active generations
    const generation = {
      id: generation_id,
      character_name: formData.value.character_name,
      generation_type: formData.value.generation_type,
      status: "queued",
      progress: 0,
      logs: [],
      created_at: new Date().toISOString(),
    };

    activeGenerations.value.push(generation);

    // Set up WebSocket event handlers
    ws.on("progress", (data) => {
      const gen = activeGenerations.value.find((g) => g.id === generation_id);
      if (gen) {
        gen.progress = data.progress;
        gen.status = "processing";
        if (currentGeneration.value) {
          currentGeneration.value.progress = data.progress;
          currentGeneration.value.message = data.message || "Processing...";
        }
      }
    });

    ws.on("status", (data) => {
      const gen = activeGenerations.value.find((g) => g.id === generation_id);
      if (gen) {
        gen.status = data.status;
        if (data.message) {
          gen.logs.push(data.message);
        }
      }
    });

    ws.on("completed", (data) => {
      const gen = activeGenerations.value.find((g) => g.id === generation_id);
      if (gen) {
        gen.status = "completed";
        gen.progress = 100;
        gen.output = data.output;
        gen.completed_at = new Date().toISOString();

        // Move to completed
        completedGenerations.value.unshift(gen);
        activeGenerations.value = activeGenerations.value.filter(
          (g) => g.id !== generation_id,
        );
      }

      // Reset current generation
      currentGeneration.value = null;
      isGenerating.value = false;

      // Close WebSocket
      ws.disconnect();
      wsConnections.delete(generation_id);
    });

    ws.on("error", (data) => {
      const gen = activeGenerations.value.find((g) => g.id === generation_id);
      if (gen) {
        gen.status = "failed";
        gen.error = data.error;
      }

      currentGeneration.value = null;
      isGenerating.value = false;

      // Close WebSocket
      ws.disconnect();
      wsConnections.delete(generation_id);
    });
  } catch (error) {
    console.error("Generation failed:", error);
    alert(`Generation failed: ${error.message}`);
    isGenerating.value = false;
    currentGeneration.value = null;
  }
};

const generateBatch = async () => {
  const batchRequest = {
    ...formData.value,
    batch_size: 4,
  };

  try {
    const response = await api.character.generateBatch(batchRequest);
    const { generation_ids } = response.data;

    // Create WebSocket connections for each generation
    generation_ids.forEach((id) => {
      const ws = new WebSocketService(id);
      wsConnections.set(id, ws);

      const generation = {
        id,
        character_name: formData.value.character_name,
        generation_type: formData.value.generation_type,
        status: "queued",
        progress: 0,
        logs: [],
        created_at: new Date().toISOString(),
      };

      activeGenerations.value.push(generation);

      // Set up handlers (similar to single generation)
      setupWebSocketHandlers(ws, id);
    });

    alert(`Batch generation started: ${generation_ids.length} images`);
  } catch (error) {
    console.error("Batch generation failed:", error);
    alert(`Batch generation failed: ${error.message}`);
  }
};

const setupWebSocketHandlers = (ws, generationId) => {
  ws.on("progress", (data) => {
    const gen = activeGenerations.value.find((g) => g.id === generationId);
    if (gen) {
      gen.progress = data.progress;
      gen.status = "processing";
    }
  });

  ws.on("completed", (data) => {
    const gen = activeGenerations.value.find((g) => g.id === generationId);
    if (gen) {
      gen.status = "completed";
      gen.progress = 100;
      gen.output = data.output;
      gen.completed_at = new Date().toISOString();

      completedGenerations.value.unshift(gen);
      activeGenerations.value = activeGenerations.value.filter(
        (g) => g.id !== generationId,
      );
    }

    ws.disconnect();
    wsConnections.delete(generationId);
  });

  ws.on("error", (data) => {
    const gen = activeGenerations.value.find((g) => g.id === generationId);
    if (gen) {
      gen.status = "failed";
      gen.error = data.error;
    }

    ws.disconnect();
    wsConnections.delete(generationId);
  });
};

// Debounced search functions
const getSuggestionsDebounced = debounce(async () => {
  if (!formData.value.prompt || formData.value.prompt.length < 10) {
    promptSuggestions.value = [];
    return;
  }

  try {
    const response = await api.vector.search(formData.value.prompt, 5);
    promptSuggestions.value = response.data.results;
  } catch (error) {
    console.error("Failed to get suggestions:", error);
  }
}, 500);

const searchSimilarDebounced = debounce(async () => {
  if (!formData.value.character_name) {
    similarCharacters.value = [];
    return;
  }

  try {
    const response = await api.vector.search(formData.value.character_name, 4);
    similarCharacters.value = response.data.results;
  } catch (error) {
    console.error("Failed to search similar:", error);
  }
}, 500);

// UI Actions
const applyPromptSuggestion = (suggestion) => {
  formData.value.prompt = suggestion.prompt;
  promptSuggestions.value = [];
};

const loadSimilarCharacter = (char) => {
  formData.value.character_name = char.character_name;
  formData.value.prompt = char.prompt;
};

const applyStyleTransfer = (char) => {
  // Extract style elements from the character
  const styleElements = char.prompt.match(
    /(style|lighting|mood|atmosphere|quality):[^,]*/g,
  );
  if (styleElements) {
    formData.value.prompt += ", " + styleElements.join(", ");
  }
};

const retryGeneration = async (generationId) => {
  try {
    await api.jobs.retry(generationId);
    alert("Retry initiated");
  } catch (error) {
    console.error("Retry failed:", error);
  }
};

const viewFullSize = (gen) => {
  if (gen.output) {
    window.open(gen.output, "_blank");
  }
};

const generateVariations = async (gen) => {
  formData.value.prompt = gen.prompt || formData.value.prompt;
  formData.value.character_name = gen.character_name + "_variation";
  formData.value.seed = Math.floor(Math.random() * 1000000);
  await generateCharacter();
};

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString();
};

// Cleanup on unmount
onUnmounted(() => {
  // Close all WebSocket connections
  wsConnections.forEach((ws) => ws.disconnect());
  wsConnections.clear();
});

// Load initial data
onMounted(async () => {
  // Could load recent generations, models, etc.
  console.log("CharacterGeneratorEnhanced mounted");
});
</script>

<style scoped>
.character-generator-enhanced {
  max-width: 1600px;
  margin: 0 auto;
  padding: 2rem;
  color: white;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
