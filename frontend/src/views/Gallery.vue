<template>
  <div class="gallery-view">
    <div class="gallery-header">
      <h1>Content Gallery</h1>
      <div class="view-options">
        <button
          v-for="view in viewModes"
          :key="view.value"
          :class="['view-btn', { active: viewMode === view.value }]"
          @click="viewMode = view.value"
        >
          <i :class="view.icon"></i>
          <span>{{ view.label }}</span>
        </button>
      </div>
    </div>

    <div class="gallery-filters">
      <!-- Character Filter -->
      <div class="filter-group">
        <label>Character</label>
        <select v-model="filters.character" @change="loadContent">
          <option value="">All Characters</option>
          <option
            v-for="char in store.characters"
            :key="char.id"
            :value="char.id"
          >
            {{ char.character_name }}
          </option>
        </select>
      </div>

      <!-- Content Type Filter -->
      <div class="filter-group">
        <label>Type</label>
        <select v-model="filters.type" @change="loadContent">
          <option value="">All Types</option>
          <option value="single_image">Single Images</option>
          <option value="turnaround">Turnarounds</option>
          <option value="pose_sheet">Pose Sheets</option>
          <option value="expression_sheet">Expressions</option>
          <option value="animation">Animations</option>
        </select>
      </div>

      <!-- Content Rating Filter -->
      <div class="filter-group">
        <label>Rating</label>
        <div class="rating-filters">
          <label class="checkbox-label">
            <input
              v-model="filters.sfw"
              type="checkbox"
              @change="loadContent"
            />
            <span class="badge sfw">SFW</span>
          </label>
          <label class="checkbox-label">
            <input
              v-model="filters.artistic"
              type="checkbox"
              @change="loadContent"
            />
            <span class="badge artistic">Artistic</span>
          </label>
          <label class="checkbox-label nsfw">
            <input
              v-model="filters.nsfw"
              type="checkbox"
              @change="loadContent"
            />
            <span class="badge nsfw">NSFW</span>
          </label>
        </div>
      </div>

      <!-- Date Range Filter -->
      <div class="filter-group">
        <label>Date Range</label>
        <select v-model="filters.dateRange" @change="loadContent">
          <option value="">All Time</option>
          <option value="today">Today</option>
          <option value="week">This Week</option>
          <option value="month">This Month</option>
        </select>
      </div>

      <!-- Search -->
      <div class="filter-group search-group">
        <label>Search</label>
        <div class="search-input">
          <input
            v-model="searchQuery"
            placeholder="Search prompts..."
            @input="debounceSearch"
          />
          <button class="btn-search" @click="semanticSearch">
            <i class="pi pi-search"></i>
          </button>
        </div>
      </div>

      <!-- Actions -->
      <div class="filter-actions">
        <button class="btn-reset" @click="resetFilters">
          <i class="pi pi-refresh"></i> Reset
        </button>
        <button
          class="btn-download"
          :disabled="selectedItems.length === 0"
          @click="downloadSelected"
        >
          <i class="pi pi-download"></i> Download ({{ selectedItems.length }})
        </button>
      </div>
    </div>

    <!-- Grid View -->
    <div v-if="viewMode === 'grid'" class="gallery-grid">
      <div
        v-for="item in filteredContent"
        :key="item.id"
        :class="['gallery-item', { selected: selectedItems.includes(item.id) }]"
        @click="toggleSelection(item)"
      >
        <div v-if="item.content_type" class="item-badge">
          <span :class="['badge', item.content_type]">{{
            item.content_type.toUpperCase()
          }}</span>
        </div>
        <div class="item-media">
          <img
            v-if="item.type !== 'animation'"
            :src="item.url"
            :alt="item.character_name"
          />
          <video v-else :src="item.url" controls muted loop></video>
        </div>
        <div class="item-info">
          <div class="character-name">{{ item.character_name }}</div>
          <div class="item-type">{{ item.generation_type || item.type }}</div>
          <div class="item-meta">
            <span class="date">{{ formatDate(item.created_at) }}</span>
            <span class="size">{{ item.width }}x{{ item.height }}</span>
          </div>
        </div>
        <div class="item-actions">
          <button class="btn-action" @click.stop="viewFullsize(item)">
            <i class="pi pi-eye"></i>
          </button>
          <button class="btn-action" @click.stop="editItem(item)">
            <i class="pi pi-pencil"></i>
          </button>
          <button class="btn-action delete" @click.stop="deleteItem(item)">
            <i class="pi pi-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- List View -->
    <div v-if="viewMode === 'list'" class="gallery-list">
      <table>
        <thead>
          <tr>
            <th><input type="checkbox" @change="toggleAllSelection" /></th>
            <th>Preview</th>
            <th>Character</th>
            <th>Type</th>
            <th>Rating</th>
            <th>Prompt</th>
            <th>Date</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filteredContent" :key="item.id">
            <td>
              <input
                type="checkbox"
                :checked="selectedItems.includes(item.id)"
                @change="toggleSelection(item)"
              />
            </td>
            <td class="preview-cell">
              <img
                v-if="item.type !== 'animation'"
                :src="item.url"
                class="list-preview"
              />
              <video v-else :src="item.url" class="list-preview" muted></video>
            </td>
            <td>{{ item.character_name }}</td>
            <td>
              <span class="type-badge">{{
                item.generation_type || item.type
              }}</span>
            </td>
            <td>
              <span :class="['badge', item.content_type]">{{
                item.content_type
              }}</span>
            </td>
            <td class="prompt-cell">{{ truncatePrompt(item.prompt) }}</td>
            <td>{{ formatDate(item.created_at) }}</td>
            <td>
              <div class="list-actions">
                <button class="btn-icon" @click="viewFullsize(item)">
                  <i class="pi pi-eye"></i>
                </button>
                <button class="btn-icon" @click="editItem(item)">
                  <i class="pi pi-pencil"></i>
                </button>
                <button class="btn-icon delete" @click="deleteItem(item)">
                  <i class="pi pi-trash"></i>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Mosaic View (for pose sheets and turnarounds) -->
    <div v-if="viewMode === 'mosaic'" class="gallery-mosaic">
      <div
        v-for="group in groupedContent"
        :key="group.character"
        class="mosaic-group"
      >
        <h3>{{ group.character }}</h3>
        <div class="mosaic-grid">
          <div
            v-for="item in group.items"
            :key="item.id"
            class="mosaic-item"
            @click="viewFullsize(item)"
          >
            <img :src="item.url" :alt="item.character_name" />
            <div class="mosaic-label">{{ item.generation_type }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox Modal -->
    <div v-if="lightboxItem" class="lightbox" @click="closeLightbox">
      <div class="lightbox-content" @click.stop>
        <button class="lightbox-close" @click="closeLightbox">
          <i class="pi pi-times"></i>
        </button>
        <div class="lightbox-media">
          <img
            v-if="lightboxItem.type !== 'animation'"
            :src="lightboxItem.url"
          />
          <video v-else :src="lightboxItem.url" controls autoplay loop></video>
        </div>
        <div class="lightbox-info">
          <h3>{{ lightboxItem.character_name }}</h3>
          <p class="lightbox-prompt">{{ lightboxItem.prompt }}</p>
          <div class="lightbox-meta">
            <span>{{ lightboxItem.generation_type }}</span>
            <span>{{ lightboxItem.width }}x{{ lightboxItem.height }}</span>
            <span>{{ formatDate(lightboxItem.created_at) }}</span>
          </div>
          <div class="lightbox-actions">
            <button class="btn-primary" @click="regenerate(lightboxItem)">
              <i class="pi pi-refresh"></i> Regenerate
            </button>
            <button class="btn-secondary" @click="downloadItem(lightboxItem)">
              <i class="pi pi-download"></i> Download
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { useCharacterStore } from "@/stores/characterStore";
import { api } from "@/services/api";

const store = useCharacterStore();

const viewMode = ref("grid");
const content = ref([]);
const selectedItems = ref([]);
const lightboxItem = ref(null);
const searchQuery = ref("");
const searchTimeout = ref(null);

const viewModes = [
  { value: "grid", label: "Grid", icon: "pi pi-th-large" },
  { value: "list", label: "List", icon: "pi pi-list" },
  { value: "mosaic", label: "Mosaic", icon: "pi pi-table" },
];

const filters = reactive({
  character: "",
  type: "",
  sfw: true,
  artistic: true,
  nsfw: false,
  dateRange: "",
});

const filteredContent = computed(() => {
  let filtered = content.value;

  if (filters.character) {
    filtered = filtered.filter(
      (item) => item.character_id === parseInt(filters.character),
    );
  }

  if (filters.type) {
    filtered = filtered.filter(
      (item) =>
        item.generation_type === filters.type || item.type === filters.type,
    );
  }

  // Content type filtering
  const allowedTypes = [];
  if (filters.sfw) allowedTypes.push("sfw");
  if (filters.artistic) allowedTypes.push("artistic");
  if (filters.nsfw) allowedTypes.push("nsfw");

  if (allowedTypes.length < 3) {
    filtered = filtered.filter((item) =>
      allowedTypes.includes(item.content_type || "sfw"),
    );
  }

  // Date range filtering
  if (filters.dateRange) {
    const now = new Date();
    const cutoff = new Date();

    switch (filters.dateRange) {
      case "today":
        cutoff.setHours(0, 0, 0, 0);
        break;
      case "week":
        cutoff.setDate(cutoff.getDate() - 7);
        break;
      case "month":
        cutoff.setMonth(cutoff.getMonth() - 1);
        break;
    }

    filtered = filtered.filter((item) => new Date(item.created_at) >= cutoff);
  }

  // Search filtering
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(
      (item) =>
        item.prompt?.toLowerCase().includes(query) ||
        item.character_name?.toLowerCase().includes(query),
    );
  }

  return filtered;
});

