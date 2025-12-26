<template>
  <div
    class="creative-chat"
    :class="{ 'sidebar-collapsed': chatStore.isSidebarCollapsed }"
  >
    <!-- Chat Header -->
    <div class="chat-header">
      <div class="header-left">
        <button class="sidebar-toggle" @click="chatStore.toggleSidebar()">
          <i
            :class="chatStore.isSidebarCollapsed ? 'icon-menu' : 'icon-close'"
          ></i>
        </button>
        <div class="chat-mode-selector">
          <div class="current-mode">
            <span class="mode-icon">{{
              chatStore.currentModeConfig.icon
            }}</span>
            <span class="mode-name">{{
              chatStore.currentModeConfig.name
            }}</span>
          </div>
          <div v-if="showModeDropdown" class="mode-dropdown">
            <div
              v-for="mode in chatStore.availableModes"
              :key="mode.id"
              class="mode-option"
              :class="{ active: mode.id === chatStore.chatMode }"
              @click="selectMode(mode.id)"
            >
              <span class="mode-icon">{{ mode.icon }}</span>
              <div class="mode-details">
                <div class="mode-name">{{ mode.name }}</div>
                <div class="mode-desc">{{ mode.description }}</div>
              </div>
            </div>
          </div>
          <button
            class="mode-toggle"
            @click="showModeDropdown = !showModeDropdown"
          >
            <i class="icon-chevron-down"></i>
          </button>
        </div>
      </div>

      <div class="header-center">
        <div class="connection-status">
          <span
            :class="[
              'status-dot',
              chatStore.isConnected ? 'online' : 'offline',
            ]"
            :title="
              chatStore.isConnected ? 'Connected to Echo Brain' : 'Disconnected'
            "
          ></span>
          <span class="status-text">{{
            chatStore.isConnected ? "Connected" : "Offline"
          }}</span>
        </div>
      </div>

      <div class="header-right">
        <button class="header-btn" title="Clear Chat" @click="clearChat">
          <i class="icon-trash"></i>
        </button>
        <button class="header-btn" title="Export Chat" @click="exportChat">
          <i class="icon-download"></i>
        </button>
      </div>
    </div>

    <!-- Main Chat Content -->
    <div class="chat-content">
      <!-- Sidebar -->
      <div v-if="!chatStore.isSidebarCollapsed" class="chat-sidebar">
        <div class="sidebar-section">
          <h3>Context</h3>
          <div class="context-info">
            <div v-if="animeStore.selectedProject" class="context-item">
              <span class="label">Project:</span>
              <span class="value">{{ animeStore.selectedProject.name }}</span>
            </div>
            <div v-if="animeStore.selectedCharacter" class="context-item">
              <span class="label">Character:</span>
              <span class="value">{{ animeStore.selectedCharacter.name }}</span>
            </div>
            <div v-if="animeStore.selectedScene" class="context-item">
              <span class="label">Scene:</span>
              <span class="value">{{ animeStore.selectedScene.name }}</span>
            </div>
          </div>
        </div>

        <div class="sidebar-section">
          <h3>Quick Actions</h3>
          <div class="quick-actions">
            <button
              v-for="suggestion in chatStore.contextualSuggestions.slice(0, 4)"
              :key="suggestion"
              class="quick-action-btn"
              @click="sendQuickMessage(suggestion)"
            >
              {{ suggestion }}
            </button>
          </div>
        </div>

        <div class="sidebar-section">
          <h3>Recent Projects</h3>
          <div class="recent-projects">
            <div
              v-for="project in animeStore.projects.slice(0, 3)"
              :key="project.id"
              class="project-item"
              :class="{ active: animeStore.selectedProject?.id === project.id }"
              @click="switchToProject(project)"
            >
              <div class="project-name">{{ project.name }}</div>
              <div class="project-status">{{ project.status }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Chat Messages Area -->
      <div class="chat-main">
        <div ref="messagesContainer" class="chat-messages">
          <!-- Welcome Message -->
          <div v-if="chatStore.messages.length === 0" class="welcome-message">
            <div class="welcome-content">
              <div class="welcome-icon">
                {{ chatStore.currentModeConfig.icon }}
              </div>
              <h2>{{ chatStore.currentModeConfig.name }}</h2>
              <p>{{ chatStore.currentModeConfig.description }}</p>
              <div class="welcome-suggestions">
                <button
                  v-for="suggestion in chatStore.contextualSuggestions.slice(
                    0,
                    3,
                  )"
                  :key="suggestion"
                  class="suggestion-btn"
                  @click="sendQuickMessage(suggestion)"
                >
                  {{ suggestion }}
                </button>
              </div>
            </div>
          </div>

          <!-- Messages -->
          <MessageBubble
            v-for="message in chatStore.recentMessages"
            :key="message.id"
            :message="message"
            @retry="retryMessage"
            @edit="editMessage"
            @copy="copyMessage"
          />

          <!-- Typing Indicator -->
          <div v-if="chatStore.typingStatus" class="typing-indicator">
            <div class="typing-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span class="typing-text">Echo is thinking...</span>
          </div>

          <!-- Schema Form -->
          <div v-if="chatStore.hasActiveSchema" class="schema-form-container">
            <SchemaFormRenderer
              :schema="chatStore.currentSchema"
              :form-data="chatStore.formData"
              @submit="chatStore.submitSchemaForm"
              @cancel="cancelForm"
            />
          </div>
        </div>

        <!-- Input Area -->
        <div class="chat-input-area">
          <!-- Error Message -->
          <div v-if="chatStore.error" class="error-banner">
            <span class="error-text">{{ chatStore.error }}</span>
            <button class="error-close" @click="chatStore.error = null">
              <i class="icon-close"></i>
            </button>
          </div>

          <!-- Input Bar -->
          <InputBar
            :disabled="chatStore.isLoading || !chatStore.isConnected"
            :suggestions="chatStore.suggestions"
            @send="handleSendMessage"
            @voice-toggle="toggleVoiceInput"
          />
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="chatStore.isLoading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>Processing...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from "vue";
import { useCreativeChatStore } from "@/stores/creativeChatStore";
import { useAnimeStore } from "@/stores/animeStore";
import MessageBubble from "./MessageBubble.vue";
import InputBar from "./InputBar.vue";
import SchemaFormRenderer from "./SchemaFormRenderer.vue";

