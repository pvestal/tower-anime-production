<template>
  <div class="project-manager">
    <!-- Header -->
    <div class="header">
      <h1>Project Management</h1>
      <button class="btn-primary" @click="showCreateModal = true">
        <i class="icon-plus"></i> Create Project
      </button>
    </div>

    <!-- Project List -->
    <div class="project-grid">
      <div
        v-for="project in projects"
        :key="project.id"
        class="project-card"
        :class="{ selected: selectedProject?.id === project.id }"
        @click="selectProject(project)"
      >
        <div class="project-header">
          <h3>{{ project.name }}</h3>
          <div class="project-actions">
            <button class="btn-icon" @click.stop="editProject(project)">
              <i class="icon-edit"></i>
            </button>
            <button
              class="btn-icon danger"
              @click.stop="deleteProject(project.id)"
            >
              <i class="icon-delete"></i>
            </button>
          </div>
        </div>

        <p class="project-description">
          {{ project.description || "No description" }}
        </p>

        <div class="project-stats">
          <div class="stat">
            <span class="stat-value">{{ project.character_count || 0 }}</span>
            <span class="stat-label">Characters</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ project.generation_count || 0 }}</span>
            <span class="stat-label">Generations</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ project.episode_count || 0 }}</span>
            <span class="stat-label">Episodes</span>
          </div>
        </div>

        <div class="project-footer">
          <span class="status" :class="project.status">{{
            project.status
          }}</span>
          <span class="date">{{ formatDate(project.created_at) }}</span>
        </div>
      </div>
    </div>

    <!-- Project Details Panel -->
    <div v-if="selectedProject" class="project-details">
      <div class="details-header">
        <h2>{{ selectedProject.name }}</h2>
        <button class="btn-icon" @click="selectedProject = null">
          <i class="icon-close"></i>
        </button>
      </div>

      <div class="details-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-button"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="tab-content">
        <!-- Overview Tab -->
        <div v-if="activeTab === 'overview'" class="overview-tab">
          <div class="info-grid">
            <div class="info-item">
              <label>Description</label>
              <p>
                {{ selectedProject.description || "No description provided" }}
              </p>
            </div>
            <div class="info-item">
              <label>Status</label>
              <span class="status" :class="selectedProject.status">{{
                selectedProject.status
              }}</span>
            </div>
            <div class="info-item">
              <label>Created</label>
              <p>{{ formatDate(selectedProject.created_at) }}</p>
            </div>
            <div class="info-item">
              <label>Last Updated</label>
              <p>{{ formatDate(selectedProject.updated_at) }}</p>
            </div>
          </div>

          <div v-if="selectedProject.style_guide" class="style-guide">
            <h4>Style Guide</h4>
            <div class="style-tags">
              <span
                v-for="(value, key) in selectedProject.style_guide"
                :key="key"
                class="style-tag"
              >
                {{ key }}: {{ value }}
              </span>
            </div>
          </div>
        </div>

        <!-- Characters Tab -->
        <div v-if="activeTab === 'characters'" class="characters-tab">
          <div class="section-header">
            <h4>Project Characters</h4>
            <button
              class="btn-secondary"
              @click="showCreateCharacterModal = true"
            >
              Add Character
            </button>
          </div>

          <div class="characters-grid">
            <div
              v-for="character in projectCharacters"
              :key="character.id"
              class="character-card"
            >
              <div class="character-header">
                <h5>{{ character.name }}</h5>
                <span class="character-type">{{
                  character.character_type
                }}</span>
              </div>

              <div class="character-info">
                <p class="character-prompt">{{ character.base_prompt }}</p>
                <div class="character-stats">
                  <span class="stat"
                    >{{ character.generation_count || 0 }} generations</span
                  >
                  <span class="stat"
                    >{{ character.reference_images?.length || 0 }} refs</span
                  >
                </div>
              </div>

              <div class="character-actions">
                <button class="btn-small" @click="editCharacter(character)">
                  Edit
                </button>
                <button class="btn-small" @click="viewCharacterRefs(character)">
                  References
                </button>
                <button
                  class="btn-small primary"
                  @click="generateCharacter(character)"
                >
                  Generate
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Generations Tab -->
        <div v-if="activeTab === 'generations'" class="generations-tab">
          <div class="section-header">
            <h4>Recent Generations</h4>
            <div class="generation-filters">
              <select
                v-model="generationFilter"
                @change="loadProjectGenerations"
              >
                <option value="">All Types</option>
                <option value="image">Images</option>
                <option value="video">Videos</option>
              </select>
              <select
                v-model="characterFilter"
                @change="loadProjectGenerations"
              >
                <option value="">All Characters</option>
                <option
                  v-for="char in projectCharacters"
                  :key="char.id"
                  :value="char.id"
                >
                  {{ char.name }}
                </option>
              </select>
            </div>
          </div>

          <div class="generations-grid">
            <div
              v-for="generation in projectGenerations"
              :key="generation.id"
              class="generation-card"
            >
              <div class="generation-preview">
                <img
                  v-if="
                    generation.generation_type === 'image' &&
                    generation.output_path
                  "
                  :src="getGenerationPreview(generation)"
                  alt="Generated image"
                  @error="handleImageError"
                />
                <div
                  v-else-if="generation.generation_type === 'video'"
                  class="video-preview"
                >
                  <i class="icon-video"></i>
                  <span>Video</span>
                </div>
                <div v-else class="placeholder-preview">
                  <i class="icon-image"></i>
                  <span>{{ generation.status }}</span>
                </div>
              </div>

              <div class="generation-info">
                <div class="generation-header">
                  <span class="generation-type">{{
                    generation.generation_type
                  }}</span>
                  <span class="status" :class="generation.status">{{
                    generation.status
                  }}</span>
                </div>

                <p class="generation-prompt">
                  {{ truncateText(generation.prompt, 60) }}
                </p>

                <div class="generation-meta">
                  <span v-if="generation.character_name" class="character">{{
                    generation.character_name
                  }}</span>
                  <span v-if="generation.scene_name" class="scene"
                    >Scene: {{ generation.scene_name }}</span
                  >
                  <span class="date">{{
                    formatDate(generation.created_at)
                  }}</span>
                </div>

                <div
                  v-if="generation.consistency_score"
                  class="consistency-score"
                >
                  <span class="label">Consistency:</span>
                  <div class="score-bar">
                    <div
                      class="score-fill"
                      :style="{
                        width: generation.consistency_score * 100 + '%',
                      }"
                      :class="{
                        good: generation.consistency_score >= 0.75,
                        fair: generation.consistency_score >= 0.5,
                        poor: generation.consistency_score < 0.5,
                      }"
                    ></div>
                  </div>
                  <span class="score-value"
                    >{{
                      (generation.consistency_score * 100).toFixed(1)
                    }}%</span
                  >
                </div>
              </div>

              <div class="generation-actions">
                <button
                  v-if="generation.output_path"
                  class="btn-small"
                  @click="downloadGeneration(generation)"
                >
                  Download
                </button>
                <button class="btn-small" @click="useAsReference(generation)">
                  Use as Ref
                </button>
                <button
                  class="btn-small primary"
                  @click="regenerate(generation)"
                >
                  Regenerate
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Configuration Tab -->
        <div v-if="activeTab === 'configuration'" class="configuration-tab">
          <ProjectConfiguration
            :project="selectedProject"
            @updated="loadProjectDetails"
          />
        </div>

        <!-- Assets Tab -->
        <div v-if="activeTab === 'assets'" class="assets-tab">
          <ProjectAssets
            :project="selectedProject"
            @uploaded="loadProjectDetails"
          />
        </div>
      </div>
    </div>

    <!-- Create Project Modal -->
    <div
      v-if="showCreateModal"
      class="modal-overlay"
      @click="showCreateModal = false"
    >
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>Create New Project</h3>
          <button class="btn-icon" @click="showCreateModal = false">
            <i class="icon-close"></i>
          </button>
        </div>

        <form class="modal-body" @submit.prevent="createProject">
          <div class="form-group">
            <label>Project Name *</label>
            <input
              v-model="newProject.name"
              type="text"
              required
              placeholder="Enter project name"
            />
          </div>

          <div class="form-group">
            <label>Description</label>
            <textarea
              v-model="newProject.description"
              placeholder="Project description (optional)"
              rows="3"
            ></textarea>
          </div>

          <div class="form-group">
            <label>Art Style</label>
            <select v-model="newProject.style_guide.art_style">
              <option value="">Select style</option>
              <option value="anime">Anime</option>
              <option value="manga">Manga</option>
              <option value="realistic">Realistic</option>
              <option value="cartoon">Cartoon</option>
            </select>
          </div>

          <div class="form-group">
            <label>Color Palette</label>
            <select v-model="newProject.style_guide.color_palette">
              <option value="">Select palette</option>
              <option value="vibrant">Vibrant</option>
              <option value="pastel">Pastel</option>
              <option value="dark">Dark</option>
              <option value="monochrome">Monochrome</option>
            </select>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="btn-secondary"
              @click="showCreateModal = false"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="btn-primary"
              :disabled="!newProject.name"
            >
              Create Project
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Create Character Modal -->
    <div
      v-if="showCreateCharacterModal"
      class="modal-overlay"
      @click="showCreateCharacterModal = false"
    >
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>Add Character</h3>
          <button class="btn-icon" @click="showCreateCharacterModal = false">
            <i class="icon-close"></i>
          </button>
        </div>

        <form class="modal-body" @submit.prevent="createCharacter">
          <div class="form-group">
            <label>Character Name *</label>
            <input
              v-model="newCharacter.name"
              type="text"
              required
              placeholder="Enter character name"
            />
          </div>

          <div class="form-group">
            <label>Character Type</label>
            <select v-model="newCharacter.character_type">
              <option value="primary">Primary</option>
              <option value="secondary">Secondary</option>
              <option value="background">Background</option>
            </select>
          </div>

          <div class="form-group">
            <label>Base Prompt *</label>
            <textarea
              v-model="newCharacter.base_prompt"
              required
              placeholder="anime girl, blue hair, school uniform..."
              rows="3"
            ></textarea>
          </div>

          <div class="form-group">
            <label>Negative Prompt</label>
            <textarea
              v-model="newCharacter.negative_prompt"
              placeholder="low quality, blurry..."
              rows="2"
            ></textarea>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="btn-secondary"
              @click="showCreateCharacterModal = false"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="btn-primary"
              :disabled="!newCharacter.name || !newCharacter.base_prompt"
            >
              Add Character
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>{{ loadingMessage }}</p>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, computed } from "vue";
import { useProjectStore } from "../stores/projectStore";
import { useNotificationStore } from "../stores/notificationStore";
import ProjectConfiguration from "./ProjectConfiguration.vue";
import ProjectAssets from "./ProjectAssets.vue";

