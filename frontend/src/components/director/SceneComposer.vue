<template>
  <div class="scene-composer">
    <h2 class="text-2xl font-bold mb-4">
      Scene Composer - Enterprise Director Mode
    </h2>

    <!-- Character Selection -->
    <div class="mb-6">
      <label class="block text-sm font-medium mb-2">Select Character</label>
      <select
        v-model="selectedCharacter"
        data-test="character-select"
        class="w-full p-2 border rounded-md"
        @change="onCharacterChange"
      >
        <option :value="null">-- Select Character --</option>
        <option
          v-for="character in availableCharacters"
          :key="character.id"
          :value="character"
        >
          {{ character.name }}
        </option>
      </select>
    </div>

    <!-- Action Category Filter -->
    <div class="mb-6">
      <label class="block text-sm font-medium mb-2">Action Category</label>
      <div class="flex gap-2 flex-wrap">
        <button
          v-for="category in actionCategories"
          :key="category"
          :data-test="`action-category-${category}`"
          :class="[
            'px-4 py-2 rounded-md transition-colors',
            selectedCategory === category
              ? 'bg-blue-500 text-white'
              : 'bg-gray-200 hover:bg-gray-300',
          ]"
          @click="filterByCategory(category)"
        >
          {{ category }}
          <span v-if="getCategoryCount(category)" class="ml-1 text-xs">
            ({{ getCategoryCount(category) }})
          </span>
        </button>
      </div>
    </div>

    <!-- Action Selection -->
    <div class="mb-6">
      <label class="block text-sm font-medium mb-2">Select Action</label>
      <div
        class="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto border rounded-md p-2"
      >
        <div
          v-for="action in filteredActions"
          :key="action.id"
          :data-test="`action-${action.action_tag}`"
          :class="[
            'p-3 border rounded cursor-pointer transition-all',
            selectedAction?.id === action.id
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-200 hover:border-gray-400',
          ]"
          @click="selectAction(action)"
        >
          <div class="font-medium">{{ action.action_tag }}</div>
          <div class="text-xs text-gray-600">{{ action.description }}</div>
          <div class="flex items-center gap-2 mt-1">
            <span
              :class="[
                'text-xs px-1 py-0.5 rounded',
                action.intensity_level >= 7
                  ? 'bg-red-100 text-red-700'
                  : action.intensity_level >= 4
                    ? 'bg-yellow-100 text-yellow-700'
                    : 'bg-green-100 text-green-700',
              ]"
            >
              Intensity: {{ action.intensity_level }}
            </span>
            <span
              v-if="action.is_nsfw"
              class="text-xs bg-purple-500 text-white px-1 py-0.5 rounded"
            >
              Mature
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Style Selection -->
    <div class="mb-6">
      <label class="block text-sm font-medium mb-2">Visual Style</label>
      <div class="grid grid-cols-2 gap-2">
        <div
          v-for="style in compatibleStyles"
          :key="style.id"
          :data-test="`style-${style.name}`"
          :class="[
            'p-3 border rounded cursor-pointer transition-all',
            selectedStyle?.id === style.id
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-200 hover:border-gray-400',
          ]"
          @click="selectStyle(style)"
        >
          <div class="font-medium">{{ style.name }}</div>
          <div class="text-xs text-gray-600">
            Camera: {{ style.camera_angle || "Default" }}
          </div>
          <div class="text-xs text-gray-600">
            Lighting: {{ style.lighting_style || "Default" }}
          </div>
        </div>
      </div>
    </div>

    <!-- Duration Control -->
    <div class="mb-6">
      <label class="block text-sm font-medium mb-2">
        Duration: {{ duration }} seconds
      </label>
      <input
        v-model.number="duration"
        type="range"
        data-test="duration-input"
        min="2"
        max="30"
        step="1"
        class="w-full"
      />
      <div class="flex justify-between text-xs text-gray-500 mt-1">
        <span>2s</span>
        <span>15s</span>
        <span>30s</span>
      </div>
    </div>

    <!-- Generation Preview -->
    <div v-if="generationPayload" class="mb-6 p-4 bg-gray-50 rounded-md">
      <h3 class="font-medium mb-2">Generation Preview</h3>
      <div class="text-sm space-y-1">
        <div>
          <span class="font-medium">Character:</span>
          {{ selectedCharacter?.name }}
        </div>
        <div>
          <span class="font-medium">Action:</span>
          {{ selectedAction?.action_tag }}
        </div>
        <div>
          <span class="font-medium">Style:</span> {{ selectedStyle?.name }}
        </div>
        <div><span class="font-medium">Duration:</span> {{ duration }}s</div>
        <div>
          <span class="font-medium">Workflow:</span>
          {{ generationPayload.workflow_tier }}
        </div>
        <div>
          <span class="font-medium">Est. Time:</span> {{ estimatedTime }}s
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="flex gap-3">
      <button
        :disabled="!canGenerate"
        data-test="generate-button"
        :class="[
          'px-6 py-2 rounded-md font-medium transition-colors',
          canGenerate
            ? 'bg-blue-500 text-white hover:bg-blue-600'
            : 'bg-gray-300 text-gray-500 cursor-not-allowed',
        ]"
        @click="generateScene"
      >
        Generate Scene
      </button>

      <button
        v-if="lastGeneration"
        class="px-6 py-2 border border-blue-500 text-blue-500 rounded-md hover:bg-blue-50"
        @click="showRapidRegenerate = true"
      >
        Rapid Regenerate
      </button>

      <button
        v-if="hasCache"
        class="px-6 py-2 border border-green-500 text-green-500 rounded-md hover:bg-green-50"
        @click="loadFromCache"
      >
        Load Cached
      </button>
    </div>

    <!-- Job Status -->
    <div v-if="currentJob" class="mt-6 p-4 bg-blue-50 rounded-md">
      <h3 class="font-medium mb-2" data-test="job-status">
        Status: {{ currentJob.status }}
      </h3>
      <div class="w-full bg-gray-200 rounded-full h-2.5">
        <div
          class="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
          :style="`width: ${currentJob.progress}%`"
        />
      </div>
      <div v-if="currentJob.eta" class="text-sm text-gray-600 mt-2">
        ETA: {{ currentJob.eta }} seconds
      </div>
    </div>

    <!-- Video Preview -->
    <div v-if="generatedVideo" class="mt-6">
      <h3 class="font-medium mb-2">Generated Output</h3>
      <video
        :src="generatedVideo.url"
        controls
        data-test="video-preview"
        class="w-full rounded-md"
      />
      <div class="text-sm text-gray-600 mt-2">
        Duration:
        <span data-test="video-duration">{{ generatedVideo.duration }}</span
        >s
      </div>
    </div>

    <!-- Rapid Regeneration Modal -->
    <teleport to="body">
      <div
        v-if="showRapidRegenerate"
        class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      >
        <div class="bg-white rounded-lg p-6 w-full max-w-md">
          <h3 class="text-lg font-bold mb-4">Rapid Regeneration</h3>

          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-1"
                >Seed Adjustment</label
              >
              <input
                v-model.number="regenerateOptions.seed"
                type="number"
                class="w-full p-2 border rounded"
              />
            </div>

            <div>
              <label class="block text-sm font-medium mb-1"
                >Motion Intensity</label
              >
              <input
                v-model.number="regenerateOptions.motionIntensity"
                type="range"
                min="0"
                max="1"
                step="0.1"
                class="w-full"
              />
            </div>

            <div>
              <label class="block text-sm font-medium mb-1"
                >Denoise Strength</label
              >
              <input
                v-model.number="regenerateOptions.denoise"
                type="range"
                min="0.2"
                max="0.8"
                step="0.05"
                class="w-full"
              />
            </div>
          </div>

          <div class="flex gap-3 mt-6">
            <button
              class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              @click="executeRapidRegenerate"
            >
              Regenerate
            </button>
            <button
              class="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50"
              @click="showRapidRegenerate = false"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useOrchestrator } from "@/composables/useOrchestrator";
