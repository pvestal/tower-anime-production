<template>
  <div class="character-manager">
    <!-- Character Grid -->
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <v-card>
            <v-card-title>
              <v-icon class="mr-2">mdi-account-group</v-icon>
              Characters in {{ projectName }}
              <v-spacer />
              <v-btn
                color="primary"
                prepend-icon="mdi-plus"
                @click="showAddDialog = true"
              >
                Add Character
              </v-btn>
            </v-card-title>
          </v-card>
        </v-col>
      </v-row>

      <!-- Character Cards -->
      <v-row>
        <v-col
          v-for="character in characters"
          :key="character.id"
          cols="12"
          md="4"
          lg="3"
        >
          <v-card
            :elevation="selectedCharacter?.id === character.id ? 8 : 2"
            class="character-card"
            @click="selectCharacter(character)"
          >
            <!-- Character Image -->
            <v-img :src="getCharacterImage(character)" height="300" cover>
              <v-chip
                v-if="character.has_lora"
                color="green"
                class="ma-2"
                small
              >
                LoRA
              </v-chip>
              <v-chip
                v-if="character.has_faceid"
                color="blue"
                class="ma-2"
                small
              >
                FaceID
              </v-chip>
            </v-img>

            <v-card-title>
              {{ character.name }}
            </v-card-title>

            <v-card-subtitle>
              {{ character.description }}
            </v-card-subtitle>

            <v-card-text>
              <div class="character-stats">
                <v-row dense>
                  <v-col cols="6">
                    <v-icon small>mdi-image</v-icon>
                    {{ character.image_count || 0 }} Images
                  </v-col>
                  <v-col cols="6">
                    <v-icon small>mdi-video</v-icon>
                    {{ character.video_count || 0 }} Videos
                  </v-col>
                </v-row>
                <v-chip
                  v-if="character.consistency_score"
                  :color="getScoreColor(character.consistency_score)"
                  small
                  class="mt-2"
                >
                  Consistency:
                  {{ (character.consistency_score * 100).toFixed(0) }}%
                </v-chip>
              </div>
            </v-card-text>

            <v-card-actions>
              <v-btn
                text
                color="primary"
                @click.stop="generateImage(character)"
              >
                Generate
              </v-btn>
              <v-btn text @click.stop="testConsistency(character)">
                Test
              </v-btn>
              <v-spacer />
              <v-btn icon @click.stop="showCharacterMenu(character, $event)">
                <v-icon>mdi-dots-vertical</v-icon>
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-col>

        <!-- Add Character Card -->
        <v-col cols="12" md="4" lg="3">
          <v-card
            class="add-character-card"
            height="100%"
            min-height="400"
            @click="showAddDialog = true"
          >
            <v-card-text
              class="d-flex align-center justify-center"
              style="height: 100%"
            >
              <div class="text-center">
                <v-icon size="64" color="grey">mdi-account-plus</v-icon>
                <div class="text-h6 mt-2">Add Character</div>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </v-container>

    <!-- Add Character Dialog -->
    <v-dialog v-model="showAddDialog" max-width="800">
      <v-card>
        <v-card-title> Add Character to {{ projectName }} </v-card-title>

        <v-card-text>
          <v-form ref="addForm">
            <v-text-field
              v-model="newCharacter.name"
              label="Character Name"
              required
              :rules="[(v) => !!v || 'Name is required']"
              hint="Use underscores for spaces"
            />

            <v-textarea
              v-model="newCharacter.description"
              label="Character Description"
              rows="3"
              hint="Physical appearance, personality, role in story"
            />

            <v-textarea
              v-model="newCharacter.base_prompt"
              label="Base Prompt"
              rows="2"
              hint="Default prompt elements for this character"
              placeholder="young woman, black hair, blue eyes, school uniform"
            />

            <!-- Reference Images -->
            <v-file-input
              v-model="newCharacter.reference_images"
              label="Reference Images"
              multiple
              accept="image/*"
              prepend-icon="mdi-image"
              hint="Upload reference images for training"
            />

            <v-row>
              <v-col cols="12" md="6">
                <v-checkbox
                  v-model="newCharacter.train_lora"
                  label="Train LoRA Model"
                  hint="Train a custom LoRA for this character"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-checkbox
                  v-model="newCharacter.use_faceid"
                  label="Use FaceID"
                  hint="Enable face consistency with IP-Adapter"
                />
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn text @click="showAddDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="adding" @click="addCharacter">
            Add Character
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Generation Dialog -->
    <v-dialog v-model="showGenerationDialog" max-width="900">
      <v-card>
        <v-card-title>
          Generate for {{ selectedCharacter?.name }}
        </v-card-title>

        <v-card-text>
          <v-tabs v-model="generationTab">
            <v-tab>Image</v-tab>
            <v-tab>Video</v-tab>
            <v-tab>Batch</v-tab>
          </v-tabs>

          <v-tabs-items v-model="generationTab">
            <!-- Image Generation -->
            <v-tab-item>
              <v-form class="mt-4">
                <v-textarea
                  v-model="generation.prompt"
                  label="Prompt"
                  rows="3"
                  required
                />

                <v-row>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model.number="generation.seed"
                      label="Seed"
                      type="number"
                      hint="Leave empty for random"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-slider
                      v-model="generation.cfg_scale"
                      label="CFG Scale"
                      min="1"
                      max="20"
                      step="0.5"
                      thumb-label
                    />
                  </v-col>
                </v-row>
              </v-form>
            </v-tab-item>

            <!-- Video Generation -->
            <v-tab-item>
              <v-form class="mt-4">
                <v-textarea
                  v-model="generation.prompt"
                  label="Video Prompt"
                  rows="3"
                  required
                />

                <v-row>
                  <v-col cols="12" md="6">
                    <v-slider
                      v-model="generation.duration_frames"
                      label="Duration (frames)"
                      min="16"
                      max="96"
                      step="8"
                      thumb-label
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-slider
                      v-model="generation.motion_strength"
                      label="Motion Strength"
                      min="0"
                      max="1"
                      step="0.1"
                      thumb-label
                    />
                  </v-col>
                </v-row>

                <v-row>
                  <v-col cols="12" md="6">
                    <v-checkbox
                      v-model="generation.use_lora"
                      label="Use Character LoRA"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-checkbox
                      v-model="generation.use_faceid"
                      label="Use FaceID"
                    />
                  </v-col>
                </v-row>
              </v-form>
            </v-tab-item>

            <!-- Batch Generation -->
            <v-tab-item>
              <div class="mt-4">
                <v-textarea
                  v-model="batchPrompts"
                  label="Batch Prompts (one per line)"
                  rows="10"
                  hint="Enter multiple prompts, one per line"
                />
                <v-chip class="mt-2"> {{ batchPromptCount }} prompts </v-chip>
              </div>
            </v-tab-item>
          </v-tabs-items>
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn text @click="showGenerationDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="generating" @click="startGeneration">
            Generate
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Consistency Test Results -->
    <v-dialog v-model="showTestResults" max-width="1200">
      <v-card>
        <v-card-title>
          Consistency Test Results - {{ selectedCharacter?.name }}
        </v-card-title>

        <v-card-text>
          <v-row>
            <v-col
              v-for="(result, idx) in testResults"
              :key="idx"
              cols="12"
              md="3"
            >
              <v-card>
                <v-img :src="result.image_url" height="200" />
                <v-card-subtitle>
                  {{ result.prompt }}
                </v-card-subtitle>
                <v-card-text>
                  Score: {{ (result.score * 100).toFixed(1) }}%
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <div class="mt-4">
            <v-alert :type="getOverallScoreType()" prominent>
              Overall Consistency Score: {{ (overallScore * 100).toFixed(1) }}%
            </v-alert>
          </div>
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn text @click="showTestResults = false">Close</v-btn>
          <v-btn color="primary" @click="saveTestResults"> Save Results </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import axios from "axios";

