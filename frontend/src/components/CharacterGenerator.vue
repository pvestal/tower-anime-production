<template>
  <div class="character-generator">
    <h2 class="text-2xl font-bold mb-6">
      Character Generator - Project Chimera
    </h2>

    <!-- Character Input Form -->
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
          <textarea
            v-model="formData.prompt"
            rows="4"
            class="w-full px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-blue-500"
            placeholder="Describe the character appearance, outfit, pose, style..."
          ></textarea>
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

      <div class="mt-6 flex gap-4">
        <button
          :disabled="isGenerating"
          class="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          @click="generateCharacter"
        >
          {{ isGenerating ? "Generating..." : "Generate Character" }}
        </button>

        <button
          :disabled="!formData.prompt"
          class="px-6 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
          @click="searchSimilar"
        >
          Find Similar
        </button>
      </div>
    </div>

    <!-- Vector Search Section -->
    <div class="search-section bg-gray-800 rounded-lg p-6 mb-6">
      <h3 class="text-xl font-semibold mb-4">Semantic Search</h3>

      <div class="flex gap-4">
        <input
          v-model="searchQuery"
          type="text"
          class="flex-1 px-3 py-2 bg-gray-700 rounded border border-gray-600 focus:border-purple-500"
          placeholder="Search characters by description..."
          @keyup.enter="performSearch"
        />
        <button
          class="px-6 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
          @click="performSearch"
        >
          Search
        </button>
      </div>

      <!-- Search Results -->
      <div v-if="searchResults.length > 0" class="mt-6">
        <h4 class="text-lg font-medium mb-3">Search Results</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="result in searchResults"
            :key="result.id"
            class="bg-gray-700 rounded-lg p-4 cursor-pointer hover:bg-gray-600"
            @click="loadCharacter(result)"
          >
            <div class="font-semibold">{{ result.character_name }}</div>
            <div class="text-sm text-gray-400 mt-1">
              Score: {{ result.score.toFixed(3) }}
            </div>
            <div class="text-sm mt-2 line-clamp-3">{{ result.prompt }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Generation History -->
    <div class="history-section bg-gray-800 rounded-lg p-6">
      <h3 class="text-xl font-semibold mb-4">Recent Generations</h3>

      <div v-if="generationHistory.length === 0" class="text-gray-500">
        No generations yet. Create your first character above!
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="gen in generationHistory"
          :key="gen.generation_id"
          class="bg-gray-700 rounded-lg overflow-hidden"
        >
          <!-- Placeholder for image preview -->
          <div class="h-48 bg-gray-600 flex items-center justify-center">
            <span class="text-gray-400">{{ gen.character_name }}</span>
          </div>

          <div class="p-4">
            <div class="font-semibold">{{ gen.character_name }}</div>
            <div class="text-sm text-gray-400 mt-1">
              {{ gen.generation_type }}
            </div>
            <div class="text-sm text-gray-400">
              {{ formatDate(gen.created_at) }}
            </div>

            <div class="mt-3 flex gap-2">
              <button
                class="text-sm px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                @click="viewGeneration(gen)"
              >
                View
              </button>
              <button
                class="text-sm px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700"
                @click="findSimilarTo(gen)"
              >
                Similar
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useCharacterStore } from "../stores/useCharacterStore";

const store = useCharacterStore();

// Form data
const formData = ref({
  character_name: "",
  prompt: "",
  negative_prompt: "",
  content_type: "sfw",
  generation_type: "single_image",
  model_name: "chilloutmix_NiPrunedFp32Fix.safetensors",
  seed: -1,
  num_images: 1,
});

// State
const isGenerating = ref(false);
const searchQuery = ref("");
const searchResults = ref([]);
const generationHistory = ref([]);

// Methods
const generateCharacter = async () => {
  if (!formData.value.character_name || !formData.value.prompt) {
    alert("Please provide character name and description");
    return;
  }

  isGenerating.value = true;

  try {
    const response = await fetch("/api/anime/character/v2/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(formData.value),
    });

    const result = await response.json();

    if (response.ok) {
      alert(`Character generation started! Job ID: ${result.generation_id}`);
      // Add to history
      generationHistory.value.unshift({
        ...formData.value,
        generation_id: result.generation_id,
        created_at: new Date().toISOString(),
      });
    } else {
      alert(`Error: ${result.detail || "Generation failed"}`);
    }
  } catch (error) {
    alert(`Error: ${error.message}`);
  } finally {
    isGenerating.value = false;
  }
};

const performSearch = async () => {
  if (!searchQuery.value) return;

  try {
    const response = await fetch(
      `/api/v1/vector/search?q=${encodeURIComponent(searchQuery.value)}&limit=6`,
    );
    const data = await response.json();

    if (data.status === "success") {
      searchResults.value = data.results;
    }
  } catch (error) {
    console.error("Search error:", error);
  }
};

const searchSimilar = async () => {
  if (!formData.value.prompt) return;
  searchQuery.value = formData.value.prompt;
  await performSearch();
};

const loadCharacter = (result) => {
  formData.value.character_name = result.character_name;
  formData.value.prompt = result.prompt;
  alert("Character loaded into form");
};

const findSimilarTo = async (gen) => {
  searchQuery.value = gen.prompt;
  await performSearch();
};

const viewGeneration = (gen) => {
  // TODO: Implement view logic
  console.log("View generation:", gen);
};

const formatDate = (dateString) => {
  return new Date(dateString).toLocaleString();
};

// Load recent generations on mount
onMounted(async () => {
  try {
    // TODO: Load from API
    console.log("Component mounted");
  } catch (error) {
    console.error("Failed to load history:", error);
  }
});
</script>

<style scoped>
.character-generator {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem;
  color: white;
}

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
