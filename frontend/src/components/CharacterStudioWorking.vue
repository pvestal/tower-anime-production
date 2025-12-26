<template>
  <div class="character-studio-working">
    <h2>Character Consistency Studio</h2>

    <!-- Reference Image Section -->
    <div class="reference-section">
      <h3>Reference Image</h3>
      <div class="reference-controls">
        <select v-model="selectedReference" @change="loadReference">
          <option value="reference_woman.png">Default Woman</option>
          <option v-for="ref in references" :key="ref.name" :value="ref.name">
            {{ ref.name }}
          </option>
        </select>
        <input type="file" accept="image/*" @change="uploadReference" />
      </div>
      <img
        v-if="referencePreview"
        :src="referencePreview"
        class="reference-preview"
      />
    </div>

    <!-- Generation Controls -->
    <div class="generation-section">
      <h3>Generate Consistent Character</h3>

      <!-- Current Active Settings Display -->
      <div class="current-settings">
        <h4>🔧 Current Active Settings:</h4>
        <div class="settings-grid">
          <div><strong>Seed:</strong> {{ currentSeed }}</div>
          <div><strong>Model:</strong> {{ currentModel }}</div>
          <div><strong>Sampler:</strong> {{ currentSampler }}</div>
          <div><strong>Steps:</strong> {{ currentSteps }}</div>
          <div>
            <strong>Character:</strong>
            {{ selectedGeneration?.character_name || "None Selected" }}
          </div>
          <div><strong>Reference:</strong> {{ selectedReference }}</div>
        </div>
      </div>

      <div class="control-group">
        <label>Prompt (keep minimal for consistency):</label>
        <input v-model="prompt" placeholder="same woman, sitting" />
      </div>

      <div class="control-group">
        <label>Denoise (lower = more consistent): {{ denoise }}</label>
        <input v-model="denoise" type="range" min="0.1" max="0.5" step="0.05" />
      </div>

      <button
        :disabled="generating"
        class="generate-btn"
        @click="generateConsistent"
      >
        {{ generating ? "Generating..." : "Generate Consistent Character" }}
      </button>
    </div>

    <!-- Gallery Section -->
    <div class="gallery-section">
      <h3>Generation History</h3>
      <button class="refresh-btn" @click="loadGallery">Refresh Gallery</button>

      <div class="gallery-grid">
        <div
          v-for="gen in gallery"
          :key="gen.job_id"
          class="gallery-item"
          :class="{ selected: selectedGeneration?.job_id === gen.job_id }"
        >
          <img :src="getImageUrl(gen)" @click="selectGeneration(gen)" />

          <div class="metadata">
            <strong>{{ gen.character_name || "unnamed" }}</strong>
            <div class="settings-preview">
              Seed: {{ gen.seed }}<br />
              Model: {{ gen.checkpoint }}<br />
              Denoise: {{ gen.denoise }}<br />
              Steps: {{ gen.steps }}
            </div>

            <div class="actions">
              <button class="action-btn" @click="useAsReference(gen)">
                Use as Reference
              </button>
              <button class="action-btn" @click="copySeed(gen)">
                Copy Seed
              </button>
              <button class="action-btn" @click="copyAllSettings(gen)">
                Copy All Settings
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="results.length > 0" class="results-section">
      <h3>Current Session</h3>
      <div class="results-grid">
        <div
          v-for="(result, index) in results"
          :key="index"
          class="result-item"
        >
          <img :src="result.url" :alt="`Result ${index + 1}`" />
          <p>{{ result.prompt }}</p>
        </div>
      </div>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessage" class="status-message" :class="statusClass">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from "vue";
import axios from "axios";

const API_BASE = "/api/anime";

