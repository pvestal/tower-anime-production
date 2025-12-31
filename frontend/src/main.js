import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { createPinia } from "pinia";
import App from "./App.vue";

// Import views
import Dashboard from "./views/Dashboard.vue";
import Characters from "./views/Characters.vue";
import CharacterStudio from "./views/CharacterStudio.vue";
import DirectorStudio from "./views/DirectorStudio.vue";
import SceneDirector from "./views/SceneDirector.vue";
import Generation from "./views/Generation.vue";
import Gallery from "./views/Gallery.vue";
import Projects from "./views/Projects.vue";
import Chat from "./views/Chat.vue";

const routes = [
  { path: "/", name: "dashboard", component: Dashboard },
  { path: "/projects", name: "projects", component: Projects },
  { path: "/characters", name: "characters", component: Characters },
  { path: "/studio", name: "studio", component: CharacterStudio },
  { path: "/director", name: "director", component: DirectorStudio },
  { path: "/scene", name: "scene-director", component: SceneDirector },
  { path: "/generate", name: "generate", component: Generation },
  { path: "/gallery/:character?", name: "gallery", component: Gallery },
  { path: "/chat", name: "chat", component: Chat },
];

const router = createRouter({
  history: createWebHistory("/anime/"),
  routes,
});

const pinia = createPinia();

const app = createApp(App);
app.use(router);
app.use(pinia);
app.mount("#app");
