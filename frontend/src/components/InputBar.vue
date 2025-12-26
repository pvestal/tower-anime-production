<template>
  <div class="input-bar" :class="{ 'input-disabled': disabled }">
    <!-- Suggestion Dropdown -->
    <div
      v-if="showSuggestions && filteredSuggestions.length > 0"
      class="suggestions-dropdown"
    >
      <div
        v-for="(suggestion, index) in filteredSuggestions"
        :key="index"
        class="suggestion-item"
        :class="{
          'suggestion-highlighted': index === highlightedSuggestionIndex,
          'suggestion-hovered': index === hoveredSuggestionIndex,
        }"
        @click="applySuggestion(suggestion)"
        @mouseover="hoveredSuggestionIndex = index"
      >
        <div class="suggestion-text">{{ suggestion }}</div>
        <div class="suggestion-shortcut">Tab</div>
      </div>
    </div>

    <!-- Main Input Container -->
    <div class="input-container">
      <!-- Attachment Button -->
      <button
        class="input-btn attachment-btn"
        :disabled="disabled"
        title="Attach file"
        @click="triggerFileUpload"
      >
        <i class="icon-paperclip"></i>
      </button>

      <!-- Text Input Area -->
      <div class="input-wrapper">
        <textarea
          ref="textInput"
          v-model="inputText"
          :disabled="disabled"
          :placeholder="currentPlaceholder"
          class="text-input"
          rows="1"
          maxlength="4000"
          @input="handleInput"
          @keydown="handleKeydown"
          @keyup="handleKeyup"
          @paste="handlePaste"
          @focus="handleFocus"
          @blur="handleBlur"
        ></textarea>

        <!-- Character Counter -->
        <div v-if="showCharCounter" class="char-counter">
          {{ inputText.length }}/4000
        </div>

        <!-- Input Formatting Overlay -->
        <div v-if="hasFormattedText" class="input-overlay">
          <div class="formatted-text" v-html="formattedInputText"></div>
        </div>
      </div>

      <!-- Voice Input Button -->
      <button
        class="input-btn voice-btn"
        :class="{ 'voice-active': isRecording }"
        :disabled="disabled || !voiceEnabled"
        :title="isRecording ? 'Stop recording' : 'Start voice input'"
        @click="toggleVoiceInput"
      >
        <i :class="isRecording ? 'icon-mic-off' : 'icon-mic'"></i>
        <div v-if="isRecording" class="recording-indicator">
          <span class="recording-dot"></span>
        </div>
      </button>

      <!-- Send Button -->
      <button
        class="input-btn send-btn"
        :disabled="disabled || !canSend"
        title="Send message (Ctrl+Enter)"
        @click="sendMessage"
      >
        <i v-if="!sending" class="icon-send"></i>
        <div v-else class="sending-spinner"></div>
      </button>
    </div>

    <!-- Quick Actions Bar -->
    <div v-if="showQuickActions" class="quick-actions">
      <button
        v-for="action in quickActions"
        :key="action.id"
        class="quick-action"
        :title="action.description"
        @click="executeQuickAction(action)"
      >
        <i :class="action.icon"></i>
        <span>{{ action.label }}</span>
      </button>
    </div>

    <!-- File Upload Input (Hidden) -->
    <input
      ref="fileInput"
      type="file"
      multiple
      accept=".jpg,.jpeg,.png,.gif,.webp,.mp4,.mov,.avi,.webm,.pdf,.txt,.json"
      class="file-input"
      @change="handleFileUpload"
    />

    <!-- Voice Recording Modal -->
    <div v-if="isRecording" class="voice-modal">
      <div class="voice-content">
        <div class="voice-animation">
          <div class="voice-circle"></div>
          <div class="voice-waves">
            <span class="wave wave-1"></span>
            <span class="wave wave-2"></span>
            <span class="wave wave-3"></span>
          </div>
        </div>
        <div class="voice-text">
          <h4>Listening...</h4>
          <p v-if="transcription">{{ transcription }}</p>
          <p v-else class="voice-hint">Speak clearly into your microphone</p>
        </div>
        <div class="voice-controls">
          <button class="voice-cancel" @click="cancelVoiceInput">
            <i class="icon-x"></i>
            Cancel
          </button>
          <button class="voice-done" @click="stopVoiceInput">
            <i class="icon-check"></i>
            Done
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue";

