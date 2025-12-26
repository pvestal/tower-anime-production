import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import prettier from '@vue/eslint-config-prettier'

export default [
  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  prettier,
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        // Browser globals
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        WebSocket: 'readonly',
        setTimeout: 'readonly',
        setInterval: 'readonly',
        clearTimeout: 'readonly',
        clearInterval: 'readonly',
        alert: 'readonly',
        confirm: 'readonly',
        Promise: 'readonly',
        URL: 'readonly',
        FormData: 'readonly',
        Event: 'readonly',
        EventTarget: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        location: 'readonly',
        history: 'readonly',
        navigator: 'readonly',
        HTMLElement: 'readonly',
        Element: 'readonly',
        Node: 'readonly',
        // Animation frame APIs
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        // Additional browser APIs
        Blob: 'readonly',
        prompt: 'readonly',
        FileReader: 'readonly',
        Notification: 'readonly',
        URLSearchParams: 'readonly',
        onUnmounted: 'readonly',
        // Node.js globals (if needed)
        process: 'readonly',
        Buffer: 'readonly',
        global: 'readonly',
        __dirname: 'readonly',
        __filename: 'readonly',
        module: 'readonly',
        require: 'readonly',
        exports: 'readonly'
      }
    },
    rules: {
      // Vue.js specific rules
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'off', // Allow unused vars in development
      'vue/require-default-prop': 'off', // Allow props without defaults
      'vue/no-v-html': 'off', // Allow v-html for trusted content
      'vue/no-template-shadow': 'off', // Allow template variable shadowing
      'vue/no-required-prop-with-default': 'off', // Allow flexible prop patterns

      // General JavaScript rules
      'no-unused-vars': 'off', // Allow unused vars for development
      'no-undef': 'warn'
    }
  }
]