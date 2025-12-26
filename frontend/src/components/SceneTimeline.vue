<template>
  <div class="scene-timeline">
    <!-- Timeline Header -->
    <div class="timeline-header">
      <h3>Scene Timeline</h3>
      <div class="timeline-controls">
        <button class="btn-preview" @click="playPreview">
          <span class="icon">▶</span> Preview
        </button>
        <button class="btn-save" @click="$emit('save')">
          <span class="icon">💾</span> Save
        </button>
      </div>
    </div>

    <!-- Timeline Track -->
    <div class="timeline-track">
      <div class="time-ruler">
        <div
          v-for="mark in timeMarks"
          :key="mark"
          class="time-mark"
          :style="{ left: `${(mark / totalDuration) * 100}%` }"
        >
          {{ formatTime(mark) }}
        </div>
      </div>

      <!-- Scene Blocks -->
      <div class="scene-blocks">
        <div
          v-for="(scene, index) in scenes"
          :key="scene.id"
          class="scene-block"
          :class="{
            active: activeScene === index,
            selected: selectedScenes.includes(index),
          }"
          :style="{
            left: `${(getSceneStart(index) / totalDuration) * 100}%`,
            width: `${(scene.duration / totalDuration) * 100}%`,
            backgroundColor: getSceneColor(index),
          }"
          draggable="true"
          @click="selectScene(index)"
          @dragstart="startDrag(index, $event)"
          @dragover.prevent
          @drop="handleDrop(index, $event)"
        >
          <div class="scene-info">
            <span class="scene-label">Scene {{ index + 1 }}</span>
            <span class="scene-duration">{{ scene.duration }}f</span>
          </div>

          <!-- Transition Marker -->
          <div
            v-if="index > 0 && scene.transition_type"
            class="transition-marker"
            :class="scene.transition_type"
          >
            <span>{{ scene.transition_type }}</span>
          </div>
        </div>
      </div>

      <!-- Playhead -->
      <div
        v-if="isPlaying"
        class="playhead"
        :style="{ left: `${(currentTime / totalDuration) * 100}%` }"
      ></div>
    </div>

    <!-- Scene Details -->
    <div v-if="activeScene !== null" class="scene-details">
      <h4>Scene {{ activeScene + 1 }} Details</h4>
      <div class="detail-grid">
        <div class="detail-item">
          <label>Location</label>
          <p>{{ scenes[activeScene].location_prompt }}</p>
        </div>
        <div class="detail-item">
          <label>Action</label>
          <p>{{ scenes[activeScene].action_prompt }}</p>
        </div>
        <div class="detail-item">
          <label>Emotion</label>
          <p>{{ scenes[activeScene].emotion_prompt }}</p>
        </div>
        <div class="detail-item">
          <label>Duration</label>
          <input
            :value="scenes[activeScene].duration"
            type="number"
            min="10"
            max="300"
            @change="
              (e) => updateSceneDuration(activeScene, parseInt(e.target.value))
            "
          />
          frames
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";

const props = defineProps({
  scenes: {
    type: Array,
    required: true,
  },
  fps: {
    type: Number,
    default: 24,
  },
});

const emit = defineEmits(["update:scenes", "save", "preview"]);

// State
const activeScene = ref(null);
const selectedScenes = ref([]);
const isPlaying = ref(false);
const currentTime = ref(0);
const playInterval = ref(null);
const draggedScene = ref(null);

// Computed
const totalDuration = computed(() => {
  return props.scenes.reduce((total, scene) => {
    return total + (scene.duration || 60);
  }, 0);
});

const timeMarks = computed(() => {
  const marks = [];
  const interval = (Math.ceil(totalDuration.value / 10) * 10) / 5;
  for (let i = 0; i <= totalDuration.value; i += interval) {
    marks.push(i);
  }
  return marks;
});

// Methods
const getSceneStart = (index) => {
  let start = 0;
  for (let i = 0; i < index; i++) {
    start += props.scenes[i].duration || 60;
  }
  return start;
};

const getSceneColor = (index) => {
  const colors = [
    "#667eea",
    "#764ba2",
    "#f093fb",
    "#f5576c",
    "#4facfe",
    "#00f2fe",
    "#43e97b",
    "#38f9d7",
  ];
  return colors[index % colors.length];
};

const formatTime = (frames) => {
  const seconds = frames / props.fps;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
};

const selectScene = (index) => {
  activeScene.value = index;
  if (!selectedScenes.value.includes(index)) {
    selectedScenes.value = [index];
  }
};

const startDrag = (index, event) => {
  draggedScene.value = index;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/html", event.target.innerHTML);
};

