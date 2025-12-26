<template>
  <div
    class="message-bubble"
    :class="[
      `message-${message.type}`,
      {
        'has-metadata': hasMetadata,
        'is-streaming': isStreaming,
        'is-failed': message.status === 'failed',
      },
    ]"
  >
    <!-- Message Header -->
    <div v-if="showHeader" class="message-header">
      <div class="message-avatar">
        <span class="avatar-icon">{{ avatarIcon }}</span>
      </div>
      <div class="message-meta">
        <span class="sender-name">{{ senderName }}</span>
        <span class="message-time">{{ formattedTime }}</span>
      </div>
      <div v-if="message.type !== 'system'" class="message-actions">
        <button class="action-btn" title="Copy message" @click="copyMessage">
          <i class="icon-copy"></i>
        </button>
        <button
          v-if="message.type === 'user'"
          class="action-btn"
          title="Edit message"
          @click="editMessage"
        >
          <i class="icon-edit"></i>
        </button>
        <button
          v-if="message.status === 'failed'"
          class="action-btn retry-btn"
          title="Retry message"
          @click="retryMessage"
        >
          <i class="icon-refresh"></i>
        </button>
      </div>
    </div>

    <!-- Message Content -->
    <div class="message-content">
      <!-- Text Content -->
      <div v-if="message.messageType === 'text'" class="text-content">
        <div class="message-text" v-html="formattedContent"></div>
      </div>

      <!-- System Message -->
      <div v-else-if="message.messageType === 'system'" class="system-content">
        <div
          class="system-message"
          :class="`system-${message.level || 'info'}`"
        >
          <i :class="systemIcon"></i>
          <span>{{ message.content }}</span>
        </div>
      </div>

      <!-- Progress Message -->
      <div
        v-else-if="message.messageType === 'progress'"
        class="progress-content"
      >
        <div class="progress-header">
          <span class="progress-title">{{ message.content }}</span>
          <span class="progress-percentage">{{ message.progress }}%</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: `${message.progress}%` }"
          ></div>
        </div>
        <div v-if="message.eta" class="progress-eta">
          ETA: {{ formatETA(message.eta) }}
        </div>
      </div>

      <!-- Image Content -->
      <div v-else-if="message.messageType === 'image'" class="image-content">
        <div class="image-container">
          <img
            :src="message.content"
            :alt="message.alt || 'Generated image'"
            @load="handleImageLoad"
            @error="handleImageError"
          />
          <div v-if="imageLoading" class="image-loading">
            <div class="loading-spinner"></div>
          </div>
        </div>
        <div v-if="message.metadata?.prompt" class="image-prompt">
          <strong>Prompt:</strong> {{ message.metadata.prompt }}
        </div>
      </div>

      <!-- Generation Preview -->
      <div
        v-else-if="message.messageType === 'generation_preview'"
        class="preview-content"
      >
        <div class="preview-header">
          <h4>Generation Preview</h4>
          <span class="preview-type">{{
            message.preview?.type || "Unknown"
          }}</span>
        </div>
        <div class="preview-grid">
          <img
            v-for="(image, index) in message.preview?.images || []"
            :key="index"
            :src="image"
            :alt="`Preview ${index + 1}`"
            class="preview-image"
          />
        </div>
        <div class="preview-actions">
          <button class="btn-primary" @click="approveGeneration">
            <i class="icon-check"></i> Approve
          </button>
          <button class="btn-secondary" @click="regeneratePreview">
            <i class="icon-refresh"></i> Regenerate
          </button>
        </div>
      </div>

      <!-- Code Content -->
      <div v-else-if="message.messageType === 'code'" class="code-content">
        <div class="code-header">
          <span class="code-language">{{
            message.metadata?.language || "code"
          }}</span>
          <button class="copy-code-btn" @click="copyCode">
            <i class="icon-copy"></i> Copy
          </button>
        </div>
        <pre><code v-html="highlightedCode"></code></pre>
      </div>

      <!-- Error Content -->
      <div v-else-if="message.messageType === 'error'" class="error-content">
        <div class="error-message">
          <i class="icon-alert-circle"></i>
          <div class="error-details">
            <div class="error-title">
              {{ message.metadata?.title || "Error" }}
            </div>
            <div class="error-text">{{ message.content }}</div>
            <div v-if="message.metadata?.details" class="error-stack">
              <details>
                <summary>Show details</summary>
                <pre>{{ message.metadata.details }}</pre>
              </details>
            </div>
          </div>
        </div>
      </div>

      <!-- File Attachment -->
      <div v-else-if="message.messageType === 'file'" class="file-content">
        <div class="file-attachment">
          <div class="file-icon">
            <i :class="getFileIcon(message.metadata?.filename)"></i>
          </div>
          <div class="file-details">
            <div class="file-name">
              {{ message.metadata?.filename || "Unknown file" }}
            </div>
            <div class="file-size">
              {{ formatFileSize(message.metadata?.size) }}
            </div>
          </div>
          <button class="file-download" @click="downloadFile">
            <i class="icon-download"></i>
          </button>
        </div>
      </div>

      <!-- Fallback for unknown types -->
      <div v-else class="unknown-content">
        <div class="unknown-message">
          <i class="icon-help-circle"></i>
          <span>Unsupported message type: {{ message.messageType }}</span>
        </div>
        <pre class="debug-data">{{ JSON.stringify(message, null, 2) }}</pre>
      </div>
    </div>

    <!-- Message Metadata -->
    <div v-if="hasMetadata && message.metadata" class="message-metadata">
      <div v-if="message.metadata.model" class="metadata-item">
        <span class="metadata-label">Model:</span>
        <span class="metadata-value">{{ message.metadata.model }}</span>
      </div>
      <div v-if="message.metadata.tokens" class="metadata-item">
        <span class="metadata-label">Tokens:</span>
        <span class="metadata-value">{{ message.metadata.tokens }}</span>
      </div>
      <div v-if="message.metadata.processingTime" class="metadata-item">
        <span class="metadata-label">Time:</span>
        <span class="metadata-value"
          >{{ formatTime(message.metadata.processingTime) }}ms</span
        >
      </div>
    </div>

    <!-- Suggestions -->
    <div
      v-if="message.suggestions && message.suggestions.length > 0"
      class="message-suggestions"
    >
      <div class="suggestions-header">Suggestions:</div>
      <div class="suggestions-list">
        <button
          v-for="(suggestion, index) in message.suggestions"
          :key="index"
          class="suggestion-chip"
          @click="applySuggestion(suggestion)"
        >
          {{ suggestion }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";

// Props
const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
});