// Store references
const chatStore = useCreativeChatStore();
const animeStore = useAnimeStore();

// Component state
const messagesContainer = ref(null);
const showModeDropdown = ref(false);

// Methods
const handleSendMessage = async (message) => {
  try {
    await chatStore.sendMessage(message);
    scrollToBottom();
  } catch (error) {
    console.error("Failed to send message:", error);
  }
};

const sendQuickMessage = async (suggestion) => {
  await handleSendMessage(suggestion);
};

const selectMode = (modeId) => {
  chatStore.setChatMode(modeId);
  showModeDropdown.value = false;
};

const switchToProject = (project) => {
  animeStore.selectProject(project);
  chatStore.updateContext({
    project_id: project.id,
    character_id: null,
    scene_id: null,
  });
};

const clearChat = () => {
  if (
    confirm("Are you sure you want to clear the chat? This cannot be undone.")
  ) {
    chatStore.clearChat();
  }
};

const exportChat = () => {
  const chatData = {
    messages: chatStore.messages,
    context: chatStore.currentContext,
    timestamp: new Date().toISOString(),
  };

  const blob = new Blob([JSON.stringify(chatData, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `chat-export-${new Date().toISOString().slice(0, 19)}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

const retryMessage = (message) => {
  // Retry failed message
  handleSendMessage(message.content);
};

const editMessage = (message) => {
  // TODO: Implement message editing
  console.log("Edit message:", message);
};

const copyMessage = (message) => {
  navigator.clipboard
    .writeText(message.content)
    .then(() => {
      chatStore.addSystemMessage("Message copied to clipboard", "success");
    })
    .catch(() => {
      chatStore.addSystemMessage("Failed to copy message", "error");
    });
};

const cancelForm = () => {
  chatStore.setCurrentSchema(null);
  chatStore.addSystemMessage("Form cancelled", "info");
};

const toggleVoiceInput = () => {
  // TODO: Implement voice input
  console.log("Toggle voice input");
};

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  });
};

// Watchers
watch(
  () => chatStore.messages.length,
  () => scrollToBottom(),
  { flush: "post" },
);

// Click outside handler for mode dropdown
const handleClickOutside = (event) => {
  if (!event.target.closest(".chat-mode-selector")) {
    showModeDropdown.value = false;
  }
};

// Lifecycle
onMounted(() => {
  // Initialize WebSocket connection
  chatStore.initializeWebSocket();

  // Set initial context from anime store
  chatStore.updateContext({
    project_id: animeStore.selectedProject?.id,
    character_id: animeStore.selectedCharacter?.id,
    scene_id: animeStore.selectedScene?.id,
  });

  // Add click outside listener
  document.addEventListener("click", handleClickOutside);

  // Focus on page load
  scrollToBottom();
});

onUnmounted(() => {
  // Cleanup WebSocket
  chatStore.disconnect();

  // Remove listeners
  document.removeEventListener("click", handleClickOutside);
});
</script>

<style scoped>
.creative-chat {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  color: #ffffff;
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  background: rgba(45, 45, 45, 0.9);
  border-bottom: 1px solid #4a4a4a;
  backdrop-filter: blur(10px);
  z-index: 10;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.sidebar-toggle {
  background: none;
  border: none;
  color: #cccccc;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.2s;
}

.sidebar-toggle:hover {
  background: rgba(123, 104, 238, 0.2);
  color: #7b68ee;
}

.chat-mode-selector {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.current-mode {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: rgba(123, 104, 238, 0.2);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.current-mode:hover {
  background: rgba(123, 104, 238, 0.3);
}

.mode-icon {
  font-size: 1.2rem;
}

.mode-name {
  font-weight: 500;
  color: #7b68ee;
}

.mode-toggle {
  background: none;
  border: none;
  color: #cccccc;
  cursor: pointer;
  padding: 4px;
  transition: transform 0.2s;
}

.mode-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: rgba(45, 45, 45, 0.95);
  border: 1px solid #4a4a4a;
  border-radius: 8px;
  backdrop-filter: blur(10px);
  z-index: 100;
  margin-top: 0.5rem;
  min-width: 280px;
}

.mode-option {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #3a3a3a;
}

.mode-option:last-child {
  border-bottom: none;
}

.mode-option:hover {
  background: rgba(123, 104, 238, 0.1);
}

.mode-option.active {
  background: rgba(123, 104, 238, 0.2);
}

.mode-details {
  flex: 1;
}

.mode-desc {
  font-size: 0.8rem;
  color: #999;
  margin-top: 0.25rem;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f44336;
  animation: pulse 2s infinite;
}

.status-dot.online {
  background: #4caf50;
}

.status-text {
  font-size: 0.9rem;
  color: #cccccc;
}

.header-btn {
  background: none;
  border: none;
  color: #cccccc;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.2s;
}

.header-btn:hover {
  background: rgba(123, 104, 238, 0.2);
  color: #7b68ee;
}

/* Content */
.chat-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Sidebar */
.chat-sidebar {
  width: 300px;
  background: rgba(26, 26, 26, 0.9);
  border-right: 1px solid #4a4a4a;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  transition: width 0.3s ease;
}

.sidebar-collapsed .chat-sidebar {
  width: 0;
  overflow: hidden;
}

.sidebar-section {
  padding: 1.5rem;
  border-bottom: 1px solid #3a3a3a;
}

.sidebar-section h3 {
  margin: 0 0 1rem 0;
  font-size: 0.9rem;
  color: #7b68ee;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.context-info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.context-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.context-item .label {
  font-size: 0.8rem;
  color: #999;
  min-width: 60px;
}

.context-item .value {
  font-size: 0.8rem;
  color: #cccccc;
  font-weight: 500;
}

.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.quick-action-btn {
  background: rgba(123, 104, 238, 0.1);
  border: 1px solid rgba(123, 104, 238, 0.3);
  color: #7b68ee;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  text-align: left;
  transition: all 0.2s;
}

.quick-action-btn:hover {
  background: rgba(123, 104, 238, 0.2);
  border-color: rgba(123, 104, 238, 0.5);
}

.recent-projects {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.project-item {
  padding: 0.75rem;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.project-item:hover {
  background: rgba(123, 104, 238, 0.1);
}

.project-item.active {
  background: rgba(123, 104, 238, 0.2);
  border: 1px solid rgba(123, 104, 238, 0.4);
}

.project-name {
  font-size: 0.8rem;
  color: #cccccc;
  font-weight: 500;
}

.project-status {
  font-size: 0.7rem;
  color: #999;
  margin-top: 0.25rem;
  text-transform: uppercase;
}

/* Main Chat */
.chat-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Welcome Message */
.welcome-message {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  text-align: center;
}

.welcome-content {
  max-width: 500px;
  padding: 2rem;
}

.welcome-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.welcome-content h2 {
  color: #7b68ee;
  margin-bottom: 0.5rem;
  font-size: 2rem;
}

.welcome-content p {
  color: #999;
  margin-bottom: 2rem;
  font-size: 1.1rem;
  line-height: 1.5;
}

.welcome-suggestions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: center;
}

.suggestion-btn {
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  border: none;
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
  min-width: 200px;
}

.suggestion-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(123, 104, 238, 0.3);
}

/* Typing Indicator */
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
  max-width: 200px;
}

.typing-dots {
  display: flex;
  gap: 0.25rem;
}

.typing-dots span {
  width: 6px;
  height: 6px;
  background: #7b68ee;
  border-radius: 50%;
  animation: typing-pulse 1.4s infinite ease-in-out;
}

.typing-dots span:nth-child(1) {
  animation-delay: -0.32s;
}
.typing-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

.typing-text {
  font-size: 0.9rem;
  color: #999;
  font-style: italic;
}

/* Schema Form */
.schema-form-container {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #4a4a4a;
  border-radius: 12px;
  padding: 1.5rem;
  margin-top: 1rem;
}

/* Input Area */
.chat-input-area {
  padding: 1rem 1.5rem;
  border-top: 1px solid #4a4a4a;
  background: rgba(26, 26, 26, 0.9);
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid rgba(244, 67, 54, 0.3);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.error-text {
  color: #f44336;
  font-size: 0.9rem;
}

.error-close {
  background: none;
  border: none;
  color: #f44336;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.error-close:hover {
  background: rgba(244, 67, 54, 0.1);
}

/* Loading Overlay */
.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
  z-index: 1000;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(123, 104, 238, 0.2);
  border-top: 4px solid #7b68ee;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

.loading-overlay p {
  color: #cccccc;
  font-size: 1.1rem;
}

/* Animations */
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes typing-pulse {
  0%,
  80%,
  100% {
    transform: scale(1);
  }
  40% {
    transform: scale(1.2);
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
  .chat-header {
    padding: 1rem;
  }

  .chat-sidebar {
    width: 250px;
  }

  .mode-dropdown {
    min-width: 250px;
  }

  .welcome-content h2 {
    font-size: 1.5rem;
  }

  .welcome-suggestions {
    flex-direction: column;
  }
}

@media (max-width: 480px) {
  .chat-header {
    flex-direction: column;
    gap: 1rem;
  }

  .header-left,
  .header-center,
  .header-right {
    justify-content: center;
  }
}
</style>
