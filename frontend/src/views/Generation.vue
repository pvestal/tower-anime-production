<template>
  <div class="generation-view">
    <!-- Echo Assist Panel -->
    <EchoAssistPanel
      :prompt="form.prompt"
      :current-model="form.model_name || 'svd'"
      @apply-model="(model) => (form.model_name = model)"
      @select-character="(char) => (form.character_name = char)"
    />
    <div class="view-header">
      <h1>Generation Studio</h1>
      <div class="header-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          :class="['tab', { active: activeTab === tab.value }]"
          @click="activeTab = tab.value"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <!-- Single Generation Tab -->
    <div v-if="activeTab === 'single'" class="generation-form">
      <div class="form-row">
        <div class="form-group">
          <label>Character</label>
          <select v-model="form.character_name">
            <option value="">New Character...</option>
            <option
              v-for="char in store.characters"
              :key="char.id"
              :value="char.character_name"
            >
              {{ char.character_name }}
            </option>
          </select>
          <input
            v-if="!form.character_name"
            v-model="newCharacterName"
            placeholder="Enter character name"
            class="mt-2"
          />
        </div>
        <div class="form-group">
          <label>Generation Type</label>
          <select v-model="form.generation_type">
            <option value="single_image">Single Image</option>
            <option value="turnaround">Turnaround Sheet</option>
            <option value="pose_sheet">Pose Sheet</option>
            <option value="expression_sheet">Expression Sheet</option>
          </select>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Content Type</label>
          <div class="content-type-selector">
            <label v-for="ct in contentTypes" :key="ct.value">
              <input
                v-model="form.content_type"
                type="radio"
                :value="ct.value"
              />
              <span :class="['badge', ct.value]">{{ ct.label }}</span>
            </label>
          </div>
        </div>
        <div class="form-group">
          <label>Model</label>
          <select v-model="form.model_name">
            <option value="">Default (RealisticVision)</option>
            <option value="chilloutmix_NiPrunedFp32.safetensors">
              ChilloutMix
            </option>
            <option value="realisticVision_v51.safetensors">
              Realistic Vision v5.1
            </option>
            <option value="epicRealism_newEra.safetensors">Epic Realism</option>
            <option value="cyberrealistic_v50.safetensors">
              CyberRealistic v5.0
            </option>
          </select>
        </div>
      </div>

      <div class="form-group">
        <label>Prompt</label>
        <div class="prompt-helpers">
          <button
            v-for="helper in promptHelpers"
            :key="helper"
            class="helper-btn"
            @click="addToPrompt(helper)"
          >
            {{ helper }}
          </button>
        </div>
        <textarea
          v-model="form.prompt"
          rows="4"
          placeholder="Describe your character in detail..."
        ></textarea>
      </div>

      <div class="form-group">
        <label>Negative Prompt</label>
        <textarea
          v-model="form.negative_prompt"
          rows="2"
          placeholder="What to avoid..."
        ></textarea>
      </div>

      <div v-if="showAdvanced" class="advanced-panel">
        <div class="form-row">
          <div class="form-group">
            <label>Width</label>
            <input
              v-model.number="form.width"
              type="number"
              min="512"
              max="1024"
              step="64"
            />
          </div>
          <div class="form-group">
            <label>Height</label>
            <input
              v-model.number="form.height"
              type="number"
              min="512"
              max="1024"
              step="64"
            />
          </div>
          <div class="form-group">
            <label>Steps</label>
            <input
              v-model.number="form.steps"
              type="number"
              min="20"
              max="50"
            />
          </div>
          <div class="form-group">
            <label>CFG Scale</label>
            <input
              v-model.number="form.cfg_scale"
              type="number"
              min="5"
              max="15"
              step="0.5"
            />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Seed</label>
            <input
              v-model.number="form.seed"
              type="number"
              placeholder="Random"
            />
          </div>
          <div class="form-group">
            <label>Batch Size</label>
            <input
              v-model.number="form.num_images"
              type="number"
              min="1"
              max="10"
            />
          </div>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-secondary" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? "Hide" : "Show" }} Advanced
        </button>
        <button
          class="btn btn-primary"
          :disabled="generating"
          @click="generate"
        >
          {{ generating ? "Generating..." : "Generate" }}
        </button>
      </div>
    </div>

    <!-- Animation Tab -->
    <div v-if="activeTab === 'animation'" class="animation-form">
      <div class="form-group">
        <label>Character</label>
        <select v-model="animationForm.character_id">
          <option value="">Select character...</option>
          <option
            v-for="char in store.characters"
            :key="char.id"
            :value="char.id"
          >
            {{ char.character_name }}
          </option>
        </select>
      </div>

      <div class="form-group">
        <label>Animation Type</label>
        <select v-model="animationForm.animation_type">
          <option value="idle">Idle Loop</option>
          <option value="walk">Walk Cycle</option>
          <option value="talk">Talking</option>
          <option value="action">Action Sequence</option>
          <option value="emotion">Emotion Transition</option>
        </select>
      </div>

      <div class="form-group">
        <label>Upload Reference Image</label>
        <input type="file" accept="image/*" @change="handleImageUpload" />
        <div v-if="animationForm.reference_image" class="preview">
          <img :src="animationForm.reference_image" alt="Reference" />
        </div>
      </div>

      <div class="form-group">
        <label>Motion Prompt</label>
        <textarea
          v-model="animationForm.prompt"
          rows="3"
          placeholder="Describe the motion..."
        ></textarea>
      </div>

      <div class="form-group" v-if="systemLimits">
        <label>Frames ({{ animationForm.frames }})</label>
        <input
          type="range"
          v-model.number="animationForm.frames"
          :min="systemLimits.frame_limits.svd.min"
          :max="systemLimits.frame_limits.svd.max"
          :step="1"
        />
        <div class="frame-info">
          <span>Duration: {{ (animationForm.frames / 8).toFixed(2) }}s</span>
          <span class="vram-warning" v-if="systemLimits.frame_limits.svd.vram_mb[animationForm.frames]">
            VRAM: {{ systemLimits.frame_limits.svd.vram_mb[animationForm.frames] }}MB
          </span>
        </div>
        <div class="limit-warning" v-if="animationForm.frames > 25">
          ⚠️ Warning: Untested beyond 25 frames. May fail.
        </div>
      </div>

      <button
        class="btn btn-primary"
        :disabled="generating"
        @click="generateAnimation"
      >
        Generate Animation (SVD - Coherent)
      </button>
      <div v-if="systemLimits" class="model-recommendation">
        💡 Using SVD: {{ systemLimits.recommendations[0] }}
      </div>
    </div>

    <!-- Batch Testing Tab -->
    <div v-if="activeTab === 'batch'" class="batch-form">
      <div class="form-group">
        <label>Character</label>
        <select v-model="batchForm.character_id">
          <option value="">Select character...</option>
          <option
            v-for="char in store.characters"
            :key="char.id"
            :value="char.id"
          >
            {{ char.character_name }}
          </option>
        </select>
      </div>

      <div class="batch-options">
        <h3>Quick Actions</h3>
        <div class="batch-buttons">
          <button class="batch-btn" @click="quickTest">
            <i class="pi pi-bolt"></i>
            Quick Test (3 images)
          </button>
          <button class="batch-btn" @click="generateAllPoses">
            <i class="pi pi-users"></i>
            All Poses (10 variations)
          </button>
          <button class="batch-btn nsfw" @click="generateNSFWBatch">
            <i class="pi pi-exclamation-triangle"></i>
            NSFW Batch (5 intimate)
          </button>
          <button class="batch-btn" @click="massProduction">
            <i class="pi pi-clone"></i>
            Mass Production (20 images)
          </button>
        </div>
      </div>

      <div v-if="optimalSettings" class="optimal-settings">
        <h4>Recommended Settings</h4>
        <pre>{{ JSON.stringify(optimalSettings, null, 2) }}</pre>
      </div>
    </div>

    <!-- Audit Truth Tab -->
    <div v-if="activeTab === 'audit'" class="audit-panel">
      <div class="audit-controls">
        <h3>Generation Controls</h3>
        <label>
          <input type="checkbox" v-model="auditControls.forceSVD" @change="updateAuditControls">
          Force SVD for Video (No Flashing Frames)
        </label>
        <button @click="forceSVD" class="btn-danger">FORCE SVD NOW</button>
      </div>

      <div class="audit-entries" v-if="auditEntries.length > 0">
        <h3>Recent Generations</h3>
        <div class="audit-entry" v-for="entry in auditEntries" :key="entry.job_id">
          <div class="entry-header">
            <span class="job-id">{{ entry.job_id }}</span>
            <span class="timestamp">{{ new Date(entry.timestamp).toLocaleString() }}</span>
          </div>
          <div class="entry-details">
            <div class="prompt">{{ entry.prompt }}</div>
            <div class="model-info">
              <span class="label">Echo:</span> {{ entry.echo_recommendation }}
              <span class="label">Used:</span> {{ entry.actual_model_used || 'Unknown' }}
              <span v-if="entry.is_coherent" class="coherent-badge">✅ Coherent</span>
              <span v-else class="incoherent-badge">⚡ Flashing</span>
            </div>
          </div>
          <div class="entry-actions">
            <button
              v-if="entry.verification_status === 'FAIL' || !entry.is_coherent"
              @click="rerunWithFixes(entry)"
              class="btn-fix"
            >
              🔄 Re-run with SVD
            </button>
            <button
              v-if="entry.echo_recommendation && entry.echo_recommendation.split('|')[0] !== entry.actual_model_used"
              @click="trainEcho(entry)"
              class="btn-train"
            >
              📚 Train Echo
            </button>
          </div>
        </div>
      </div>

      <div class="audit-stats" v-if="auditTruth">
        <h3>The Truth</h3>
        <div class="stats-grid">
          <div class="stat">
            <span>Total:</span> {{ auditTruth.total_generations }}
          </div>
          <div class="stat">
            <span>Verified:</span> {{ auditTruth.verified_generations }} ({{ auditTruth.verification_coverage }})
          </div>
          <div class="stat success">
            <span>SVD Coherent:</span> {{ auditTruth.svd_coherent_videos }}
          </div>
          <div class="stat warning">
            <span>AnimateDiff Flashing:</span> {{ auditTruth.animatediff_flashing_videos }}
          </div>
        </div>
      </div>

      <div class="audit-table">
        <h3>Recent Generations</h3>
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Prompt</th>
              <th>Model Used</th>
              <th>Coherent?</th>
              <th>Output</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in auditEntries" :key="entry.job_id">
              <td>{{ entry.job_id }}</td>
              <td>{{ entry.user_prompt?.substring(0, 50) }}...</td>
              <td>{{ entry.actual_model_used || entry.comfyui_workflow_used }}</td>
              <td>
                <span v-if="entry.is_coherent" class="success">✅</span>
                <span v-else class="error">❌</span>
              </td>
              <td>
                <span v-if="entry.output_file" class="success">✓</span>
                <span v-else class="error">✗</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Generation Status -->
    <div v-if="currentJob" class="status-panel">
      <div class="status-header">
        <h3>Generation Progress</h3>
        <span class="job-id">Job: {{ currentJob.job_id }}</span>
      </div>
      <div class="progress-bar-container">
        <div
          class="progress-bar"
          :style="{ width: progressPercent + '%' }"
        ></div>
      </div>
      <div class="status-info">
        <span class="status-label">{{ currentJob.status }}</span>
        <span class="progress-percent">{{ progressPercent }}%</span>
      </div>
      <div v-if="currentJob.message" class="status-message">
        {{ currentJob.message }}
      </div>
      <button
        v-if="currentJob.status === 'failed'"
        class="btn btn-warning"
        @click="retryJob"
      >
        Retry
      </button>
    </div>

    <!-- Results Gallery -->
    <div v-if="results.length > 0" class="results-gallery">
      <h3>Generated Images</h3>
      <div class="gallery-grid">
        <div v-for="(result, idx) in results" :key="idx" class="gallery-item">
          <img
            :src="result.url"
            :alt="result.character_name"
            @click="viewFullsize(result)"
          />
          <div class="gallery-info">
            <span>{{ result.character_name }}</span>
            <span class="gallery-type">{{ result.type }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from "vue";
import { useCharacterStore } from "@/stores/characterStore";
import { api, WebSocketService } from "@/services/api";
import EchoAssistPanel from "@/components/EchoAssistPanel.vue";

const store = useCharacterStore();
const generating = ref(false);
const activeTab = ref("single");
const showAdvanced = ref(false);
const results = ref([]);
const currentJob = ref(null);
const ws = ref(null);
const newCharacterName = ref("");
const optimalSettings = ref(null);
const systemLimits = ref(null);

// Audit system data
const auditEntries = ref([]);
const auditTruth = ref(null);
const auditControls = reactive({
  forceSVD: true
});

const tabs = [
  { value: "single", label: "Single Generation" },
  { value: "animation", label: "Animation" },
  { value: "batch", label: "Batch Testing" },
  { value: "audit", label: "🔍 Audit Truth" },
];

const contentTypes = [
  { value: "sfw", label: "SFW" },
  { value: "artistic", label: "Artistic" },
  { value: "nsfw", label: "NSFW" },
];

const promptHelpers = [
  "RAW photo",
  "photorealistic",
  "8k uhd",
  "detailed skin",
  "professional",
  "studio lighting",
  "cinematic",
  "highly detailed",
];

const form = reactive({
  character_name: "",
  prompt: "",
  negative_prompt:
    "cartoon, anime, drawing, painting, sketch, 3d render, low quality",
  content_type: "sfw",
  generation_type: "single_image",
  model_name: "",
  seed: null,
  num_images: 1,
  width: 512,
  height: 768,
  steps: 30,
  cfg_scale: 7.5,
});

const animationForm = reactive({
  character_id: null,
  animation_type: "idle",
  reference_image: null,
  prompt: "",
  negative_prompt: "",
  frames: 16,  // Default to optimal based on limits
});

const batchForm = reactive({
  character_id: null,
  batch_type: "poses",
  count: 5,
  nsfw: false,
});

const progressPercent = computed(() => {
  if (!currentJob.value) return 0;
  return currentJob.value.progress || 0;
});

const addToPrompt = (helper) => {
  if (form.prompt && !form.prompt.endsWith(", ")) {
    form.prompt += ", ";
  }
  form.prompt += helper;
};

const generate = async () => {
  try {
    generating.value = true;

    const requestData = {
      ...form,
      character_name: form.character_name || newCharacterName.value,
    };

    const response = await api.character.generate(requestData);
    currentJob.value = response.data;

    // Connect WebSocket
    if (response.data.generation_id) {
      connectWebSocket(response.data.generation_id);
    }

    // Start polling
    pollJobStatus(response.data.generation_id);
  } catch (error) {
    console.error("Generation failed:", error);
    alert(
      "Generation failed: " + (error.response?.data?.detail || error.message),
    );
  } finally {
    generating.value = false;
  }
};

const generateAnimation = async () => {
  try {
    generating.value = true;

    const response = await api.animation.generate({
      character_id: animationForm.character_id,
      animation_type: animationForm.animation_type,
      prompt: animationForm.prompt,
      negative_prompt: animationForm.negative_prompt,
      reference_image: animationForm.reference_image,
    });

    currentJob.value = response.data;
    pollJobStatus(response.data.animation_id);
  } catch (error) {
    console.error("Animation generation failed:", error);
    alert("Animation failed: " + error.message);
  } finally {
    generating.value = false;
  }
};

const quickTest = async () => {
  try {
    generating.value = true;
    const response = await api.batch.quickTest(batchForm.character_id);
    currentJob.value = response.data;
    pollJobStatus(response.data.job_id);
  } catch (error) {
    alert("Quick test failed: " + error.message);
  } finally {
    generating.value = false;
  }
};

const generateAllPoses = async () => {
  try {
    generating.value = true;
    const response = await api.batch.generatePoses(batchForm.character_id);
    currentJob.value = response.data;
    pollJobStatus(response.data.job_id);
  } catch (error) {
    alert("Pose generation failed: " + error.message);
  } finally {
    generating.value = false;
  }
};

const generateNSFWBatch = async () => {
  try {
    generating.value = true;
    const response = await api.batch.generateNSFW({
      character_id: batchForm.character_id,
      batch_type: "poses",
      nsfw: true,
    });
    currentJob.value = response.data;
    pollJobStatus(response.data.job_id);
  } catch (error) {
    alert("NSFW batch failed: " + error.message);
  } finally {
    generating.value = false;
  }
};

const massProduction = async () => {
  try {
    generating.value = true;
    const response = await api.batch.massProduction(batchForm.character_id, 20);
    currentJob.value = response.data;
    pollJobStatus(response.data.job_id);
  } catch (error) {
    alert("Mass production failed: " + error.message);
  } finally {
    generating.value = false;
  }
};

const handleImageUpload = (event) => {
  const file = event.target.files[0];
  if (file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      animationForm.reference_image = e.target.result;
    };
    reader.readAsDataURL(file);
  }
};

