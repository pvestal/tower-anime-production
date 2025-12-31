<template>
  <div class="director-studio">
    <div class="header">
      <h1 class="text-3xl font-bold mb-6">Anime Director Studio</h1>
      <p class="text-gray-400 mb-8">
        Professional anime production and scene management
      </p>

      <div class="nav-links">
        <router-link to="/scene" class="btn btn-primary">
          🎬 Scene Director
        </router-link>
        <router-link to="/generate" class="btn btn-secondary">
          ⚡ Quick Generate
        </router-link>
        <router-link to="/gallery" class="btn btn-secondary">
          🖼️ Gallery
        </router-link>
      </div>
    </div>

    <div class="features-grid">
      <div class="feature-card">
        <h3>🎭 Scene Composer</h3>
        <p>
          Create professional scenes with semantic actions and visual styles
        </p>
        <router-link to="/scene" class="btn btn-outline"
          >Open Scene Director</router-link
        >
      </div>

      <div class="feature-card">
        <h3>⚡ Tokyo Production</h3>
        <p>Quick generation for Tokyo Debt Desire project</p>
        <button class="btn btn-outline" @click="generateTokyo">
          Generate Tokyo Pose
        </button>
      </div>

      <div class="feature-card">
        <h3>📊 SSOT Tracking</h3>
        <p>Monitor generation workflow decisions and quality</p>
        <button class="btn btn-outline" @click="viewMetrics">
          View Metrics
        </button>
      </div>
    </div>

    <!-- Status Display -->
    <div v-if="metrics" class="metrics-panel">
      <h3>System Status</h3>
      <div class="metrics-grid">
        <div class="metric">
          <span class="label">Total Requests:</span>
          <span class="value">{{ metrics.total_requests || 0 }}</span>
        </div>
        <div class="metric">
          <span class="label">Completed:</span>
          <span class="value">{{ metrics.completed || 0 }}</span>
        </div>
        <div class="metric">
          <span class="label">Avg Response Time:</span>
          <span class="value"
            >{{ Math.round(metrics.avg_response_time || 0) }}ms</span
          >
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const metrics = ref(null);

const generateTokyo = async () => {
  try {
    const response = await fetch(
      "http://localhost:8328/api/production/tokyo/generate",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          pose: "professional",
        }),
      },
    );

    if (response.ok) {
      const result = await response.json();
      alert(`Tokyo generation started: ${result.job_id}`);
    }
  } catch (error) {
    console.error("Tokyo generation failed:", error);
  }
};

const viewMetrics = async () => {
  try {
    const response = await fetch(
      "http://localhost:8328/api/anime/ssot/metrics",
    );
    if (response.ok) {
      metrics.value = await response.json();
    }
  } catch (error) {
    console.error("Failed to load metrics:", error);
  }
};

onMounted(() => {
  viewMetrics();
});
</script>

<style scoped>
.director-studio {
  min-height: 100vh;
  background: #0f0f0f;
  color: #e0e0e0;
  padding: 2rem;
}

.header {
  text-align: center;
  margin-bottom: 3rem;
}

.nav-links {
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin-bottom: 2rem;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
  margin-bottom: 3rem;
}

.feature-card {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 2rem;
  text-align: center;
}

.feature-card h3 {
  margin-bottom: 1rem;
  font-size: 1.2rem;
}

.feature-card p {
  color: #999;
  margin-bottom: 1.5rem;
}

.metrics-panel {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 2rem;
}

.metrics-panel h3 {
  margin-bottom: 1rem;
  text-align: center;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.metric {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem;
  background: #2a2a2a;
  border-radius: 4px;
}

.metric .label {
  color: #999;
}

.metric .value {
  color: #4a90e2;
  font-weight: bold;
}

.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  font-weight: 500;
  text-decoration: none;
  display: inline-block;
  cursor: pointer;
  border: 1px solid;
  transition: all 0.2s;
}

.btn-primary {
  background: #4a90e2;
  color: white;
  border-color: #4a90e2;
}

.btn-primary:hover {
  background: #357abd;
}

.btn-secondary {
  background: #2a2a2a;
  color: #e0e0e0;
  border-color: #3a3a3a;
}

.btn-secondary:hover {
  background: #333;
}

.btn-outline {
  background: transparent;
  color: #4a90e2;
  border-color: #4a90e2;
}

.btn-outline:hover {
  background: #4a90e2;
  color: white;
}
</style>