export default {
  name: "ProjectManager",
  components: {
    ProjectConfiguration,
    ProjectAssets,
  },
  setup() {
    const projectStore = useProjectStore();
    const notificationStore = useNotificationStore();

    // Reactive state
    const selectedProject = ref(null);
    const activeTab = ref("overview");
    const showCreateModal = ref(false);
    const showCreateCharacterModal = ref(false);
    const loading = ref(false);
    const loadingMessage = ref("");

    // Filters
    const generationFilter = ref("");
    const characterFilter = ref("");

    // Form data
    const newProject = ref({
      name: "",
      description: "",
      style_guide: {
        art_style: "",
        color_palette: "",
      },
      default_settings: {},
    });

    const newCharacter = ref({
      name: "",
      character_type: "primary",
      base_prompt: "",
      negative_prompt: "",
      personality_traits: {},
      appearance_config: {},
    });

    // Computed properties
    const projects = computed(() => projectStore.projects);
    const projectCharacters = computed(
      () => projectStore.selectedProjectCharacters,
    );
    const projectGenerations = computed(
      () => projectStore.selectedProjectGenerations,
    );

    const tabs = ref([
      { id: "overview", label: "Overview" },
      { id: "characters", label: "Characters" },
      { id: "generations", label: "Generations" },
      { id: "configuration", label: "Configuration" },
      { id: "assets", label: "Assets" },
    ]);

    // Methods
    const loadProjects = async () => {
      try {
        loading.value = true;
        loadingMessage.value = "Loading projects...";
        await projectStore.loadProjects();
      } catch (error) {
        notificationStore.addNotification("Failed to load projects", "error");
      } finally {
        loading.value = false;
      }
    };

    const selectProject = async (project) => {
      try {
        selectedProject.value = project;
        activeTab.value = "overview";
        await loadProjectDetails();
      } catch (error) {
        notificationStore.addNotification(
          "Failed to load project details",
          "error",
        );
      }
    };

    const loadProjectDetails = async () => {
      if (!selectedProject.value) return;

      try {
        loading.value = true;
        loadingMessage.value = "Loading project details...";

        // Load detailed project info
        const details = await projectStore.getProjectDetails(
          selectedProject.value.id,
        );
        selectedProject.value = details;

        // Load characters and generations
        await Promise.all([
          projectStore.loadProjectCharacters(selectedProject.value.id),
          projectStore.loadProjectGenerations(selectedProject.value.id),
        ]);
      } catch (error) {
        notificationStore.addNotification(
          "Failed to load project details",
          "error",
        );
      } finally {
        loading.value = false;
      }
    };

    const createProject = async () => {
      try {
        loading.value = true;
        loadingMessage.value = "Creating project...";

        await projectStore.createProject(newProject.value);

        showCreateModal.value = false;
        resetNewProject();

        notificationStore.addNotification(
          "Project created successfully",
          "success",
        );
        await loadProjects();
      } catch (error) {
        notificationStore.addNotification("Failed to create project", "error");
      } finally {
        loading.value = false;
      }
    };

    const createCharacter = async () => {
      try {
        loading.value = true;
        loadingMessage.value = "Adding character...";

        await projectStore.createCharacter(
          selectedProject.value.id,
          newCharacter.value,
        );

        showCreateCharacterModal.value = false;
        resetNewCharacter();

        notificationStore.addNotification(
          "Character added successfully",
          "success",
        );
        await loadProjectDetails();
      } catch (error) {
        notificationStore.addNotification("Failed to add character", "error");
      } finally {
        loading.value = false;
      }
    };

    const editProject = (project) => {
      // TODO: Implement edit project modal
      notificationStore.addNotification(
        "Edit project functionality coming soon",
        "info",
      );
    };

    const deleteProject = async (projectId) => {
      if (
        !confirm(
          "Are you sure you want to delete this project? This action cannot be undone.",
        )
      ) {
        return;
      }

      try {
        loading.value = true;
        loadingMessage.value = "Deleting project...";

        await projectStore.deleteProject(projectId);

        if (selectedProject.value?.id === projectId) {
          selectedProject.value = null;
        }

        notificationStore.addNotification(
          "Project deleted successfully",
          "success",
        );
        await loadProjects();
      } catch (error) {
        notificationStore.addNotification("Failed to delete project", "error");
      } finally {
        loading.value = false;
      }
    };

    const editCharacter = (character) => {
      // TODO: Implement edit character modal
      notificationStore.addNotification(
        "Edit character functionality coming soon",
        "info",
      );
    };

    const viewCharacterRefs = (character) => {
      // TODO: Implement character references viewer
      notificationStore.addNotification(
        "Character references viewer coming soon",
        "info",
      );
    };

    const generateCharacter = async (character) => {
      try {
        loading.value = true;
        loadingMessage.value = "Starting generation...";

        const generationData = {
          scene_id: null,
          character_id: character.id,
          generation_type: "image",
          prompt: character.base_prompt,
          negative_prompt: character.negative_prompt || "",
          generation_settings: {},
        };

        await projectStore.generateInProject(
          selectedProject.value.id,
          generationData,
        );
        notificationStore.addNotification("Generation started", "success");

        // Refresh generations after a delay
        setTimeout(async () => {
          await loadProjectDetails();
        }, 2000);
      } catch (error) {
        notificationStore.addNotification(
          "Failed to start generation",
          "error",
        );
      } finally {
        loading.value = false;
      }
    };

    const loadProjectGenerations = async () => {
      if (!selectedProject.value) return;

      try {
        const filters = {};
        if (generationFilter.value)
          filters.generation_type = generationFilter.value;
        if (characterFilter.value) filters.character_id = characterFilter.value;

        await projectStore.loadProjectGenerations(
          selectedProject.value.id,
          filters,
        );
      } catch (error) {
        notificationStore.addNotification(
          "Failed to load generations",
          "error",
        );
      }
    };

    const getGenerationPreview = (generation) => {
      if (!generation.output_path) return "";

      // Handle relative paths
      if (generation.output_path.startsWith("http")) {
        return generation.output_path;
      }

      return `/api/anime/image/${generation.job_id}`;
    };

    const handleImageError = (event) => {
      event.target.style.display = "none";
      if (event.target.nextElementSibling) {
        event.target.nextElementSibling.style.display = "flex";
      }
    };

    const downloadGeneration = (generation) => {
      if (generation.output_path) {
        const url =
          generation.generation_type === "video"
            ? `/api/anime/video/${generation.job_id}`
            : `/api/anime/image/${generation.job_id}`;

        window.open(url, "_blank");
      }
    };

    const useAsReference = (generation) => {
      // TODO: Implement use as reference functionality
      notificationStore.addNotification(
        "Use as reference functionality coming soon",
        "info",
      );
    };

    const regenerate = (generation) => {
      // TODO: Implement regenerate functionality
      notificationStore.addNotification(
        "Regenerate functionality coming soon",
        "info",
      );
    };

    const resetNewProject = () => {
      newProject.value = {
        name: "",
        description: "",
        style_guide: {
          art_style: "",
          color_palette: "",
        },
        default_settings: {},
      };
    };

    const resetNewCharacter = () => {
      newCharacter.value = {
        name: "",
        character_type: "primary",
        base_prompt: "",
        negative_prompt: "",
        personality_traits: {},
        appearance_config: {},
      };
    };

    const formatDate = (dateString) => {
      if (!dateString) return "Unknown";

      const date = new Date(dateString);
      return (
        date.toLocaleDateString() +
        " " +
        date.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })
      );
    };

    const truncateText = (text, maxLength) => {
      if (!text || text.length <= maxLength) return text;
      return text.substring(0, maxLength) + "...";
    };

    // Lifecycle
    onMounted(() => {
      loadProjects();
    });

    return {
      // State
      selectedProject,
      activeTab,
      showCreateModal,
      showCreateCharacterModal,
      loading,
      loadingMessage,
      generationFilter,
      characterFilter,
      newProject,
      newCharacter,

      // Computed
      projects,
      projectCharacters,
      projectGenerations,
      tabs,

      // Methods
      selectProject,
      loadProjectDetails,
      createProject,
      createCharacter,
      editProject,
      deleteProject,
      editCharacter,
      viewCharacterRefs,
      generateCharacter,
      loadProjectGenerations,
      getGenerationPreview,
      handleImageError,
      downloadGeneration,
      useAsReference,
      regenerate,
      formatDate,
      truncateText,
    };
  },
};
</script>