const groupedContent = computed(() => {
  const groups = {};

  filteredContent.value.forEach((item) => {
    const char = item.character_name || "Unknown";
    if (!groups[char]) {
      groups[char] = { character: char, items: [] };
    }
    groups[char].items.push(item);
  });

  return Object.values(groups);
});

const loadContent = async () => {
  try {
    // Load generations from multiple endpoints
    const promises = [];

    if (filters.character) {
      promises.push(api.character.getGenerations(filters.character));
    } else {
      // Load recent generations
      promises.push(api.jobs.list());
    }

    const responses = await Promise.all(promises);

    // Flatten and format content
    content.value = responses.flatMap((r) => {
      const data = r.data;
      if (Array.isArray(data)) {
        return data.map(formatContentItem);
      } else if (data.generations) {
        return data.generations.map(formatContentItem);
      } else if (data.results) {
        return data.results.map(formatContentItem);
      }
      return [];
    });
  } catch (error) {
    console.error("Failed to load content:", error);
  }
};

const formatContentItem = (item) => {
  // Standardize the content item format
  return {
    id: item.id || item.generation_id || item.job_id,
    character_id: item.character_id,
    character_name: item.character_name || item.character || "Unknown",
    generation_type: item.generation_type || item.type || "single_image",
    content_type: item.content_type || "sfw",
    prompt: item.prompt || "",
    negative_prompt: item.negative_prompt || "",
    url:
      item.output_path ||
      item.url ||
      item.outputs?.[0] ||
      "/api/anime/placeholder.jpg",
    width: item.width || 512,
    height: item.height || 768,
    created_at: item.created_at || item.timestamp || new Date().toISOString(),
    type: item.type || (item.animation_id ? "animation" : "image"),
  };
};

