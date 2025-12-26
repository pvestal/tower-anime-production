<template>
  <div class="project-configuration">
    <div class="config-section">
      <h3>Project Configuration</h3>
      <p>Project configuration interface coming soon...</p>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  project: Object,
});

const emit = defineEmits(["update-project"]);
</script>

<style scoped>
.project-configuration {
  padding: 1rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
}

.config-section h3 {
  margin-bottom: 1rem;
  color: #333;
}
</style>