<style scoped>
.project-manager {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}

.header h1 {
  margin: 0;
  color: #333;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.project-card {
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.project-card:hover {
  border-color: #007bff;
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.1);
}

.project-card.selected {
  border-color: #007bff;
  background: #f8f9ff;
}

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.project-header h3 {
  margin: 0;
  color: #333;
  flex: 1;
}

.project-actions {
  display: flex;
  gap: 8px;
}

.project-description {
  color: #666;
  margin: 10px 0 15px 0;
  line-height: 1.4;
}

.project-stats {
  display: flex;
  gap: 20px;
  margin: 15px 0;
}

.stat {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: bold;
  color: #007bff;
}

.stat-label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
}

.project-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 15px;
  border-top: 1px solid #e0e0e0;
  margin-top: 15px;
}

.status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  text-transform: uppercase;
}

.status.active {
  background: #e8f5e8;
  color: #2e7d32;
}

.status.inactive {
  background: #ffebee;
  color: #c62828;
}

.date {
  font-size: 12px;
  color: #999;
}

.project-details {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin-top: 30px;
}

.details-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.details-header h2 {
  margin: 0;
  color: #333;
}

.details-tabs {
  display: flex;
  border-bottom: 1px solid #e0e0e0;
}

.tab-button {
  padding: 15px 25px;
  border: none;
  background: none;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
  border-bottom: 3px solid transparent;
}

