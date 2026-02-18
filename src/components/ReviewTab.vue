<template>
  <div>
    <!-- Sub-tab toggle -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <button
        class="review-subtab"
        :class="{ active: subtab === 'pending' }"
        @click="subtab = 'pending'"
      >
        Pending
        <span v-if="pendingCount > 0" class="review-badge">{{ pendingCount }}</span>
      </button>
      <button
        class="review-subtab"
        :class="{ active: subtab === 'library' }"
        @click="subtab = 'library'"
      >
        Library
      </button>
    </div>

    <!-- Pending sub-tab (existing PendingTab content) -->
    <PendingTab v-if="subtab === 'pending'" />

    <!-- Library sub-tab (existing LibraryTab content) -->
    <LibraryTab v-if="subtab === 'library'" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import PendingTab from './PendingTab.vue'
import LibraryTab from './LibraryTab.vue'

const approvalStore = useApprovalStore()
const subtab = ref<'pending' | 'library'>('pending')
const pendingCount = computed(() => approvalStore.pendingImages.length)
</script>

<style scoped>
.review-subtab {
  padding: 10px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  font-family: var(--font-primary);
  transition: color 150ms ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.review-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
}

.review-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--accent-primary);
  color: #fff;
  min-width: 18px;
  text-align: center;
}
</style>