const connectWebSocket = (jobId) => {
  if (ws.value) {
    ws.value.disconnect();
  }

  ws.value = new WebSocketService(jobId);

  ws.value.on("progress", (data) => {
    if (currentJob.value) {
      currentJob.value.progress = data.progress;
      currentJob.value.message = data.message;
    }
  });

  ws.value.on("completed", (data) => {
    if (currentJob.value) {
      currentJob.value.status = "completed";
      handleJobComplete(data);
    }
  });

  ws.value.on("error", (data) => {
    console.error("Job error:", data);
    if (currentJob.value) {
      currentJob.value.status = "failed";
      currentJob.value.error = data.error;
    }
  });
};

const pollJobStatus = async (jobId) => {
  if (!jobId) return;

  const poll = async () => {
    try {
      const response = await api.jobs.getStatus(jobId);

      if (currentJob.value) {
        currentJob.value.status = response.data.status;
        currentJob.value.progress = response.data.progress;
        currentJob.value.message = response.data.message;
      }

      if (response.data.status === "completed") {
        handleJobComplete(response.data.result);
      } else if (response.data.status !== "failed") {
        setTimeout(poll, 2000);
      }
    } catch (error) {
      console.error("Status poll failed:", error);
    }
  };

  setTimeout(poll, 2000);
};