.tab-button:hover {
  background: #f5f5f5;
}

.tab-button.active {
  border-bottom-color: #007bff;
  color: #007bff;
}

.tab-content {
  padding: 20px;
}

.overview-tab .info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.info-item label {
  display: block;
  font-weight: bold;
  color: #333;
  margin-bottom: 5px;
}

.info-item p {
  margin: 0;
  color: #666;
}

.style-guide {
  margin-top: 30px;
}

.style-guide h4 {
  margin: 0 0 15px 0;
  color: #333;
}

.style-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.style-tag {
  background: #e3f2fd;
  color: #1976d2;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 14px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h4 {
  margin: 0;
  color: #333;
}

.characters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 15px;
}

.character-card {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
  border: 1px solid #e0e0e0;
}

.character-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.character-header h5 {
  margin: 0;
  color: #333;
}

.character-type {
  background: #e0e0e0;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  text-transform: uppercase;
}

.character-prompt {
  color: #666;
  font-size: 14px;
  margin: 10px 0;
  line-height: 1.4;
}

.character-stats {
  display: flex;
  gap: 15px;
  margin: 10px 0;
  font-size: 12px;
  color: #999;
}

.character-actions {
  display: flex;
  gap: 8px;
  margin-top: 15px;
}

.generation-filters {
  display: flex;
  gap: 10px;
}

