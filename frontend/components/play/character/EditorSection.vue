<template>
  <transition name="section-slide" mode="out-in">
    <div :key="part" class="editor-section">
      <!-- Identity -->
      <template v-if="part === 'identity'">
        <FieldGroup label="Description">
          <textarea
            :value="character?.description || ''"
            @input="emitIdentity('description', ($event.target as HTMLTextAreaElement).value)"
            rows="3"
            placeholder="Character description..."
          />
        </FieldGroup>
        <FieldGroup label="Personality">
          <textarea
            :value="character?.personality || ''"
            @input="emitIdentity('personality', ($event.target as HTMLTextAreaElement).value)"
            rows="2"
            placeholder="Personality traits..."
          />
        </FieldGroup>
        <FieldGroup label="Background">
          <textarea
            :value="character?.background || ''"
            @input="emitIdentity('background', ($event.target as HTMLTextAreaElement).value)"
            rows="2"
            placeholder="Character background..."
          />
        </FieldGroup>
        <div class="field-row">
          <FieldGroup label="Age" class="field-half">
            <input
              type="number"
              :value="character?.age ?? ''"
              @input="emitIdentity('age', Number(($event.target as HTMLInputElement).value) || null)"
              placeholder="—"
            />
          </FieldGroup>
          <FieldGroup label="Role" class="field-half">
            <input
              type="text"
              :value="character?.character_role || ''"
              @input="emitIdentity('character_role', ($event.target as HTMLInputElement).value)"
              placeholder="protagonist, villain..."
            />
          </FieldGroup>
        </div>
      </template>

      <!-- Hair -->
      <template v-else-if="part === 'hair'">
        <FieldGroup label="Color">
          <input type="text" :value="getField('hair.color')" @input="setField('hair.color', $event)" placeholder="blonde, dark blue..." />
        </FieldGroup>
        <FieldGroup label="Style">
          <input type="text" :value="getField('hair.style')" @input="setField('hair.style', $event)" placeholder="twin tails, short bob..." />
        </FieldGroup>
        <FieldGroup label="Length">
          <input type="text" :value="getField('hair.length')" @input="setField('hair.length', $event)" placeholder="long, shoulder-length..." />
        </FieldGroup>
      </template>

      <!-- Eyes -->
      <template v-else-if="part === 'eyes'">
        <FieldGroup label="Color">
          <input type="text" :value="getField('eyes.color')" @input="setField('eyes.color', $event)" placeholder="amber, heterochromia..." />
        </FieldGroup>
        <FieldGroup label="Shape">
          <input type="text" :value="getField('eyes.shape')" @input="setField('eyes.shape', $event)" placeholder="almond, wide..." />
        </FieldGroup>
        <FieldGroup label="Special">
          <input type="text" :value="getField('eyes.special')" @input="setField('eyes.special', $event)" placeholder="glowing, cat pupils..." />
        </FieldGroup>
      </template>

      <!-- Face -->
      <template v-else-if="part === 'face'">
        <FieldGroup label="Shape">
          <input type="text" :value="getField('face.shape')" @input="setField('face.shape', $event)" placeholder="heart, oval..." />
        </FieldGroup>
        <FieldGroup label="Features">
          <input type="text" :value="getField('face.features')" @input="setField('face.features', $event)" placeholder="sharp jawline, freckles..." />
        </FieldGroup>
      </template>

      <!-- Skin -->
      <template v-else-if="part === 'skin'">
        <FieldGroup label="Tone">
          <input type="text" :value="getField('skin.tone')" @input="setField('skin.tone', $event)" placeholder="pale, olive, dark..." />
        </FieldGroup>
        <FieldGroup label="Markings">
          <input type="text" :value="getField('skin.markings')" @input="setField('skin.markings', $event)" placeholder="tattoo, scars, birthmark..." />
        </FieldGroup>
      </template>

      <!-- Body -->
      <template v-else-if="part === 'body'">
        <FieldGroup label="Build">
          <input type="text" :value="getField('body.build')" @input="setField('body.build', $event)" placeholder="athletic, slender..." />
        </FieldGroup>
        <FieldGroup label="Height">
          <input type="text" :value="getField('body.height')" @input="setField('body.height', $event)" placeholder="tall, petite..." />
        </FieldGroup>
        <div class="field-row">
          <FieldGroup label="Body Type" class="field-half">
            <input type="text" :value="appearance?.body_type || ''" @input="setTopLevel('body_type', $event)" placeholder="—" />
          </FieldGroup>
          <FieldGroup label="Species" class="field-half">
            <input type="text" :value="appearance?.species || ''" @input="setTopLevel('species', $event)" placeholder="human, elf..." />
          </FieldGroup>
        </div>
      </template>

      <!-- Outfit -->
      <template v-else-if="part === 'outfit'">
        <FieldGroup label="Default Outfit">
          <textarea
            :value="getField('clothing.default_outfit')"
            @input="setField('clothing.default_outfit', $event)"
            rows="3"
            placeholder="school uniform, armor set..."
          />
        </FieldGroup>
        <FieldGroup label="Style">
          <input type="text" :value="getField('clothing.style')" @input="setField('clothing.style', $event)" placeholder="gothic, casual..." />
        </FieldGroup>
      </template>

      <!-- Weapons -->
      <template v-else-if="part === 'weapons'">
        <div v-if="weaponsList.length === 0" class="empty-state">
          No weapons defined
        </div>
        <div v-for="(w, i) in weaponsList" :key="i" class="weapon-card">
          <FieldGroup label="Name">
            <input type="text" :value="w.name || ''" @input="updateWeapon(i, 'name', ($event.target as HTMLInputElement).value)" />
          </FieldGroup>
          <FieldGroup label="Type">
            <input type="text" :value="w.type || ''" @input="updateWeapon(i, 'type', ($event.target as HTMLInputElement).value)" />
          </FieldGroup>
          <FieldGroup label="Description">
            <input type="text" :value="w.description || ''" @input="updateWeapon(i, 'description', ($event.target as HTMLInputElement).value)" />
          </FieldGroup>
          <button class="remove-btn" @click="removeWeapon(i)">&times; Remove</button>
        </div>
        <button class="add-btn" @click="addWeapon">+ Add Weapon</button>
      </template>

      <!-- Accessories -->
      <template v-else-if="part === 'accessories'">
        <div class="tags-editor">
          <span
            v-for="(acc, i) in accessoriesList"
            :key="i"
            class="tag"
          >
            {{ acc }}
            <button class="tag-remove" @click="removeAccessory(i)">&times;</button>
          </span>
          <input
            type="text"
            class="tag-input"
            placeholder="Add accessory..."
            @keydown.enter.prevent="addAccessory($event)"
          />
        </div>
      </template>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BodyPart } from '@/stores/characterViewer'
