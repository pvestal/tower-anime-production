<template>
  <div class="schema-form-renderer">
    <!-- Form Header -->
    <div class="form-header">
      <div class="form-title">
        <h3>{{ schema.title || "Configuration" }}</h3>
        <p v-if="schema.description" class="form-description">
          {{ schema.description }}
        </p>
      </div>
      <button class="close-btn" @click="$emit('cancel')">
        <i class="icon-x"></i>
      </button>
    </div>

    <!-- Form Content -->
    <form class="form-content" @submit.prevent="handleSubmit">
      <div class="form-fields">
        <div
          v-for="(property, key) in schema.properties"
          :key="key"
          class="form-field"
          :class="{
            'field-required': schema.required?.includes(key),
            'field-error': errors[key],
            'field-conditional':
              property.condition && !isFieldVisible(key, property),
          }"
        >
          <!-- Field Label -->
          <label :for="`field-${key}`" class="field-label">
            {{ property.title || formatFieldName(key) }}
            <span
              v-if="schema.required?.includes(key)"
              class="required-indicator"
              >*</span
            >
            <span
              v-if="property.description"
              class="field-help"
              :title="property.description"
            >
              <i class="icon-help-circle"></i>
            </span>
          </label>

          <!-- String Input -->
          <input
            v-if="
              property.type === 'string' && !property.enum && !property.format
            "
            :id="`field-${key}`"
            v-model="localFormData[key]"
            :placeholder="property.placeholder || property.example"
            :maxlength="property.maxLength"
            :minlength="property.minLength"
            class="field-input"
            type="text"
          />

          <!-- Number Input -->
          <input
            v-else-if="
              property.type === 'number' || property.type === 'integer'
            "
            :id="`field-${key}`"
            v-model.number="localFormData[key]"
            :placeholder="property.placeholder || property.example"
            :min="property.minimum"
            :max="property.maximum"
            :step="property.type === 'integer' ? 1 : 0.1"
            class="field-input"
            type="number"
          />

          <!-- Range Slider -->
          <div
            v-else-if="property.ui?.widget === 'range'"
            class="range-container"
          >
            <input
              :id="`field-${key}`"
              v-model.number="localFormData[key]"
              :min="property.minimum || 0"
              :max="property.maximum || 100"
              :step="property.ui?.step || 1"
              class="range-slider"
              type="range"
            />
            <div class="range-labels">
              <span class="range-min">{{ property.minimum || 0 }}</span>
              <span class="range-value">{{ localFormData[key] }}</span>
              <span class="range-max">{{ property.maximum || 100 }}</span>
            </div>
          </div>

          <!-- Boolean Checkbox -->
          <label
            v-else-if="property.type === 'boolean'"
            :for="`field-${key}`"
            class="checkbox-container"
          >
            <input
              :id="`field-${key}`"
              v-model="localFormData[key]"
              class="checkbox-input"
              type="checkbox"
            />
            <span class="checkbox-checkmark"></span>
            <span class="checkbox-label">{{
              property.title || formatFieldName(key)
            }}</span>
          </label>

          <!-- Select Dropdown -->
          <select
            v-else-if="property.enum"
            :id="`field-${key}`"
            v-model="localFormData[key]"
            class="field-select"
          >
            <option value="" disabled>
              Select {{ property.title || formatFieldName(key) }}
            </option>
            <option
              v-for="option in property.enum"
              :key="option"
              :value="option"
            >
              {{
                property.enumNames?.[property.enum.indexOf(option)] || option
              }}
            </option>
          </select>

          <!-- Multi-Select -->
          <div
            v-else-if="property.type === 'array' && property.items?.enum"
            class="multi-select"
          >
            <div class="multi-select-options">
              <label
                v-for="option in property.items.enum"
                :key="option"
                class="multi-option"
              >
                <input
                  :value="option"
                  :checked="(localFormData[key] || []).includes(option)"
                  type="checkbox"
                  @change="toggleArrayValue(key, option)"
                />
                <span class="multi-option-text">
                  {{
                    property.items.enumNames?.[
                      property.items.enum.indexOf(option)
                    ] || option
                  }}
                </span>
              </label>
            </div>
          </div>

          <!-- Textarea -->
          <textarea
            v-else-if="
              property.format === 'textarea' ||
              property.ui?.widget === 'textarea'
            "
            :id="`field-${key}`"
            v-model="localFormData[key]"
            :placeholder="property.placeholder || property.example"
            :rows="property.ui?.rows || 4"
            :maxlength="property.maxLength"
            class="field-textarea"
          ></textarea>

          <!-- Color Picker -->
          <div v-else-if="property.format === 'color'" class="color-container">
            <input
              :id="`field-${key}`"
              v-model="localFormData[key]"
              class="color-input"
              type="color"
            />
            <input
              v-model="localFormData[key]"
              :placeholder="property.placeholder || '#000000'"
              class="color-text"
              type="text"
            />
          </div>

          <!-- File Upload -->
          <div v-else-if="property.format === 'file'" class="file-container">
            <input
              :id="`field-${key}`"
              :accept="property.accept"
              :multiple="property.type === 'array'"
              class="file-input"
              type="file"
              @change="handleFileUpload(key, $event)"
            />
            <label :for="`field-${key}`" class="file-label">
              <i class="icon-upload"></i>
              <span>{{ getFileButtonText(key, property) }}</span>
            </label>
            <div v-if="getFileDisplay(key)" class="file-preview">
              {{ getFileDisplay(key) }}
            </div>
          </div>

          <!-- Array of Strings -->
          <div
            v-else-if="
              property.type === 'array' && property.items?.type === 'string'
            "
            class="array-container"
          >
            <div class="array-items">
              <div
                v-for="(item, index) in localFormData[key] || []"
                :key="index"
                class="array-item"
              >
                <input
                  v-model="localFormData[key][index]"
                  :placeholder="`Item ${index + 1}`"
                  class="array-input"
                  type="text"
                />
                <button
                  type="button"
                  class="array-remove"
                  @click="removeArrayItem(key, index)"
                >
                  <i class="icon-x"></i>
                </button>
              </div>
            </div>
            <button type="button" class="array-add" @click="addArrayItem(key)">
              <i class="icon-plus"></i>
              Add {{ property.items.title || "Item" }}
            </button>
          </div>

          <!-- Object Fields (Nested) -->
          <div
            v-else-if="property.type === 'object' && property.properties"
            class="object-container"
          >
            <div class="object-fields">
              <div
                v-for="(nestedProperty, nestedKey) in property.properties"
                :key="nestedKey"
                class="nested-field"
              >
                <!-- Recursively render nested fields -->
                <SchemaFormRenderer
                  :schema="{
                    properties: { [nestedKey]: nestedProperty },
                    required: property.required || [],
                  }"
                  :form-data="localFormData[key] = localFormData[key] || {}"
                  :nested="true"
                  @update:form-data="updateNestedData(key, $event)"
                />
              </div>
            </div>
          </div>

          <!-- Custom Widget -->
          <component
            :is="customWidgets[property.ui.widget]"
            v-else-if="property.ui?.widget && customWidgets[property.ui.widget]"
            :id="`field-${key}`"
            :value="localFormData[key]"
            :property="property"
            @update:value="localFormData[key] = $event"
          />

          <!-- Fallback Input -->
          <input
            v-else
            :id="`field-${key}`"
            v-model="localFormData[key]"
            :placeholder="property.placeholder || property.example"
            class="field-input"
            type="text"
          />

          <!-- Field Error -->
          <div v-if="errors[key]" class="field-error-message">
            {{ errors[key] }}
          </div>

          <!-- Field Hint -->
          <div v-if="property.description" class="field-hint">
            {{ property.description }}
          </div>
        </div>
      </div>

      <!-- Form Actions -->
      <div v-if="!nested" class="form-actions">
        <button type="button" class="btn-secondary" @click="$emit('cancel')">
          Cancel
        </button>
        <button
          type="submit"
          class="btn-primary"
          :disabled="!isValid || submitting"
        >
          <div v-if="submitting" class="loading-spinner"></div>
          <span v-else>Submit</span>
        </button>
      </div>
    </form>

    <!-- Schema Debug (Development only) -->
    <details v-if="debugMode" class="schema-debug">
      <summary>Debug Schema & Data</summary>
      <pre>{{ JSON.stringify({ schema, formData, errors }, null, 2) }}</pre>
    </details>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";