// Emits
const emit = defineEmits([
  "retry",
  "edit",
  "copy",
  "approve-generation",
  "regenerate",
]);

// State
const imageLoading = ref(true);
const isStreaming = ref(false);

// Computed properties
const showHeader = computed(() => {
  return (
    props.message.type !== "system" || props.message.messageType === "progress"
  );
});

const senderName = computed(() => {
  switch (props.message.type) {
    case "user":
      return "You";
    case "echo":
      return "Echo Brain";
    case "system":
      return "System";
    default:
      return "Unknown";
  }
});

const avatarIcon = computed(() => {
  switch (props.message.type) {
    case "user":
      return "👤";
    case "echo":
      return "🧠";
    case "system":
      return "⚙️";
    default:
      return "❓";
  }
});

const systemIcon = computed(() => {
  switch (props.message.level) {
    case "success":
      return "icon-check-circle";
    case "warning":
      return "icon-alert-triangle";
    case "error":
      return "icon-alert-circle";
    default:
      return "icon-info";
  }
});

const formattedTime = computed(() => {
  if (!props.message.timestamp) return "";

  const date = new Date(props.message.timestamp);
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
});

const hasMetadata = computed(() => {
  return (
    props.message.metadata && Object.keys(props.message.metadata).length > 0
  );
});