import type { Character, AppearanceData } from '@/types'
import FieldGroup from './FieldGroup.vue'

const props = defineProps<{
  part: BodyPart
  appearance: AppearanceData
  character: Character | null
}>()

const emit = defineEmits<{
  'update:appearance': [path: string, value: any]
  'update:identity': [field: string, value: any]
}>()

function getField(path: string): string {
  const keys = path.split('.')
  let obj: any = props.appearance
  for (const k of keys) {
    if (!obj || typeof obj !== 'object') return ''
    obj = obj[k]
  }
  return typeof obj === 'string' ? obj : ''
}

function setField(path: string, event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:appearance', path, value)
}

function setTopLevel(field: string, event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:appearance', field, value)
}

function emitIdentity(field: string, value: any) {
  emit('update:identity', field, value)
}

// Weapons
const weaponsList = computed(() => {
  const w = props.appearance?.weapons
  return Array.isArray(w) ? w : []
})

function updateWeapon(index: number, field: string, value: string) {
  const weapons = [...weaponsList.value]
  weapons[index] = { ...weapons[index], [field]: value }
  emit('update:appearance', 'weapons', weapons)
}

function addWeapon() {
  const weapons = [...weaponsList.value, { name: '', type: '', description: '' }]
  emit('update:appearance', 'weapons', weapons)
}

function removeWeapon(index: number) {
  const weapons = weaponsList.value.filter((_, i) => i !== index)
  emit('update:appearance', 'weapons', weapons)
}

// Accessories
const accessoriesList = computed(() => {
  const a = props.appearance?.accessories
  return Array.isArray(a) ? a : []
})

function addAccessory(event: Event) {
  const input = event.target as HTMLInputElement
  const val = input.value.trim()
  if (!val) return
  const accs = [...accessoriesList.value, val]
  emit('update:appearance', 'accessories', accs)
  input.value = ''
}

function removeAccessory(index: number) {
  const accs = accessoriesList.value.filter((_, i) => i !== index)
  emit('update:appearance', 'accessories', accs)
}
</script>

<style scoped>
.editor-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-row {
  display: flex;
  gap: 12px;
}

.field-half {
  flex: 1;
}

textarea, input[type="text"], input[type="number"] {
  width: 100%;
  padding: 8px 12px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  color: var(--text-primary, #e8e8e8);
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.2s ease, background 0.2s ease;
  box-sizing: border-box;
}

textarea:focus, input:focus {
  outline: none;
  border-color: rgba(99,102,241,0.5);
  background: rgba(99,102,241,0.06);
}

/* Weapons */
.weapon-card {
  padding: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.remove-btn {
  align-self: flex-end;
  background: none;
  border: none;
  color: #f07070;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 6px;
  font-family: inherit;
}

.add-btn {
  padding: 8px 14px;
  background: rgba(99,102,241,0.1);
  border: 1px dashed rgba(99,102,241,0.3);
  border-radius: 8px;
  color: var(--accent-primary, #6366f1);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.2s ease;
}

.add-btn:hover {
  background: rgba(99,102,241,0.18);
}

/* Tags (accessories) */
.tags-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  min-height: 44px;
}

.tag {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: rgba(99,102,241,0.12);
  border-radius: 14px;
  color: var(--text-primary, #e8e8e8);
  font-size: 12px;
}

.tag-remove {
  background: none;
  border: none;
  color: var(--text-muted, #888);
  cursor: pointer;
  font-size: 14px;
  padding: 0;
  line-height: 1;
}

.tag-input {
  flex: 1;
  min-width: 100px;
  background: none !important;
  border: none !important;
  padding: 4px !important;
  font-size: 12px;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-muted, #666);
  font-size: 13px;
}

/* Transition */
.section-slide-enter-active,
.section-slide-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.section-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.section-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