// Props
const props = defineProps({
  schema: {
    type: Object,
    required: true,
  },
  formData: {
    type: Object,
    default: () => ({}),
  },
  nested: {
    type: Boolean,
    default: false,
  },
  debugMode: {
    type: Boolean,
    default: false,
  },
});

// Emits
const emit = defineEmits(["submit", "cancel", "update:form-data"]);

// State
const errors = ref({});
const submitting = ref(false);
// Create a local copy of formData to avoid prop mutation
const localFormData = ref(JSON.parse(JSON.stringify(props.formData)));

// Watch for changes and emit updates to parent
watch(
  localFormData,
  (newValue) => {
    emit("update:form-data", newValue);
  },
  { deep: true },
);

// Custom widgets registry
const customWidgets = ref({
  // Add custom widgets here
  // 'custom-slider': CustomSliderWidget,
  // 'model-selector': ModelSelectorWidget
});

// Computed
const isValid = computed(() => {
  return Object.keys(errors.value).length === 0 && validateRequiredFields();
});

// Methods
const validateRequiredFields = () => {
  if (!props.schema.required) return true;

  return props.schema.required.every((field) => {
    const value = localFormData.value[field];
    return value !== undefined && value !== null && value !== "";
  });
};

const validateField = (key, value) => {
  const property = props.schema.properties[key];
  if (!property) return null;

  // Required validation
  if (props.schema.required?.includes(key)) {
    if (value === undefined || value === null || value === "") {
      return "This field is required";
    }
  }

  // Type validation
  switch (property.type) {
    case "string":
      if (value && typeof value !== "string") {
        return "Must be a string";
      }
      if (property.minLength && value.length < property.minLength) {
        return `Must be at least ${property.minLength} characters`;
      }
      if (property.maxLength && value.length > property.maxLength) {
        return `Must be no more than ${property.maxLength} characters`;
      }
      if (property.pattern && !new RegExp(property.pattern).test(value)) {
        return "Invalid format";
      }
      break;

    case "number":
    case "integer":
      if (value !== undefined && value !== null && value !== "") {
        const numValue = Number(value);
        if (isNaN(numValue)) {
          return "Must be a number";
        }
        if (property.type === "integer" && !Number.isInteger(numValue)) {
          return "Must be an integer";
        }
        if (property.minimum !== undefined && numValue < property.minimum) {
          return `Must be at least ${property.minimum}`;
        }
        if (property.maximum !== undefined && numValue > property.maximum) {
          return `Must be no more than ${property.maximum}`;
        }
      }
      break;

    case "array":
      if (value && !Array.isArray(value)) {
        return "Must be an array";
      }
      if (property.minItems && value.length < property.minItems) {
        return `Must have at least ${property.minItems} items`;
      }
      if (property.maxItems && value.length > property.maxItems) {
        return `Must have no more than ${property.maxItems} items`;
      }
      break;
  }

  return null;
};

