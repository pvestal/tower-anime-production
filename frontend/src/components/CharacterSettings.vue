<template>
  <div class="character-settings">
    <h2 class="text-2xl font-bold mb-6">Character Settings & Persistence</h2>

    <!-- Character Configuration -->
    <div class="settings-section mb-6">
      <h3 class="text-xl font-semibold mb-4">Character Configuration</h3>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block mb-2">Project Name</label>
          <input
            v-model="settings.project_name"
            class="w-full p-2 border rounded"
            placeholder="Tokyo Debt Desire"
          />
        </div>

        <div>
          <label class="block mb-2">Character Name</label>
          <input
            v-model="settings.character_name"
            class="w-full p-2 border rounded"
            placeholder="Character name"
          />
        </div>

        <div>
          <label class="block mb-2">Reference Image</label>
          <div class="flex gap-2">
            <input
              v-model="settings.reference_image"
              class="flex-1 p-2 border rounded"
              placeholder="/path/to/reference.png"
            />
            <button
              class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              @click="selectReferenceImage"
            >
              Browse
            </button>
          </div>
          <div v-if="settings.reference_image" class="mt-2">
            <img
              :src="getImageUrl(settings.reference_image)"
              class="h-32 rounded"
            />
          </div>
        </div>

        <div>
          <label class="block mb-2">Character Seed</label>
          <input
            v-model.number="settings.character_seed"
            type="number"
            class="w-full p-2 border rounded"
            placeholder="888890"
          />
        </div>
      </div>
    </div>

    <!-- Generation Settings -->
    <div class="settings-section mb-6">
      <h3 class="text-xl font-semibold mb-4">Generation Settings</h3>

      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="block mb-2">Model</label>
          <select v-model="settings.model" class="w-full p-2 border rounded">
            <option value="dreamshaper_8.safetensors">DreamShaper 8</option>
            <option value="AOM3A1B.safetensors">AOM3A1B</option>
            <option value="chilloutmix_NiPrunedFp32Fix.safetensors">
              ChilloutMix
            </option>
            <option value="deliberate_v2.safetensors">Deliberate v2</option>
          </select>
        </div>

        <div>
          <label class="block mb-2">Sampler</label>
          <select v-model="settings.sampler" class="w-full p-2 border rounded">
            <option value="dpmpp_2m">DPM++ 2M</option>
            <option value="euler">Euler</option>
            <option value="euler_a">Euler A</option>
            <option value="ddim">DDIM</option>
          </select>
        </div>

        <div>
          <label class="block mb-2">Scheduler</label>
          <select
            v-model="settings.scheduler"
            class="w-full p-2 border rounded"
          >
            <option value="karras">Karras</option>
            <option value="normal">Normal</option>
            <option value="exponential">Exponential</option>
          </select>
        </div>

        <div>
          <label class="block mb-2">Steps</label>
          <input
            v-model.number="settings.steps"
            type="number"
            min="10"
            max="50"
            class="w-full p-2 border rounded"
          />
        </div>

        <div>
          <label class="block mb-2">CFG Scale</label>
          <input
            v-model.number="settings.cfg_scale"
            type="number"
            min="1"
            max="20"
            step="0.5"
            class="w-full p-2 border rounded"
          />
        </div>

        <div>
          <label class="block mb-2">Batch Size</label>
          <input
            v-model.number="settings.batch_size"
            type="number"
            min="1"
            max="24"
            class="w-full p-2 border rounded"
          />
        </div>

        <div>
          <label class="block mb-2">Width</label>
          <input
            v-model.number="settings.width"
            type="number"
            step="64"
            class="w-full p-2 border rounded"
          />
        </div>

        <div>
          <label class="block mb-2">Height</label>
          <input
            v-model.number="settings.height"
            type="number"
            step="64"
            class="w-full p-2 border rounded"
          />
        </div>

        <div>
          <label class="block mb-2">Denoise</label>
          <input
            v-model.number="settings.denoise"
            type="number"
            min="0"
            max="1"
            step="0.05"
            class="w-full p-2 border rounded"
          />
        </div>
      </div>
    </div>

    <!-- Prompt Configuration -->
    <div class="settings-section mb-6">
      <h3 class="text-xl font-semibold mb-4">Prompt Configuration</h3>

      <div class="mb-4">
        <label class="block mb-2">Positive Prompt Base</label>
        <textarea
          v-model="settings.positive_prompt_base"
          rows="4"
          class="w-full p-2 border rounded"
          placeholder="tokyo debt desire, photorealistic Asian woman..."
        ></textarea>
      </div>

      <div class="mb-4">
        <label class="block mb-2">Negative Prompt Base</label>
        <textarea
          v-model="settings.negative_prompt_base"
          rows="3"
          class="w-full p-2 border rounded"
          placeholder="blurry, deformed, extra limbs..."
        ></textarea>
      </div>

      <div>
        <label class="block mb-2">Style</label>
        <select v-model="settings.style" class="w-full p-2 border rounded">
          <option value="photorealistic">Photorealistic</option>
          <option value="anime">Anime</option>
          <option value="3d">3D Render</option>
          <option value="artistic">Artistic</option>
        </select>
      </div>
    </div>

    <!-- Character Description -->
    <div class="settings-section mb-6">
      <h3 class="text-xl font-semibold mb-4">Character Description</h3>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block mb-2">Age</label>
          <input
            v-model="settings.character_description.age"
            class="w-full p-2 border rounded"
            placeholder="26"
          />
        </div>

        <div>
          <label class="block mb-2">Ethnicity</label>
          <input
            v-model="settings.character_description.ethnicity"
            class="w-full p-2 border rounded"
            placeholder="Japanese"
          />
        </div>

        <div>
          <label class="block mb-2">Hair</label>
          <input
            v-model="settings.character_description.hair"
            class="w-full p-2 border rounded"
            placeholder="black with red highlights"
          />
        </div>

        <div>
          <label class="block mb-2">Eyes</label>
          <input
            v-model="settings.character_description.eyes"
            class="w-full p-2 border rounded"
            placeholder="dark brown, almond-shaped"
          />
        </div>

        <div>
          <label class="block mb-2">Build</label>
          <input
            v-model="settings.character_description.build"
            class="w-full p-2 border rounded"
            placeholder="curvy, voluptuous"
          />
        </div>

        <div>
          <label class="block mb-2">Height</label>
          <input
            v-model="settings.character_description.height"
            class="w-full p-2 border rounded"
            placeholder="5'6"
          />
        </div>
      </div>

      <div class="mt-4">
        <label class="block mb-2">Distinctive Features</label>
        <textarea
          v-model="settings.character_description.distinctive_features"
          rows="2"
          class="w-full p-2 border rounded"
          placeholder="beauty mark under left eye, sharp jawline..."
        ></textarea>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="flex gap-4">
      <button
        class="px-6 py-2 bg-green-500 text-white rounded hover:bg-green-600"
        @click="saveSettings"
      >
        💾 Save Settings
      </button>

      <button
        class="px-6 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        @click="loadSettings"
      >
        📂 Load Settings
      </button>

      <button
        class="px-6 py-2 bg-purple-500 text-white rounded hover:bg-purple-600"
        @click="exportSettings"
      >
        📥 Export JSON
      </button>

      <button
        class="px-6 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600"
        @click="importSettings"
      >
        📤 Import JSON
      </button>

      <button
        class="px-6 py-2 bg-red-500 text-white rounded hover:bg-red-600"
        @click="testGeneration"
      >
        🧪 Test Generation
      </button>
    </div>

    <!-- Recent Generations -->
    <div v-if="recentGenerations.length > 0" class="mt-8">
      <h3 class="text-xl font-semibold mb-4">Recent Generations</h3>
      <div class="grid grid-cols-4 gap-4">
        <div
          v-for="img in recentGenerations"
          :key="img"
          class="cursor-pointer"
          @click="selectAsReference(img)"
        >
          <img
            :src="getImageUrl(img)"
            class="w-full rounded hover:opacity-80"
          />
          <p class="text-xs mt-1 truncate">{{ img.split("/").pop() }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useToast } from "vue-toastification";