const formattedContent = computed(() => {
  if (!props.message.content) return "";

  // Basic markdown-like formatting
  let content = props.message.content
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");

  // Handle code blocks
  content = content.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");

  return content;
});

const highlightedCode = computed(() => {
  // Basic syntax highlighting (would use a library like Prism.js in production)
  if (!props.message.content) return "";

  let code = props.message.content
    .replace(
      /\b(function|const|let|var|if|else|for|while|return)\b/g,
      '<span class="keyword">$1</span>',
    )
    .replace(/("[^"]*"|'[^']*')/g, '<span class="string">$1</span>')
    .replace(/\/\/.*$/gm, '<span class="comment">$&</span>');

  return code;
});

// Methods
const copyMessage = () => {
  emit("copy", props.message);
};

const editMessage = () => {
  emit("edit", props.message);
};

const retryMessage = () => {
  emit("retry", props.message);
};

const handleImageLoad = () => {
  imageLoading.value = false;
};

const handleImageError = () => {
  imageLoading.value = false;
  // Could emit an event to handle broken images
};

const approveGeneration = () => {
  emit("approve-generation", props.message);
};

const regeneratePreview = () => {
  emit("regenerate", props.message);
};

const copyCode = () => {
  navigator.clipboard.writeText(props.message.content);
};

const applySuggestion = (suggestion) => {
  // Emit to parent to apply suggestion
  emit("apply-suggestion", suggestion);
};

const downloadFile = () => {
  if (props.message.content) {
    window.open(props.message.content, "_blank");
  }
};

const getFileIcon = (filename) => {
  if (!filename) return "icon-file";

  const ext = filename.split(".").pop()?.toLowerCase();

  switch (ext) {
    case "jpg":
    case "jpeg":
    case "png":
    case "gif":
    case "webp":
      return "icon-image";
    case "mp4":
    case "mov":
    case "avi":
    case "webm":
      return "icon-video";
    case "mp3":
    case "wav":
    case "ogg":
      return "icon-music";
    case "pdf":
      return "icon-file-pdf";
    case "json":
      return "icon-code";
    default:
      return "icon-file";
  }
};

const formatFileSize = (bytes) => {
  if (!bytes) return "";

  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return Math.round((bytes / Math.pow(1024, i)) * 100) / 100 + " " + sizes[i];
};

const formatETA = (seconds) => {
  if (!seconds || seconds < 0) return "Unknown";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
};

const formatTime = (ms) => {
  return Math.round(ms * 100) / 100;
};

// Lifecycle
onMounted(() => {
  // Set streaming state based on message
  if (props.message.status === "streaming") {
    isStreaming.value = true;
  }
});
</script>

<style scoped>
.message-bubble {
  display: flex;
  flex-direction: column;
  margin-bottom: 1rem;
  max-width: 800px;
  animation: slideIn 0.3s ease-out;
}

.message-user {
  align-self: flex-end;
}

.message-echo,
.message-system {
  align-self: flex-start;
}

/* Message Header */
.message-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}