const validateAllFields = () => {
  const newErrors = {};

  Object.keys(props.schema.properties).forEach((key) => {
    const error = validateField(key, localFormData.value[key]);
    if (error) {
      newErrors[key] = error;
    }
  });

  errors.value = newErrors;
  return Object.keys(newErrors).length === 0;
};

const handleSubmit = () => {
  if (!validateAllFields()) {
    return;
  }

  submitting.value = true;

  try {
    emit("submit", localFormData.value);
  } catch (error) {
    console.error("Form submission error:", error);
  } finally {
    submitting.value = false;
  }
};

const formatFieldName = (key) => {
  return key
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (str) => str.toUpperCase())
    .replace(/_/g, " ");
};

const isFieldVisible = (key, property) => {
  if (!property.condition) return true;

  const { field, value, operator = "equals" } = property.condition;
  const fieldValue = localFormData.value[field];

  switch (operator) {
    case "equals":
      return fieldValue === value;
    case "not_equals":
      return fieldValue !== value;
    case "contains":
      return Array.isArray(fieldValue) && fieldValue.includes(value);
    case "greater_than":
      return Number(fieldValue) > Number(value);
    case "less_than":
      return Number(fieldValue) < Number(value);
    default:
      return true;
  }
};

const toggleArrayValue = (key, value) => {
  if (!localFormData.value[key]) {
    localFormData.value[key] = [];
  }

  const array = localFormData.value[key];
  const index = array.indexOf(value);

  if (index > -1) {
    array.splice(index, 1);
  } else {
    array.push(value);
  }

  emit("update:form-data", localFormData.value);
};

const addArrayItem = (key) => {
  if (!localFormData.value[key]) {
    localFormData.value[key] = [];
  }

  localFormData.value[key].push("");
  emit("update:form-data", localFormData.value);
};

const removeArrayItem = (key, index) => {
  if (localFormData.value[key] && localFormData.value[key].length > index) {
    localFormData.value[key].splice(index, 1);
    emit("update:form-data", localFormData.value);
  }
};

const handleFileUpload = (key, event) => {
  const files = Array.from(event.target.files);
  const property = props.schema.properties[key];

  if (property.type === "array") {
    localFormData.value[key] = files.map((file) => file.name);
  } else {
    localFormData.value[key] = files[0]?.name || "";
  }

  emit("update:form-data", localFormData.value);
};

