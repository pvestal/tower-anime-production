<template>
  <div class="echo-assist-panel">
    <!-- Placeholder for Echo Assist functionality -->
  </div>
</template>

<script setup>
defineProps({
  prompt: String,
  currentModel: String,
});

defineEmits(["apply-model", "select-character"]);
</script>

<style scoped>
.echo-assist-panel {
  /* Minimal styling to prevent errors */
  display: none;
}
</style>