export default {
  name: "CharacterStudioWorking",
  setup() {
    const selectedReference = ref("reference_woman.png");
    const referencePreview = ref(null);
    const references = ref([]);
    const prompt = ref("same woman");
    const denoise = ref(0.35);
    const generating = ref(false);
    const results = ref([]);
    const statusMessage = ref("");
    const statusClass = ref("");
    const gallery = ref([]);
    const selectedGeneration = ref(null);
    const currentSeed = ref(888890);
    const currentModel = ref("dreamshaper_8.safetensors");
    const currentSampler = ref("dpmpp_2m");
    const currentSteps = ref(25);

    const loadReferences = async () => {
      try {
        const response = await axios.get(`${API_BASE}/character/references`);
        references.value = response.data.references || [];
      } catch (error) {
        console.error("Failed to load references:", error);
      }
    };

    const loadReference = () => {
      // Load actual image preview from API
      referencePreview.value = `${API_BASE}/image/${selectedReference.value}`;
    };

    const uploadReference = async (event) => {
      const file = event.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append("file", file);

      try {
        statusMessage.value = "Uploading reference image...";
        statusClass.value = "info";

        const response = await axios.post(
          `${API_BASE}/character/upload-reference`,
          formData,
          { headers: { "Content-Type": "multipart/form-data" } },
        );

        selectedReference.value = response.data.filename;
        await loadReferences();
        statusMessage.value = "Reference uploaded successfully!";
        statusClass.value = "success";
      } catch (error) {
        statusMessage.value = `Upload failed: ${error.message}`;
        statusClass.value = "error";
      }
    };

    const loadGallery = async () => {
      try {
        const response = await axios.get(`${API_BASE}/character/gallery`);
        gallery.value = response.data.generations || [];
      } catch (error) {
        console.error("Failed to load gallery:", error);
      }
    };

    const getImageUrl = (gen) => {
      // Handle different path formats
      if (gen.output_path) {
        const filename = gen.output_path.split("/").pop();
        // Use the character API image endpoint
        return `${API_BASE}/image/${filename}`;
      }
      return gen.image_url || "";
    };

    const selectGeneration = (gen) => {
      selectedGeneration.value = gen;
      statusMessage.value = `Selected: ${gen.character_name || gen.job_id}`;
      statusClass.value = "info";
    };

    const useAsReference = async (gen) => {
      try {
        const response = await axios.post(
          `${API_BASE}/character/use-as-reference/${gen.job_id}`,
        );
        selectedReference.value = response.data.reference_name;

        // Copy all settings
        currentSeed.value = gen.seed;
        currentModel.value = gen.checkpoint;
        currentSampler.value = gen.sampler_name;
        currentSteps.value = gen.steps;
        denoise.value = gen.denoise || 0.35;

        statusMessage.value = `Using ${gen.character_name} as reference with all settings`;
        statusClass.value = "success";

        await loadReferences();
      } catch (error) {
        statusMessage.value = `Failed to use as reference: ${error.message}`;
        statusClass.value = "error";
      }
    };

    const copySeed = (gen) => {
      currentSeed.value = gen.seed;
      statusMessage.value = `Copied seed: ${gen.seed}`;
      statusClass.value = "success";
    };

    const copyAllSettings = (gen) => {
      currentSeed.value = gen.seed;
      currentModel.value = gen.checkpoint;
      currentSampler.value = gen.sampler_name;
      currentSteps.value = gen.steps;
      denoise.value = gen.denoise || 0.35;

      statusMessage.value = "Copied all settings from generation";
      statusClass.value = "success";
    };

    const generateConsistent = async () => {
      if (generating.value) return;

      generating.value = true;
      statusMessage.value = "Generating consistent character...";
      statusClass.value = "info";

      try {
        const requestData = {
          reference_image: selectedReference.value,
          prompt: prompt.value,
          denoise: denoise.value,
          character_name: selectedGeneration.value?.character_name,
        };

        // If we have a selected generation, use its settings
        if (selectedGeneration.value) {
          requestData.use_settings_from = selectedGeneration.value.job_id;
        }

        const response = await axios.post(
          `${API_BASE}/character/generate-consistent`,
          requestData,
        );

        const jobId = response.data.job_id;

        // Poll for completion
        const checkStatus = async () => {
          const statusResponse = await axios.get(
            `${API_BASE}/character/job/${jobId}`,
          );

          if (statusResponse.data.status === "completed") {
            results.value.push({
              url: statusResponse.data.output,
              prompt: prompt.value,
              jobId: jobId,
            });
            statusMessage.value = "Generation complete!";
            statusClass.value = "success";
            generating.value = false;
          } else {
            // Check again in 2 seconds
            setTimeout(checkStatus, 2000);
          }
        };

        setTimeout(checkStatus, 2000);
      } catch (error) {
        statusMessage.value = `Generation failed: ${error.message}`;
        statusClass.value = "error";
        generating.value = false;
      }
    };

    onMounted(() => {
      loadReferences();
      loadReference();
      loadGallery();
    });

    return {
      selectedReference,
      referencePreview,
      references,
      prompt,
      denoise,
      generating,
      results,
      statusMessage,
      statusClass,
      gallery,
      selectedGeneration,
      currentSeed,
      currentModel,
      currentSampler,
      currentSteps,
      loadReference,
      uploadReference,
      generateConsistent,
      loadGallery,
      getImageUrl,
      selectGeneration,
      useAsReference,
      copySeed,
      copyAllSettings,
    };
  },
};
</script>