const getFileButtonText = (key, property) => {
  const hasValue = localFormData.value[key];
  const isArray = property.type === "array";

  if (hasValue) {
    if (isArray) {
      const count = Array.isArray(localFormData.value[key])
        ? localFormData.value[key].length
        : 0;
      return count > 0 ? `${count} file(s) selected` : "Choose files";
    } else {
      return "Change file";
    }
  }

  return isArray ? "Choose files" : "Choose file";
};

const getFileDisplay = (key) => {
  const value = localFormData.value[key];
  if (!value) return null;

  if (Array.isArray(value)) {
    return value.join(", ");
  }

  return typeof value === "object" ? value.name : value;
};

const updateNestedData = (key, nestedData) => {
  localFormData.value[key] = { ...localFormData.value[key], ...nestedData };
  emit("update:form-data", localFormData.value);
};

// Watchers
watch(
  () => localFormData.value,
  (newData) => {
    // Validate on data change
    Object.keys(newData).forEach((key) => {
      const error = validateField(key, newData[key]);
      if (error) {
        errors.value[key] = error;
      } else {
        delete errors.value[key];
      }
    });

    emit("update:form-data", newData);
  },
  { deep: true },
);

// Lifecycle
onMounted(() => {
  // Initialize form data with defaults
  Object.keys(props.schema.properties).forEach((key) => {
    const property = props.schema.properties[key];

    if (
      localFormData.value[key] === undefined &&
      property.default !== undefined
    ) {
      localFormData.value[key] = property.default;
    }

    // Initialize empty arrays
    if (property.type === "array" && !localFormData.value[key]) {
      localFormData.value[key] = [];
    }

    // Initialize empty objects
    if (property.type === "object" && !localFormData.value[key]) {
      localFormData.value[key] = {};
    }
  });

  emit("update:form-data", localFormData.value);
});
</script>

<style scoped>
.schema-form-renderer {
  background: rgba(45, 45, 45, 0.95);
  border-radius: 12px;
  border: 1px solid #4a4a4a;
  overflow: hidden;
  backdrop-filter: blur(10px);
}

/* Form Header */
.form-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #4a4a4a;
  background: rgba(0, 0, 0, 0.2);
}

.form-title h3 {
  margin: 0 0 0.5rem 0;
  color: #7b68ee;
  font-size: 1.2rem;
}

.form-description {
  margin: 0;
  color: #cccccc;
  font-size: 0.9rem;
  line-height: 1.4;
}

.close-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

/* Form Content */
.form-content {
  padding: 1.5rem;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

/* Form Field */
.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-field.field-conditional {
  display: none;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: #ffffff;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}

.required-indicator {
  color: #f44336;
  font-weight: bold;
}

.field-help {
  color: #999;
  cursor: help;
  transition: color 0.2s;
}

.field-help:hover {
  color: #7b68ee;
}

/* Input Styles */
.field-input,
.field-textarea,
.field-select,
.array-input,
.color-text {
  width: 100%;
  padding: 0.75rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #4a4a4a;
  border-radius: 6px;
  color: #ffffff;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.field-input:focus,
.field-textarea:focus,
.field-select:focus,
.array-input:focus,
.color-text:focus {
  outline: none;
  border-color: #7b68ee;
  box-shadow: 0 0 0 2px rgba(123, 104, 238, 0.2);
}

.field-input::placeholder,
.field-textarea::placeholder,
.array-input::placeholder {
  color: #999;
}

.field-error .field-input,
.field-error .field-textarea,
.field-error .field-select {
  border-color: #f44336;
}

/* Range Slider */
.range-container {
  padding: 0.5rem 0;
}

.range-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.3);
  outline: none;
  appearance: none;
}

.range-slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.range-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.range-labels {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: #999;
}

.range-value {
  background: rgba(123, 104, 238, 0.2);
  color: #7b68ee;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-weight: bold;
}

/* Checkbox */
.checkbox-container {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  padding: 0.5rem 0;
}

.checkbox-input {
  display: none;
}

.checkbox-checkmark {
  width: 20px;
  height: 20px;
  border: 2px solid #4a4a4a;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.3);
  position: relative;
  transition: all 0.2s;
}

.checkbox-input:checked + .checkbox-checkmark {
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  border-color: #7b68ee;
}

.checkbox-input:checked + .checkbox-checkmark::after {
  content: "✓";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: white;
  font-weight: bold;
  font-size: 14px;
}

.checkbox-label {
  flex: 1;
  color: #ffffff;
  font-weight: 500;
}

/* Multi-Select */
.multi-select-options {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  border: 1px solid #4a4a4a;
}

.multi-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 4px;
  transition: background 0.2s;
}

