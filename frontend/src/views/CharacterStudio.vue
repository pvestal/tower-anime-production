<template>
  <div class="character-studio">
    <!-- Header with tabs -->
    <div class="studio-header">
      <h1>🎬 Character Studio & Director Controls</h1>
      <div class="studio-tabs">
        <button
          :class="['tab', { active: activeTab === 'character' }]"
          @click="activeTab = 'character'"
        >
          👤 Character
        </button>
        <button
          :class="['tab', { active: activeTab === 'training' }]"
          @click="activeTab = 'training'"
        >
          🎯 LoRA Training
        </button>
        <button
          :class="['tab', { active: activeTab === 'generation' }]"
          @click="activeTab = 'generation'"
        >
          🎨 Generation
        </button>
        <button
          :class="['tab', { active: activeTab === 'consistency' }]"
          @click="activeTab = 'consistency'"
        >
          🔒 Consistency
        </button>
        <button
          :class="['tab', { active: activeTab === 'video' }]"
          @click="activeTab = 'video'"
        >
          🎥 Video
        </button>
      </div>
    </div>

    <!-- Character Selection -->
    <div class="character-selector">
      <select v-model="selectedCharacter" @change="loadCharacter">
        <option value="">Select Character</option>
        <option value="kai_nakamura">Kai Nakamura</option>
        <option value="rina_suzuki">Rina Suzuki</option>
      </select>
      <button class="btn btn-primary" @click="createNewCharacter">
        ➕ New Character
      </button>
    </div>

    <!-- Tab Content -->
    <div class="studio-content">
      <!-- Character Tab -->
      <div v-if="activeTab === 'character'" class="tab-content">
        <div class="character-details">
          <h2>Character Details</h2>
          <div class="detail-grid">
            <div class="detail-group">
              <label>Name</label>
              <input v-model="character.name" type="text" />
            </div>
            <div class="detail-group">
              <label>Project</label>
              <input v-model="character.project" type="text" />
            </div>
            <div class="detail-group">
              <label>Token</label>
              <input
                v-model="character.token"
                type="text"
                placeholder="e.g., kainakamura"
              />
            </div>
            <div class="detail-group">
              <label>Style</label>
              <select v-model="character.style">
                <option value="anime">Anime</option>
                <option value="realistic">Realistic</option>
                <option value="semi-realistic">Semi-Realistic</option>
                <option value="cyberpunk">Cyberpunk</option>
              </select>
            </div>
          </div>

          <div class="prompt-section">
            <label>Base Prompt</label>
            <textarea
              v-model="character.basePrompt"
              rows="4"
              placeholder="Detailed character description..."
            ></textarea>
          </div>

          <div class="reference-images">
            <h3>Reference Images</h3>
            <div class="image-grid">
              <div
                v-for="(img, idx) in character.referenceImages"
                :key="idx"
                class="ref-image"
              >
                <img :src="img" :alt="`Reference ${idx + 1}`" />
                <button class="remove-btn" @click="removeImage(idx)">✖</button>
              </div>
              <div class="add-image" @click="$refs.imageUpload.click()">
                <span>➕ Add Image</span>
                <input
                  ref="imageUpload"
                  type="file"
                  accept="image/*"
                  multiple
                  style="display: none"
                  @change="uploadImages"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- LoRA Training Tab -->
      <div v-if="activeTab === 'training'" class="tab-content">
        <div class="lora-training">
          <h2>LoRA Training Control</h2>

          <div class="training-status">
            <div v-if="!trainingStatus.trained" class="status-alert warning">
              ⚠️ No LoRA trained for this character
            </div>
            <div v-else class="status-alert success">
              ✅ LoRA Model Ready: {{ trainingStatus.loraPath }}
            </div>
          </div>

          <div class="training-config">
            <h3>Training Configuration</h3>
            <div class="config-grid">
              <div class="config-group">
                <label>Epochs</label>
                <input
                  v-model.number="trainingConfig.epochs"
                  type="number"
                  min="1"
                  max="100"
                />
              </div>
              <div class="config-group">
                <label>Learning Rate</label>
                <input
                  v-model.number="trainingConfig.learningRate"
                  type="number"
                  step="0.0001"
                />
              </div>
              <div class="config-group">
                <label>Network Rank</label>
                <input
                  v-model.number="trainingConfig.networkRank"
                  type="number"
                  min="1"
                  max="128"
                />
              </div>
              <div class="config-group">
                <label>Network Alpha</label>
                <input
                  v-model.number="trainingConfig.networkAlpha"
                  type="number"
                  min="1"
                  max="128"
                />
              </div>
            </div>

            <div class="training-dataset">
              <h3>Dataset ({{ datasetImages.length }} images)</h3>
              <div class="dataset-grid">
                <img
                  v-for="(img, idx) in datasetImages"
                  :key="idx"
                  :src="img"
                  class="dataset-thumb"
                />
              </div>
            </div>

            <div class="training-actions">
              <button
                class="btn btn-primary"
                :disabled="isTraining || datasetImages.length < 5"
                @click="startTraining"
              >
                {{ isTraining ? "🔄 Training..." : "🚀 Start Training" }}
              </button>
              <button class="btn" @click="prepareDataset">
                📁 Prepare Dataset
              </button>
            </div>

            <div v-if="isTraining" class="training-progress">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="`width: ${trainingProgress}%`"
                ></div>
              </div>
              <div class="training-log">
                <pre>{{ trainingLog }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Generation Tab -->
      <div v-if="activeTab === 'generation'" class="tab-content">
        <div class="generation-controls">
          <h2>Scene Generation Director</h2>

          <div class="generation-grid">
            <!-- Prompt Controls -->
            <div class="prompt-controls">
              <h3>Prompts</h3>
              <div class="prompt-group">
                <label>Positive Prompt</label>
                <textarea
                  v-model="generation.positivePrompt"
                  rows="4"
                  :placeholder="`${character.basePrompt}, dynamic action pose`"
                ></textarea>
              </div>
              <div class="prompt-group">
                <label>Negative Prompt</label>
                <textarea
                  v-model="generation.negativePrompt"
                  rows="3"
                  placeholder="bad quality, deformed, different person"
                ></textarea>
              </div>
            </div>

            <!-- Generation Settings -->
            <div class="generation-settings">
              <h3>Settings</h3>
              <div class="settings-grid">
                <div class="setting">
                  <label>Seed</label>
                  <div class="seed-control">
                    <input v-model.number="generation.seed" type="number" />
                    <button @click="randomSeed">🎲</button>
                    <button @click="fixSeed">🔒</button>
                  </div>
                </div>
                <div class="setting">
                  <label>Steps</label>
                  <input
                    v-model.number="generation.steps"
                    type="range"
                    min="10"
                    max="50"
                  />
                  <span>{{ generation.steps }}</span>
                </div>
                <div class="setting">
                  <label>CFG Scale</label>
                  <input
                    v-model.number="generation.cfg"
                    type="range"
                    min="1"
                    max="20"
                    step="0.5"
                  />
                  <span>{{ generation.cfg }}</span>
                </div>
                <div class="setting">
                  <label>Batch Size</label>
                  <input
                    v-model.number="generation.batchSize"
                    type="number"
                    min="1"
                    max="16"
                  />
                </div>
              </div>

              <div class="model-selection">
                <label>Checkpoint</label>
                <select v-model="generation.checkpoint">
                  <option value="AOM3A1B.safetensors">AOM3A1B (Anime)</option>
                  <option value="realisticVision_v51.safetensors">
                    Realistic Vision
                  </option>
                  <option value="counterfeit_v3.safetensors">
                    Counterfeit V3
                  </option>
                </select>
              </div>
            </div>
          </div>

          <!-- Live Preview -->
          <div class="live-preview-section">
            <h3>Live Preview</h3>
            <div class="preview-container">
              <div v-if="!currentPreview" class="preview-placeholder">
                Click "Generate Preview" to see results
              </div>
              <img v-else :src="currentPreview" alt="Preview" />
            </div>

            <div class="preview-actions">
              <button class="btn btn-primary" @click="generatePreview">
                🔄 Generate Preview
              </button>
              <button class="btn btn-success" @click="generateBatch">
                🎬 Generate Batch
              </button>
            </div>

            <div v-if="generationProgress" class="generation-status">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="`width: ${generationProgress}%`"
                ></div>
              </div>
              <span>{{ generationStatus }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Consistency Tab -->
      <div v-if="activeTab === 'consistency'" class="tab-content">
        <div class="consistency-controls">
          <h2>Character Consistency Settings</h2>

          <div class="consistency-methods">
            <h3>Active Methods</h3>
            <div class="method-toggles">
              <label class="toggle-item">
                <input v-model="consistency.useLoRA" type="checkbox" />
                <span
                  >LoRA ({{
                    trainingStatus.trained ? "Ready" : "Not Trained"
                  }})</span
                >
              </label>
              <label class="toggle-item">
                <input v-model="consistency.useFaceID" type="checkbox" />
                <span>IP-Adapter FaceID</span>
              </label>
              <label class="toggle-item">
                <input v-model="consistency.useFixedSeed" type="checkbox" />
                <span>Fixed Seed</span>
              </label>
              <label class="toggle-item">
                <input v-model="consistency.useControlNet" type="checkbox" />
                <span>ControlNet Pose</span>
              </label>
            </div>
          </div>

          <div class="strength-controls">
            <h3>Consistency Strength</h3>
            <div class="strength-sliders">
              <div v-if="consistency.useLoRA" class="slider-group">
                <label>LoRA Strength</label>
                <input
                  v-model.number="consistency.loraStrength"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                />
                <span>{{ consistency.loraStrength }}</span>
              </div>
              <div v-if="consistency.useFaceID" class="slider-group">
                <label>FaceID Strength</label>
                <input
                  v-model.number="consistency.faceIDStrength"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                />
                <span>{{ consistency.faceIDStrength }}</span>
              </div>
            </div>
          </div>

          <div class="consistency-test">
            <h3>Consistency Test</h3>
            <p>Generate multiple images to test character consistency</p>
            <button class="btn btn-primary" @click="runConsistencyTest">
              🧪 Run Test (8 images)
            </button>

            <div v-if="consistencyTestResults.length > 0" class="test-results">
              <div class="result-grid">
                <img
                  v-for="(img, idx) in consistencyTestResults"
                  :key="idx"
                  :src="img"
                  class="test-image"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Video Tab -->
      <div v-if="activeTab === 'video'" class="tab-content">
        <div class="video-controls">
          <h2>Video Generation</h2>

          <div class="video-settings">
            <h3>AnimateDiff Settings</h3>
            <div class="settings-grid">
              <div class="setting">
                <label>Duration (frames)</label>
                <input
                  v-model.number="video.frames"
                  type="range"
                  min="16"
                  max="96"
                  step="8"
                />
                <span
                  >{{ video.frames }} frames ({{
                    (video.frames / 8).toFixed(1)
                  }}s)</span
                >
              </div>
              <div class="setting">
                <label>Motion Type</label>
                <select v-model="video.motionType">
                  <option value="idle">Idle</option>
                  <option value="walk">Walking</option>
                  <option value="run">Running</option>
                  <option value="fight">Fighting</option>
                  <option value="dramatic">Dramatic</option>
                </select>
              </div>
              <div class="setting">
                <label>Motion Strength</label>
                <input
                  v-model.number="video.motionStrength"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                />
                <span>{{ video.motionStrength }}</span>
              </div>
            </div>

            <button class="btn btn-primary" @click="generateVideo">
              🎥 Generate Video
            </button>
          </div>

          <div v-if="videoProgress" class="video-status">
            <div class="progress-bar">
              <div class="progress-fill" :style="`width: ${videoProgress}%`">
                {{ videoProgress }}%
              </div>
            </div>
            <span>{{ videoStatus }}</span>
          </div>

          <div v-if="currentVideo" class="video-preview">
            <video :src="currentVideo" controls autoplay loop></video>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import axios from "axios";

// API base URL
const API_BASE = "/api";

// State
const activeTab = ref("character");
const selectedCharacter = ref("");
const isTraining = ref(false);
const trainingProgress = ref(0);
const trainingLog = ref("");
const generationProgress = ref(0);
const generationStatus = ref("");
const currentPreview = ref(null);
const datasetImages = ref([]);
const consistencyTestResults = ref([]);
const videoProgress = ref(0);
const videoStatus = ref("");
const currentVideo = ref(null);

// Character data
const character = ref({
  name: "",
  project: "",
  token: "",
  style: "anime",
  basePrompt: "",
  referenceImages: [],
});

// Training status
const trainingStatus = ref({
  trained: false,
  loraPath: "",
});

// Training config
const trainingConfig = ref({
  epochs: 10,
  learningRate: 0.0001,
  networkRank: 32,
  networkAlpha: 16,
});

// Generation settings
const generation = ref({
  positivePrompt: "",
  negativePrompt: "bad quality, deformed",
  seed: 12004,
  steps: 30,
  cfg: 7.5,
  batchSize: 4,
  checkpoint: "AOM3A1B.safetensors",
});

// Consistency settings
const consistency = ref({
  useLoRA: true,
  useFaceID: true,
  useFixedSeed: true,
  useControlNet: false,
  loraStrength: 0.8,
  faceIDStrength: 0.9,
});

// Video settings
const video = ref({
  frames: 48,
  motionType: "idle",
  motionStrength: 0.7,
});

// Methods
async function loadCharacter() {
  if (!selectedCharacter.value) return;

  try {
    const name = selectedCharacter.value.replace("_", " ");
    const response = await fetch(`${API_BASE}/character/${name}/settings`);
    const data = await response.json();

    character.value = {
      name: data.name,
      project: data.project,
      token: data.token || selectedCharacter.value.replace("_", ""),
      style: data.style || "anime",
      basePrompt: data.prompt || "",
      referenceImages: data.face_images || [],
    };

    trainingStatus.value = {
      trained: data.lora_trained || false,
      loraPath: data.lora_path || "",
    };

    // Load dataset images
    loadDatasetImages();
  } catch (error) {
    console.error("Failed to load character:", error);
  }
}

async function loadDatasetImages() {
  const charName = selectedCharacter.value.replace("_", " ");
  const charDir = charName.replace(" ", "_");

  // Mock dataset images for now
  datasetImages.value = [
    `/mnt/1TB-storage/character_datasets/${charDir}/image_001.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_002.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_003.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_004.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_005.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_006.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_007.png`,
    `/mnt/1TB-storage/character_datasets/${charDir}/image_008.png`,
  ];
}

async function uploadImages(event) {
  const files = event.target.files;
  if (!files.length) return;

  const formData = new FormData();
  formData.append("character_id", selectedCharacter.value);

  for (let file of files) {
    formData.append("images", file);
  }

  try {
    const response = await fetch(`${API_BASE}/character/upload-images`, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (data.success) {
      character.value.referenceImages.push(...data.images);
      loadDatasetImages();
    }
  } catch (error) {
    console.error("Failed to upload images:", error);
  }
}

async function startTraining() {
  if (datasetImages.value.length < 5) {
    alert("Need at least 5 images for training");
    return;
  }

  isTraining.value = true;
  trainingProgress.value = 0;
  trainingLog.value = "Starting LoRA training...\n";

  // Simulate training progress
  const interval = setInterval(() => {
    trainingProgress.value += 10;
    trainingLog.value += `Epoch ${Math.floor(trainingProgress.value / 10)}/10 - Loss: ${(Math.random() * 0.1 + 0.01).toFixed(4)}\n`;

    if (trainingProgress.value >= 100) {
      clearInterval(interval);
      isTraining.value = false;
      trainingStatus.value.trained = true;
      trainingStatus.value.loraPath = `/mnt/1TB-storage/ComfyUI/models/loras/${selectedCharacter.value}.safetensors`;
      alert("LoRA training complete!");
    }
  }, 2000);
}

async function generatePreview() {
  generationProgress.value = 10;
  generationStatus.value = "Preparing workflow...";

  const workflow = buildWorkflow();

  // Simulate generation
  const interval = setInterval(() => {
    generationProgress.value += 20;
    generationStatus.value = `Generating... ${generationProgress.value}%`;

    if (generationProgress.value >= 100) {
      clearInterval(interval);
      currentPreview.value = `/mnt/1TB-storage/ComfyUI/output/preview_${Date.now()}.png`;
      generationStatus.value = "Complete!";
    }
  }, 1000);
}

async function generateBatch() {
  const workflow = buildWorkflow();
  workflow.batch_size = generation.value.batchSize;

  alert(
    `Batch generation started: ${generation.value.batchSize} images queued`,
  );
}

async function generateVideo() {
  videoProgress.value = 0;
  videoStatus.value = "Initializing video generation...";

  const interval = setInterval(() => {
    videoProgress.value += 5;
    videoStatus.value = `Generating frame ${Math.floor((videoProgress.value * video.value.frames) / 100)} of ${video.value.frames}`;

    if (videoProgress.value >= 100) {
      clearInterval(interval);
      currentVideo.value = `/mnt/1TB-storage/ComfyUI/output/video_${Date.now()}.mp4`;
      videoStatus.value = "Video complete!";
    }
  }, 500);
}

function buildWorkflow() {
  const workflow = {
    positive_prompt:
      generation.value.positivePrompt || character.value.basePrompt,
    negative_prompt: generation.value.negativePrompt,
    seed: generation.value.seed,
    steps: generation.value.steps,
    cfg_scale: generation.value.cfg,
    checkpoint: generation.value.checkpoint,
  };

  // Add consistency methods
  if (consistency.value.useLoRA && trainingStatus.value.trained) {
    workflow.lora = {
      path: trainingStatus.value.loraPath,
      strength: consistency.value.loraStrength,
    };
  }

  if (consistency.value.useFaceID) {
    workflow.faceid = {
      enabled: true,
      strength: consistency.value.faceIDStrength,
      reference: character.value.referenceImages[0],
    };
  }

  if (consistency.value.useFixedSeed) {
    workflow.fixed_seed = true;
  }

  return workflow;
}

async function runConsistencyTest() {
  consistencyTestResults.value = [];

  // Simulate generating 8 test images
  for (let i = 0; i < 8; i++) {
    consistencyTestResults.value.push(
      `/mnt/1TB-storage/ComfyUI/output/test_${i}.png`,
    );
  }
}

function randomSeed() {
  generation.value.seed = Math.floor(Math.random() * 1000000);
}

function fixSeed() {
  consistency.value.useFixedSeed = true;
}

function removeImage(index) {
  character.value.referenceImages.splice(index, 1);
}

function createNewCharacter() {
  selectedCharacter.value = "";
  character.value = {
    name: "",
    project: "",
    token: "",
    style: "anime",
    basePrompt: "",
    referenceImages: [],
  };
  activeTab.value = "character";
}

function prepareDataset() {
  alert("Dataset preparation tool coming soon");
}

// Load initial data
onMounted(async () => {
  // Load available characters from API
  try {
    const response = await axios.get(`${API_BASE}/anime/characters`);
    if (response.data.characters && response.data.characters.length > 0) {
      // Add all characters to the list, including Zara if she exists
      response.data.characters.forEach((char) => {
        if (!characters.value.find((c) => c.name === char.name)) {
          characters.value.push({
            name: char.name,
            project: char.project || "Default",
          });
        }
      });
    }
  } catch (error) {
    console.error("Failed to load characters:", error);
  }

  // Also check for Zara specifically via the test endpoint
  try {
    const zaraResponse = await axios.get(`${API_BASE}/anime/zara/profile`);
    if (zaraResponse.data && !characters.value.find((c) => c.name === "Zara")) {
      characters.value.push({
        name: "Zara",
        project: "Test Project",
      });
    }
  } catch (error) {
    // Zara test endpoint might not be available yet
    console.log("Zara test profile not available");
  }

  if (selectedCharacter.value) {
    loadCharacter();
  }
});
</script>

<style scoped>
/* Copy all the styles from the component version */
.character-studio {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.studio-header {
  background: white;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.studio-header h1 {
  margin: 0 0 20px 0;
  color: #1a1a1a;
}

.studio-tabs {
  display: flex;
  gap: 8px;
}

.tab {
  padding: 10px 20px;
  border: 1px solid #ddd;
  background: #f5f5f5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab:hover {
  background: #e0e0e0;
}

.tab.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.character-selector {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  display: flex;
  gap: 16px;
  align-items: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.character-selector select {
  flex: 1;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 16px;
}

.studio-content {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.tab-content {
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

/* Include all other styles from component */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.btn {
  padding: 10px 20px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #f5f5f5;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.btn-success {
  background: #10b981;
  color: white;
  border-color: #10b981;
}

.progress-bar {
  height: 24px;
  background: #e9ecef;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 16px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #10b981);
  transition: width 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 600;
}
</style>
