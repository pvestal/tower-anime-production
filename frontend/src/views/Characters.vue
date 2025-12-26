<template>
  <div class="characters-view">
    <div class="header">
      <h1>Characters</h1>
      <button class="btn btn-primary" @click="showEditor = true">
        Add Character
      </button>
    </div>

    <div class="characters-grid">
      <div
        v-for="(char, key) in store.characters"
        :key="key"
        class="character-card"
      >
        <h3>{{ char.name }}</h3>
        <div class="character-info">
          <div class="info-row">
            <strong>Archetype:</strong> {{ char.archetype }}
          </div>
          <div class="info-row">
            <strong>Height:</strong> {{ char.appearance.height }}
          </div>
          <div class="info-row">
            <strong>Figure:</strong> {{ char.appearance.figure }}
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-sm" @click="editCharacter(key, char)">
            Edit
          </button>
          <button class="btn btn-sm btn-danger" @click="deleteChar(key)">
            Delete
          </button>
        </div>
      </div>
    </div>

    <CharacterEditor
      v-if="showEditor"
      :character="currentCharacter"
      :character-key="currentKey"
      @save="saveCharacter"
      @close="showEditor = false"
    />
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useCharacterStore } from "@/stores/characterStore";
import CharacterEditor from "@/components/CharacterEditor.vue";

const store = useCharacterStore();
const showEditor = ref(false);
const currentCharacter = ref(null);
const currentKey = ref(null);

function editCharacter(key, char) {
  currentKey.value = key;
  currentCharacter.value = { ...char };
  showEditor.value = true;
}

async function saveCharacter(key, character) {
  await store.saveCharacter(key, character);
  showEditor.value = false;
}

async function deleteChar(key) {
  if (confirm(`Delete ${store.characters[key].name}?`)) {
    // Add delete functionality
  }
}
</script>

<style scoped>
.characters-view {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  border-radius: 8px;
  padding: 2rem;
  border: 1px solid #4a4a4a;
  min-height: 100vh;
  color: #ffffff;
}

h1 {
  color: #7b68ee;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 1.5rem;
  text-shadow: 0 0 10px rgba(123, 104, 238, 0.3);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.characters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
}

.character-card {
  background: rgba(45, 45, 45, 0.8);
  border-radius: 6px;
  padding: 1.5rem;
  border: 1px solid #4a4a4a;
  transition: all 0.2s;
}

.character-card:hover {
  border-color: #7b68ee;
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(123, 104, 238, 0.2);
}

.character-card h3 {
  color: #7b68ee;
  margin-bottom: 1rem;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
}

.info-row {
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
  color: #cccccc;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
}

.info-row strong {
  color: #ffffff;
}

.card-actions {
  margin-top: 1rem;
  display: flex;
  gap: 0.5rem;
}

.btn {
  padding: 0.5rem 1rem;
  border: 1px solid #4a4a4a;
  border-radius: 6px;
  cursor: pointer;
  background: #2a2a2a;
  color: #ffffff;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.85rem;
  transition: all 0.2s;
  font-weight: 500;
}

.btn:hover {
  background: #3a3a3a;
  border-color: #7b68ee;
  color: #7b68ee;
}

.btn-primary {
  border-color: #7b68ee;
  background: #7b68ee;
  color: #1a1a1a;
}

.btn-primary:hover {
  background: #9b8aff;
  color: #1a1a1a;
}

.btn-sm {
  padding: 0.3rem 0.8rem;
  font-size: 0.8rem;
}

.btn-danger {
  border-color: #dc3545;
  color: #dc3545;
}

.btn-danger:hover {
  background: #dc3545;
  color: #1a1a1a;
}
</style>
