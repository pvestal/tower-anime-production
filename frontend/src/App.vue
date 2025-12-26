<template>
  <div id="app">
    <nav class="navbar">
      <div class="nav-brand">
        <span class="title">Anime Studio</span>
      </div>
      <div class="nav-links">
        <router-link to="/" class="nav-link">Dashboard</router-link>
        <router-link to="/projects" class="nav-link">Projects</router-link>
        <router-link to="/characters" class="nav-link">Characters</router-link>
        <router-link to="/studio" class="nav-link">🎬 Studio</router-link>
        <router-link to="/generate" class="nav-link">Generate</router-link>
        <router-link to="/gallery" class="nav-link">Gallery</router-link>
        <router-link to="/chat" class="nav-link">🧠 Chat</router-link>
      </div>
      <div class="nav-status">
        <span :class="['status-dot', comfyStatus]"></span>
        <span class="status-text">ComfyUI</span>
      </div>
    </nav>

    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { useCharacterStore } from "@/stores/characterStore";

const store = useCharacterStore();
const comfyStatus = ref("checking");

let intervalId = null;

const checkComfyUI = async () => {
  try {
    await store.updateQueue();
    comfyStatus.value = "online";
  } catch {
    comfyStatus.value = "offline";
  }
};

onMounted(() => {
  store.loadCharacters();
  store.loadStyles();
  store.loadModels();
  checkComfyUI();
  intervalId = setInterval(checkComfyUI, 5000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  color: #ffffff;
  min-height: 100vh;
}

.navbar {
  background: rgba(45, 45, 45, 0.9);
  border-bottom: 1px solid #4a4a4a;
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  backdrop-filter: blur(10px);
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.2rem;
  font-weight: 600;
  color: #7b68ee;
  text-shadow: 0 0 10px rgba(123, 104, 238, 0.3);
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
}

.nav-links {
  display: flex;
  gap: 2rem;
}

.nav-link {
  text-decoration: none;
  color: #cccccc;
  font-weight: 500;
  transition: color 0.2s;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.9rem;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: #7b68ee;
  font-weight: bold;
  text-shadow: 0 0 5px rgba(123, 104, 238, 0.3);
}

.nav-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #ffffff;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ccc;
}

.status-dot.online {
  background: green;
}

.status-dot.offline {
  background: red;
}

.status-dot.checking {
  background: orange;
}

.main-content {
  flex: 1;
  padding: 0;
  max-width: 100%;
  margin: 0;
  width: 100%;
  min-height: calc(100vh - 80px);
}
</style>