const semanticSearch = async () => {
  if (!searchQuery.value) return;

  try {
    const response = await api.vector.search(searchQuery.value, 50);
    content.value = response.data.results.map(formatContentItem);
  } catch (error) {
    console.error("Semantic search failed:", error);
  }
};

const debounceSearch = () => {
  clearTimeout(searchTimeout.value);
  searchTimeout.value = setTimeout(() => {
    if (searchQuery.value) {
      semanticSearch();
    } else {
      loadContent();
    }
  }, 500);
};

const toggleSelection = (item) => {
  const idx = selectedItems.value.indexOf(item.id);
  if (idx >= 0) {
    selectedItems.value.splice(idx, 1);
  } else {
    selectedItems.value.push(item.id);
  }
};

const toggleAllSelection = () => {
  if (selectedItems.value.length === filteredContent.value.length) {
    selectedItems.value = [];
  } else {
    selectedItems.value = filteredContent.value.map((item) => item.id);
  }
};

const viewFullsize = (item) => {
  lightboxItem.value = item;
};

const closeLightbox = () => {
  lightboxItem.value = null;
};

const editItem = (item) => {
  // Navigate to edit view or open edit modal
  console.log("Edit item:", item);
};

const deleteItem = async (item) => {
  if (confirm(`Delete this ${item.generation_type}?`)) {
    try {
      // Call appropriate delete endpoint
      if (item.animation_id) {
        await api.animation.deleteSequence(item.animation_id);
      } else {
        // Generic delete
        await api.jobs.cancel(item.id);
      }

      // Remove from local content
      content.value = content.value.filter((c) => c.id !== item.id);
    } catch (error) {
      console.error("Failed to delete item:", error);
      alert("Failed to delete item");
    }
  }
};

