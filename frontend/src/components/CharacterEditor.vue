<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <h2>{{ characterKey ? "Edit Character" : "Add Character" }}</h2>

      <div class="form-grid">
        <div class="form-group">
          <label>Name</label>
          <input v-model="localChar.name" />
        </div>

        <div class="form-group">
          <label>Archetype</label>
          <input v-model="localChar.archetype" />
        </div>

        <div class="form-group">
          <label>Hair</label>
          <input v-model="localChar.appearance.hair" />
        </div>

        <div class="form-group">
          <label>Eyes</label>
          <input v-model="localChar.appearance.eyes" />
        </div>

        <div class="form-group full-width">
          <label>Figure</label>
          <textarea v-model="localChar.appearance.figure" rows="3"></textarea>
        </div>

        <div class="form-group">
          <label>Height</label>
          <input v-model="localChar.appearance.height" />
        </div>

        <div class="form-group">
          <label>Style</label>
          <input v-model="localChar.appearance.style" />
        </div>

        <div class="form-group full-width">
          <label>Prompt Base</label>
          <textarea v-model="localChar.prompt_base" rows="4"></textarea>
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn btn-primary" @click="save">Save</button>
        <button class="btn" @click="$emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  character: Object,
  characterKey: String,
});

const emit = defineEmits(["save", "close"]);

const localChar = ref({
  name: "",
  archetype: "",
  appearance: {
    hair: "",
    eyes: "",
    figure: "",
    height: "",
    style: "",
  },
  outfits: {
    casual: "",
    home: "",
    sleepwear: "",
    work: "",
  },
  personality: "",
  prompt_base: "",
});

watch(
  () => props.character,
  (newChar) => {
    if (newChar) {
      localChar.value = JSON.parse(JSON.stringify(newChar));
    }
  },
  { immediate: true },
);

function save() {
  const key =
    props.characterKey ||
    localChar.value.name.toLowerCase().replace(/\s+/g, "_");
  emit("save", key, localChar.value);
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 2rem;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  color: #e0e0e0;
}

.modal h2 {
  color: #e0e0e0;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  margin-bottom: 1.5rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin: 2rem 0;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #999;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.form-group input,
.form-group textarea {
  padding: 0.75rem;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  color: #e0e0e0;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.9rem;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #4a90e2;
  background: #2a2a2a;
}

.modal-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}
</style>