import { useSSO } from "@/composables/useSSO";
import { useNotification } from "@/composables/useNotification";

// Character type definition
// {
//   id: number
//   name: string
//   base_prompt?: string
//   lora_path?: string
// }

// SemanticAction type removed - not using TypeScript

// StyleAngle type removed - not using TypeScript

// GenerationJob type removed - not using TypeScript

// Composables
const { submitGenerationJob, pollJobStatus, rapidRegenerate } =
  useOrchestrator();
const { fetchSemanticActions, fetchStyles, fetchCharacters } = useSSO();
const { showSuccess, showError, showWarning } = useNotification();

// State
const availableCharacters = ref([]);
const availableActions = ref([]);
const availableStyles = ref([]);

const selectedCharacter = ref(null);
const selectedAction = ref(null);
const selectedStyle = ref(null);
const selectedCategory = ref("all");
const duration = ref(12);

const currentJob = ref(null);
const generatedVideo = ref(null);
const lastGeneration = ref(null);
const generationPayload = ref(null);

const showRapidRegenerate = ref(false);
const regenerateOptions = ref({
  seed: 12345,
  motionIntensity: 0.3,
  denoise: 0.4,
});

// Computed
const actionCategories = computed(() => {
  const categories = new Set(availableActions.value.map((a) => a.category));
  return ["all", ...Array.from(categories)];
});

