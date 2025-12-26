import { defineStore } from "pinia";
import { ref } from "vue";

export const useNotificationStore = defineStore("notification", () => {
  const notifications = ref([]);

  const addNotification = (notification) => {
    const id = Date.now();
    const newNotification = {
      id,
      type: "info",
      message: "",
      duration: 5000,
      ...notification,
    };

    notifications.value.push(newNotification);

    // Auto remove after duration
    if (newNotification.duration > 0) {
      setTimeout(() => {
        removeNotification(id);
      }, newNotification.duration);
    }

    return id;
  };

  const removeNotification = (id) => {
    const index = notifications.value.findIndex((n) => n.id === id);
    if (index > -1) {
      notifications.value.splice(index, 1);
    }
  };

  const clearAll = () => {
    notifications.value = [];
  };

  // Convenience methods
  const success = (message, duration = 5000) => {
    return addNotification({ type: "success", message, duration });
  };

  const error = (message, duration = 8000) => {
    return addNotification({ type: "error", message, duration });
  };

  const warning = (message, duration = 6000) => {
    return addNotification({ type: "warning", message, duration });
  };

  const info = (message, duration = 5000) => {
    return addNotification({ type: "info", message, duration });
  };

  return {
    notifications,
    addNotification,
    removeNotification,
    clearAll,
    success,
    error,
    warning,
    info,
  };
});
