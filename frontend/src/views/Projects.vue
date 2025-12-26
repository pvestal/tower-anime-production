<template>
  <div class="projects-view">
    <ProjectManager />
  </div>
</template>

<script setup>
import ProjectManager from "@/components/ProjectManager.vue";
</script>

<style scoped>
.projects-view {
  width: 100%;
  height: 100vh;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  color: #ffffff;
}
</style>