const toast = useToast();

const settings = ref({
  project_name: "Tokyo Debt Desire",
  character_name: "",
  character_seed: 888890,
  reference_image: "",
  model: "dreamshaper_8.safetensors",
  sampler: "dpmpp_2m",
  scheduler: "karras",
  cfg_scale: 8.5,
  steps: 25,
  batch_size: 24,
  width: 512,
  height: 768,
  denoise: 1.0,
  positive_prompt_base: "",
  negative_prompt_base: "",
  style: "photorealistic",
  character_description: {
    age: "",
    ethnicity: "",
    hair: "",
    eyes: "",
    build: "",
    height: "",
    distinctive_features: "",
  },
});

const recentGenerations = ref([]);

onMounted(async () => {
  await loadSettings();
  await loadRecentGenerations();
});

const saveSettings = async () => {
  try {
    const response = await fetch("/api/anime/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings.value),
    });

    if (response.ok) {
      toast.success("Settings saved to database!");
    } else {
      toast.error("Failed to save settings");
    }
  } catch (error) {
    console.error("Save error:", error);
    toast.error("Error saving settings");
  }
};

const loadSettings = async () => {
  try {
    const response = await fetch("/api/anime/settings");
    if (response.ok) {
      const data = await response.json();
      if (data && Object.keys(data).length > 0) {
        settings.value = { ...settings.value, ...data };
        toast.success("Settings loaded from database");
      }
    }
  } catch (error) {
    console.error("Load error:", error);
    toast.error("Error loading settings");
  }
};

