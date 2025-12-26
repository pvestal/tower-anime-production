<template>
  <div class="project-assets">
    <div class="assets-section">
      <h3>Project Assets</h3>
      <p>Project assets management interface coming soon...</p>
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
.project-assets {
  padding: 1rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
}

.assets-section h3 {
  margin-bottom: 1rem;
  color: #333;
}
</style>