const filteredActions = computed(() => {
  if (selectedCategory.value === "all") {
    return availableActions.value;
  }
  return availableActions.value.filter(
    (a) => a.category === selectedCategory.value,
  );
});

const compatibleStyles = computed(() => {
  if (!selectedAction.value) return availableStyles.value;

  return availableStyles.value.filter((style) => {
    if (!style.compatible_categories) return true;
    return style.compatible_categories.includes(selectedAction.value.category);
  });
});

const canGenerate = computed(() => {
  return !!(
    selectedCharacter.value &&
    selectedAction.value &&
    selectedStyle.value
  );
});

const estimatedTime = computed(() => {
  if (!generationPayload.value) return 0;
  return generationPayload.value.estimated_duration || 60;
});

const hasCache = computed(() => {
  // Check if we have cached generations for current selection
  return false; // TODO: Implement cache check
});

// Methods
const onCharacterChange = () => {
  // Reset selections when character changes
  selectedAction.value = null;
  selectedStyle.value = null;
};

const filterByCategory = (category) => {
  selectedCategory.value = category;
};

const getCategoryCount = (category) => {
  if (category === "all") return availableActions.value.length;
  return availableActions.value.filter((a) => a.category === category).length;
};

const selectAction = (action) => {
  selectedAction.value = action;
  duration.value = action.default_duration_seconds;

  // Auto-select compatible style if only one available
  const compatible = compatibleStyles.value;
  if (compatible.length === 1) {
    selectedStyle.value = compatible[0];
  }
};

const selectStyle = (style) => {
  selectedStyle.value = style;
};

const buildGenerationPayload = () => {
  if (
    !selectedCharacter.value ||
    !selectedAction.value ||
    !selectedStyle.value
  ) {
    return null;
  }

  const workflowTier = determineWorkflowTier();

  return {
    character_id: selectedCharacter.value.id,
    action_id: selectedAction.value.id,
    style_angle_id: selectedStyle.value.id,
    duration_seconds: duration.value,
    workflow_tier: workflowTier,
    options: {
      enforce_consistency: true,
    },
    estimated_duration: estimateGenerationTime(workflowTier),
  };
};

