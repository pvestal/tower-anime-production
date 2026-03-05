<template>
  <div class="play-director">
    <!-- Scene panel (left) -->
    <div class="director-scene" :class="{ 'has-scene': store.hasScene }">
      <template v-if="store.hasScene">
        <!-- Background image -->
        <div class="scene-bg" :class="{ loaded: imageLoaded }">
          <img
            v-if="imageUrl"
            :src="imageUrl"
            alt=""
            class="scene-image"
            @load="imageLoaded = true"
          />
          <div v-else class="scene-loading">
            <div class="loading-shimmer" />
            <p class="loading-text">{{ imageLoadingText }}</p>
            <div v-if="store.imageStatus.progress > 0" class="progress-bar">
              <div class="progress-fill" :style="{ width: (store.imageStatus.progress * 100) + '%' }" />
            </div>
          </div>
        </div>
        <div class="scene-overlay" />

        <!-- Scene info overlay -->
        <div class="scene-info-bar">
          <span class="scene-number">Scene {{ (store.currentScene?.scene_index ?? 0) + 1 }}</span>
          <span v-if="store.currentScene?.director_note" class="director-note">
            {{ store.currentScene.director_note }}
          </span>
        </div>

        <!-- Narration (editable on click) -->
        <div class="scene-narration" @dblclick="startEditNarration">
          <template v-if="editingNarration">
            <textarea
              v-model="editNarrationValue"
              class="edit-textarea"
              @keydown.escape="editingNarration = false"
              @keydown.ctrl.enter="submitNarrationEdit"
              ref="narrationInput"
            />
            <div class="edit-actions">
              <button class="edit-btn save" @click="submitNarrationEdit">Save</button>
              <button class="edit-btn cancel" @click="editingNarration = false">Cancel</button>
            </div>
          </template>
          <p v-else class="narration-text">{{ store.currentScene?.narration }}</p>
        </div>

        <!-- Dialogue -->
        <div v-if="store.currentScene?.dialogue?.length" class="scene-dialogue">
          <div v-for="(line, i) in store.currentScene.dialogue" :key="i" class="dialogue-line">
            <span class="char-name" :class="`emotion-${line.emotion}`">{{ line.character }}</span>
            <span class="char-text">"{{ line.text }}"</span>
          </div>
        </div>

        <!-- Choices -->
        <div v-if="store.currentScene?.choices?.length && !store.isEnded" class="scene-choices">
          <button
            v-for="(choice, i) in store.currentScene.choices"
            :key="i"
            class="choice-btn"
            :class="`tone-${choice.tone}`"
            :disabled="store.thinking"
            @click="store.submitChoice(i)"
          >
            <span class="choice-marker">{{ i + 1 }}</span>
            <span>{{ choice.text }}</span>
          </button>
        </div>
      </template>

      <!-- No scene yet: project intro -->
      <template v-else>
        <div class="scene-placeholder">
          <h2>{{ store.projectName || 'Interactive Story' }}</h2>
          <p>Chat with the AI Director to shape your story before it begins.</p>
          <div v-if="store.characters.length" class="char-tags">
            <span v-for="c in store.characters" :key="c.slug" class="char-tag">
              {{ c.name }}
            </span>
          </div>
        </div>
      </template>
    </div>

    <!-- Chat panel (right) -->
    <div class="director-chat">
      <div class="chat-header">
        <h3>AI Director</h3>
        <div class="header-controls">
          <div v-if="Object.keys(store.relationships).length" class="mini-rels">
            <span v-for="(val, name) in store.relationships" :key="name" class="rel-chip" :class="{ negative: val < 0 }">
              {{ name }}: {{ val > 0 ? '+' : '' }}{{ val }}
            </span>
          </div>
          <button class="quit-btn" @click="confirmQuit" title="End session">&times;</button>
        </div>
      </div>

      <!-- Messages -->
      <div class="chat-messages" ref="messagesContainer">
        <div
          v-for="msg in store.messages"
          :key="msg.id"
          class="chat-msg"
          :class="`msg-${msg.role}`"
        >
          <div class="msg-bubble">
            <p class="msg-text">{{ msg.text }}</p>

            <!-- Suggestions -->
            <div v-if="msg.suggestions?.length && msg === lastDirectorMsg" class="msg-suggestions">
              <button
                v-for="(s, i) in msg.suggestions"
                :key="i"
                class="suggestion-btn"
                :disabled="store.thinking"
                @click="store.sendMessage(s)"
              >
                {{ s }}
              </button>
            </div>
          </div>
          <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
        </div>

        <!-- Thinking indicator -->
        <div v-if="store.thinking" class="chat-msg msg-system">
          <div class="msg-bubble thinking-bubble">
            <span class="thinking-dot" />
            <span class="thinking-dot" />
            <span class="thinking-dot" />
          </div>
        </div>
      </div>

      <!-- Pipeline status -->
      <div v-if="store.pipelineSteps.length" class="pipeline-bar">
        <div v-for="(step, i) in store.pipelineSteps" :key="i" class="pipeline-step" :class="step.status">
          <span class="step-icon">
            {{ step.status === 'done' ? '✓' : step.status === 'active' ? '◉' : '○' }}
          </span>
          {{ step.label }}
        </div>
      </div>

      <!-- Input -->
      <div class="chat-input-area">
        <textarea
          v-model="inputText"
          class="chat-input"
          placeholder="Type a message, give a direction, or describe what you want..."
          :disabled="store.thinking || store.isEnded"
          @keydown.enter.exact.prevent="sendInput"
          rows="2"
        />
        <button
          class="send-btn"
          :disabled="!inputText.trim() || store.thinking || store.isEnded"
          @click="sendInput"
        >
          Send
        </button>
      </div>

      <!-- Preferences drawer -->
      <div v-if="Object.keys(store.preferences).length" class="prefs-drawer">
        <span class="prefs-label">Preferences:</span>
        <span v-for="(v, k) in store.preferences" :key="k" class="pref-chip">
          {{ k }}: {{ v }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useDirectorStore } from '@/stores/director'