.message-user .message-avatar {
  background: linear-gradient(135deg, #4caf50 0%, #66bb6a 100%);
}

.message-system .message-avatar {
  background: linear-gradient(135deg, #757575 0%, #9e9e9e 100%);
}

.message-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sender-name {
  font-weight: 600;
  color: #ffffff;
  font-size: 0.9rem;
}

.message-time {
  font-size: 0.8rem;
  color: #999;
}

.message-actions {
  display: flex;
  gap: 0.25rem;
  opacity: 0;
  transition: opacity 0.2s;
}

.message-bubble:hover .message-actions {
  opacity: 1;
}

.action-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 4px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: rgba(123, 104, 238, 0.2);
  color: #7b68ee;
}

.retry-btn:hover {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

/* Message Content */
.message-content {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  padding: 1rem;
  border: 1px solid #4a4a4a;
  position: relative;
}

.message-user .message-content {
  background: rgba(123, 104, 238, 0.2);
  border-color: rgba(123, 104, 238, 0.3);
}

.is-failed .message-content {
  border-color: rgba(244, 67, 54, 0.5);
  background: rgba(244, 67, 54, 0.1);
}

.is-streaming .message-content::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, #7b68ee, transparent);
  animation: streaming 2s infinite;
}

/* Text Content */
.text-content .message-text {
  line-height: 1.6;
  color: #ffffff;
}

.message-text :deep(strong) {
  color: #7b68ee;
  font-weight: 600;
}

.message-text :deep(em) {
  color: #9c88ff;
  font-style: italic;
}

.message-text :deep(code) {
  background: rgba(0, 0, 0, 0.5);
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-family: "SF Mono", "Monaco", "Inconsolata", monospace;
  font-size: 0.85em;
  color: #7b68ee;
}

.message-text :deep(pre) {
  background: rgba(0, 0, 0, 0.5);
  padding: 1rem;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5rem 0;
  border: 1px solid #4a4a4a;
}

/* System Content */
.system-content {
  background: none;
  border: none;
  padding: 0.5rem;
}

.system-message {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: 8px;
  font-size: 0.9rem;
}

.system-info {
  background: rgba(33, 150, 243, 0.2);
  color: #2196f3;
  border: 1px solid rgba(33, 150, 243, 0.3);
}

.system-success {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
  border: 1px solid rgba(76, 175, 80, 0.3);
}

.system-warning {
  background: rgba(255, 152, 0, 0.2);
  color: #ff9800;
  border: 1px solid rgba(255, 152, 0, 0.3);
}

.system-error {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
  border: 1px solid rgba(244, 67, 54, 0.3);
}

/* Progress Content */
.progress-content {
  background: none;
  border: none;
  padding: 0;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.progress-title {
  font-weight: 500;
  color: #ffffff;
}

.progress-percentage {
  font-size: 0.9rem;
  color: #7b68ee;
  font-weight: 600;
}

.progress-bar {
  height: 6px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7b68ee, #9c88ff);
  border-radius: 3px;
  transition: width 0.3s ease;
  animation: progress-pulse 2s infinite;
}

.progress-eta {
  font-size: 0.8rem;
  color: #999;
  text-align: right;
}

/* Image Content */
.image-content {
  padding: 0;
  background: none;
  border: none;
}

.image-container {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.5);
  margin-bottom: 0.5rem;
}

.image-container img {
  width: 100%;
  height: auto;
  display: block;
}

.image-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(123, 104, 238, 0.2);
  border-top: 3px solid #7b68ee;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.image-prompt {
  font-size: 0.8rem;
  color: #999;
  padding: 0.5rem;
}

/* Generation Preview */
.preview-content {
  padding: 0;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1rem 0.5rem;
  border-bottom: 1px solid #4a4a4a;
  margin-bottom: 1rem;
}

.preview-header h4 {
  margin: 0;
  color: #7b68ee;
}

.preview-type {
  font-size: 0.8rem;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding: 0 1rem;
}

.preview-image {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 6px;
  cursor: pointer;
  transition: transform 0.2s;
}

.preview-image:hover {
  transform: scale(1.02);
}

.preview-actions {
  display: flex;
  gap: 0.5rem;
  padding: 0 1rem 1rem;
}

.btn-primary,
.btn-secondary {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  color: white;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(123, 104, 238, 0.3);
}

.btn-secondary {
  background: rgba(0, 0, 0, 0.3);
  color: #cccccc;
  border: 1px solid #4a4a4a;
}

.btn-secondary:hover {
  background: rgba(0, 0, 0, 0.5);
  border-color: #666;
}

/* Code Content */
.code-content {
  padding: 0;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: rgba(0, 0, 0, 0.5);
  border-bottom: 1px solid #4a4a4a;
}

.code-language {
  font-size: 0.8rem;
  color: #7b68ee;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.copy-code-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  transition: color 0.2s;
}

