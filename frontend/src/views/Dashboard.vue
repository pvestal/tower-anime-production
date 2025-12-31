<template>
  <div class="dashboard">
    <h1>Dashboard</h1>
    <div class="stats-grid">
      <div class="stat-card">
        <h3>Characters</h3>
        <div class="stat-value">{{ Object.keys(store.characters).length }}</div>
      </div>
      <div class="stat-card">
        <h3>Queue</h3>
        <div class="stat-value">
          {{ queueStats.pending + queueStats.processing }}
        </div>
      </div>
      <div class="stat-card">
        <h3>Models</h3>
        <div class="stat-value">{{ store.models.length }}</div>
      </div>
      <div class="stat-card">
        <h3>Styles</h3>
        <div class="stat-value">{{ store.styles.length }}</div>
      </div>
    </div>

    <div class="recent-section">
      <h2>Recent Generations</h2>
      <div class="recent-grid">
        <div v-for="job in recentJobs" :key="job.job_id" class="recent-item">
          <div class="job-card">
            <h4>{{ job.character_name }}</h4>
            <p>{{ job.prompt }}</p>
            <div class="job-meta">
              <span :class="'status-' + job.status">{{ job.status }}</span>
              <span>{{ formatDate(job.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useCharacterStore } from "@/stores/characterStore";
import api from "@/api/animeApi";

const store = useCharacterStore();
const recentJobs = ref([]);
const queueStats = ref({ pending: 0, processing: 0 });
const recentImages = ref([]);

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleDateString();
};

onMounted(async () => {
  try {
    // Load recent jobs from V2 API
    const jobsResponse = await api.v2.getJobs(5);
    recentJobs.value = jobsResponse.data.jobs;

    // Load queue stats
    const queueResponse = await api.v2.getJobs(100);
    const jobs = queueResponse.data.jobs;
    queueStats.value = {
      pending: jobs.filter((j) => j.status === "pending").length,
      processing: jobs.filter((j) => j.status === "processing").length,
    };
  } catch (error) {
    console.error("Failed to load dashboard data:", error);
    // Fallback to old behavior if V2 fails
    try {
      const response = await api.getCharacterImages("mei", 6);
      recentImages.value = response.data;
    } catch (fallbackError) {
      console.error("Fallback also failed:", fallbackError);
    }
  }
});
</script>

<style scoped>
.dashboard {
  background: #1a1a1a;
  color: #00ff00;
  padding: 20px;
  font-family: "Courier New", monospace;
  margin: 0;
}

h1 {
  color: #00ff00;
  font-family: "Courier New", monospace;
  font-size: 24px;
  margin-bottom: 20px;
  font-weight: normal;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
  margin-bottom: 30px;
}

.stat-card {
  background: #000000;
  border: 1px solid #333333;
  color: #00ff00;
  padding: 15px;
  font-family: "Courier New", monospace;
  text-align: left;
}

.stat-card:hover {
  border-color: #00ff00;
}

.stat-card h3 {
  margin-bottom: 8px;
  font-size: 12px;
  color: #888888;
  text-transform: uppercase;
  font-family: "Courier New", monospace;
  font-weight: normal;
}

.stat-value {
  font-size: 24px;
  font-weight: normal;
  color: #00ff00;
  font-family: "Courier New", monospace;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.recent-section {
  margin-top: 2rem;
}

.recent-section h2 {
  color: black;
  font-size: 1.2rem;
  margin-bottom: 1rem;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
}

.recent-item img {
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ddd;
  transition: border-color 0.2s;
}

.recent-item:hover img {
  border-color: #4a90e2;
}

.job-card {
  background: #f9f9f9;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 1rem;
  height: 200px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.job-card h4 {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: black;
}

.job-card p {
  margin: 0;
  font-size: 0.8rem;
  color: #666;
  flex-grow: 1;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.job-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.7rem;
  margin-top: 0.5rem;
}

.status-completed {
  color: #28a745;
  font-weight: 600;
}

.status-processing {
  color: #ffc107;
  font-weight: 600;
}

.status-pending {
  color: #6c757d;
  font-weight: 600;
}

.status-failed {
  color: #dc3545;
  font-weight: 600;
}
</style>
