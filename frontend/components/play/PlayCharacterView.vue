<template>
  <div class="play-character-view">
    <!-- Left: Canvas -->
    <div class="canvas-panel">
      <CharacterCanvas
        :portrait-url="store.portraitUrl"
        :name="store.name"
        :slug="store.slug"
        :active-part="store.activePart"
        :generating="store.generating"
        @select-part="store.setActivePart($event)"
        @generate="store.generatePortrait()"
      />
    </div>

    <!-- Right: Editor -->
    <div class="editor-panel">
      <CharacterEditor
        v-model:active-part="activePart"
        :characters="store.characters"
        :selected-slug="store.slug"
        :character="store.character"
        :appearance="store.appearance"
        :dirty="store.dirty"
        :saving="store.saving"
        @select="handleSelect"
        @save="store.save()"
        @update:appearance="(path: string, value: any) => store.updateAppearanceField(path, value)"
        @update:identity="(field: string, value: any) => store.updateIdentityField(field, value)"
      />
    </div>

    <!-- Back button -->
    <button class="back-btn" @click="handleBack" title="Back to Play">
      &#x2190; Back
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useCharacterViewerStore, type BodyPart } from '@/stores/characterViewer'
import CharacterCanvas from './character/CharacterCanvas.vue'
import CharacterEditor from './character/CharacterEditor.vue'

const emit = defineEmits<{ back: [] }>()
const store = useCharacterViewerStore()

const activePart = computed({
  get: () => store.activePart,
  set: (v: BodyPart) => store.setActivePart(v),
})

onMounted(() => {
  store.loadCharacters()
})

onUnmounted(() => {
  store.reset()
})

async function handleSelect(slug: string) {
  await store.selectCharacter(slug)
}

function handleBack() {
  store.reset()
  emit('back')
}
</script>

<style scoped>
.play-character-view {
  display: flex;
  height: calc(100vh - 100px);
  position: relative;
}

.canvas-panel {
  flex: 0 0 420px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 20px;
  border-right: 1px solid rgba(255,255,255,0.06);
  overflow-y: auto;
}

.editor-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.back-btn {
  position: absolute;
  top: 12px;
  left: 12px;
  padding: 6px 14px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  color: var(--text-muted, #aaa);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.2s ease;
  z-index: 10;
}

.back-btn:hover {
  background: rgba(255,255,255,0.1);
  color: var(--text-primary, #e8e8e8);
}
</style>