const handleJobComplete = (data) => {
  if (data && data.outputs) {
    data.outputs.forEach((output) => {
      results.value.unshift({
        url: output,
        character_name: form.character_name || newCharacterName.value,
        type: form.generation_type,
        timestamp: new Date(),
      });
    });
  }
  currentJob.value = null;
};

const retryJob = async () => {
  if (currentJob.value && currentJob.value.job_id) {
    try {
      const response = await api.jobs.retry(currentJob.value.job_id);
      currentJob.value = response.data;
      pollJobStatus(response.data.job_id);
    } catch (error) {
      alert("Retry failed: " + error.message);
    }
  }
};

const viewFullsize = (result) => {
  window.open(result.url, "_blank");
};

const loadOptimalSettings = async () => {
  try {
    const response = await api.batch.getOptimalSettings(form.content_type);
    optimalSettings.value = response.data;
  } catch (error) {
    console.error("Failed to load optimal settings:", error);
  }
};

// Audit system functions
async function loadAuditEntries() {
  try {
    const response = await fetch("http://localhost:8328/api/anime/audit/entries?limit=20");
    auditEntries.value = await response.json();
  } catch (error) {
    console.error("Failed to load audit entries:", error);
  }
}

async function loadAuditTruth() {
  try {
    const response = await fetch("http://localhost:8328/api/anime/audit/truth");
    const data = await response.json();
    auditTruth.value = data.truth;
  } catch (error) {
    console.error("Failed to load audit truth:", error);
  }
}

