import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from '@/views/Dashboard.vue'
const Minearea = () => import('@/views/minearea/index.vue')
const Gas = () => import('@/views/gas/index.vue')
const Ventilation = () => import('@/views/ventilation/index.vue')
const Roof = () => import('@/views/roof/index.vue')
const Waterhazard = () => import('@/views/waterhazard/index.vue')
const Rockburst = () => import('@/views/rockburst/index.vue')
const Personnel = () => import('@/views/personnel/index.vue')
const Dust = () => import('@/views/dust/index.vue')
const Fireprevent = () => import('@/views/fireprevent/index.vue')
const Belt = () => import('@/views/belt/index.vue')
const Hoist = () => import('@/views/hoist/index.vue')
const Power = () => import('@/views/power/index.vue')
const Rescue = () => import('@/views/rescue/index.vue')
const Training = () => import('@/views/training/index.vue')
const Shift = () => import('@/views/shift/index.vue')
const Explosive = () => import('@/views/explosive/index.vue')
const Roadway = () => import('@/views/roadway/index.vue')
const Monitorstation = () => import('@/views/monitorstation/index.vue')
const Certificate = () => import('@/views/certificate/index.vue')
const Emergencydrill = () => import('@/views/emergencydrill/index.vue')
const Safetyfee = () => import('@/views/safetyfee/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/minearea', name: 'minearea', component: Minearea },
    { path: '/gas', name: 'gas', component: Gas },
    { path: '/ventilation', name: 'ventilation', component: Ventilation },
    { path: '/roof', name: 'roof', component: Roof },
    { path: '/waterhazard', name: 'waterhazard', component: Waterhazard },
    { path: '/rockburst', name: 'rockburst', component: Rockburst },
    { path: '/personnel', name: 'personnel', component: Personnel },
    { path: '/dust', name: 'dust', component: Dust },
    { path: '/fireprevent', name: 'fireprevent', component: Fireprevent },
    { path: '/belt', name: 'belt', component: Belt },
    { path: '/hoist', name: 'hoist', component: Hoist },
    { path: '/power', name: 'power', component: Power },
    { path: '/rescue', name: 'rescue', component: Rescue },
    { path: '/training', name: 'training', component: Training },
    { path: '/shift', name: 'shift', component: Shift },
    { path: '/explosive', name: 'explosive', component: Explosive },
    { path: '/roadway', name: 'roadway', component: Roadway },
    { path: '/monitorstation', name: 'monitorstation', component: Monitorstation },
    { path: '/certificate', name: 'certificate', component: Certificate },
    { path: '/emergencydrill', name: 'emergencydrill', component: Emergencydrill },
    { path: '/safetyfee', name: 'safetyfee', component: Safetyfee },
  ],
})

export default router