const store = useDirectorStore()

const inputText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const editingNarration = ref(false)
const editNarrationValue = ref('')
const narrationInput = ref<HTMLTextAreaElement | null>(null)
const imageLoaded = ref(false)

defineEmits<{ quit: [] }>()

const imageUrl = computed(() => {
  if (store.imageStatus.status === 'ready' && store.imageStatus.url) {
    return store.imageStatus.url
  }
  return null
})

const imageLoadingText = computed(() => {
  switch (store.imageStatus.status) {
    case 'pending': return 'Preparing scene...'
    case 'generating': return 'Painting the scene...'
    case 'failed': return 'Image generation failed'
    default: return 'Loading...'
  }
})

const lastDirectorMsg = computed(() => {
  const dirMsgs = store.messages.filter(m => m.role === 'director' && m.suggestions?.length)
  return dirMsgs[dirMsgs.length - 1] || null
})

// Auto-scroll chat
watch(() => store.messages.length, () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
})

// Reset image loaded on scene change
watch(() => store.currentScene?.scene_index, () => {
  imageLoaded.value = false
})

function sendInput() {
  const text = inputText.value.trim()
  if (!text || store.thinking) return
  inputText.value = ''
  store.sendMessage(text)
}

function startEditNarration() {
  if (!store.currentScene) return
  editNarrationValue.value = store.currentScene.narration
  editingNarration.value = true
  nextTick(() => narrationInput.value?.focus())
}

function submitNarrationEdit() {
  if (!store.currentScene) return
  store.editScene(store.currentScene.scene_index, 'narration', editNarrationValue.value)
  editingNarration.value = false
}