const props = defineProps({
  projectName: {
    type: String,
    required: true,
  },
});

// State
const characters = ref([]);
const selectedCharacter = ref(null);
const showAddDialog = ref(false);
const showGenerationDialog = ref(false);
const showTestResults = ref(false);
const adding = ref(false);
const generating = ref(false);
const generationTab = ref(0);
const testResults = ref([]);
const batchPrompts = ref("");

// Forms
const newCharacter = ref({
  name: "",
  description: "",
  base_prompt: "",
  reference_images: [],
  train_lora: false,
  use_faceid: true,
});

const generation = ref({
  prompt: "",
  seed: null,
  cfg_scale: 7.5,
  duration_frames: 48,
  motion_strength: 0.7,
  use_lora: true,
  use_faceid: true,
});

// Computed
const batchPromptCount = computed(() => {
  return batchPrompts.value.split("\n").filter((p) => p.trim()).length;
});

const overallScore = computed(() => {
  if (testResults.value.length === 0) return 0;
  const sum = testResults.value.reduce((acc, r) => acc + r.score, 0);
  return sum / testResults.value.length;
});

// Methods
const loadCharacters = async () => {
  try {
    const response = await axios.get(
      `/api/anime/projects/v2/${props.projectName}/characters`,
    );
    characters.value = response.data.characters;
  } catch (error) {
    console.error("Failed to load characters:", error);
  }
};