async function forceSVD() {
  try {
    const response = await fetch("http://localhost:8328/api/anime/audit/force-svd", {
      method: "POST"
    });
    const result = await response.json();
    alert(result.message);
    loadAuditTruth();
  } catch (error) {
    console.error("Failed to force SVD:", error);
  }
}

async function updateAuditControls() {
  try {
    const response = await fetch("http://localhost:8328/api/anime/audit/controls", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        force_svd_for_video: auditControls.forceSVD
      })
    });
  } catch (error) {
    console.error("Failed to update controls:", error);
  }
}

async function rerunWithFixes(entry) {
  try {
    generating.value = true;

    // Clone the original request but force SVD
    const fixedRequest = {
      character_identity: entry.prompt.split(" - ")[0] || "character",
      action_sequence: entry.prompt.split(" - ")[1] || entry.prompt,
      frames: entry.frames || 25,
      force_svd: true,  // Force SVD for coherent video
      parent_job_id: entry.job_id  // Link to original
    };

    const response = await fetch("http://localhost:8328/api/anime/coherent/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fixedRequest)
    });

    const result = await response.json();
    alert(`Re-run started with SVD: Job ${result.job_id}`);

    // Reload audit entries to show new job
    setTimeout(loadAuditEntries, 2000);
  } catch (error) {
    console.error("Failed to re-run with fixes:", error);
    alert("Re-run failed: " + error.message);
  } finally {
    generating.value = false;
  }
}