// Props
const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  suggestions: {
    type: Array,
    default: () => [],
  },
  placeholder: {
    type: String,
    default: "Type your message...",
  },
  voiceEnabled: {
    type: Boolean,
    default: false,
  },
  showQuickActions: {
    type: Boolean,
    default: true,
  },
});

// Emits
const emit = defineEmits([
  "send",
  "voice-toggle",
  "file-upload",
  "quick-action",
]);

// Template refs
const textInput = ref(null);
const fileInput = ref(null);

// State
const inputText = ref("");
const sending = ref(false);
const isRecording = ref(false);
const transcription = ref("");
const showSuggestions = ref(false);
const highlightedSuggestionIndex = ref(-1);
const hoveredSuggestionIndex = ref(-1);
const inputFocused = ref(false);
const lastCursorPosition = ref(0);

// Voice recognition state
const recognition = ref(null);
const voiceSupported = ref(false);

// Computed properties
const canSend = computed(() => {
  return inputText.value.trim().length > 0 && !sending.value;
});

const showCharCounter = computed(() => {
  return inputText.value.length > 3000 || inputFocused.value;
});

const currentPlaceholder = computed(() => {
  if (props.disabled) return "Offline - Unable to send messages";
  if (isRecording.value) return "Recording voice input...";
  return props.placeholder;
});

const filteredSuggestions = computed(() => {
  if (!inputText.value || !showSuggestions.value) return [];

  const query = inputText.value.toLowerCase();
  return props.suggestions
    .filter((suggestion) => suggestion.toLowerCase().includes(query))
    .slice(0, 5);
});

