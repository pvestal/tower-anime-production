<template>
  <div class="tower-card bg-gray-900 rounded-lg shadow-lg border border-gray-700">
    <slot />
  </div>
</template>

<script setup>
// Simple card wrapper component
</script>

<style scoped>
.tower-card {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}
</style>
