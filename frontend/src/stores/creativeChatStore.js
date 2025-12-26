import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * Creative Chat Store - Enhanced AI chat interface for anime production
 * Manages real-time conversations, UI schema rendering, and Echo Brain integration
 */
export const useCreativeChatStore = defineStore("creativeChat", () => {
  // ==================== STATE ====================

  // Chat Messages
  const messages = ref([]);
  const currentMessageId = ref(null);
  const typingStatus = ref(false);
  const streamingMessage = ref(null);

  // Chat Context
  const currentContext = ref({
    project_id: null,
    character_id: null,
    scene_id: null,
    conversation_type: "general", // general, character_creation, scene_development, generation
  });

  // UI State
  const isConnected = ref(false);
  const isSidebarCollapsed = ref(false);
  const isLoading = ref(false);
  const error = ref(null);

  // WebSocket Connection
  const wsConnection = ref(null);
  const wsReconnectAttempts = ref(0);
  const maxReconnectAttempts = 5;

  // Form Schema & Dynamic UI
  const currentSchema = ref(null);
  const formData = ref({});
  const schemaQueue = ref([]);

  // Suggestions & Auto-complete
  const suggestions = ref([]);
  const suggestionIndex = ref(-1);

  // Voice Input (Future expansion)
  const voiceEnabled = ref(false);
  const isRecording = ref(false);

  // Chat Modes
  const chatMode = ref("assistant"); // assistant, designer, director, technical
  const availableModes = ref([
    {
      id: "assistant",
      name: "Creative Assistant",
      icon: "🎭",
      description: "General anime production help",
    },
    {
      id: "designer",
      name: "Character Designer",
      icon: "👤",
      description: "Character creation and design",
    },
    {
      id: "director",
      name: "Scene Director",
      icon: "🎬",
      description: "Scene composition and storytelling",
    },
    {
      id: "technical",
      name: "Technical Support",
      icon: "⚙️",
      description: "Workflow and technical guidance",
    },
  ]);

  // ==================== COMPUTED ====================

  const recentMessages = computed(() => {
    return messages.value.slice(-50); // Keep last 50 messages visible
  });

  const contextualSuggestions = computed(() => {
    if (!currentContext.value.conversation_type) return [];

    const suggestionsByType = {
      general: [
        "Create a new character",
        "Develop a scene",
        "Generate artwork",
        "Review project status",
      ],
      character_creation: [
        "Define personality traits",
        "Set appearance details",
        "Create character backstory",
        "Generate reference images",
      ],
      scene_development: [
        "Set scene mood",
        "Define camera angles",
        "Plan character interactions",
        "Generate scene previews",
      ],
      generation: [
        "Adjust generation settings",
        "Preview results",
        "Apply style variations",
        "Export final results",
      ],
    };

    return suggestionsByType[currentContext.value.conversation_type] || [];
  });

  const currentModeConfig = computed(() => {
    return (
      availableModes.value.find((mode) => mode.id === chatMode.value) ||
      availableModes.value[0]
    );
  });

  const hasActiveSchema = computed(() => {
    return currentSchema.value !== null;
  });

  // ==================== ACTIONS ====================

  // WebSocket Management
  function initializeWebSocket() {
    if (typeof window === "undefined") return;

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/api/anime/ws`;

      wsConnection.value = new WebSocket(wsUrl);

      wsConnection.value.onopen = () => {
        isConnected.value = true;
        wsReconnectAttempts.value = 0;
        addSystemMessage("Connected to Echo Brain", "success");

        // Send initial context
        sendContextUpdate();
      };

      wsConnection.value.onmessage = (event) => {
        handleWebSocketMessage(JSON.parse(event.data));
      };

      wsConnection.value.onclose = () => {
        isConnected.value = false;
        if (wsReconnectAttempts.value < maxReconnectAttempts) {
          setTimeout(() => {
            wsReconnectAttempts.value++;
            initializeWebSocket();
          }, 2000 * wsReconnectAttempts.value);
        }
      };

      wsConnection.value.onerror = (error) => {
        console.error("WebSocket error:", error);
        addSystemMessage("Connection error. Retrying...", "error");
      };
    } catch (err) {
      console.error("Failed to initialize WebSocket:", err);
      error.value = err.message;
    }
  }

  function handleWebSocketMessage(data) {
    switch (data.type) {
      case "message_response":
        handleEchoResponse(data);
        break;
      case "schema_update":
        handleSchemaUpdate(data);
        break;
      case "typing_status":
        typingStatus.value = data.typing;
        break;
      case "generation_progress":
        handleGenerationProgress(data);
        break;
      case "error":
        addSystemMessage(data.message, "error");
        break;
      default:
        console.log("Unknown message type:", data);
    }
  }

  // Message Management
  async function sendMessage(content, messageType = "text") {
    if (!content.trim()) return;

    const userMessage = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: "user",
      content: content.trim(),
      messageType,
      timestamp: new Date().toISOString(),
      context: { ...currentContext.value },
      mode: chatMode.value,
    };

    // Add user message immediately
    messages.value.push(userMessage);
    currentMessageId.value = userMessage.id;

    // Start typing indicator
    typingStatus.value = true;

    try {
      if (isConnected.value && wsConnection.value) {
        // Send via WebSocket for real-time response
        wsConnection.value.send(
          JSON.stringify({
            type: "chat_message",
            message: userMessage,
          }),
        );
      } else {
        // Fallback to HTTP API
        await sendMessageViaAPI(userMessage);
      }
    } catch (err) {
      console.error("Failed to send message:", err);
      addSystemMessage("Failed to send message. Please try again.", "error");
      typingStatus.value = false;
    }
  }

  async function sendMessageViaAPI(message) {
    try {
      isLoading.value = true;

      const response = await fetch("/api/anime/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message.content,
          context: message.context,
          mode: message.mode,
          conversation_id: generateConversationId(),
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const echoResponse = await response.json();
      handleEchoResponse({ message: echoResponse });
    } catch (err) {
      error.value = `Failed to get response: ${err.message}`;
      throw err;
    } finally {
      isLoading.value = false;
      typingStatus.value = false;
    }
  }

  function handleEchoResponse(data) {
    const responseMessage = {
      id: `echo_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: "echo",
      content: data.message.response || data.message.content,
      messageType: data.message.type || "text",
      timestamp: new Date().toISOString(),
      metadata: data.message.metadata || {},
      suggestions: data.message.suggestions || [],
    };

    // Handle special message types
    if (data.message.type === "schema_form") {
      responseMessage.schema = data.message.schema;
      setCurrentSchema(data.message.schema);
    }

    if (data.message.type === "generation_preview") {
      responseMessage.preview = data.message.preview;
    }

    messages.value.push(responseMessage);
    typingStatus.value = false;

    // Update suggestions
    if (data.message.suggestions) {
      suggestions.value = data.message.suggestions;
    }

    // Scroll to latest message
    scrollToLatest();
  }

  function handleSchemaUpdate(data) {
    setCurrentSchema(data.schema);
    addSystemMessage("Please fill out the form below", "info");
  }

  function handleGenerationProgress(data) {
    const progressMessage = {
      id: `progress_${Date.now()}`,
      type: "system",
      content: `Generation Progress: ${data.progress}%`,
      messageType: "progress",
      timestamp: new Date().toISOString(),
      progress: data.progress,
      eta: data.eta,
    };

    // Update existing progress message or add new one
    const existingProgressIndex = messages.value.findIndex(
      (msg) => msg.messageType === "progress" && msg.id.startsWith("progress_"),
    );

    if (existingProgressIndex !== -1) {
      messages.value[existingProgressIndex] = progressMessage;
    } else {
      messages.value.push(progressMessage);
    }
  }

  function addSystemMessage(content, level = "info") {
    const systemMessage = {
      id: `system_${Date.now()}`,
      type: "system",
      content,
      messageType: "system",
      level,
      timestamp: new Date().toISOString(),
    };

    messages.value.push(systemMessage);
  }

  // Context Management
  function updateContext(newContext) {
    currentContext.value = { ...currentContext.value, ...newContext };
    sendContextUpdate();
  }

  function sendContextUpdate() {
    if (isConnected.value && wsConnection.value) {
      wsConnection.value.send(
        JSON.stringify({
          type: "context_update",
          context: currentContext.value,
        }),
      );
    }
  }

  function setChatMode(mode) {
    chatMode.value = mode;
    updateContext({ conversation_type: mode });

    const modeConfig = currentModeConfig.value;
    addSystemMessage(
      `Switched to ${modeConfig.name} mode: ${modeConfig.description}`,
      "info",
    );
  }

  // Schema Form Management
  function setCurrentSchema(schema) {
    currentSchema.value = schema;
    formData.value = {};

    // Pre-populate with defaults
    if (schema && schema.properties) {
      Object.keys(schema.properties).forEach((key) => {
        const property = schema.properties[key];
        if (property.default !== undefined) {
          formData.value[key] = property.default;
        }
      });
    }
  }

  async function submitSchemaForm() {
    if (!currentSchema.value) return;

    try {
      isLoading.value = true;

      // Validate form data against schema
      const validation = validateFormData(formData.value, currentSchema.value);
      if (!validation.valid) {
        addSystemMessage(
          `Form validation failed: ${validation.errors.join(", ")}`,
          "error",
        );
        return;
      }

      // Send form data
      const formMessage = {
        type: "schema_response",
        schema_id: currentSchema.value.id,
        data: formData.value,
        timestamp: new Date().toISOString(),
      };

      if (isConnected.value && wsConnection.value) {
        wsConnection.value.send(JSON.stringify(formMessage));
      } else {
        await sendFormViaAPI(formMessage);
      }

      // Clear current schema
      currentSchema.value = null;
      formData.value = {};
    } catch (err) {
      console.error("Failed to submit form:", err);
      addSystemMessage("Failed to submit form. Please try again.", "error");
    } finally {
      isLoading.value = false;
    }
  }

  async function sendFormViaAPI(formMessage) {
    const response = await fetch("/api/anime/chat/form", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formMessage),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result = await response.json();
    handleEchoResponse({ message: result });
  }

  // Utility Functions
  function validateFormData(data, schema) {
    const errors = [];

    // Check required fields
    if (schema.required) {
      schema.required.forEach((field) => {
        if (data[field] === undefined || data[field] === "") {
          errors.push(`${field} is required`);
        }
      });
    }

    // Basic type validation
    Object.keys(data).forEach((key) => {
      const property = schema.properties[key];
      if (!property) return;

      const value = data[key];
      if (value !== undefined && value !== "") {
        switch (property.type) {
          case "number":
            if (isNaN(value)) errors.push(`${key} must be a number`);
            break;
          case "integer":
            if (!Number.isInteger(Number(value)))
              errors.push(`${key} must be an integer`);
            break;
          case "string":
            if (typeof value !== "string")
              errors.push(`${key} must be a string`);
            break;
        }
      }
    });

    return { valid: errors.length === 0, errors };
  }

  function generateConversationId() {
    return `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  function scrollToLatest() {
    // This will be called from components to scroll to latest message
    setTimeout(() => {
      const chatContainer = document.querySelector(".chat-messages");
      if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      }
    }, 100);
  }

  // UI State Management
  function toggleSidebar() {
    isSidebarCollapsed.value = !isSidebarCollapsed.value;
  }

  function clearChat() {
    messages.value = [];
    currentSchema.value = null;
    formData.value = {};
    suggestions.value = [];
    error.value = null;
  }

  // Cleanup
  function disconnect() {
    if (wsConnection.value) {
      wsConnection.value.close();
      wsConnection.value = null;
    }
    isConnected.value = false;
  }

  // ==================== RETURN STORE ====================

  return {
    // State
    messages,
    currentMessageId,
    typingStatus,
    streamingMessage,
    currentContext,
    isConnected,
    isSidebarCollapsed,
    isLoading,
    error,
    wsConnection,
    currentSchema,
    formData,
    suggestions,
    suggestionIndex,
    voiceEnabled,
    isRecording,
    chatMode,
    availableModes,

    // Computed
    recentMessages,
    contextualSuggestions,
    currentModeConfig,
    hasActiveSchema,

    // Actions
    initializeWebSocket,
    sendMessage,
    updateContext,
    setChatMode,
    setCurrentSchema,
    submitSchemaForm,
    toggleSidebar,
    clearChat,
    disconnect,
    addSystemMessage,
    scrollToLatest,
  };
});
