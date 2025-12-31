/**
 * Notification composable
 */

import { ref } from "vue";

export function useNotification() {
  const notifications = ref([]);

  const addNotification = (message, type = "info", duration = 5000) => {
    const notification = {
      id: Date.now() + Math.random(),
      message,
      type,
      duration,
    };

    notifications.value.push(notification);

    if (duration > 0) {
      setTimeout(() => {
        removeNotification(notification.id);
      }, duration);
    }

    return notification.id;
  };

  const removeNotification = (id) => {
    const index = notifications.value.findIndex((n) => n.id === id);
    if (index > -1) {
      notifications.value.splice(index, 1);
    }
  };

  const showSuccess = (message, duration = 3000) => {
    console.log("✅ Success:", message);
    return addNotification(message, "success", duration);
  };

  const showError = (message, duration = 5000) => {
    console.error("❌ Error:", message);
    return addNotification(message, "error", duration);
  };

  const showWarning = (message, duration = 4000) => {
    console.warn("⚠️ Warning:", message);
    return addNotification(message, "warning", duration);
  };

  const showInfo = (message, duration = 3000) => {
    console.log("ℹ️ Info:", message);
    return addNotification(message, "info", duration);
  };

  const clearAll = () => {
    notifications.value = [];
  };

  return {
    notifications,
    addNotification,
    removeNotification,
    showSuccess,
    showError,
    showWarning,
    showInfo,
    clearAll,
  };
}
