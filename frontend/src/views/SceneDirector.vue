<template>
  <div class="scene-director-view">
    <div class="container mx-auto p-6">
      <h1 class="text-3xl font-bold mb-6 text-center">Scene Director</h1>
      <p class="text-gray-400 text-center mb-8">
        Create professional scenes using the Enterprise Director Mode
      </p>

      <!-- Scene Composer Component -->
      <SceneComposer />
    </div>
  </div>
</template>

<script setup>
import SceneComposer from "@/components/director/SceneComposer.vue";
</script>

<style scoped>
.scene-director-view {
  min-height: 100vh;
  background: #0f0f0f;
  color: #e0e0e0;
}
</style>