const exportSettings = () => {
  const dataStr = JSON.stringify(settings.value, null, 2);
  const dataUri =
    "data:application/json;charset=utf-8," + encodeURIComponent(dataStr);
  const exportFileDefaultName = `character_settings_${Date.now()}.json`;

  const linkElement = document.createElement("a");
  linkElement.setAttribute("href", dataUri);
  linkElement.setAttribute("download", exportFileDefaultName);
  linkElement.click();

  toast.success("Settings exported to JSON file");
};

const importSettings = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json";

  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (file) {
      const text = await file.text();
      try {
        const imported = JSON.parse(text);
        settings.value = { ...settings.value, ...imported };
        toast.success("Settings imported from JSON");
      } catch (error) {
        toast.error("Invalid JSON file");
      }
    }
  };

  input.click();
};

const testGeneration = async () => {
  try {
    const response = await fetch("/api/anime/test-generation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        settings: settings.value,
        prompt: "test generation with saved settings",
      }),
    });

    if (response.ok) {
      const result = await response.json();
      toast.success("Test generation submitted!");

      // Refresh recent generations after a delay
      setTimeout(() => loadRecentGenerations(), 5000);
    } else {
      toast.error("Test generation failed");
    }
  } catch (error) {
    console.error("Test error:", error);
    toast.error("Error testing generation");
  }
};

const selectReferenceImage = async () => {
  // Show recent images to select from
  const images = await loadRecentGenerations();
  if (images.length > 0) {
    // For now, just use the first one
    settings.value.reference_image = images[0];
    toast.success("Reference image selected");
  }
};

const selectAsReference = (imagePath) => {
  settings.value.reference_image = imagePath;
  toast.success("Selected as reference image");
};

const loadRecentGenerations = async () => {
  try {
    const response = await fetch("/api/anime/recent-images?limit=8");
    if (response.ok) {
      const data = await response.json();
      recentGenerations.value = data.images || [];
      return data.images || [];
    }
  } catch (error) {
    console.error("Error loading recent images:", error);
  }
  return [];
};

const getImageUrl = (path) => {
  if (!path) return "";
  // Convert local path to served URL
  if (path.startsWith("/home/patrick/ComfyUI/output/")) {
    const filename = path.split("/").pop();
    return `/api/anime/images/${filename}`;
  }
  return path;
};
</script>

<style scoped>
.character-settings {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.settings-section {
  background: #f9fafb;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

input,
select,
textarea {
  font-size: 14px;
}

label {
  font-weight: 600;
  color: #374151;
  font-size: 14px;
}
</style>