const regenerate = async (item) => {
  try {
    const response = await api.character.generate({
      character_name: item.character_name,
      prompt: item.prompt,
      negative_prompt: item.negative_prompt,
      content_type: item.content_type,
      generation_type: item.generation_type,
      width: item.width,
      height: item.height,
    });

    alert("Regeneration started! Job ID: " + response.data.generation_id);
    closeLightbox();
  } catch (error) {
    console.error("Regeneration failed:", error);
    alert("Failed to regenerate");
  }
};

const downloadItem = (item) => {
  const link = document.createElement("a");
  link.href = item.url;
  link.download = `${item.character_name}_${item.generation_type}_${item.id}.png`;
  link.click();
};

const downloadSelected = () => {
  selectedItems.value.forEach((id) => {
    const item = content.value.find((c) => c.id === id);
    if (item) downloadItem(item);
  });
};

const resetFilters = () => {
  filters.character = "";
  filters.type = "";
  filters.sfw = true;
  filters.artistic = true;
  filters.nsfw = false;
  filters.dateRange = "";
  searchQuery.value = "";
  selectedItems.value = [];
  loadContent();
};

const truncatePrompt = (prompt, maxLength = 50) => {
  if (!prompt) return "";
  return prompt.length > maxLength
    ? prompt.substring(0, maxLength) + "..."
    : prompt;
};

const formatDate = (dateString) => {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return "Unknown";
    }
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "Unknown";
  }
};

onMounted(() => {
  store.loadCharacters();
  loadContent();
});
</script>

<style scoped>
.gallery-view {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 2rem;
  border: 1px solid #2a2a2a;
  min-height: 600px;
}

.gallery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.view-options {
  display: flex;
  gap: 0.5rem;
}

.view-btn {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  color: #999;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.view-btn:hover {
  background: #333;
  color: #e0e0e0;
}

.view-btn.active {
  background: #4a90e2;
  border-color: #4a90e2;
  color: white;
}

h1 {
  color: #e0e0e0;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 1.5rem;
  margin-bottom: 1.5rem;
}

.gallery-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 2rem;
  background: #252525;
  padding: 1rem;
  border-radius: 8px;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.filter-group label {
  color: #999;
  font-size: 0.85rem;
  font-weight: 500;
  text-transform: uppercase;
}

.filter-group select,
.filter-group input[type="text"] {
  padding: 0.5rem;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 0.9rem;
  min-width: 150px;
}

.filter-group select:focus,
.filter-group input:focus {
  outline: none;
  border-color: #4a90e2;
}

.rating-filters {
  display: flex;
  gap: 0.75rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
}

.checkbox-label.nsfw {
  opacity: 0.7;
}

.checkbox-label:hover {
  opacity: 1;
}

.badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.badge.sfw {
  background: #28a745;
  color: white;
}

.badge.artistic {
  background: #6f42c1;
  color: white;
}

.badge.nsfw {
  background: #dc3545;
  color: white;
}

.search-group {
  flex: 1;
}

.search-input {
  display: flex;
  gap: 0.5rem;
}

.search-input input {
  flex: 1;
}

.btn-search {
  background: #4a90e2;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  color: white;
  cursor: pointer;
}

.btn-search:hover {
  background: #357abd;
}

.filter-actions {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
}

.btn-reset,
.btn-download {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-reset {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  color: #999;
}

.btn-reset:hover {
  background: #333;
  color: #e0e0e0;
}

.btn-download {
  background: #28a745;
  border: none;
  color: white;
}

.btn-download:hover:not(:disabled) {
  background: #218838;
}

.btn-download:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1.5rem;
}