async function trainEcho(entry) {
  try {
    const echoRec = entry.echo_recommendation ? entry.echo_recommendation.split("|")[0] : "unknown";
    const actual = entry.actual_model_used || "svd";

    const trainingData = {
      prompt: entry.prompt,
      echo_recommended: echoRec,
      correct_model: actual,
      reason: actual === "svd"
        ? "SVD produces coherent video, AnimateDiff creates flashing frames"
        : "Model performed better in this context",
      frames: entry.frames,
      success: entry.verification_status === "PASS"
    };

    const response = await fetch("http://localhost:8328/api/anime/echo/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(trainingData)
    });

    const result = await response.json();
    alert(`Echo trained: ${result.message}`);
  } catch (error) {
    console.error("Failed to train Echo:", error);
    alert("Training failed: " + error.message);
  }
}

// Watch for tab changes to load audit data
watch(activeTab, (newTab) => {
  if (newTab === "audit") {
    loadAuditEntries();
    loadAuditTruth();
  }
});

// Load system limits
async function loadSystemLimits() {
  try {
    const response = await fetch("http://localhost:8328/api/anime/system/limits");
    systemLimits.value = await response.json();

    // Set default frames to optimal
    if (systemLimits.value && systemLimits.value.frame_limits.svd.optimal) {
      animationForm.frames = systemLimits.value.frame_limits.svd.optimal;
    }
  } catch (error) {
    console.error("Failed to load system limits:", error);
  }
}