.copy-code-btn:hover {
  color: #7b68ee;
}

.code-content pre {
  margin: 0;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.7);
  overflow-x: auto;
  font-family: "SF Mono", "Monaco", "Inconsolata", monospace;
  font-size: 0.85rem;
  line-height: 1.5;
}

.code-content :deep(.keyword) {
  color: #ff79c6;
  font-weight: 600;
}

.code-content :deep(.string) {
  color: #f1fa8c;
}

.code-content :deep(.comment) {
  color: #6272a4;
  font-style: italic;
}

/* Error Content */
.error-content {
  padding: 0;
}

.error-message {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid rgba(244, 67, 54, 0.3);
  border-radius: 8px;
  color: #f44336;
}

.error-message i {
  font-size: 1.2rem;
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.error-details {
  flex: 1;
}

.error-title {
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.error-text {
  margin-bottom: 0.5rem;
}

.error-stack {
  margin-top: 0.5rem;
}

.error-stack summary {
  cursor: pointer;
  font-size: 0.8rem;
  color: #999;
}

.error-stack pre {
  margin-top: 0.5rem;
  font-size: 0.8rem;
  background: rgba(0, 0, 0, 0.5);
  padding: 0.5rem;
  border-radius: 4px;
  overflow-x: auto;
}

/* File Content */
.file-attachment {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #4a4a4a;
  border-radius: 8px;
}

.file-icon {
  width: 48px;
  height: 48px;
  background: rgba(123, 104, 238, 0.2);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #7b68ee;
  font-size: 1.5rem;
}

.file-details {
  flex: 1;
}

.file-name {
  font-weight: 500;
  color: #ffffff;
  margin-bottom: 0.25rem;
}

.file-size {
  font-size: 0.8rem;
  color: #999;
}

.file-download {
  background: rgba(123, 104, 238, 0.2);
  border: 1px solid rgba(123, 104, 238, 0.3);
  color: #7b68ee;
  padding: 0.5rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.file-download:hover {
  background: rgba(123, 104, 238, 0.3);
}

/* Unknown Content */
.unknown-content {
  padding: 1rem;
  background: rgba(255, 152, 0, 0.1);
  border: 1px solid rgba(255, 152, 0, 0.3);
  border-radius: 8px;
}

.unknown-message {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #ff9800;
  margin-bottom: 1rem;
}

.debug-data {
  background: rgba(0, 0, 0, 0.5);
  padding: 0.75rem;
  border-radius: 4px;
  font-size: 0.8rem;
  color: #999;
  overflow-x: auto;
}

/* Message Metadata */
.message-metadata {
  display: flex;
  gap: 1rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid #3a3a3a;
  font-size: 0.8rem;
}

.metadata-item {
  display: flex;
  gap: 0.25rem;
}

.metadata-label {
  color: #999;
}

.metadata-value {
  color: #7b68ee;
  font-weight: 500;
}

/* Message Suggestions */
.message-suggestions {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #3a3a3a;
}

.suggestions-header {
  font-size: 0.8rem;
  color: #999;
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.suggestions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.suggestion-chip {
  background: rgba(123, 104, 238, 0.1);
  border: 1px solid rgba(123, 104, 238, 0.3);
  color: #7b68ee;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s;
}

.suggestion-chip:hover {
  background: rgba(123, 104, 238, 0.2);
  transform: translateY(-1px);
}

/* Animations */
@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes streaming {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

@keyframes progress-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
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

/* Responsive Design */
@media (max-width: 768px) {
  .message-bubble {
    max-width: 100%;
  }

  .message-header {
    gap: 0.5rem;
  }

  .message-avatar {
    width: 32px;
    height: 32px;
  }

  .message-meta {
    font-size: 0.8rem;
  }

  .message-content {
    padding: 0.75rem;
  }

  .preview-grid {
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  }

  .preview-actions {
    flex-direction: column;
  }

  .message-metadata {
    flex-direction: column;
    gap: 0.5rem;
  }
}
</style>
