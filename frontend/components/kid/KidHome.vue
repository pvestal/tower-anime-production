<template>
  <div class="kid-home">
    <div class="kid-greeting">
      <span class="greeting-wave">Hi {{ displayName }}!</span>
      <span class="greeting-sub">What do you want to do?</span>
    </div>

    <div class="kid-tiles">
      <RouterLink to="/cast/characters" class="kid-tile tile-characters">
        <div class="tile-icon">
          <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="32" cy="22" r="14" fill="currentColor" opacity="0.25"/>
            <circle cx="32" cy="22" r="10" fill="currentColor"/>
            <path d="M12 56c0-11 9-20 20-20s20 9 20 20" stroke="currentColor" stroke-width="4" fill="currentColor" opacity="0.25" stroke-linecap="round"/>
          </svg>
        </div>
        <span class="tile-label">Characters</span>
        <span class="tile-desc">Meet the cast</span>
      </RouterLink>

      <RouterLink to="/publish/library" class="kid-tile tile-watch">
        <div class="tile-icon">
          <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="6" y="12" width="52" height="36" rx="6" fill="currentColor" opacity="0.25"/>
            <rect x="10" y="16" width="44" height="28" rx="3" fill="currentColor" opacity="0.15"/>
            <polygon points="26,24 26,40 42,32" fill="currentColor"/>
            <rect x="22" y="52" width="20" height="4" rx="2" fill="currentColor" opacity="0.4"/>
          </svg>
        </div>
        <span class="tile-label">Watch</span>
        <span class="tile-desc">See episodes</span>
      </RouterLink>

      <RouterLink to="/play" class="kid-tile tile-play">
        <div class="tile-icon">
          <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="14" width="56" height="36" rx="10" fill="currentColor" opacity="0.25"/>
            <circle cx="20" cy="32" r="7" fill="currentColor" opacity="0.4"/>
            <rect x="17" y="29" width="6" height="6" rx="1" fill="currentColor"/>
            <circle cx="44" cy="28" r="3.5" fill="currentColor"/>
            <circle cx="50" cy="34" r="3.5" fill="currentColor"/>
            <circle cx="44" cy="40" r="3.5" fill="currentColor" opacity="0.4"/>
            <circle cx="38" cy="34" r="3.5" fill="currentColor" opacity="0.4"/>
          </svg>
        </div>
        <span class="tile-label">Play</span>
        <span class="tile-desc">Start a story</span>
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const displayName = computed(() => {
  const name = authStore.user?.display_name || ''
  return name.split(' ')[0]
})
</script>

<style scoped>
.kid-home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 70vh;
  padding: 32px 24px;
  gap: 48px;
}

.kid-greeting {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.greeting-wave {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
}

.greeting-sub {
  font-size: 20px;
  color: var(--text-secondary);
  font-weight: 400;
}

.kid-tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  max-width: 720px;
  width: 100%;
}

.kid-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 24px 32px;
  border-radius: 24px;
  text-decoration: none;
  cursor: pointer;
  transition: transform 200ms ease, box-shadow 200ms ease;
  border: 3px solid transparent;
}

.kid-tile:hover {
  transform: translateY(-6px) scale(1.03);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

.kid-tile:active {
  transform: translateY(-2px) scale(1.01);
}

.tile-characters {
  background: linear-gradient(145deg, #5b4fa8, #7c6dd8);
  border-color: rgba(124, 109, 216, 0.4);
}
.tile-characters:hover { border-color: #a090f0; }

.tile-watch {
  background: linear-gradient(145deg, #2d7d6e, #3daa96);
  border-color: rgba(61, 170, 150, 0.4);
}
.tile-watch:hover { border-color: #60d0b8; }

.tile-play {
  background: linear-gradient(145deg, #b8593e, #e07050);
  border-color: rgba(224, 112, 80, 0.4);
}
.tile-play:hover { border-color: #f09878; }

.tile-icon {
  width: 80px;
  height: 80px;
  color: #fff;
}

.tile-icon svg {
  width: 100%;
  height: 100%;
}

.tile-label {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.5px;
}

.tile-desc {
  font-size: 15px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 400;
}

/* Responsive: stack on small screens */
@media (max-width: 600px) {
  .kid-tiles {
    grid-template-columns: 1fr;
    max-width: 300px;
  }
  .greeting-wave {
    font-size: 28px;
  }
}
</style>