<style scoped>
.character-studio-working {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.reference-section,
.generation-section,
.results-section {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.reference-controls {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.reference-preview {
  max-width: 300px;
  border-radius: 4px;
}

.control-group {
  margin-bottom: 15px;
}

.control-group label {
  display: block;
  margin-bottom: 5px;
  color: #888;
}

.control-group input {
  width: 100%;
  padding: 8px;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  color: white;
}

.fixed-settings {
  background: #2a2a2a;
  padding: 10px;
  border-radius: 4px;
  margin: 15px 0;
}

.fixed-settings h4 {
  margin: 0 0 10px 0;
  color: #ff9800;
}

.fixed-settings ul {
  margin: 0;
  padding-left: 20px;
  color: #888;
}

.generate-btn {
  width: 100%;
  padding: 12px;
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 16px;
  cursor: pointer;
}

.generate-btn:disabled {
  background: #666;
  cursor: not-allowed;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
}

.result-item img {
  width: 100%;
  border-radius: 4px;
}

.result-item p {
  margin: 5px 0 0 0;
  font-size: 12px;
  color: #888;
}

.status-message {
  padding: 10px;
  border-radius: 4px;
  margin-top: 20px;
}

.status-message.info {
  background: #2196f3;
  color: white;
}

.status-message.success {
  background: #4caf50;
  color: white;
}

.status-message.error {
  background: #f44336;
  color: white;
}

.gallery-section {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
  margin-top: 15px;
}

.gallery-item {
  background: #2a2a2a;
  border-radius: 4px;
  padding: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.gallery-item:hover {
  background: #3a3a3a;
}

.gallery-item.selected {
  border: 2px solid #4caf50;
}

.gallery-item img {
  width: 100%;
  border-radius: 4px;
  margin-bottom: 10px;
}

.metadata {
  font-size: 12px;
  color: #888;
}

.settings-preview {
  margin: 5px 0;
  font-family: monospace;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 10px;
}

.action-btn {
  padding: 4px 8px;
  background: #333;
  color: white;
  border: none;
  border-radius: 3px;
  font-size: 11px;
  cursor: pointer;
}

.action-btn:hover {
  background: #444;
}

.refresh-btn {
  padding: 8px 16px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.current-settings {
  background: #2a2a2a;
  border: 2px solid #4caf50;
  border-radius: 4px;
  padding: 15px;
  margin-bottom: 20px;
}

.current-settings h4 {
  margin-top: 0;
  color: #4caf50;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 10px;
}

.settings-grid div {
  font-size: 12px;
  color: #ddd;
}

.settings-grid strong {
  color: #888;
  margin-right: 5px;
}
</style>
