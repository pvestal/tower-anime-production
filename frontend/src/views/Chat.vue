<template>
  <div class="chat-view">
    <!-- Echo Brain integration wrapper -->
    <CreativeChat />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from "vue";
import { useAnimeStore } from "@/stores/animeStore";
import { useCreativeChatStore } from "@/stores/creativeChatStore";
import CreativeChat from "@/components/CreativeChat.vue";

const animeStore = useAnimeStore();
const chatStore = useCreativeChatStore();

// Initialize data when component mounts
onMounted(async () => {
  try {
    // Load projects and characters for context
    await Promise.all([
      animeStore.loadProjects(),
      animeStore.loadGenerationHistory(),
    ]);

    // Connect to Echo Brain
    await animeStore.connectToEcho();

    // Set initial context
    chatStore.updateContext({
      project_id: animeStore.selectedProject?.id,
      character_id: animeStore.selectedCharacter?.id,
      scene_id: animeStore.selectedScene?.id,
      conversation_type: "general",
    });

    // Add welcome message if no messages exist
    if (chatStore.messages.length === 0) {
      chatStore.addSystemMessage(
        "Welcome to the Creative Chat! I'm here to help with anime production tasks.",
        "info",
      );
    }
  } catch (error) {
    console.error("Failed to initialize chat:", error);
    chatStore.addSystemMessage(
      "Failed to connect to Echo Brain. Some features may be limited.",
      "warning",
    );
  }
});

// Cleanup when component unmounts
onUnmounted(() => {
  chatStore.disconnect();
});
</script>

<style scoped>
.chat-view {
  height: 100vh;
  width: 100%;
  overflow: hidden;
}

/* Ensure the chat fills the entire view */
.chat-view :deep(.creative-chat) {
  height: 100vh;
}
</style>
