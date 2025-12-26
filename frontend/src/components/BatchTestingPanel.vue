<template>
  <div class="batch-testing-panel">
    <div class="panel-header">
      <h3>Batch Testing & Optimization</h3>
      <button class="btn-icon" @click="refreshStats">
        <i class="pi pi-refresh"></i>
      </button>
    </div>

    <!-- Quick Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ stats.totalGenerations || 0 }}</div>
        <div class="stat-label">Total Generations</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.successRate || "0%" }}</div>
        <div class="stat-label">Success Rate</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.avgTime || "0s" }}</div>
        <div class="stat-label">Avg Generation Time</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.activeJobs || 0 }}</div>
        <div class="stat-label">Active Jobs</div>
      </div>
    </div>

    <!-- Character Selection -->
    <div class="section">
      <h4>Select Character</h4>
      <div class="character-selector">
        <div
          v-for="char in characters"
          :key="char.id"
          :class="[
            'character-option',
            { selected: selectedCharacter?.id === char.id },
          ]"
          @click="selectCharacter(char)"
        >
          <div class="char-avatar">
            <img
              v-if="char.thumbnail"
              :src="char.thumbnail"
              :alt="char.character_name"
            />
            <div v-else class="avatar-placeholder">
              {{ char.character_name.charAt(0) }}
            </div>
          </div>
          <div class="char-name">{{ char.character_name }}</div>
        </div>
      </div>
    </div>

    <!-- Batch Test Options -->
    <div class="section">
      <h4>Batch Test Options</h4>
      <div class="test-options">
        <!-- Quick Test -->
        <div class="test-card">
          <div class="test-header">
            <i class="pi pi-bolt"></i>
            <h5>Quick Test</h5>
          </div>
          <p>Generate 3 test images with varying seeds</p>
          <div class="test-params">
            <label>
              <span>Model:</span>
              <select v-model="quickTestParams.model">
                <option value="realisticVision_v51.safetensors">
                  Realistic Vision
                </option>
                <option value="chilloutmix_NiPrunedFp32.safetensors">
                  ChilloutMix
                </option>
                <option value="epicRealism_newEra.safetensors">
                  Epic Realism
                </option>
              </select>
            </label>
          </div>
          <button
            class="btn-action"
            :disabled="!selectedCharacter || running.quickTest"
            @click="runQuickTest"
          >
            {{ running.quickTest ? "Running..." : "Run Quick Test" }}
          </button>
        </div>

        <!-- Pose Variations -->
        <div class="test-card">
          <div class="test-header">
            <i class="pi pi-users"></i>
            <h5>Pose Variations</h5>
          </div>
          <p>Generate all standard poses (10 variations)</p>
          <div class="test-params">
            <label>
              <span>Angles:</span>
              <div class="checkbox-group">
                <label
                  ><input v-model="poseParams.angles.front" type="checkbox" />
                  Front</label
                >
                <label
                  ><input v-model="poseParams.angles.side" type="checkbox" />
                  Side</label
                >
                <label
                  ><input v-model="poseParams.angles.back" type="checkbox" />
                  Back</label
                >
                <label
                  ><input
                    v-model="poseParams.angles.threequarter"
                    type="checkbox"
                  />
                  3/4</label
                >
              </div>
            </label>
          </div>
          <button
            class="btn-action"
            :disabled="!selectedCharacter || running.poseTest"
            @click="runPoseTest"
          >
            {{ running.poseTest ? "Generating..." : "Generate Poses" }}
          </button>
        </div>

        <!-- NSFW Batch -->
        <div class="test-card nsfw">
          <div class="test-header">
            <i class="pi pi-exclamation-triangle"></i>
            <h5>NSFW Content</h5>
          </div>
          <p>Generate intimate/artistic content (5 images)</p>
          <div class="test-params">
            <label>
              <span>Style:</span>
              <select v-model="nsfwParams.style">
                <option value="intimate">Intimate</option>
                <option value="artistic">Artistic Nude</option>
                <option value="lingerie">Lingerie</option>
                <option value="swimwear">Swimwear</option>
              </select>
            </label>
            <label>
              <span>Clothing:</span>
              <select v-model="nsfwParams.clothing">
                <option value="minimal">Minimal</option>
                <option value="revealing">Revealing</option>
                <option value="suggestive">Suggestive</option>
                <option value="none">None</option>
              </select>
            </label>
          </div>
          <button
            class="btn-action nsfw"
            :disabled="!selectedCharacter || running.nsfwBatch"
            @click="runNSFWBatch"
          >
            {{ running.nsfwBatch ? "Generating..." : "Generate NSFW" }}
          </button>
        </div>

        <!-- Mass Production -->
        <div class="test-card">
          <div class="test-header">
            <i class="pi pi-clone"></i>
            <h5>Mass Production</h5>
          </div>
          <p>Generate large batch with optimized settings</p>
          <div class="test-params">
            <label>
              <span>Count:</span>
              <input
                v-model="massParams.count"
                type="number"
                min="10"
                max="100"
              />
            </label>
            <label>
              <span>Quality:</span>
              <select v-model="massParams.quality">
                <option value="fast">Fast (20 steps)</option>
                <option value="balanced">Balanced (30 steps)</option>
                <option value="quality">Quality (50 steps)</option>
              </select>
            </label>
          </div>
          <button
            class="btn-action"
            :disabled="!selectedCharacter || running.massProduction"
            @click="runMassProduction"
          >
            {{ running.massProduction ? "Producing..." : "Start Production" }}
          </button>
        </div>

        <!-- Parameter Optimization -->
        <div class="test-card">
          <div class="test-header">
            <i class="pi pi-cog"></i>
            <h5>Parameter Optimization</h5>
          </div>
          <p>Test different parameter combinations</p>
          <div class="test-params">
            <label>
              <span>Test Type:</span>
              <select v-model="optimizeParams.type">
                <option value="cfg_scale">CFG Scale (5-15)</option>
                <option value="steps">Steps (20-50)</option>
                <option value="sampler">Sampler Methods</option>
                <option value="model">Model Comparison</option>
              </select>
            </label>
          </div>
          <button
            class="btn-action"
            :disabled="!selectedCharacter || running.optimization"
            @click="runOptimization"
          >
            {{ running.optimization ? "Optimizing..." : "Run Optimization" }}
          </button>
        </div>

        <!-- SVD Animation Test -->
        <div class="test-card">
          <div class="test-header">
            <i class="pi pi-video"></i>
            <h5>SVD Animation</h5>
          </div>
          <p>Test Stable Video Diffusion with best image</p>
          <div class="test-params">
            <label>
              <span>Motion:</span>
              <select v-model="svdParams.motion_bucket">
                <option value="50">Subtle (50)</option>
                <option value="127">Medium (127)</option>
                <option value="200">Dynamic (200)</option>
              </select>
            </label>
            <label>
              <span>FPS:</span>
              <select v-model="svdParams.fps">
                <option value="6">6 FPS</option>
                <option value="12">12 FPS</option>
                <option value="24">24 FPS</option>
              </select>
            </label>
          </div>
          <button
            class="btn-action"
            :disabled="!selectedCharacter || running.svdTest"
            @click="runSVDTest"
          >
            {{ running.svdTest ? "Animating..." : "Test Animation" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Current Jobs -->
    <div v-if="activeJobs.length > 0" class="section">
      <h4>Active Jobs</h4>
      <div class="jobs-list">
        <div v-for="job in activeJobs" :key="job.id" class="job-item">
          <div class="job-info">
            <span class="job-type">{{ job.type }}</span>
            <span class="job-character">{{ job.character_name }}</span>
          </div>
          <div class="job-progress">
            <div class="progress-bar-mini">
              <div
                class="progress-fill"
                :style="{ width: job.progress + '%' }"
              ></div>
            </div>
            <span class="progress-text">{{ job.progress }}%</span>
          </div>
          <button class="btn-cancel" @click="cancelJob(job.id)">
            <i class="pi pi-times"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Optimization Results -->
    <div v-if="optimizationResults" class="section">
      <h4>Optimization Results</h4>
      <div class="optimization-results">
        <div class="result-header">
          <h5>{{ optimizationResults.type }} Test Results</h5>
          <span class="result-time">{{
            formatTime(optimizationResults.timestamp)
          }}</span>
        </div>
        <div class="result-grid">
          <div
            v-for="result in optimizationResults.results"
            :key="result.id"
            class="result-item"
          >
            <img :src="result.image" :alt="result.parameter" />
            <div class="result-info">
              <span class="param-value"
                >{{ result.parameter }}: {{ result.value }}</span
              >
              <span class="quality-score">Score: {{ result.score }}/10</span>
            </div>
          </div>
        </div>
        <div class="best-params">
          <h5>Recommended Settings</h5>
          <pre>{{ JSON.stringify(optimizationResults.best, null, 2) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { api } from "@/services/api";
import { useCharacterStore } from "@/stores/characterStore";

const store = useCharacterStore();

const characters = computed(() => store.characters);
const selectedCharacter = ref(null);
const activeJobs = ref([]);
const optimizationResults = ref(null);

const stats = reactive({
  totalGenerations: 0,
  successRate: "0%",
  avgTime: "0s",
  activeJobs: 0,
});

const running = reactive({
  quickTest: false,
  poseTest: false,
  nsfwBatch: false,
  massProduction: false,
  optimization: false,
  svdTest: false,
});

const quickTestParams = reactive({
  model: "realisticVision_v51.safetensors",
});

const poseParams = reactive({
  angles: {
    front: true,
    side: true,
    back: true,
    threequarter: true,
  },
});

const nsfwParams = reactive({
  style: "intimate",
  clothing: "minimal",
});

const massParams = reactive({
  count: 20,
  quality: "balanced",
});

const optimizeParams = reactive({
  type: "cfg_scale",
});

const svdParams = reactive({
  motion_bucket: 127,
  fps: 12,
});

const selectCharacter = (char) => {
  selectedCharacter.value = char;
};

const refreshStats = async () => {
  try {
    const response = await api.batch.getStats();
    Object.assign(stats, response.data);
  } catch (error) {
    console.error("Failed to refresh stats:", error);
  }
};

const runQuickTest = async () => {
  if (!selectedCharacter.value) return;

  try {
    running.quickTest = true;
    const response = await api.batch.quickTest(selectedCharacter.value.id);

    activeJobs.value.push({
      id: response.data.job_id,
      type: "Quick Test",
      character_name: selectedCharacter.value.character_name,
      progress: 0,
    });

    pollJobProgress(response.data.job_id);
  } catch (error) {
    alert("Quick test failed: " + error.message);
  } finally {
    running.quickTest = false;
  }
};

const runPoseTest = async () => {
  if (!selectedCharacter.value) return;

  try {
    running.poseTest = true;
    const response = await api.batch.generatePoses(selectedCharacter.value.id);

    activeJobs.value.push({
      id: response.data.job_id,
      type: "Pose Variations",
      character_name: selectedCharacter.value.character_name,
      progress: 0,
    });

    pollJobProgress(response.data.job_id);
  } catch (error) {
    alert("Pose generation failed: " + error.message);
  } finally {
    running.poseTest = false;
  }
};

const runNSFWBatch = async () => {
  if (!selectedCharacter.value) return;

  try {
    running.nsfwBatch = true;
    const response = await api.batch.generateNSFW({
      character_id: selectedCharacter.value.id,
      batch_type: "poses",
      nsfw: true,
      style: nsfwParams.style,
      clothing: nsfwParams.clothing,
    });

    activeJobs.value.push({
      id: response.data.job_id,
      type: "NSFW Batch",
      character_name: selectedCharacter.value.character_name,
      progress: 0,
    });

    pollJobProgress(response.data.job_id);
  } catch (error) {
    alert("NSFW batch failed: " + error.message);
  } finally {
    running.nsfwBatch = false;
  }
};

const runMassProduction = async () => {
  if (!selectedCharacter.value) return;

  try {
    running.massProduction = true;
    const response = await api.batch.massProduction(
      selectedCharacter.value.id,
      massParams.count,
    );

    activeJobs.value.push({
      id: response.data.job_id,
      type: "Mass Production",
      character_name: selectedCharacter.value.character_name,
      progress: 0,
    });

    pollJobProgress(response.data.job_id);
  } catch (error) {
    alert("Mass production failed: " + error.message);
  } finally {
    running.massProduction = false;
  }
};

const runOptimization = async () => {
  if (!selectedCharacter.value) return;

  try {
    running.optimization = true;

    // Simulate optimization test (would call actual API)
    const testParams = {
      character_id: selectedCharacter.value.id,
      test_type: optimizeParams.type,
    };

    // Start optimization job
    activeJobs.value.push({
      id: "opt_" + Date.now(),
      type: "Parameter Optimization",
      character_name: selectedCharacter.value.character_name,
      progress: 0,
    });

    // Simulate results
    setTimeout(() => {
      optimizationResults.value = {
        type: optimizeParams.type,
        timestamp: new Date(),
        results: generateMockOptimizationResults(),
        best: {
          cfg_scale: 7.5,
          steps: 30,
          sampler: "DPM++ 2M Karras",
        },
      };
    }, 5000);
  } catch (error) {
    alert("Optimization failed: " + error.message);
  } finally {
    running.optimization = false;
  }
};

const runSVDTest = async () => {
  if (!selectedCharacter.value) return;

  try {
    running.svdTest = true;

    // Would call animation API with SVD params
    const response = await api.animation.generate({
      character_id: selectedCharacter.value.id,
      animation_type: "svd_test",
      motion_bucket: svdParams.motion_bucket,
      fps: svdParams.fps,
    });

    activeJobs.value.push({
      id: response.data.animation_id,
      type: "SVD Animation",
      character_name: selectedCharacter.value.character_name,
      progress: 0,
    });

    pollJobProgress(response.data.animation_id);
  } catch (error) {
    alert("SVD test failed: " + error.message);
  } finally {
    running.svdTest = false;
  }
};

const pollJobProgress = async (jobId) => {
  const job = activeJobs.value.find((j) => j.id === jobId);
  if (!job) return;

  const poll = async () => {
    try {
      const response = await api.jobs.getStatus(jobId);

      if (job) {
        job.progress = response.data.progress || 0;
        job.status = response.data.status;
      }

      if (response.data.status === "completed") {
        // Remove from active jobs
        activeJobs.value = activeJobs.value.filter((j) => j.id !== jobId);
        refreshStats();
      } else if (response.data.status !== "failed") {
        setTimeout(poll, 2000);
      }
    } catch (error) {
      console.error("Job poll failed:", error);
    }
  };

  setTimeout(poll, 1000);
};

const cancelJob = async (jobId) => {
  try {
    await api.jobs.cancel(jobId);
    activeJobs.value = activeJobs.value.filter((j) => j.id !== jobId);
  } catch (error) {
    console.error("Failed to cancel job:", error);
  }
};

const formatTime = (date) => {
  return new Date(date).toLocaleTimeString();
};

const generateMockOptimizationResults = () => {
  // Mock data for demonstration
  const results = [];
  for (let i = 0; i < 6; i++) {
    results.push({
      id: i,
      parameter: optimizeParams.type,
      value: 5 + i * 2,
      score: Math.floor(Math.random() * 5) + 5,
      image: `/api/anime/placeholder/${i}.jpg`,
    });
  }
  return results;
};

onMounted(() => {
  store.loadCharacters();
  refreshStats();

  // Refresh stats every 10 seconds
  setInterval(refreshStats, 10000);
});
</script>

<style scoped>
.batch-testing-panel {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 1.5rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.panel-header h3 {
  color: #e0e0e0;
  margin: 0;
}

.btn-icon {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.5rem;
  color: #999;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-icon:hover {
  background: #333;
  color: #e0e0e0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 1rem;
  text-align: center;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: #4a90e2;
  margin-bottom: 0.25rem;
}

.stat-label {
  font-size: 0.85rem;
  color: #999;
}

.section {
  margin-bottom: 2rem;
}

.section h4 {
  color: #e0e0e0;
  margin-bottom: 1rem;
}

.character-selector {
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}

.character-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 80px;
}

.character-option:hover {
  background: #333;
}

.character-option.selected {
  border-color: #4a90e2;
  background: #333;
}

.char-avatar {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  overflow: hidden;
  background: #1a1a1a;
}

.char-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  color: #666;
}

.char-name {
  font-size: 0.85rem;
  color: #999;
  text-align: center;
}

.test-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}

.test-card {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.test-card.nsfw {
  border-color: #dc3545;
}

.test-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.test-header i {
  font-size: 1.25rem;
  color: #4a90e2;
}

.test-header h5 {
  margin: 0;
  color: #e0e0e0;
}

.test-card p {
  color: #999;
  font-size: 0.9rem;
  margin: 0;
}

.test-params {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.test-params label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.test-params span {
  color: #999;
  font-size: 0.85rem;
}

.test-params select,
.test-params input {
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 0.5rem;
  font-size: 0.9rem;
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.checkbox-group label {
  flex-direction: row;
  align-items: center;
  gap: 0.25rem;
  color: #999;
  font-size: 0.85rem;
}

.btn-action {
  background: #2a2a2a;
  border: 1px solid #4a90e2;
  border-radius: 4px;
  color: #4a90e2;
  padding: 0.75rem;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-action:hover:not(:disabled) {
  background: #4a90e2;
  color: #1a1a1a;
}

.btn-action.nsfw {
  border-color: #dc3545;
  color: #dc3545;
}

.btn-action.nsfw:hover:not(:disabled) {
  background: #dc3545;
  color: white;
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.jobs-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.job-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.75rem;
}

.job-info {
  flex: 1;
  display: flex;
  gap: 1rem;
}

.job-type {
  color: #4a90e2;
  font-weight: 500;
  font-size: 0.9rem;
}

.job-character {
  color: #999;
  font-size: 0.9rem;
}

.job-progress {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 150px;
}

.progress-bar-mini {
  flex: 1;
  height: 4px;
  background: #1a1a1a;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #4a90e2;
  transition: width 0.3s ease;
}

.progress-text {
  color: #666;
  font-size: 0.85rem;
  min-width: 35px;
  text-align: right;
}

.btn-cancel {
  background: transparent;
  border: none;
  color: #dc3545;
  cursor: pointer;
  padding: 0.25rem;
}

.btn-cancel:hover {
  color: #ff6b6b;
}

.optimization-results {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 1rem;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.result-header h5 {
  color: #e0e0e0;
  margin: 0;
}

.result-time {
  color: #666;
  font-size: 0.85rem;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.result-item {
  background: #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
}

.result-item img {
  width: 100%;
  aspect-ratio: 2/3;
  object-fit: cover;
}

.result-info {
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.param-value {
  color: #999;
  font-size: 0.75rem;
}

.quality-score {
  color: #4a90e2;
  font-size: 0.75rem;
  font-weight: 500;
}

.best-params {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #3a3a3a;
}

.best-params h5 {
  color: #4a90e2;
  margin-bottom: 0.5rem;
}

.best-params pre {
  color: #999;
  font-size: 0.85rem;
  background: #1a1a1a;
  padding: 0.5rem;
  border-radius: 4px;
  overflow-x: auto;
}
</style>