onMounted(() => {
  store.loadCharacters();
  loadOptimalSettings();
  loadSystemLimits();
});

onUnmounted(() => {
  if (ws.value) {
    ws.value.disconnect();
  }
});
</script>

<style scoped>
.generation-view {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 2rem;
  border: 1px solid #2a2a2a;
  max-width: 1200px;
  margin: 0 auto;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

h1 {
  color: #e0e0e0;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 1.5rem;
  margin: 0;
}

.header-tabs {
  display: flex;
  gap: 0.5rem;
}

.frame-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  color: #888;
  margin-top: 0.5rem;
}

.vram-warning {
  color: #f59e0b;
}

.limit-warning {
  color: #ef4444;
  background: #ef444420;
  padding: 0.5rem;
  border-radius: 4px;
  margin-top: 0.5rem;
  font-size: 0.9rem;
}

.model-recommendation {
  margin-top: 1rem;
  padding: 0.75rem;
  background: #10b98120;
  border: 1px solid #10b981;
  border-radius: 4px;
  color: #10b981;
  font-size: 0.9rem;
}

.tab {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  color: #999;
  cursor: pointer;
  transition: all 0.2s;
}

.tab:hover {
  background: #333;
  color: #e0e0e0;
}

.tab.active {
  background: #4a90e2;
  border-color: #4a90e2;
  color: white;
}

.generation-form,
.animation-form,
.batch-form {
  max-width: 800px;
}

/* Audit Panel Styles */
.audit-panel {
  max-width: 1000px;
}

.audit-controls {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
}

.audit-controls label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 1rem 0;
}