const handleDrop = (targetIndex, event) => {
  event.preventDefault();
  if (draggedScene.value !== null && draggedScene.value !== targetIndex) {
    // Swap scenes
    const scenes = [...props.scenes];
    const [draggedItem] = scenes.splice(draggedScene.value, 1);
    scenes.splice(targetIndex, 0, draggedItem);

    // Update scene orders
    scenes.forEach((scene, idx) => {
      scene.scene_order = idx + 1;
    });

    emit("update:scenes", scenes);
  }
  draggedScene.value = null;
};

const updateTimeline = () => {
  emit("update:scenes", props.scenes);
};

const updateSceneDuration = (index, duration) => {
  const updatedScenes = [...props.scenes];
  updatedScenes[index] = { ...updatedScenes[index], duration };
  emit("update:scenes", updatedScenes);
};

const playPreview = () => {
  if (isPlaying.value) {
    stopPreview();
    return;
  }

  isPlaying.value = true;
  currentTime.value = 0;

  playInterval.value = setInterval(() => {
    currentTime.value += 1;
    if (currentTime.value >= totalDuration.value) {
      stopPreview();
    }

    // Highlight active scene based on playhead position
    let accumulated = 0;
    for (let i = 0; i < props.scenes.length; i++) {
      const sceneDuration = props.scenes[i].duration || 60;
      if (
        currentTime.value >= accumulated &&
        currentTime.value < accumulated + sceneDuration
      ) {
        activeScene.value = i;
        break;
      }
      accumulated += sceneDuration;
    }
  }, 1000 / props.fps);

  emit("preview");
};

const stopPreview = () => {
  isPlaying.value = false;
  currentTime.value = 0;
  if (playInterval.value) {
    clearInterval(playInterval.value);
    playInterval.value = null;
  }
};

// Initialize scene durations if not set
watch(
  () => props.scenes,
  (scenes) => {
    scenes.forEach((scene) => {
      if (!scene.duration) {
        scene.duration = 60; // Default 60 frames
      }
    });
  },
  { immediate: true, deep: true },
);
</script>

<style scoped>
.scene-timeline {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.timeline-header h3 {
  margin: 0;
  color: #333;
}

.timeline-controls {
  display: flex;
  gap: 10px;
}

.btn-preview,
.btn-save {
  padding: 8px 15px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: all 0.3s;
}

.btn-preview {
  background: #4facfe;
  color: white;
}

.btn-preview:hover {
  background: #00f2fe;
}

.btn-save {
  background: #43e97b;
  color: white;
}

.btn-save:hover {
  background: #38f9d7;
}

.timeline-track {
  position: relative;
  height: 120px;
  background: #f8f9fa;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 20px;
}

.time-ruler {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 30px;
  background: #e9ecef;
  border-bottom: 1px solid #dee2e6;
}

.time-mark {
  position: absolute;
  top: 0;
  height: 30px;
  display: flex;
  align-items: center;
  padding-left: 5px;
  font-size: 0.75em;
  color: #666;
  border-left: 1px solid #ccc;
}

.scene-blocks {
  position: absolute;
  top: 40px;
  left: 0;
  right: 0;
  height: 60px;
}

.scene-block {
  position: absolute;
  height: 60px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 500;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.scene-block:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
}

.scene-block.active {
  border: 3px solid #333;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.scene-block.selected {
  opacity: 0.8;
}

.scene-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.scene-label {
  font-size: 0.9em;
}

.scene-duration {
  font-size: 0.75em;
  opacity: 0.9;
}

.transition-marker {
  position: absolute;
  left: -2px;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.9);
  color: #333;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.7em;
  font-weight: bold;
}

.transition-marker.blend {
  background: #ffd93d;
}

.transition-marker.fade {
  background: #6bcf7f;
}

.transition-marker.cut {
  background: #ff6b6b;
}

.playhead {
  position: absolute;
  top: 30px;
  width: 2px;
  height: 90px;
  background: #ff0000;
  box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
  pointer-events: none;
  transition: left 0.04s linear;
}

.playhead::before {
  content: "";
  position: absolute;
  top: -5px;
  left: -4px;
  width: 10px;
  height: 10px;
  background: #ff0000;
  border-radius: 50%;
}

.scene-details {
  background: #f8f9fa;
  border-radius: 10px;
  padding: 15px;
}

.scene-details h4 {
  margin: 0 0 15px 0;
  color: #333;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.detail-item label {
  font-size: 0.85em;
  color: #666;
  font-weight: 500;
}

.detail-item p {
  margin: 0;
  color: #333;
}

.detail-item input {
  width: 80px;
  padding: 5px;
  border: 1px solid #ddd;
  border-radius: 3px;
  margin-right: 5px;
}
</style>