const addCharacter = async () => {
  adding.value = true;
  try {
    const formData = new FormData();
    Object.keys(newCharacter.value).forEach((key) => {
      if (key === "reference_images") {
        newCharacter.value[key].forEach((file) => {
          formData.append("reference_images", file);
        });
      } else {
        formData.append(key, newCharacter.value[key]);
      }
    });

    const response = await axios.post(
      `/api/anime/projects/v2/${props.projectName}/characters/add`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );

    characters.value.push(response.data);
    showAddDialog.value = false;
    resetNewCharacter();
  } catch (error) {
    console.error("Failed to add character:", error);
  } finally {
    adding.value = false;
  }
};

const selectCharacter = (character) => {
  selectedCharacter.value = character;
};

const generateImage = (character) => {
  selectedCharacter.value = character;
  generationTab.value = 0;
  showGenerationDialog.value = true;
};

const testConsistency = async (character) => {
  selectedCharacter.value = character;
  try {
    const response = await axios.post(
      `/api/anime/projects/v2/${props.projectName}/consistency-test/${character.name}`,
    );
    testResults.value = response.data.results;
    showTestResults.value = true;
  } catch (error) {
    console.error("Failed to run consistency test:", error);
  }
};

const startGeneration = async () => {
  generating.value = true;
  try {
    let endpoint, data;

    if (generationTab.value === 0) {
      // Image generation
      endpoint = `/api/anime/video/generate`;
      data = {
        project_name: props.projectName,
        character_name: selectedCharacter.value.name,
        prompt: generation.value.prompt,
        duration_frames: 1, // Single frame for image
        ...generation.value,
      };
    } else if (generationTab.value === 1) {
      // Video generation
      endpoint = `/api/anime/video/generate`;
      data = {
        project_name: props.projectName,
        character_name: selectedCharacter.value.name,
        ...generation.value,
      };
    } else {
      // Batch generation
      endpoint = `/api/anime/video/batch`;
      const prompts = batchPrompts.value.split("\n").filter((p) => p.trim());
      data = {
        project_name: props.projectName,
        character_name: selectedCharacter.value.name,
        prompts: prompts,
        base_settings: generation.value,
      };
    }

    const response = await axios.post(endpoint, data);
    console.log("Generation started:", response.data);
    showGenerationDialog.value = false;

    // TODO: Show generation progress
  } catch (error) {
    console.error("Failed to start generation:", error);
  } finally {
    generating.value = false;
  }
};

const getCharacterImage = (character) => {
  // TODO: Return actual character thumbnail
  return `/api/anime/characters/${character.name}/thumbnail`;
};

const getScoreColor = (score) => {
  if (score > 0.8) return "green";
  if (score > 0.6) return "orange";
  return "red";
};

const getOverallScoreType = () => {
  const score = overallScore.value;
  if (score > 0.8) return "success";
  if (score > 0.6) return "warning";
  return "error";
};

const resetNewCharacter = () => {
  newCharacter.value = {
    name: "",
    description: "",
    base_prompt: "",
    reference_images: [],
    train_lora: false,
    use_faceid: true,
  };
};

const showCharacterMenu = (character, event) => {
  // TODO: Show context menu for character actions
  console.log("Show menu for:", character);
};

const saveTestResults = async () => {
  // TODO: Save test results to database
  console.log("Saving test results");
  showTestResults.value = false;
};

// Lifecycle
onMounted(() => {
  loadCharacters();
});

// Watch for project changes
watch(
  () => props.projectName,
  () => {
    loadCharacters();
  },
);
</script>

<style scoped>
.character-card {
  cursor: pointer;
  transition: all 0.3s;
}

.character-card:hover {
  transform: translateY(-4px);
}

.add-character-card {
  cursor: pointer;
  border: 2px dashed rgba(0, 0, 0, 0.2);
  transition: all 0.3s;
}

.add-character-card:hover {
  border-color: rgba(0, 0, 0, 0.4);
  background-color: rgba(0, 0, 0, 0.02);
}

.character-stats {
  font-size: 0.9em;
}
</style>
