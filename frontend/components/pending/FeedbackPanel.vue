<template>
  <div class="feedback-panel">
    <!-- Phase 1: Rating + categories + text -->
    <div v-if="phase === 'input'" class="feedback-input">
      <div class="star-rating">
        <span
          v-for="s in 5"
          :key="s"
          class="star"
          :class="{ active: s <= rating }"
          @click="rating = s"
        >&#9733;</span>
        <span class="star-label">Rate this shot</span>
      </div>

      <div class="category-chips">
        <button
          v-for="cat in availableCategories"
          :key="cat"
          class="chip"
          :class="{ selected: selectedCategories.includes(cat) }"
          @click="toggleCategory(cat)"
        >{{ cat }}</button>
      </div>

      <textarea
        v-model="feedbackText"
        class="field-input feedback-textarea"
        placeholder="What's wrong with this shot?"
        rows="2"
      />

      <button
        class="btn btn-primary"
        :disabled="rating === 0 || loading"
        @click="submitFeedback"
      >
        {{ loading ? 'Analyzing...' : 'Submit Feedback' }}
      </button>
    </div>

    <!-- Phase 2: Questions -->
    <div v-if="phase === 'questions'" class="feedback-questions">
      <div v-for="q in questions" :key="q.id" class="question-block">
        <div class="question-text">{{ q.text }}</div>
        <div class="option-group">
          <label
            v-for="opt in q.options"
            :key="opt.id"
            class="option-label"
            :class="{ selected: selectedOptions[q.id] === opt.id }"
          >
            <input
              type="radio"
              :name="q.id"
              :value="opt.id"
              v-model="selectedOptions[q.id]"
            />
            <span>{{ opt.label }}</span>
          </label>
        </div>
        <button
          class="btn btn-primary btn-sm"
          :disabled="!selectedOptions[q.id] || loading"
          @click="applyAnswer(q.id)"
        >
          {{ loading ? 'Applying...' : 'Apply' }}
        </button>
      </div>

      <div v-if="questions.length === 0" class="no-questions">
        No diagnostic questions generated. Try different categories.
      </div>
    </div>

    <!-- Phase 3: Results -->
    <div v-if="phase === 'result'" class="feedback-result">
      <div class="result-header">Changes Applied</div>
      <div v-if="lastAnswer" class="changes-list">
        <div v-for="(change, key) in lastAnswer.changes" :key="key" class="change-row">
          <span class="change-key">{{ key }}:</span>
          <span class="change-before">{{ formatVal(change.before) }}</span>
          <span class="change-arrow">&rarr;</span>
          <span class="change-after">{{ formatVal(change.after) }}</span>
        </div>
        <div v-if="lastAnswer.regenerated" class="regen-notice">
          Regeneration queued
        </div>
      </div>
      <div class="result-actions">
        <button class="btn btn-outline btn-sm" @click="resetPanel">New Feedback</button>
        <button class="btn btn-sm" @click="$emit('close')">Close</button>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="error" class="feedback-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFeedbackStore } from '@/stores/feedback'
import type { FeedbackQuestion } from '@/api/feedback'

const props = defineProps<{
  shotId: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'regenerated'): void
}>()

const store = useFeedbackStore()

const rating = ref(0)
const feedbackText = ref('')
const selectedCategories = ref<string[]>([])
const selectedOptions = ref<Record<string, string>>({})
const phase = ref<'input' | 'questions' | 'result'>('input')

const availableCategories = ['Motion', 'Character', 'Composition', 'Lighting', 'Interaction']

const loading = computed(() => store.loading)
const error = computed(() => store.error)
const questions = computed(() => store.questions)
const lastAnswer = computed(() => store.lastAnswer)

function toggleCategory(cat: string) {
  const idx = selectedCategories.value.indexOf(cat)
  if (idx >= 0) {
    selectedCategories.value.splice(idx, 1)
  } else {
    selectedCategories.value.push(cat)
  }
}

async function submitFeedback() {
  try {
    await store.submitReview(
      props.shotId,
      rating.value,
      feedbackText.value,
      selectedCategories.value.map(c => c.toLowerCase()),
    )
    phase.value = 'questions'
    selectedOptions.value = {}
  } catch {
    // error shown via store
  }
}

async function applyAnswer(questionId: string) {
  const optionId = selectedOptions.value[questionId]
  if (!optionId) return

  // Find the option to check if it needs extra params (edit_prompt, edit_motion)
  const q = questions.value.find(q => q.id === questionId)
  const opt = q?.options.find(o => o.id === optionId)

  // For edit actions without pre-set params, use the feedback text
  let extraParams: Record<string, unknown> | undefined
  if (opt?.action === 'edit_prompt' && !opt.params?.append && feedbackText.value) {
    extraParams = { text: feedbackText.value }
  }
  if (opt?.action === 'edit_motion' && feedbackText.value) {
    extraParams = { text: feedbackText.value }
  }

  try {
    await store.answerQuestion(questionId, optionId, extraParams)
    phase.value = 'result'
    emit('regenerated')
  } catch {
    // error shown via store
  }
}

function resetPanel() {
  store.reset()
  rating.value = 0
  feedbackText.value = ''
  selectedCategories.value = []
  selectedOptions.value = {}
  phase.value = 'input'
}

function formatVal(val: unknown): string {
  if (val === null || val === undefined) return 'null'
  if (typeof val === 'boolean') return val ? 'yes' : 'no'
  return String(val)
}
</script>

<style scoped>
.feedback-panel {
  border-top: 1px solid var(--border-primary);
  padding: 8px;
  background: var(--bg-primary);
}

.star-rating {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-bottom: 6px;
}
.star {
  font-size: 20px;
  color: var(--border-primary);
  cursor: pointer;
  transition: color 150ms;
  user-select: none;
}
.star.active {
  color: #f5a623;
}
.star:hover {
  color: #f5c563;
}
.star-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: 6px;
}

.category-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.chip {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 150ms;
}
.chip.selected {
  background: rgba(122, 162, 247, 0.2);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.chip:hover {
  border-color: var(--accent-primary);
}

.feedback-textarea {
  width: 100%;
  font-size: 11px;
  margin-bottom: 6px;
  resize: vertical;
  min-height: 36px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  color: var(--text-primary);
  padding: 4px 6px;
}

.btn-sm {
  font-size: 11px;
  padding: 3px 10px;
}

.feedback-questions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.question-block {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 6px 8px;
}

.question-text {
  font-size: 11px;
  color: var(--text-primary);
  margin-bottom: 6px;
  line-height: 1.4;
  white-space: pre-line;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 6px;
}

.option-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  transition: background 150ms;
}
.option-label:hover {
  background: rgba(122, 162, 247, 0.1);
}
.option-label.selected {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary);
}
.option-label input[type="radio"] {
  accent-color: var(--accent-primary);
}

.no-questions {
  font-size: 11px;
  color: var(--text-muted);
  padding: 8px;
  text-align: center;
}

.feedback-result {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-header {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-primary);
  padding-bottom: 4px;
}

.changes-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.change-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-family: monospace;
}
.change-key {
  color: var(--text-muted);
  min-width: 80px;
}
.change-before {
  color: var(--status-error);
}
.change-arrow {
  color: var(--text-muted);
}
.change-after {
  color: var(--status-success);
}

.regen-notice {
  font-size: 11px;
  color: var(--status-success);
  font-weight: 500;
  margin-top: 4px;
}

.result-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.feedback-error {
  font-size: 11px;
  color: var(--status-error);
  margin-top: 4px;
  padding: 4px;
  background: rgba(200, 80, 80, 0.1);
  border-radius: 3px;
}
</style>
