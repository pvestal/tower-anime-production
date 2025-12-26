import { defineStore } from "pinia";
import { ref, reactive } from "vue";
import axios from "axios";

const API_BASE = "/api/anime";

export const useProjectStore = defineStore("project", () => {
  // State
  const projects = ref([]);
  const currentProject = ref(null);
  const characters = ref([]);
  const generations = ref([]);
  const scenes = ref([]);
  const loading = ref(false);
  const error = ref(null);

  // Project Management
  const loadProjects = async () => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.get(`${API_BASE}/projects/`);
      projects.value = response.data.projects || [];
    } catch (err) {
      error.value = `Failed to load projects: ${err.response?.data?.detail || err.message}`;
      console.error("Error loading projects:", err);
    } finally {
      loading.value = false;
    }
  };

  const createProject = async (projectData) => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.post(`${API_BASE}/projects/`, projectData);
      const newProject = response.data;
      projects.value.push(newProject);
      return newProject;
    } catch (err) {
      error.value = `Failed to create project: ${err.response?.data?.detail || err.message}`;
      console.error("Error creating project:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const updateProject = async (projectId, updates) => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.patch(
        `${API_BASE}/projects/${projectId}`,
        updates,
      );
      const updatedProject = response.data;
      const index = projects.value.findIndex((p) => p.id === projectId);
      if (index !== -1) {
        projects.value[index] = updatedProject;
      }
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject;
      }
      return updatedProject;
    } catch (err) {
      error.value = `Failed to update project: ${err.response?.data?.detail || err.message}`;
      console.error("Error updating project:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const deleteProject = async (projectId) => {
    loading.value = true;
    error.value = null;
    try {
      await axios.delete(`${API_BASE}/projects/${projectId}`);
      projects.value = projects.value.filter((p) => p.id !== projectId);
      if (currentProject.value?.id === projectId) {
        currentProject.value = null;
      }
    } catch (err) {
      error.value = `Failed to delete project: ${err.response?.data?.detail || err.message}`;
      console.error("Error deleting project:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const selectProject = async (project) => {
    currentProject.value = project;
    if (project) {
      await loadProjectCharacters(project.id);
      await loadProjectGenerations(project.id);
    } else {
      characters.value = [];
      generations.value = [];
      scenes.value = [];
    }
  };

  // Character Management
  const loadProjectCharacters = async (projectId) => {
    if (!projectId) return;
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.get(
        `${API_BASE}/projects/${projectId}/characters`,
      );
      characters.value = response.data.characters || [];
    } catch (err) {
      error.value = `Failed to load characters: ${err.response?.data?.detail || err.message}`;
      console.error("Error loading characters:", err);
    } finally {
      loading.value = false;
    }
  };

  const createCharacter = async (projectId, characterData) => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.post(
        `${API_BASE}/projects/${projectId}/characters`,
        characterData,
      );
      const newCharacter = response.data;
      characters.value.push(newCharacter);
      return newCharacter;
    } catch (err) {
      error.value = `Failed to create character: ${err.response?.data?.detail || err.message}`;
      console.error("Error creating character:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const updateCharacter = async (projectId, characterId, updates) => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.patch(
        `${API_BASE}/projects/${projectId}/characters/${characterId}`,
        updates,
      );
      const updatedCharacter = response.data;
      const index = characters.value.findIndex((c) => c.id === characterId);
      if (index !== -1) {
        characters.value[index] = updatedCharacter;
      }
      return updatedCharacter;
    } catch (err) {
      error.value = `Failed to update character: ${err.response?.data?.detail || err.message}`;
      console.error("Error updating character:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const deleteCharacter = async (projectId, characterId) => {
    loading.value = true;
    error.value = null;
    try {
      await axios.delete(
        `${API_BASE}/projects/${projectId}/characters/${characterId}`,
      );
      characters.value = characters.value.filter((c) => c.id !== characterId);
    } catch (err) {
      error.value = `Failed to delete character: ${err.response?.data?.detail || err.message}`;
      console.error("Error deleting character:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  // Generation Management
  const loadProjectGenerations = async (projectId) => {
    if (!projectId) return;
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.get(
        `${API_BASE}/projects/${projectId}/generations`,
      );
      generations.value = response.data.generations || [];
    } catch (err) {
      error.value = `Failed to load generations: ${err.response?.data?.detail || err.message}`;
      console.error("Error loading generations:", err);
    } finally {
      loading.value = false;
    }
  };

  const generateInProject = async (projectId, generationData) => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.post(
        `${API_BASE}/projects/${projectId}/generate`,
        generationData,
      );
      const generation = response.data;
      generations.value.unshift(generation);
      return generation;
    } catch (err) {
      error.value = `Failed to generate: ${err.response?.data?.detail || err.message}`;
      console.error("Error generating:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  // Scene Management
  const loadProjectScenes = async (projectId) => {
    if (!projectId) return;
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.get(
        `${API_BASE}/projects/${projectId}/scenes`,
      );
      scenes.value = response.data.scenes || [];
    } catch (err) {
      error.value = `Failed to load scenes: ${err.response?.data?.detail || err.message}`;
      console.error("Error loading scenes:", err);
    } finally {
      loading.value = false;
    }
  };

  const createScene = async (projectId, sceneData) => {
    loading.value = true;
    error.value = null;
    try {
      const response = await axios.post(
        `${API_BASE}/projects/${projectId}/scenes`,
        sceneData,
      );
      const newScene = response.data;
      scenes.value.push(newScene);
      return newScene;
    } catch (err) {
      error.value = `Failed to create scene: ${err.response?.data?.detail || err.message}`;
      console.error("Error creating scene:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  };

  // Utility methods
  const clearError = () => {
    error.value = null;
  };

  const getProjectById = (projectId) => {
    return projects.value.find((p) => p.id === projectId);
  };

  const getCharacterById = (characterId) => {
    return characters.value.find((c) => c.id === characterId);
  };

  return {
    // State
    projects,
    currentProject,
    characters,
    generations,
    scenes,
    loading,
    error,

    // Project Methods
    loadProjects,
    createProject,
    updateProject,
    deleteProject,
    selectProject,

    // Character Methods
    loadProjectCharacters,
    createCharacter,
    updateCharacter,
    deleteCharacter,

    // Generation Methods
    loadProjectGenerations,
    generateInProject,

    // Scene Methods
    loadProjectScenes,
    createScene,

    // Utility Methods
    clearError,
    getProjectById,
    getCharacterById,
  };
});