function confirmQuit() {
  if (window.confirm('End this session? Progress will be saved to Echo Brain.')) {
    store.endSession()
  }
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.play-director {
  position: fixed;
  inset: 0;
  display: flex;
  background: #0a0a0f;
  z-index: 50;
}

/* --- Scene Panel --- */
.director-scene {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.scene-bg {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 1s ease;
}
.scene-bg.loaded { opacity: 1; }
.scene-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.scene-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.loading-shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(-45deg, #0a0a1a 25%, #12122a 50%, #0a0a1a 75%);
  background-size: 400% 400%;
  animation: shimmer 3s ease infinite;
}
@keyframes shimmer {
  0% { background-position: 100% 50%; }
  50% { background-position: 0% 50%; }
  100% { background-position: 100% 50%; }
}
.loading-text {
  position: relative;
  z-index: 1;
  color: rgba(255,255,255,0.5);
  font-size: 14px;
  font-style: italic;
}
.progress-bar {
  position: relative;
  z-index: 1;
  width: 180px;
  height: 3px;
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--accent-primary, #6366f1);
  transition: width 0.5s ease;
}

.scene-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 40%, transparent 70%);
  pointer-events: none;
}

.scene-info-bar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
}
.scene-number {
  padding: 3px 10px;
  background: rgba(0,0,0,0.5);
  border-radius: 12px;
  font-size: 12px;
  color: rgba(255,255,255,0.6);
}
.director-note {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  font-style: italic;
}

.scene-narration {
  position: relative;
  z-index: 2;
  padding: 12px 20px;
  cursor: default;
}
.scene-narration:hover { background: rgba(255,255,255,0.02); }
.narration-text {
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-primary, #e8e8e8);
  font-style: italic;
  margin: 0;
}