.generation-filters select {
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.generations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 15px;
}

.generation-card {
  background: #f8f9fa;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e0e0e0;
}

.generation-preview {
  height: 150px;
  background: #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.generation-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.video-preview,
.placeholder-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #666;
  text-align: center;
}

.video-preview i,
.placeholder-preview i {
  font-size: 24px;
  margin-bottom: 8px;
}

.generation-info {
  padding: 15px;
}

.generation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.generation-type {
  background: #e3f2fd;
  color: #1976d2;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  text-transform: uppercase;
}

.generation-prompt {
  color: #333;
  font-size: 14px;
  margin: 10px 0;
  line-height: 1.4;
}

.generation-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #666;
  margin: 10px 0;
}

.consistency-score {
  margin: 10px 0;
}

.consistency-score .label {
  font-size: 12px;
  color: #666;
  margin-right: 8px;
}

.score-bar {
  height: 4px;
  background: #e0e0e0;
  border-radius: 2px;
  overflow: hidden;
  margin: 4px 0;
}

.score-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.score-fill.good {
  background: #4caf50;
}
.score-fill.fair {
  background: #ff9800;
}
.score-fill.poor {
  background: #f44336;
}

.score-value {
  font-size: 12px;
  font-weight: bold;
  color: #333;
}

.generation-actions {
  display: flex;
  gap: 8px;
  padding: 15px;
  border-top: 1px solid #e0e0e0;
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  color: #333;
}

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
  color: #333;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
  margin-top: 20px;
}

/* Button styles */
.btn-primary {
  background: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background 0.3s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #0056b3;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background 0.3s ease;
}

.btn-secondary:hover {
  background: #545b62;
}

.btn-small {
  background: #f8f9fa;
  color: #333;
  border: 1px solid #ddd;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.3s ease;
}

.btn-small:hover {
  background: #e9ecef;
}

.btn-small.primary {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.btn-small.primary:hover {
  background: #0056b3;
}

.btn-icon {
  background: none;
  border: none;
  padding: 8px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.3s ease;
  color: #666;
}

.btn-icon:hover {
  background: #f5f5f5;
}

.btn-icon.danger:hover {
  background: #ffebee;
  color: #c62828;
}

/* Loading overlay */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #e0e0e0;
  border-top: 4px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 15px;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.loading-overlay p {
  color: #333;
  font-weight: 500;
}

/* Responsive design */
@media (max-width: 768px) {
  .project-grid {
    grid-template-columns: 1fr;
  }

  .characters-grid,
  .generations-grid {
    grid-template-columns: 1fr;
  }

  .details-tabs {
    overflow-x: auto;
  }

  .tab-button {
    white-space: nowrap;
  }
}
</style>
