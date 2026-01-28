import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import App from './App.vue'
import './style.css'

// PrimeVue Components
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Dialog from 'primevue/dialog'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import Toolbar from 'primevue/toolbar'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import Toast from 'primevue/toast'
import ToastService from 'primevue/toastservice'
import ProgressBar from 'primevue/progressbar'
import TabMenu from 'primevue/tabmenu'
import Dropdown from 'primevue/dropdown'
import Badge from 'primevue/badge'
import Divider from 'primevue/divider'
import Image from 'primevue/image'
import Rating from 'primevue/rating'
import Paginator from 'primevue/paginator'
import ProgressSpinner from 'primevue/progressspinner'
import 'primeicons/primeicons.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(PrimeVue, {
  unstyled: false,
  ripple: true
})
app.use(ToastService)

// Register all PrimeVue components
app.component('DataTable', DataTable)
app.component('Column', Column)
app.component('Button', Button)
app.component('InputText', InputText)
app.component('Textarea', Textarea)
app.component('Dialog', Dialog)
app.component('Splitter', Splitter)
app.component('SplitterPanel', SplitterPanel)
app.component('Toolbar', Toolbar)
app.component('Card', Card)
app.component('Tag', Tag)
app.component('Toast', Toast)
app.component('ProgressBar', ProgressBar)
app.component('TabMenu', TabMenu)
app.component('Dropdown', Dropdown)
app.component('Badge', Badge)
app.component('Divider', Divider)
app.component('Image', Image)
app.component('Rating', Rating)
app.component('Paginator', Paginator)
app.component('ProgressSpinner', ProgressSpinner)

app.mount('#app')
