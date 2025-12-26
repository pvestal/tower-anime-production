<template>
  <div class="video-project-container">
    <!-- Header -->
    <div class="project-header">
      <h1 class="project-title">
        <span class="icon">🎬</span>
        Video Project Studio
      </h1>
      <p class="subtitle">
        Create narrative-driven videos from your character library
      </p>
    </div>

    <!-- Main Content Grid -->
    <div class="project-grid">
      <!-- Left Panel: Character Selection -->
      <div class="character-panel">
        <h2>Character Selection</h2>
        <div class="character-gallery">
          <div
            v-for="character in availableCharacters"
            :key="character.id"
            class="character-card"
            :class="{ selected: selectedCharacter?.id === character.id }"
            @click="selectCharacter(character)"
          >
            <img
              v-if="character.thumbnail"
              :src="character.thumbnail"
              :alt="character.name"
              class="character-thumbnail"
            />
            <div v-else class="character-placeholder">
              {{ character.name.charAt(0) }}
            </div>
            <p class="character-name">{{ character.name }}</p>
          </div>
        </div>

        <!-- Character Controls -->
        <div v-if="selectedCharacter" class="character-controls">
          <h3>{{ selectedCharacter.name }}</h3>
          <div class="control-group">
            <label>IP-Adapter Strength</label>
            <input
              v-model.number="characterSettings.ip_adapter_strength"
              type="range"
              min="0"
              max="1"
              step="0.05"
            />
            <span>{{ characterSettings.ip_adapter_strength }}</span>
          </div>
          <div class="control-group">
            <label>ControlNet Strength</label>
            <input
              v-model.number="characterSettings.controlnet_strength"
              type="range"
              min="0"
              max="1"
              step="0.05"
            />
            <span>{{ characterSettings.controlnet_strength }}</span>
          </div>
        </div>
      </div>

      <!-- Center Panel: Scene Timeline -->
      <div class="timeline-panel">
        <h2>Scene Timeline</h2>

        <!-- Scene List -->
        <div class="scenes-container">
          <draggable
            v-model="scenes"
            group="scenes"
            item-key="id"
            class="scene-list"
            :animation="200"
          >
            <template #item="{ element: scene, index }">
              <div
                class="scene-card"
                :class="{ active: activeSceneIndex === index }"
              >
                <div class="scene-header">
                  <span class="scene-number">Scene {{ index + 1 }}</span>
                  <button class="btn-remove" @click="removeScene(index)">
                    ×
                  </button>
                </div>

                <div class="scene-content">
                  <div class="input-group">
                    <label>Location</label>
                    <input
                      v-model="scene.location_prompt"
                      placeholder="e.g., magical forest clearing"
                      @focus="activeSceneIndex = index"
                    />
                  </div>

                  <div class="input-group">
                    <label>Action</label>
                    <input
                      v-model="scene.action_prompt"
                      placeholder="e.g., practicing spell casting"
                      @focus="activeSceneIndex = index"
                    />
                  </div>

                  <div class="input-group">
                    <label>Emotion</label>
                    <input
                      v-model="scene.emotion_prompt"
                      placeholder="e.g., determined, focused"
                      @focus="activeSceneIndex = index"
                    />
                  </div>

                  <div class="input-group">
                    <label>Outfit Override (optional)</label>
                    <input
                      v-model="scene.outfit_override"
                      placeholder="e.g., blue mage robes"
                      @focus="activeSceneIndex = index"
                    />
                  </div>

                  <!-- Transition Settings -->
                  <div v-if="index > 0" class="transition-settings">
                    <label>Transition</label>
                    <select v-model="scene.transition_type">
                      <option value="blend">Blend</option>
                      <option value="fade">Fade</option>
                      <option value="cut">Cut</option>
                    </select>
                    <input
                      v-model.number="scene.transition_duration_frames"
                      type="number"
                      min="5"
                      max="30"
                      placeholder="Frames"
                    />
                  </div>
                </div>
              </div>
            </template>
          </draggable>

          <!-- Add Scene Button -->
          <button class="btn-add-scene" @click="addScene">
            <span class="icon">+</span> Add Scene
          </button>
        </div>
      </div>

      <!-- Right Panel: Settings & Generation -->
      <div class="settings-panel">
        <h2>Video Settings</h2>

        <!-- Project Name -->
        <div class="input-group">
          <label>Sequence Name</label>
          <input v-model="sequenceName" placeholder="e.g., Aria's Journey" />
        </div>

        <!-- Resolution -->
        <div class="input-group">
          <label>Resolution</label>
          <select v-model="videoSettings.resolution">
            <option value="512x768">512×768 (Portrait)</option>
            <option value="768x1024">768×1024 (Portrait HD)</option>
            <option value="768x512">768×512 (Landscape)</option>
            <option value="1024x768">1024×768 (Landscape HD)</option>
          </select>
        </div>

        <!-- FPS -->
        <div class="input-group">
          <label>Frame Rate</label>
          <select v-model.number="videoSettings.fps">
            <option :value="12">12 FPS (Animated)</option>
            <option :value="24">24 FPS (Cinema)</option>
            <option :value="30">30 FPS (Smooth)</option>
          </select>
        </div>

        <!-- Model Selection -->
        <div class="input-group">
          <label>Base Model</label>
          <select v-model="videoSettings.base_model">
            <option value="dreamshaper_8.safetensors">DreamShaper v8</option>
            <option value="animagine-xl-3.0.safetensors">
              Animagine XL 3.0
            </option>
            <option value="AOM3A1B.safetensors">AOM3A1B (Anime)</option>
            <option value="chilloutmix.safetensors">ChilloutMix</option>
          </select>
        </div>

        <!-- Generate Button -->
        <button
          :disabled="!canGenerate || isGenerating"
          class="btn-generate"
          @click="generateVideo"
        >
          <span v-if="!isGenerating">🎬 Generate Video</span>
          <span v-else>⏳ Generating...</span>
        </button>

        <!-- Progress Display -->
        <div v-if="currentJob" class="progress-container">
          <h3>Generation Progress</h3>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: `${currentJob.progress}%` }"
            ></div>
          </div>
          <p class="progress-text">
            {{ currentJob.status }} - {{ currentJob.progress }}%
          </p>
          <p v-if="currentJob.current_scene" class="progress-detail">
            Processing scene {{ currentJob.current_scene }} of
            {{ scenes.length }}
          </p>
        </div>

        <!-- Recent Videos -->
        <div v-if="recentVideos.length > 0" class="recent-videos">
          <h3>Recent Videos</h3>
          <div v-for="video in recentVideos" :key="video.id" class="video-item">
            <span class="video-name">{{ video.sequence_name }}</span>
            <span class="video-status" :class="video.status">{{
              video.status
            }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { VueDraggableNext as draggable } from "vue-draggable-next";
import axios from "axios";
import { useCharacterStore } from "@/stores/characterStore";
import { useToast } from "@/composables/useToast";

// Store and composables
const characterStore = useCharacterStore();
const { showToast } = useToast();

// State
const availableCharacters = ref([]);
const selectedCharacter = ref(null);
const scenes = ref([]);
const activeSceneIndex = ref(0);
const sequenceName = ref("");
const isGenerating = ref(false);
const currentJob = ref(null);
const recentVideos = ref([]);
const pollInterval = ref(null);

// Character settings
const characterSettings = ref({
  ip_adapter_strength: 0.8,
  controlnet_strength: 0.7,
});

// Video settings
const videoSettings = ref({
  resolution: "768x1024",
  fps: 24,
  base_model: "dreamshaper_8.safetensors",
});

// Computed
const canGenerate = computed(() => {
  return (
    scenes.value.length > 0 &&
    sequenceName.value.trim() !== "" &&
    scenes.value.every(
      (s) => s.location_prompt && s.action_prompt && s.emotion_prompt,
    )
  );
});

// Methods
const selectCharacter = (character) => {
  selectedCharacter.value = character;
};

const addScene = () => {
  const newScene = {
    id: Date.now(),
    scene_order: scenes.value.length + 1,
    location_prompt: "",
    action_prompt: "",
    emotion_prompt: "",
    outfit_override: "",
    transition_type: "blend",
    transition_duration_frames: 10,
  };
  scenes.value.push(newScene);
  activeSceneIndex.value = scenes.value.length - 1;
};

const removeScene = (index) => {
  scenes.value.splice(index, 1);
  // Update scene orders
  scenes.value.forEach((scene, idx) => {
    scene.scene_order = idx + 1;
  });
};

const saveProjectAsStory = async () => {
  // Save current project as a story
  try {
    const storyData = {
      title: `Video Project ${Date.now()}`,
      project_id: characterStore.currentProjectId || "video_project_001",
      synopsis: "Multi-scene video project",
    };

    const response = await axios.post("/api/anime/stories", storyData);
    currentStoryId.value = response.data.id;

    // Save scenes to story
    for (let i = 0; i < scenes.value.length; i++) {
      const scene = scenes.value[i];
      const sceneData = {
        scene_number: i + 1,
        scene_type: "action",
        title: `Scene ${i + 1}`,
        description: scene.action_prompt,
        location: scene.location_prompt,
        prompt: buildPromptForScene(scene),
        generation_type: "video",
        episode_number: 1,
      };

      await axios.post(
        `/api/anime/stories/${currentStoryId.value}/scenes`,
        sceneData,
      );
    }
  } catch (error) {
    console.error("Failed to save as story:", error);
  }
};

const currentStoryId = ref(null);

const generateVideo = async () => {
  if (!canGenerate.value) return;

  isGenerating.value = true;
  currentJob.value = { status: "preparing", progress: 0 };

  try {
    // Prepare request
    const request = {
      project_id: characterStore.currentProjectId || 1,
      sequence_name: sequenceName.value,
      scenes: scenes.value.map((scene, index) => ({
        scene_order: index + 1,
        location_prompt: scene.location_prompt,
        action_prompt: scene.action_prompt,
        emotion_prompt: scene.emotion_prompt,
        outfit_override: scene.outfit_override || null,
        transition_type: scene.transition_type || "blend",
        transition_duration_frames: scene.transition_duration_frames || 10,
      })),
      character_refs: selectedCharacter.value
        ? [
            {
              character_id: selectedCharacter.value.id,
              ip_adapter_strength: characterSettings.value.ip_adapter_strength,
              controlnet_strength: characterSettings.value.controlnet_strength,
            },
          ]
        : [],
      resolution: videoSettings.value.resolution,
      fps: videoSettings.value.fps,
      base_model: videoSettings.value.base_model,
    };

    // Submit to API
    const response = await axios.post("/api/anime/video/generate", request);

    if (response.data.job_id) {
      currentJob.value = {
        job_id: response.data.job_id,
        status: response.data.status,
        progress: 0,
      };

      showToast("Video generation started!", "success");

      // Start polling for progress
      startProgressPolling(response.data.job_id);
    }
  } catch (error) {
    console.error("Generation failed:", error);
    showToast("Failed to start video generation", "error");
    isGenerating.value = false;
    currentJob.value = null;
  }
};

const startProgressPolling = (jobId) => {
  pollInterval.value = setInterval(async () => {
    try {
      const response = await axios.get(`/api/anime/video/status/${jobId}`);

      currentJob.value = {
        ...currentJob.value,
        ...response.data,
      };

      if (response.data.status === "completed") {
        showToast("Video generation completed!", "success");
        stopPolling();
        loadRecentVideos();
      } else if (response.data.status === "failed") {
        showToast(
          "Video generation failed: " + response.data.error_message,
          "error",
        );
        stopPolling();
      }
    } catch (error) {
      console.error("Failed to check status:", error);
    }
  }, 5000); // Poll every 5 seconds
};

const stopPolling = () => {
  if (pollInterval.value) {
    clearInterval(pollInterval.value);
    pollInterval.value = null;
  }
  isGenerating.value = false;
};

const loadCharacters = async () => {
  try {
    const response = await axios.get("/api/anime/characters");
    availableCharacters.value = response.data.characters || [];
  } catch (error) {
    console.error("Failed to load characters:", error);
    // Use mock data for demo
    availableCharacters.value = [
      { id: 1, name: "Aria Moonwhisper", thumbnail: null },
      { id: 2, name: "Kai Shadowblade", thumbnail: null },
    ];
  }
};

const loadRecentVideos = async () => {
  try {
    const projectId = characterStore.currentProjectId || 1;
    const response = await axios.get(`/api/anime/video/sequences/${projectId}`);
    recentVideos.value = response.data.sequences || [];
  } catch (error) {
    console.error("Failed to load recent videos:", error);
  }
};

// Lifecycle
onMounted(() => {
  loadCharacters();
  loadRecentVideos();
  // Add first scene by default
  addScene();
});
</script>

<style scoped>
.video-project-container {
  padding: 20px;
  max-width: 1600px;
  margin: 0 auto;
}

.project-header {
  text-align: center;
  margin-bottom: 30px;
}

.project-title {
  font-size: 2.5em;
  margin: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  color: #666;
  margin-top: 10px;
}

.project-grid {
  display: grid;
  grid-template-columns: 300px 1fr 350px;
  gap: 20px;
}

/* Character Panel */
.character-panel {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.character-gallery {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-top: 15px;
}

.character-card {
  cursor: pointer;
  text-align: center;
  padding: 10px;
  border: 2px solid transparent;
  border-radius: 8px;
  transition: all 0.3s;
}

.character-card:hover {
  background: #f0f0f0;
}

.character-card.selected {
  border-color: #667eea;
  background: #f0f4ff;
}

.character-thumbnail {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
}

.character-placeholder {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2em;
  margin: 0 auto;
}

.character-name {
  margin-top: 5px;
  font-size: 0.9em;
}

.character-controls {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
}

.control-group label {
  flex: 1;
  font-size: 0.9em;
}

.control-group input[type="range"] {
  flex: 2;
}

.control-group span {
  width: 40px;
  text-align: center;
  font-size: 0.9em;
  color: #667eea;
}

/* Timeline Panel */
.timeline-panel {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.scenes-container {
  margin-top: 15px;
  max-height: calc(100vh - 250px);
  overflow-y: auto;
}

.scene-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.scene-card {
  background: #f8f9fa;
  border: 2px solid transparent;
  border-radius: 10px;
  padding: 15px;
  transition: all 0.3s;
}

.scene-card.active {
  border-color: #667eea;
  background: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
}

.scene-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.scene-number {
  font-weight: bold;
  color: #667eea;
}

.btn-remove {
  background: none;
  border: none;
  color: #999;
  font-size: 1.5em;
  cursor: pointer;
  padding: 0;
  width: 25px;
  height: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.3s;
}

.btn-remove:hover {
  background: #ff4444;
  color: white;
}

.scene-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.input-group label {
  font-size: 0.85em;
  color: #666;
  font-weight: 500;
}

.input-group input,
.input-group select {
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 5px;
  font-size: 0.95em;
}

.input-group input:focus,
.input-group select:focus {
  outline: none;
  border-color: #667eea;
}

.transition-settings {
  display: flex;
  gap: 10px;
  align-items: center;
  padding-top: 10px;
  border-top: 1px dashed #ddd;
}

.transition-settings label {
  font-size: 0.85em;
  color: #666;
}

.transition-settings select {
  flex: 1;
  padding: 5px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.transition-settings input[type="number"] {
  width: 80px;
  padding: 5px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.btn-add-scene {
  width: 100%;
  padding: 15px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 1em;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 15px;
  transition: all 0.3s;
}

.btn-add-scene:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.btn-add-scene .icon {
  font-size: 1.5em;
}

/* Settings Panel */
.settings-panel {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.btn-generate {
  width: 100%;
  padding: 15px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 1.1em;
  font-weight: bold;
  cursor: pointer;
  margin-top: 20px;
  transition: all 0.3s;
}

.btn-generate:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.btn-generate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.progress-container {
  margin-top: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 10px;
}

.progress-bar {
  width: 100%;
  height: 20px;
  background: #e0e0e0;
  border-radius: 10px;
  overflow: hidden;
  margin: 10px 0;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  transition: width 0.3s;
}

.progress-text {
  text-align: center;
  margin: 10px 0 5px;
  font-weight: 500;
}

.progress-detail {
  text-align: center;
  font-size: 0.9em;
  color: #666;
}

.recent-videos {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

.recent-videos h3 {
  margin-bottom: 15px;
}

.video-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  background: #f8f9fa;
  border-radius: 5px;
  margin-bottom: 10px;
}

.video-name {
  font-size: 0.9em;
  font-weight: 500;
}

.video-status {
  font-size: 0.85em;
  padding: 3px 8px;
  border-radius: 3px;
  font-weight: 500;
}

.video-status.completed {
  background: #d4edda;
  color: #155724;
}

.video-status.processing {
  background: #fff3cd;
  color: #856404;
}

.video-status.failed {
  background: #f8d7da;
  color: #721c24;
}

/* Responsive */
@media (max-width: 1400px) {
  .project-grid {
    grid-template-columns: 1fr;
    max-width: 900px;
    margin: 0 auto;
  }

  .character-panel,
  .settings-panel {
    max-width: 100%;
  }
}
</style>