const hasFormattedText = computed(() => {
  // Check if text contains formatting markers
  return /(\*\*|__|`|@|#)/.test(inputText.value);
});

const formattedInputText = computed(() => {
  if (!hasFormattedText.value) return "";

  let formatted = inputText.value
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.*?)__/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/@(\w+)/g, '<span class="mention">@$1</span>')
    .replace(/#(\w+)/g, '<span class="hashtag">#$1</span>');

  return formatted;
});

const quickActions = ref([
  {
    id: "character",
    label: "Character",
    icon: "icon-user",
    description: "Create or edit character",
    action: () => "Create a new character for the current project",
  },
  {
    id: "scene",
    label: "Scene",
    icon: "icon-video",
    description: "Generate scene",
    action: () => "Create a new scene with the current characters",
  },
  {
    id: "style",
    label: "Style",
    icon: "icon-palette",
    description: "Adjust art style",
    action: () => "Help me adjust the art style for this project",
  },
  {
    id: "generate",
    label: "Generate",
    icon: "icon-image",
    description: "Generate image/video",
    action: () => "Generate an image or video based on current context",
  },
]);

// Methods
const handleInput = (event) => {
  inputText.value = event.target.value;
  autoResize();
  updateSuggestions();
};

const handleKeydown = (event) => {
  // Handle special keys
  switch (event.key) {
    case "Enter":
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        sendMessage();
      } else if (!event.shiftKey) {
        // Check if suggestions are shown and handle selection
        if (showSuggestions.value && filteredSuggestions.value.length > 0) {
          event.preventDefault();
          if (highlightedSuggestionIndex.value >= 0) {
            applySuggestion(
              filteredSuggestions.value[highlightedSuggestionIndex.value],
            );
          } else {
            sendMessage();
          }
        }
      }
      break;

    case "Tab":
      if (showSuggestions.value && filteredSuggestions.value.length > 0) {
        event.preventDefault();
        if (highlightedSuggestionIndex.value >= 0) {
          applySuggestion(
            filteredSuggestions.value[highlightedSuggestionIndex.value],
          );
        } else {
          applySuggestion(filteredSuggestions.value[0]);
        }
      }
      break;

    case "ArrowUp":
      if (showSuggestions.value && filteredSuggestions.value.length > 0) {
        event.preventDefault();
        highlightedSuggestionIndex.value = Math.max(
          -1,
          highlightedSuggestionIndex.value - 1,
        );
      }
      break;

    case "ArrowDown":
      if (showSuggestions.value && filteredSuggestions.value.length > 0) {
        event.preventDefault();
        highlightedSuggestionIndex.value = Math.min(
          filteredSuggestions.value.length - 1,
          highlightedSuggestionIndex.value + 1,
        );
      }
      break;

    case "Escape":
      hideSuggestions();
      break;

    case "/":
      // Show quick commands
      if (inputText.value === "") {
        showSuggestions.value = true;
        highlightedSuggestionIndex.value = -1;
      }
      break;
  }

  // Store cursor position
  lastCursorPosition.value = event.target.selectionStart;
};

const handleKeyup = (event) => {
  // Update cursor position
  lastCursorPosition.value = event.target.selectionStart;
};

const handlePaste = (event) => {
  // Handle pasted content
  const clipboardData = event.clipboardData || window.clipboardData;
  const pastedData = clipboardData.getData("text");

  if (pastedData.length > 4000 - inputText.value.length) {
    event.preventDefault();

    // Truncate if too long
    const availableSpace = 4000 - inputText.value.length;
    const truncatedData = pastedData.substring(0, availableSpace);

    insertTextAtCursor(truncatedData);
  }

  nextTick(() => {
    autoResize();
    updateSuggestions();
  });
};

const handleFocus = () => {
  inputFocused.value = true;
};

const handleBlur = () => {
  inputFocused.value = false;
  // Delay hiding suggestions to allow clicking
  setTimeout(() => {
    if (!hoveredSuggestionIndex.value >= 0) {
      hideSuggestions();
    }
  }, 200);
};

const autoResize = () => {
  if (textInput.value) {
    textInput.value.style.height = "auto";
    textInput.value.style.height =
      Math.min(textInput.value.scrollHeight, 150) + "px";
  }
};

const updateSuggestions = () => {
  const text = inputText.value.toLowerCase();

  if (text.length > 1) {
    showSuggestions.value = true;
    highlightedSuggestionIndex.value = -1;
  } else {
    hideSuggestions();
  }
};

const hideSuggestions = () => {
  showSuggestions.value = false;
  highlightedSuggestionIndex.value = -1;
  hoveredSuggestionIndex.value = -1;
};

const applySuggestion = (suggestion) => {
  inputText.value = suggestion;
  hideSuggestions();
  nextTick(() => {
    textInput.value?.focus();
    autoResize();
  });
};

const insertTextAtCursor = (text) => {
  const start = lastCursorPosition.value;
  const end = start;
  const before = inputText.value.substring(0, start);
  const after = inputText.value.substring(end);

  inputText.value = before + text + after;

  nextTick(() => {
    const newPosition = start + text.length;
    textInput.value?.setSelectionRange(newPosition, newPosition);
    lastCursorPosition.value = newPosition;
  });
};

const sendMessage = async () => {
  if (!canSend.value) return;

  const message = inputText.value.trim();
  if (!message) return;

  sending.value = true;

  try {
    await emit("send", message);
    inputText.value = "";
    hideSuggestions();

    nextTick(() => {
      autoResize();
      textInput.value?.focus();
    });
  } catch (error) {
    console.error("Failed to send message:", error);
  } finally {
    sending.value = false;
  }
};

const triggerFileUpload = () => {
  fileInput.value?.click();
};

const handleFileUpload = (event) => {
  const files = Array.from(event.target.files);
  if (files.length > 0) {
    emit("file-upload", files);
  }
  // Clear the input so the same file can be uploaded again
  event.target.value = "";
};

const toggleVoiceInput = () => {
  if (isRecording.value) {
    stopVoiceInput();
  } else {
    startVoiceInput();
  }
};

const startVoiceInput = () => {
  if (!voiceSupported.value || !recognition.value) {
    emit("voice-toggle", false);
    return;
  }

  isRecording.value = true;
  transcription.value = "";

  recognition.value.start();
  emit("voice-toggle", true);
};

const stopVoiceInput = () => {
  if (recognition.value) {
    recognition.value.stop();
  }

  if (transcription.value.trim()) {
    inputText.value = transcription.value.trim();
    nextTick(() => {
      autoResize();
      textInput.value?.focus();
    });
  }

  isRecording.value = false;
  transcription.value = "";
  emit("voice-toggle", false);
};

const cancelVoiceInput = () => {
  if (recognition.value) {
    recognition.value.abort();
  }

  isRecording.value = false;
  transcription.value = "";
  emit("voice-toggle", false);
};

const executeQuickAction = (action) => {
  const actionText = action.action();
  inputText.value = actionText;

  nextTick(() => {
    autoResize();
    textInput.value?.focus();
  });

  emit("quick-action", action.id, actionText);
};

// Voice recognition setup
const initializeVoiceRecognition = () => {
  if (typeof window === "undefined") return;

  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    voiceSupported.value = true;
    recognition.value = new SpeechRecognition();

    recognition.value.continuous = true;
    recognition.value.interimResults = true;
    recognition.value.lang = "en-US";

    recognition.value.onresult = (event) => {
      let finalTranscript = "";
      let interimTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      transcription.value = finalTranscript + interimTranscript;
    };

    recognition.value.onend = () => {
      if (isRecording.value) {
        stopVoiceInput();
      }
    };

    recognition.value.onerror = (event) => {
      console.error("Speech recognition error:", event.error);
      cancelVoiceInput();
    };
  }
};

// Keyboard shortcuts
const handleGlobalKeydown = (event) => {
  // Focus input with '/' key
  if (
    event.key === "/" &&
    !inputFocused.value &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey
  ) {
    event.preventDefault();
    textInput.value?.focus();
  }
};

// Lifecycle
onMounted(() => {
  initializeVoiceRecognition();
  document.addEventListener("keydown", handleGlobalKeydown);

  // Auto-focus on mount
  nextTick(() => {
    textInput.value?.focus();
  });
});

onUnmounted(() => {
  document.removeEventListener("keydown", handleGlobalKeydown);

  if (recognition.value && isRecording.value) {
    recognition.value.stop();
  }
});

// Watchers
watch(
  () => props.disabled,
  (disabled) => {
    if (disabled && isRecording.value) {
      cancelVoiceInput();
    }
  },
);

// Expose methods for parent component
defineExpose({
  focus: () => textInput.value?.focus(),
  clear: () => {
    inputText.value = "";
    autoResize();
  },
  insertText: insertTextAtCursor,
});
</script>

<style scoped>
.input-bar {
  position: relative;
  width: 100%;
}

.input-disabled {
  opacity: 0.6;
  pointer-events: none;
}

/* Suggestions Dropdown */
.suggestions-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  background: rgba(45, 45, 45, 0.95);
  border: 1px solid #4a4a4a;
  border-radius: 8px;
  backdrop-filter: blur(10px);
  z-index: 1000;
  margin-bottom: 0.5rem;
  max-height: 200px;
  overflow-y: auto;
}

.suggestion-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #3a3a3a;
}

.suggestion-item:last-child {
  border-bottom: none;
}

.suggestion-item:hover,
.suggestion-hovered {
  background: rgba(123, 104, 238, 0.1);
}

.suggestion-highlighted {
  background: rgba(123, 104, 238, 0.2);
}

.suggestion-text {
  flex: 1;
  color: #ffffff;
}

.suggestion-shortcut {
  font-size: 0.7rem;
  color: #999;
  background: rgba(0, 0, 0, 0.3);
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  border: 1px solid #4a4a4a;
}

/* Input Container */
.input-container {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  background: rgba(26, 26, 26, 0.9);
  border: 1px solid #4a4a4a;
  border-radius: 12px;
  padding: 0.75rem;
  transition: all 0.2s;
}

.input-container:focus-within {
  border-color: #7b68ee;
  box-shadow: 0 0 0 2px rgba(123, 104, 238, 0.2);
}

.input-wrapper {
  flex: 1;
  position: relative;
}

/* Text Input */
.text-input {
  width: 100%;
  min-height: 40px;
  max-height: 150px;
  padding: 0.5rem 0;
  background: none;
  border: none;
  outline: none;
  color: #ffffff;
  font-size: 1rem;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
}

.text-input::placeholder {
  color: #999;
}

.text-input:disabled {
  color: #666;
  cursor: not-allowed;
}

/* Character Counter */
.char-counter {
  position: absolute;
  bottom: -20px;
  right: 0;
  font-size: 0.7rem;
  color: #999;
  transition: color 0.2s;
}

.char-counter[data-over-limit] {
  color: #f44336;
}

/* Input Formatting Overlay */
.input-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  padding: 0.5rem 0;
  font-size: 1rem;
  line-height: 1.5;
  z-index: 1;
}

.formatted-text {
  color: transparent;
}

.formatted-text :deep(strong) {
  background: rgba(123, 104, 238, 0.2);
  color: #7b68ee;
}

.formatted-text :deep(em) {
  background: rgba(156, 136, 255, 0.2);
  color: #9c88ff;
  font-style: italic;
}

.formatted-text :deep(code) {
  background: rgba(0, 0, 0, 0.5);
  color: #7b68ee;
  padding: 0.1rem 0.2rem;
  border-radius: 2px;
}

.formatted-text :deep(.mention) {
  background: rgba(33, 150, 243, 0.2);
  color: #2196f3;
}

.formatted-text :deep(.hashtag) {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

/* Input Buttons */
.input-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #4a4a4a;
  border-radius: 8px;
  color: #cccccc;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.input-btn:hover:not(:disabled) {
  background: rgba(123, 104, 238, 0.2);
  border-color: #7b68ee;
  color: #7b68ee;
}

.input-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-btn:not(:disabled) {
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  border-color: #7b68ee;
  color: white;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(123, 104, 238, 0.3);
}

.voice-btn.voice-active {
  background: linear-gradient(135deg, #f44336 0%, #ff5722 100%);
  border-color: #f44336;
  color: white;
  animation: pulse 2s infinite;
}

/* Recording Indicator */
.recording-indicator {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 12px;
  height: 12px;
}

.recording-dot {
  display: block;
  width: 8px;
  height: 8px;
  background: #f44336;
  border-radius: 50%;
  border: 2px solid white;
  animation: recording-pulse 1s infinite;
}

/* Sending Spinner */
.sending-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top: 2px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Quick Actions */
.quick-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border: 1px solid #3a3a3a;
}

.quick-action {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(123, 104, 238, 0.1);
  border: 1px solid rgba(123, 104, 238, 0.3);
  border-radius: 6px;
  color: #7b68ee;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.8rem;
}

.quick-action:hover {
  background: rgba(123, 104, 238, 0.2);
  border-color: rgba(123, 104, 238, 0.5);
  transform: translateY(-1px);
}

.quick-action span {
  font-weight: 500;
}

/* Hidden File Input */
.file-input {
  display: none;
}

/* Voice Recording Modal */
.voice-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(4px);
}

.voice-content {
  background: rgba(45, 45, 45, 0.95);
  border-radius: 16px;
  padding: 2rem;
  text-align: center;
  max-width: 400px;
  width: 90%;
  border: 1px solid #4a4a4a;
}

.voice-animation {
  position: relative;
  margin-bottom: 1.5rem;
}

.voice-circle {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #f44336 0%, #ff5722 100%);
  border-radius: 50%;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: voice-pulse 2s infinite;
}

.voice-circle::before {
  content: "🎤";
  font-size: 2rem;
}

.voice-waves {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 120px;
  height: 120px;
}

.wave {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 2px solid #f44336;
  border-radius: 50%;
  opacity: 0;
}

.wave-1 {
  width: 100px;
  height: 100px;
  animation: voice-wave 2s infinite;
}

.wave-2 {
  width: 120px;
  height: 120px;
  animation: voice-wave 2s infinite 0.5s;
}

.wave-3 {
  width: 140px;
  height: 140px;
  animation: voice-wave 2s infinite 1s;
}

.voice-text h4 {
  margin: 0 0 0.5rem 0;
  color: #ffffff;
}

.voice-text p {
  margin: 0;
  color: #cccccc;
  min-height: 1.2rem;
}

.voice-hint {
  color: #999 !important;
  font-style: italic;
}

.voice-controls {
  display: flex;
  gap: 1rem;
  margin-top: 1.5rem;
  justify-content: center;
}

.voice-cancel,
.voice-done {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.voice-cancel {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
  border: 1px solid rgba(244, 67, 54, 0.3);
}

.voice-cancel:hover {
  background: rgba(244, 67, 54, 0.3);
}

.voice-done {
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  color: white;
  border: 1px solid #7b68ee;
}

.voice-done:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(123, 104, 238, 0.3);
}

/* Animations */
@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

@keyframes recording-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@keyframes voice-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
}

@keyframes voice-wave {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.5);
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(1);
  }
}

/* Responsive Design */
@media (max-width: 768px) {
  .input-container {
    padding: 0.5rem;
    gap: 0.25rem;
  }

  .input-btn {
    width: 36px;
    height: 36px;
  }

  .quick-actions {
    flex-wrap: wrap;
  }

  .quick-action {
    font-size: 0.7rem;
    padding: 0.4rem 0.6rem;
  }

  .voice-content {
    padding: 1.5rem;
  }

  .voice-circle {
    width: 60px;
    height: 60px;
  }

  .voice-circle::before {
    font-size: 1.5rem;
  }
}

@media (max-width: 480px) {
  .quick-actions {
    display: none;
  }

  .voice-controls {
    flex-direction: column;
    gap: 0.5rem;
  }

  .voice-cancel,
  .voice-done {
    width: 100%;
    justify-content: center;
  }
}

/* High contrast mode support */
@media (prefers-contrast: high) {
  .input-container {
    border-width: 2px;
  }

  .input-btn {
    border-width: 2px;
  }

  .suggestion-item {
    border-bottom-width: 2px;
  }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
