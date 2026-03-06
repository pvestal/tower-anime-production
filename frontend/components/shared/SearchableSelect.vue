<template>
  <div class="ss-wrapper" ref="wrapperEl">
    <input
      ref="inputEl"
      class="ss-input"
      :placeholder="placeholder"
      :value="searchable ? query : selectedLabel"
      @input="onInput"
      @focus="onFocus"
      @keydown="onKeydown"
      autocomplete="off"
    />
    <div v-if="dropdownOpen && filtered.length > 0" class="ss-dropdown">
      <div
        v-for="(opt, i) in filtered"
        :key="opt.value ?? '__empty__'"
        class="ss-option"
        :class="{ highlighted: i === highlightIdx, selected: opt.value === modelValue }"
        @mousedown.prevent="selectOption(opt)"
        @mouseenter="highlightIdx = i"
      >
        <span class="ss-option-label">{{ opt.label }}</span>
        <span v-if="opt.detail" class="ss-option-detail">{{ opt.detail }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

export interface SearchableOption {
  value: string | number | null
  label: string
  detail?: string
}

const props = withDefaults(defineProps<{
  modelValue: string | number | null
  options: SearchableOption[]
  placeholder?: string
  searchable?: boolean
}>(), {
  placeholder: 'Select...',
  searchable: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number | null]
}>()

const wrapperEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)
const dropdownOpen = ref(false)
const query = ref('')
const highlightIdx = ref(0)

const selectedLabel = computed(() => {
  const opt = props.options.find(o => o.value === props.modelValue)
  return opt?.label ?? ''
})

const filtered = computed(() => {
  if (!props.searchable || !query.value) return props.options
  const q = query.value.toLowerCase()
  return props.options.filter(o =>
    o.label.toLowerCase().includes(q) ||
    (o.detail && o.detail.toLowerCase().includes(q))
  )
})

function onInput(e: Event) {
  query.value = (e.target as HTMLInputElement).value
  highlightIdx.value = 0
  dropdownOpen.value = true
}

function onFocus() {
  query.value = ''
  dropdownOpen.value = true
  highlightIdx.value = 0
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlightIdx.value = Math.min(highlightIdx.value + 1, filtered.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlightIdx.value = Math.max(highlightIdx.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (filtered.value[highlightIdx.value]) {
      selectOption(filtered.value[highlightIdx.value])
    }
  } else if (e.key === 'Escape') {
    dropdownOpen.value = false
    inputEl.value?.blur()
  }
}

function selectOption(opt: SearchableOption) {
  emit('update:modelValue', opt.value)
  dropdownOpen.value = false
  query.value = ''
}

function onClickOutside(e: MouseEvent) {
  if (wrapperEl.value && !wrapperEl.value.contains(e.target as Node)) {
    dropdownOpen.value = false
    query.value = ''
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))

watch(() => props.modelValue, () => {
  query.value = ''
})
</script>

<style scoped>
.ss-wrapper {
  position: relative;
  width: 100%;
}

.ss-input {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
  box-sizing: border-box;
}

.ss-input:focus {
  border-color: var(--border-focus);
  outline: none;
}

.ss-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  max-height: 240px;
  overflow-y: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-top: none;
  border-radius: 0 0 3px 3px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.ss-option {
  padding: 6px 10px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.ss-option:hover,
.ss-option.highlighted {
  background: var(--bg-hover, rgba(122, 162, 247, 0.08));
}

.ss-option.selected {
  color: var(--accent-primary);
  font-weight: 500;
}

.ss-option-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ss-option-detail {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: 8px;
  flex-shrink: 0;
}
</style>