.multi-option:hover {
  background: rgba(123, 104, 238, 0.1);
}

.multi-option input[type="checkbox"] {
  margin: 0;
}

.multi-option-text {
  color: #ffffff;
  font-size: 0.9rem;
}

/* Color Input */
.color-container {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.color-input {
  width: 50px;
  height: 40px;
  border: 1px solid #4a4a4a;
  border-radius: 6px;
  cursor: pointer;
  background: none;
}

.color-text {
  flex: 1;
}

/* File Upload */
.file-container {
  position: relative;
}

.file-input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.file-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: rgba(123, 104, 238, 0.1);
  border: 2px dashed rgba(123, 104, 238, 0.3);
  border-radius: 6px;
  color: #7b68ee;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.file-label:hover {
  background: rgba(123, 104, 238, 0.2);
  border-color: rgba(123, 104, 238, 0.5);
}

.file-preview {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
  font-size: 0.8rem;
  color: #cccccc;
  word-break: break-all;
}

/* Array Container */
.array-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.array-items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.array-item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.array-input {
  flex: 1;
  margin: 0;
}

.array-remove {
  background: rgba(244, 67, 54, 0.2);
  border: 1px solid rgba(244, 67, 54, 0.3);
  color: #f44336;
  padding: 0.5rem;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.array-remove:hover {
  background: rgba(244, 67, 54, 0.3);
}

.array-add {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: rgba(123, 104, 238, 0.1);
  border: 1px solid rgba(123, 104, 238, 0.3);
  border-radius: 6px;
  color: #7b68ee;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.9rem;
}

.array-add:hover {
  background: rgba(123, 104, 238, 0.2);
}

/* Object Container */
.object-container {
  padding: 1rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  border: 1px solid #4a4a4a;
}

.object-fields {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.nested-field {
  margin-left: 1rem;
  padding-left: 1rem;
  border-left: 2px solid #4a4a4a;
}

/* Field Messages */
.field-error-message {
  color: #f44336;
  font-size: 0.8rem;
  margin-top: 0.25rem;
}

.field-hint {
  color: #999;
  font-size: 0.8rem;
  line-height: 1.3;
  margin-top: 0.25rem;
}

/* Form Actions */
.form-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
  padding-top: 1.5rem;
  border-top: 1px solid #4a4a4a;
}

.btn-primary,
.btn-secondary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 100px;
}

.btn-primary {
  background: linear-gradient(135deg, #7b68ee 0%, #9c88ff 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(123, 104, 238, 0.3);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.btn-secondary {
  background: rgba(0, 0, 0, 0.3);
  color: #cccccc;
  border: 1px solid #4a4a4a;
}

.btn-secondary:hover {
  background: rgba(0, 0, 0, 0.5);
  border-color: #666;
}

/* Loading Spinner */
.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top: 2px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Schema Debug */
.schema-debug {
  margin-top: 1.5rem;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 6px;
  border: 1px solid #4a4a4a;
}

.schema-debug summary {
  color: #7b68ee;
  cursor: pointer;
  font-weight: 500;
  margin-bottom: 1rem;
}

.schema-debug pre {
  color: #cccccc;
  font-size: 0.8rem;
  line-height: 1.4;
  overflow-x: auto;
  margin: 0;
}

/* Animations */
@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

/* Responsive Design */
@media (max-width: 768px) {
  .form-header {
    padding: 1rem;
    flex-direction: column;
    align-items: stretch;
    gap: 1rem;
  }

  .form-content {
    padding: 1rem;
  }

  .form-actions {
    flex-direction: column-reverse;
    gap: 0.5rem;
  }

  .btn-primary,
  .btn-secondary {
    width: 100%;
  }

  .array-item {
    flex-direction: column;
    align-items: stretch;
  }

  .color-container {
    flex-direction: column;
  }

  .range-labels {
    font-size: 0.7rem;
  }
}

@media (max-width: 480px) {
  .multi-select-options {
    max-height: 150px;
    overflow-y: auto;
  }

  .object-container {
    padding: 0.5rem;
  }

  .nested-field {
    margin-left: 0.5rem;
    padding-left: 0.5rem;
  }
}

/* High contrast mode support */
@media (prefers-contrast: high) {
  .field-input,
  .field-textarea,
  .field-select {
    border-width: 2px;
  }

  .checkbox-checkmark {
    border-width: 3px;
  }

  .file-label {
    border-width: 3px;
  }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