.gallery-item {
  cursor: pointer;
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  background: #2a2a2a;
  border: 2px solid transparent;
  transition: all 0.2s;
}

.gallery-item.selected {
  border-color: #4a90e2;
}

.gallery-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
}

.item-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 10;
}

.item-media {
  width: 100%;
  aspect-ratio: 2/3;
  overflow: hidden;
  background: #1a1a1a;
}

.item-media img,
.item-media video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.item-info {
  padding: 0.75rem;
}

.character-name {
  font-weight: 500;
  color: #e0e0e0;
  margin-bottom: 0.25rem;
}

.item-type {
  font-size: 0.85rem;
  color: #999;
  margin-bottom: 0.5rem;
}

.item-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #666;
}

.item-actions {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem;
  background: rgba(0, 0, 0, 0.5);
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  transform: translateY(100%);
  transition: transform 0.2s;
}

.gallery-item:hover .item-actions {
  transform: translateY(0);
}

.btn-action {
  flex: 1;
  background: #333;
  border: none;
  border-radius: 4px;
  padding: 0.5rem;
  color: #999;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-action:hover {
  background: #4a90e2;
  color: white;
}

.btn-action.delete:hover {
  background: #dc3545;
}

.gallery-list {
  background: #2a2a2a;
  border-radius: 8px;
  overflow: hidden;
}

.gallery-list table {
  width: 100%;
  border-collapse: collapse;
}

.gallery-list th,
.gallery-list td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid #3a3a3a;
}

.gallery-list th {
  background: #252525;
  color: #999;
  font-weight: 500;
  font-size: 0.85rem;
  text-transform: uppercase;
}

.gallery-list td {
  color: #e0e0e0;
  font-size: 0.9rem;
}

.gallery-list tr:hover td {
  background: #333;
}

.preview-cell {
  width: 60px;
}

.list-preview {
  width: 50px;
  height: 75px;
  object-fit: cover;
  border-radius: 4px;
}

.prompt-cell {
  max-width: 300px;
  color: #999;
  font-size: 0.85rem;
}

.type-badge {
  background: #333;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  color: #999;
}

.list-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-icon {
  background: transparent;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  color: #999;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-icon:hover {
  background: #333;
  color: #4a90e2;
  border-color: #4a90e2;
}

.btn-icon.delete:hover {
  color: #dc3545;
  border-color: #dc3545;
}

.gallery-mosaic {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.mosaic-group h3 {
  color: #e0e0e0;
  margin-bottom: 1rem;
}

.mosaic-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.5rem;
}

.mosaic-item {
  position: relative;
  cursor: pointer;
  border-radius: 4px;
  overflow: hidden;
}

.mosaic-item img {
  width: 100%;
  aspect-ratio: 2/3;
  object-fit: cover;
}

.mosaic-item:hover img {
  transform: scale(1.1);
}

.mosaic-label {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 0.25rem;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  font-size: 0.7rem;
  text-align: center;
}

.lightbox {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
}

.lightbox-content {
  background: #1a1a1a;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  max-width: 1400px;
  max-height: 90vh;
  width: 100%;
}

.lightbox-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: rgba(0, 0, 0, 0.5);
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.lightbox-close:hover {
  background: rgba(0, 0, 0, 0.8);
}

.lightbox-media {
  flex: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  position: relative;
}

.lightbox-media img,
.lightbox-media video {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.lightbox-info {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
  background: #1a1a1a;
}

.lightbox-info h3 {
  color: #e0e0e0;
  margin-bottom: 1rem;
}

.lightbox-prompt {
  color: #999;
  font-size: 0.9rem;
  line-height: 1.4;
  margin-bottom: 1rem;
}

.lightbox-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #2a2a2a;
}

.lightbox-meta span {
  background: #2a2a2a;
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.85rem;
  color: #999;
}

.lightbox-actions {
  display: flex;
  gap: 1rem;
}

.btn-primary,
.btn-secondary {
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  justify-content: center;
}

.btn-primary {
  background: #4a90e2;
  border: none;
  color: white;
}

.btn-primary:hover {
  background: #357abd;
}

.btn-secondary {
  background: transparent;
  border: 1px solid #3a3a3a;
  color: #999;
}

.btn-secondary:hover {
  background: #2a2a2a;
  color: #e0e0e0;
}
</style>