const determineWorkflowTier = () => {
  if (!selectedAction.value) return "TIER_1_STATIC";

  // Complex actions always use Tier 3
  if (selectedAction.value.category === "complex_action") {
    return "TIER_3_ANIMATEDIFF";
  }

  // Long durations require AnimateDiff
  if (duration.value > 12) {
    return "TIER_3_ANIMATEDIFF";
  }

  // High intensity intimate/violent scenes need smooth SVD
  if (
    ["intimate", "violent"].includes(selectedAction.value.category) &&
    selectedAction.value.intensity_level >= 7
  ) {
    return "TIER_2_SVD";
  }

  // Short, simple actions can use static validation
  if (duration.value <= 4 && selectedAction.value.intensity_level <= 3) {
    return "TIER_1_STATIC";
  }

  // Default to SVD for smooth motion
  return "TIER_2_SVD";
};

const estimateGenerationTime = (tier) => {
  const baseTimes = {
    TIER_1_STATIC: 5,
    TIER_2_SVD: 30,
    TIER_3_ANIMATEDIFF: 60,
  };

  const base = baseTimes[tier] || 60;
  const durationMultiplier = duration.value / 5;

  return Math.round(base + base * durationMultiplier * 0.5);
};

const generateScene = async () => {
  generationPayload.value = buildGenerationPayload();
  if (!generationPayload.value) return;

  try {
    // Submit generation job
    const job = await submitGenerationJob(generationPayload.value);

    currentJob.value = {
      id: job.job_id,
      status: "submitting",
      progress: 0,
    };

    showSuccess("Generation job submitted successfully");

    // Start polling for status
    pollForCompletion(job.job_id);
  } catch (error) {
    showError(`Failed to generate scene: ${error.message}`);
  }
};

const pollForCompletion = async (jobId) => {
  let attempts = 0;
  const maxAttempts = 120; // 10 minutes max

  while (attempts < maxAttempts && currentJob.value) {
    try {
      const status = await pollJobStatus(jobId);

      currentJob.value = {
        ...currentJob.value,
        status: status.status,
        progress: status.progress || (attempts / maxAttempts) * 100,
        eta: status.eta,
      };

      if (status.status === "completed") {
        generatedVideo.value = {
          url: status.output_url,
          duration: duration.value,
        };
        lastGeneration.value = {
          job_id: jobId,
          cache_key: status.cache_key,
        };
        showSuccess("Generation completed successfully!");
        break;
      } else if (status.status === "failed") {
        showError(`Generation failed: ${status.error}`);
        currentJob.value = null;
        break;
      }
    } catch (error) {
      console.error("Polling error:", error);
    }

    await new Promise((resolve) => setTimeout(resolve, 5000)); // Poll every 5 seconds
    attempts++;
  }
};

const loadFromCache = async () => {
  // TODO: Implement cache loading
  showWarning("Cache loading not yet implemented");
};

const executeRapidRegenerate = async () => {
  if (!lastGeneration.value) return;

  try {
    const modifications = {
      seed: regenerateOptions.value.seed,
      motion_profile: {
        motion_intensity: regenerateOptions.value.motionIntensity,
        denoise_strength: regenerateOptions.value.denoise,
      },
    };

    const job = await rapidRegenerate(
      lastGeneration.value.cache_key,
      modifications,
    );

    currentJob.value = {
      id: job.job_id,
      status: "regenerating",
      progress: 0,
    };

    showRapidRegenerate.value = false;
    showSuccess("Rapid regeneration started");

    pollForCompletion(job.job_id);
  } catch (error) {
    showError(`Regeneration failed: ${error.message}`);
  }
};

// Watch for payload changes
watch([selectedCharacter, selectedAction, selectedStyle, duration], () => {
  if (canGenerate.value) {
    generationPayload.value = buildGenerationPayload();
  } else {
    generationPayload.value = null;
  }
});

// Lifecycle
onMounted(async () => {
  try {
    // Load all data
    const [chars, actions, styles] = await Promise.all([
      fetchCharacters(),
      fetchSemanticActions(),
      fetchStyles(),
    ]);

    availableCharacters.value = chars;
    availableActions.value = actions;
    availableStyles.value = styles;
  } catch (error) {
    showError(`Failed to load data: ${error.message}`);
  }
});
</script>

<style scoped>
.scene-composer {
  @apply max-w-6xl mx-auto p-6;
}
</style>
