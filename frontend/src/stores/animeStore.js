import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * Anime Production Store - Centralized state management for anime production workflows
 * Manages projects, characters, scenes, generation history, and Echo coordination
 */
export const useAnimeStore = defineStore("anime", () => {
  // ==================== STATE ====================

  // Project Management
  const projects = ref([]);
  const selectedProject = ref(null);
  const projectBibles = ref({}); // Map of project_id -> bible data

  // Character Management
  const characters = ref([]);
  const selectedCharacter = ref(null);
  const characterSheets = ref({}); // Map of character_name -> sheet data
  const characterConsistencyScores = ref({});

  // Scene Management
  const scenes = ref([]);
  const selectedScene = ref(null);
  const sceneTemplates = ref([]);

  // Generation Management
  const generationHistory = ref([]);
  const currentGeneration = ref(null);
  const generationQueue = ref([]);

  // WebSocket Management
  const wsConnection = ref(null);
  const wsConnected = ref(false);
  const jobProgress = ref({});
  const jobETAs = ref({});

  // Echo Coordination
  const echoCoordination = ref(null);
  const echoStatus = ref("disconnected");
  const echoMessages = ref([]);

  // UI State
  const loading = ref(false);
  const error = ref(null);
  const notifications = ref([]);
  const activeView = ref("console"); // console, studio, timeline

  // ==================== COMPUTED ====================

  const currentProjectBible = computed(() => {
    return selectedProject.value
      ? projectBibles.value[selectedProject.value.id]
      : null;
  });

  const currentProjectCharacters = computed(() => {
    return selectedProject.value
      ? characters.value.filter(
          (char) => char.project_id === selectedProject.value.id,
        )
      : [];
  });

  const currentProjectScenes = computed(() => {
    return selectedProject.value
      ? scenes.value.filter(
          (scene) => scene.project_id === selectedProject.value.id,
        )
      : [];
  });

  const recentGenerations = computed(() => {
    return generationHistory.value
      .filter((gen) =>
        selectedProject.value
          ? gen.project_id === selectedProject.value.id
          : true,
      )
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 10);
  });

  const generationStats = computed(() => {
    const total = generationHistory.value.length;
    const successful = generationHistory.value.filter(
      (gen) => gen.status === "completed",
    ).length;
    const failed = generationHistory.value.filter(
      (gen) => gen.status === "failed",
    ).length;
    const pending = generationHistory.value.filter(
      (gen) => gen.status === "pending",
    ).length;

    return {
      total,
      successful,
      failed,
      pending,
      successRate: total > 0 ? ((successful / total) * 100).toFixed(1) : 0,
    };
  });

  // ==================== ACTIONS ====================

  // Project Actions
  async function loadProjects() {
    try {
      loading.value = true;
      error.value = null;

      const response = await fetch("/api/anime/projects");
      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const data = await response.json();
      projects.value = data;

      addNotification("Projects loaded successfully", "success");
    } catch (err) {
      error.value = `Failed to load projects: ${err.message}`;
      addNotification(error.value, "error");
    } finally {
      loading.value = false;
    }
  }

  async function createProject(projectData) {
    try {
      loading.value = true;
      error.value = null;

      const response = await fetch("/api/anime/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projectData),
      });

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const newProject = await response.json();
      projects.value.push(newProject);
      selectedProject.value = newProject;

      addNotification(
        `Project "${newProject.name}" created successfully`,
        "success",
      );
      return newProject;
    } catch (err) {
      error.value = `Failed to create project: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function updateProject(projectId, updates) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const updatedProject = await response.json();
      const index = projects.value.findIndex((p) => p.id === projectId);
      if (index !== -1) {
        projects.value[index] = updatedProject;
        if (selectedProject.value?.id === projectId) {
          selectedProject.value = updatedProject;
        }
      }

      addNotification("Project updated successfully", "success");
      return updatedProject;
    } catch (err) {
      error.value = `Failed to update project: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    }
  }

  function selectProject(project) {
    selectedProject.value = project;
    // Load associated data
    if (project) {
      loadProjectBible(project.id);
      loadProjectCharacters(project.id);
      loadProjectScenes(project.id);
    }
  }

  // Project Bible Actions
  async function loadProjectBible(projectId) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible`);
      if (response.ok) {
        const bible = await response.json();
        projectBibles.value[projectId] = bible;
      } else if (response.status !== 404) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (err) {
      console.error(`Failed to load project bible: ${err.message}`);
    }
  }

  async function createProjectBible(projectId, bibleData) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bibleData),
      });

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const bible = await response.json();
      projectBibles.value[projectId] = bible;

      addNotification("Project bible created successfully", "success");
      return bible;
    } catch (err) {
      error.value = `Failed to create project bible: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    }
  }

  async function updateProjectBible(projectId, updates) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const updatedBible = await response.json();
      projectBibles.value[projectId] = updatedBible;

      addNotification("Project bible updated successfully", "success");
      return updatedBible;
    } catch (err) {
      error.value = `Failed to update project bible: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    }
  }

  // Character Actions
  async function loadProjectCharacters(projectId) {
    try {
      const response = await fetch(
        `/api/anime/projects/${projectId}/bible/characters`,
      );
      if (response.ok) {
        const projectCharacters = await response.json();
        // Update characters array with project characters
        characters.value = characters.value.filter(
          (char) => char.project_id !== projectId,
        );
        characters.value.push(
          ...projectCharacters.map((char) => ({
            ...char,
            project_id: projectId,
          })),
        );
      }
    } catch (err) {
      console.error(`Failed to load project characters: ${err.message}`);
    }
  }

  async function addCharacterToBible(projectId, characterData) {
    try {
      const response = await fetch(
        `/api/anime/projects/${projectId}/bible/characters`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(characterData),
        },
      );

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const newCharacter = await response.json();
      characters.value.push({ ...newCharacter, project_id: projectId });

      addNotification(
        `Character "${characterData.name}" added to project bible`,
        "success",
      );
      return newCharacter;
    } catch (err) {
      error.value = `Failed to add character: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    }
  }

  async function generateCharacterSheet(characterName, projectId) {
    try {
      loading.value = true;

      // Call Character Consistency Engine
      const response = await fetch(
        "/api/anime/character-consistency/generate-sheet",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            character_name: characterName,
            project_id: projectId,
          }),
        },
      );

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const characterSheet = await response.json();
      characterSheets.value[characterName] = characterSheet;

      addNotification(
        `Character sheet generated for ${characterName}`,
        "success",
      );
      return characterSheet;
    } catch (err) {
      error.value = `Failed to generate character sheet: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function validateCharacterConsistency(characterName, imagePath) {
    try {
      const response = await fetch(
        "/api/anime/character-consistency/validate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            character_name: characterName,
            image_path: imagePath,
          }),
        },
      );

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const validation = await response.json();
      characterConsistencyScores.value[characterName] =
        validation.consistency_score;

      const status = validation.status === "approved" ? "success" : "warning";
      addNotification(
        `Character validation: ${validation.consistency_score.toFixed(3)} - ${validation.status}`,
        status,
      );

      return validation;
    } catch (err) {
      error.value = `Failed to validate character: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    }
  }

  function selectCharacter(character) {
    selectedCharacter.value = character;
  }

  // Scene Actions
  async function loadProjectScenes(projectId) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/scenes`);
      if (response.ok) {
        const projectScenes = await response.json();
        scenes.value = scenes.value.filter(
          (scene) => scene.project_id !== projectId,
        );
        scenes.value.push(...projectScenes);
      }
    } catch (err) {
      console.error(`Failed to load project scenes: ${err.message}`);
    }
  }

  function selectScene(scene) {
    selectedScene.value = scene;
  }

  // Generation Actions
  async function startGeneration(generationRequest) {
    try {
      loading.value = true;

      const response = await fetch("/api/anime/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(generationRequest),
      });

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const generation = await response.json();
      generationHistory.value.unshift(generation);
      currentGeneration.value = generation;

      addNotification("Generation started successfully", "success");
      return generation;
    } catch (err) {
      error.value = `Failed to start generation: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function loadGenerationHistory() {
    try {
      const response = await fetch("/api/anime/generations");
      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const history = await response.json();
      generationHistory.value = history;
    } catch (err) {
      console.error(`Failed to load generation history: ${err.message}`);
    }
  }

  // Echo Brain Coordination
  async function connectToEcho() {
    try {
      const response = await fetch("/api/echo/health");
      if (response.ok) {
        echoStatus.value = "connected";
        addNotification("Connected to Echo Brain", "success");
        return true;
      } else {
        throw new Error("Echo Brain not available");
      }
    } catch (err) {
      echoStatus.value = "disconnected";
      console.error(`Failed to connect to Echo: ${err.message}`);
      return false;
    }
  }

  async function sendEchoMessage(message, context = "anime_production") {
    try {
      const response = await fetch("/api/echo/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: message,
          context: context,
          model: "qwen2.5-coder:32b",
        }),
      });

      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const echoResponse = await response.json();

      // Add to message history
      echoMessages.value.push({
        type: "user",
        content: message,
        timestamp: new Date().toISOString(),
      });

      echoMessages.value.push({
        type: "echo",
        content: echoResponse.response || echoResponse.result,
        timestamp: new Date().toISOString(),
      });

      return echoResponse;
    } catch (err) {
      error.value = `Failed to send Echo message: ${err.message}`;
      addNotification(error.value, "error");
      throw err;
    }
  }

  async function requestEchoCharacterGeneration(
    characterName,
    projectId,
    additionalInstructions = "",
  ) {
    const message = `Generate character ${characterName} for project ${selectedProject.value?.name || projectId}.
    
Project context: ${currentProjectBible.value?.description || "No project bible available"}
Character requirements: Use project bible specifications
Additional instructions: ${additionalInstructions}`;

    return await sendEchoMessage(message, "character_generation");
  }

  async function requestEchoSceneGeneration(sceneDescription, characters = []) {
    const message = `Generate scene: ${sceneDescription}
    
Project: ${selectedProject.value?.name || "Unknown"}
Characters involved: ${characters.join(", ")}
Project context: ${currentProjectBible.value?.description || "No project bible available"}`;

    return await sendEchoMessage(message, "scene_generation");
  }

  // Utility Actions
  function addNotification(message, type = "info", duration = 5000) {
    const notification = {
      id: Date.now() + Math.random(),
      message,
      type,
      timestamp: new Date().toISOString(),
    };

    notifications.value.push(notification);

    // Auto-remove after duration
    setTimeout(() => {
      removeNotification(notification.id);
    }, duration);

    return notification;
  }

  function removeNotification(id) {
    const index = notifications.value.findIndex((n) => n.id === id);
    if (index !== -1) {
      notifications.value.splice(index, 1);
    }
  }

  function clearError() {
    error.value = null;
  }

  function setActiveView(view) {
    activeView.value = view;
  }

  // Reset Functions
  function resetStore() {
    projects.value = [];
    selectedProject.value = null;
    projectBibles.value = {};
    characters.value = [];
    selectedCharacter.value = null;
    characterSheets.value = {};
    characterConsistencyScores.value = {};
    scenes.value = [];
    selectedScene.value = null;
    generationHistory.value = [];
    currentGeneration.value = null;
    echoMessages.value = [];
    notifications.value = [];
    error.value = null;
  }

  // ==================== RETURN STORE ====================

  return {
    // State
    projects,
    selectedProject,
    projectBibles,
    characters,
    selectedCharacter,
    characterSheets,
    characterConsistencyScores,
    scenes,
    selectedScene,
    sceneTemplates,
    generationHistory,
    currentGeneration,
    generationQueue,
    echoCoordination,
    echoStatus,
    echoMessages,
    loading,
    error,
    notifications,
    activeView,

    // Computed
    currentProjectBible,
    currentProjectCharacters,
    currentProjectScenes,
    recentGenerations,
    generationStats,

    // Actions
    loadProjects,
    createProject,
    updateProject,
    selectProject,
    loadProjectBible,
    createProjectBible,
    updateProjectBible,
    loadProjectCharacters,
    addCharacterToBible,
    generateCharacterSheet,
    validateCharacterConsistency,
    selectCharacter,
    loadProjectScenes,
    selectScene,
    startGeneration,
    loadGenerationHistory,
    connectToEcho,
    sendEchoMessage,
    requestEchoCharacterGeneration,
    requestEchoSceneGeneration,
    addNotification,
    removeNotification,
    clearError,
    setActiveView,
    resetStore,
  };
});
