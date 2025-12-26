import { defineStore } from "pinia";
import api from "@/api/animeApi";

export const useCharacterStore = defineStore("characters", {
  state: () => ({
    characters: {},
    settings: {},
    styles: [],
    models: [],
    queue: { queue_running: [], queue_pending: [] },
    loading: false,
    error: null,
  }),

  actions: {
    async loadCharacters() {
      this.loading = true;
      try {
        const response = await api.getCharacters();
        this.characters = response.data.characters || {};
        this.settings = response.data.generation_settings || {};
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },

    async saveCharacter(key, character) {
      try {
        await api.updateCharacter(key, character);
        await this.loadCharacters();
        return true;
      } catch (error) {
        this.error = error.message;
        return false;
      }
    },

    async loadStyles() {
      try {
        const response = await api.getStyles();
        this.styles = response.data;
      } catch (error) {
        this.error = error.message;
      }
    },

    async loadModels() {
      try {
        const response = await api.getModels();
        this.models = response.data;
      } catch (error) {
        this.error = error.message;
      }
    },

    async generateImage(request) {
      try {
        const response = await api.generate(request);
        return response.data;
      } catch (error) {
        this.error = error.message;
        throw error;
      }
    },

    async updateQueue() {
      try {
        const response = await api.getQueue();
        this.queue = response.data;
      } catch (error) {
        console.error("Queue update failed:", error);
      }
    },
  },
});