.edit-textarea {
  width: 100%;
  min-height: 80px;
  padding: 10px;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 6px;
  color: var(--text-primary, #e8e8e8);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
}
.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.edit-btn {
  padding: 4px 12px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}
.edit-btn.save { background: var(--accent-primary, #6366f1); color: #fff; }
.edit-btn.cancel { background: rgba(255,255,255,0.1); color: var(--text-secondary, #aaa); }

.scene-dialogue {
  position: relative;
  z-index: 2;
  padding: 0 20px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dialogue-line { font-size: 14px; }
.char-name { font-weight: 600; margin-right: 6px; }
.char-text { color: var(--text-secondary, #ccc); }
.emotion-happy { color: #f0c040; }
.emotion-sad { color: #6090d0; }
.emotion-angry { color: #e05050; }
.emotion-surprised { color: #e0a030; }
.emotion-scared { color: #a070c0; }
.emotion-romantic { color: #e070a0; }
.emotion-neutral { color: var(--accent-primary, #6366f1); }

.scene-choices {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 20px 16px;
}
.choice-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px;
  background: rgba(0,0,0,0.4);
  backdrop-filter: blur(8px);
  color: var(--text-primary, #e8e8e8);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: all 0.2s;
}
.choice-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.08);
  transform: translateX(3px);
}
.choice-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.choice-marker {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.tone-bold .choice-marker { background: rgba(220,50,50,0.3); color: #f07070; }
.tone-cautious .choice-marker { background: rgba(60,130,220,0.3); color: #70a0f0; }
.tone-romantic .choice-marker { background: rgba(220,80,150,0.3); color: #f080b0; }
.tone-dramatic .choice-marker { background: rgba(180,80,220,0.3); color: #c080f0; }
.tone-humorous .choice-marker { background: rgba(220,180,40,0.3); color: #e0c050; }
.tone-neutral .choice-marker { background: rgba(255,255,255,0.1); color: var(--text-secondary, #aaa); }

.scene-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 40px;
}
.scene-placeholder h2 {
  font-size: 28px;
  color: var(--text-primary, #e8e8e8);
  margin: 0 0 12px;
}
.scene-placeholder p {
  color: var(--text-muted, #888);
  font-size: 15px;
  max-width: 400px;
}
.char-tags {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  flex-wrap: wrap;
  justify-content: center;
}
.char-tag {
  padding: 4px 12px;
  background: rgba(99,102,241,0.15);
  border: 1px solid rgba(99,102,241,0.3);
  border-radius: 16px;
  font-size: 13px;
  color: var(--accent-primary, #6366f1);
}

/* --- Chat Panel --- */
.director-chat {
  width: 380px;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary, #111118);
  border-left: 1px solid var(--border-primary, #2a2a3a);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-primary, #2a2a3a);
}
.chat-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #e8e8e8);
  margin: 0;
}
.header-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mini-rels {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.rel-chip {
  padding: 2px 6px;
  background: rgba(99,102,241,0.15);
  border-radius: 8px;
  font-size: 10px;
  color: var(--accent-primary, #6366f1);
}
.rel-chip.negative {
  background: rgba(220,50,50,0.15);
  color: #f07070;
}
.quit-btn {
  width: 28px;
  height: 28px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 50%;
  color: var(--text-muted, #888);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.quit-btn:hover { background: rgba(220,50,50,0.2); color: #f07070; }

/* Messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-msg {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.msg-user { align-items: flex-end; }
.msg-director { align-items: flex-start; }
.msg-system { align-items: center; }

.msg-bubble {
  max-width: 90%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
}
.msg-user .msg-bubble {
  background: var(--accent-primary, #6366f1);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg-director .msg-bubble {
  background: rgba(255,255,255,0.07);
  color: var(--text-primary, #e8e8e8);
  border-bottom-left-radius: 4px;
}
.msg-system .msg-bubble {
  background: rgba(255,255,255,0.03);
  color: var(--text-muted, #888);
  font-size: 12px;
  font-style: italic;
}

.msg-text { margin: 0; white-space: pre-wrap; }
.msg-time {
  font-size: 10px;
  color: var(--text-muted, #666);
  padding: 0 4px;
}

/* Suggestions */
.msg-suggestions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}
.suggestion-btn {
  padding: 6px 10px;
  background: rgba(99,102,241,0.12);
  border: 1px solid rgba(99,102,241,0.25);
  border-radius: 6px;
  color: var(--accent-primary, #6366f1);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: all 0.15s;
}
.suggestion-btn:hover:not(:disabled) {
  background: rgba(99,102,241,0.2);
  border-color: rgba(99,102,241,0.4);
}
.suggestion-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Thinking dots */
.thinking-bubble {
  display: flex;
  gap: 4px;
  padding: 12px 18px !important;
}
.thinking-dot {
  width: 8px;
  height: 8px;
  background: var(--text-muted, #888);
  border-radius: 50%;
  animation: dot-bounce 1.2s infinite;
}
.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40% { transform: translateY(-6px); opacity: 1; }
}

/* Pipeline bar */
.pipeline-bar {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--border-primary, #2a2a3a);
  overflow-x: auto;
}
.pipeline-step {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted, #888);
  white-space: nowrap;
}
.pipeline-step.active { color: var(--accent-primary, #6366f1); }
.pipeline-step.done { color: #50d070; }
.step-icon { font-size: 10px; }

/* Input */
.chat-input-area {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--border-primary, #2a2a3a);
}
.chat-input {
  flex: 1;
  padding: 10px 12px;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-primary, #2a2a3a);
  border-radius: 8px;
  color: var(--text-primary, #e8e8e8);
  font-size: 14px;
  font-family: inherit;
  resize: none;
  line-height: 1.4;
}
.chat-input:focus {
  outline: none;
  border-color: var(--accent-primary, #6366f1);
}
.chat-input:disabled { opacity: 0.5; }
.send-btn {
  padding: 10px 16px;
  background: var(--accent-primary, #6366f1);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: opacity 0.2s;
  align-self: flex-end;
}
.send-btn:hover:not(:disabled) { opacity: 0.85; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Preferences drawer */
.prefs-drawer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-top: 1px solid var(--border-primary, #2a2a3a);
  overflow-x: auto;
}
.prefs-label {
  font-size: 11px;
  color: var(--text-muted, #888);
  white-space: nowrap;
}
.pref-chip {
  padding: 2px 8px;
  background: rgba(255,255,255,0.05);
  border-radius: 10px;
  font-size: 11px;
  color: var(--text-secondary, #aaa);
  white-space: nowrap;
}
</style>