.audit-stats {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.stat {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem;
  background: #333;
  border-radius: 4px;
}

.stat.success { color: #4caf50; }
.stat.warning { color: #ff9800; }

.audit-table {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
}

.audit-table table {
  width: 100%;
  border-collapse: collapse;
}

.audit-table th,
.audit-table td {
  padding: 0.5rem;
  text-align: left;
  border-bottom: 1px solid #444;
}

.audit-table th {
  background: #333;
  font-weight: bold;
}

.btn-danger {
  background: #ff4444;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.btn-danger:hover {
  background: #ff6666;
}

/* Audit Entry Styles */
.audit-entries {
  margin-top: 2rem;
}

.audit-entry {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.entry-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  color: #888;
}

.entry-details {
  margin-bottom: 0.75rem;
}

.entry-details .prompt {
  color: #e0e0e0;
  margin-bottom: 0.5rem;
}

.model-info {
  display: flex;
  gap: 1rem;
  font-size: 0.9rem;
  align-items: center;
}

.model-info .label {
  color: #888;
}

.coherent-badge {
  color: #10b981;
  background: #10b98120;
  padding: 2px 8px;
  border-radius: 4px;
}

.incoherent-badge {
  color: #f59e0b;
  background: #f59e0b20;
  padding: 2px 8px;
  border-radius: 4px;
}

.entry-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-fix {
  background: #3b82f6;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
}

.btn-fix:hover {
  background: #2563eb;
}

.btn-train {
  background: #8b5cf6;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
}

.btn-train:hover {
  background: #7c3aed;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.content-type-selector {
  display: flex;
  gap: 1rem;
}

.content-type-selector label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.badge {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: 500;
}

.badge.sfw {
  background: #28a745;
  color: white;
}

.badge.artistic {
  background: #6f42c1;
  color: white;
}

.badge.nsfw {
  background: #dc3545;
  color: white;
}

.prompt-helpers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.helper-btn {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  color: #999;
  font-size: 0.85rem;
  cursor: pointer;
}

.helper-btn:hover {
  background: #333;
  color: #e0e0e0;
}

.advanced-panel {
  background: #252525;
  border-radius: 4px;
  padding: 1rem;
  margin-top: 1rem;
}

.form-actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.5rem;
}

.mt-2 {
  margin-top: 0.5rem;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #999;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 0.75rem;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  color: #e0e0e0;
  font-size: 0.9rem;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #4a90e2;
  background: #2a2a2a;
}

.btn-primary,
.btn-secondary,
.btn-warning {
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  font-size: 1rem;
  cursor: pointer;
  font-weight: 500;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  transition: all 0.2s;
  border: 1px solid;
}

.btn-primary {
  background: #2a2a2a;
  color: #4a90e2;
  border-color: #4a90e2;
}

.btn-primary:hover {
  background: #4a90e2;
  color: #1a1a1a;
}

.btn-secondary {
  background: #2a2a2a;
  color: #999;
  border-color: #3a3a3a;
}

.btn-secondary:hover {
  background: #333;
  color: #e0e0e0;
}

.btn-warning {
  background: #2a2a2a;
  color: #ffc107;
  border-color: #ffc107;
}

.btn-warning:hover {
  background: #ffc107;
  color: #1a1a1a;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.batch-options {
  margin-top: 2rem;
}

.batch-options h3 {
  color: #e0e0e0;
  margin-bottom: 1rem;
}

.batch-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.batch-btn {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 1.5rem;
  color: #e0e0e0;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.batch-btn:hover {
  background: #333;
  transform: translateY(-2px);
}

.batch-btn.nsfw {
  border-color: #dc3545;
}

.batch-btn i {
  font-size: 1.5rem;
}

.preview {
  margin-top: 1rem;
  max-width: 200px;
}

.preview img {
  width: 100%;
  border-radius: 4px;
}

.optimal-settings {
  margin-top: 2rem;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 1rem;
}

.optimal-settings h4 {
  color: #4a90e2;
  margin-bottom: 0.5rem;
}

.optimal-settings pre {
  color: #999;
  font-size: 0.85rem;
  overflow-x: auto;
}

.status-panel {
  margin-top: 2rem;
  background: #252525;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 1.5rem;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.status-header h3 {
  color: #e0e0e0;
  margin: 0;
}

.job-id {
  color: #666;
  font-size: 0.85rem;
  font-family: monospace;
}

.progress-bar-container {
  width: 100%;
  height: 8px;
  background: #2a2a2a;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4a90e2, #357abd);
  transition: width 0.3s ease;
}

.status-info {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
}

.status-label {
  color: #999;
  font-size: 0.9rem;
  text-transform: capitalize;
}

.progress-percent {
  color: #4a90e2;
  font-weight: 500;
}

.status-message {
  margin-top: 0.5rem;
  color: #666;
  font-size: 0.85rem;
  font-style: italic;
}

.results-gallery {
  margin-top: 3rem;
}

.results-gallery h3 {
  color: #e0e0e0;
  margin-bottom: 1rem;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

.gallery-item {
  background: #2a2a2a;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s;
}

.gallery-item:hover {
  transform: translateY(-4px);
}

.gallery-item img {
  width: 100%;
  aspect-ratio: 2/3;
  object-fit: cover;
}

.gallery-info {
  padding: 0.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.gallery-info span {
  color: #999;
  font-size: 0.85rem;
}

.gallery-type {
  background: #333;
  padding: 0.15rem 0.5rem;
  border-radius: 3px;
  font-size: 0.75rem;
}
</style>
