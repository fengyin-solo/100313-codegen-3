<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">矿山安全监测管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向矿山井下环境监测、瓦斯治理、顶板管理、通风系统与人员定位的一体化矿山安全监测管理后台。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "安全费用台账", path: "/safety-fund" }, { label: "矿区台账", path: "/minearea" }, { label: "瓦斯监测", path: "/gas" }, { label: "通风系统", path: "/ventilation" }, { label: "顶板管理", path: "/roof" }, { label: "水害防治", path: "/waterhazard" }, { label: "冲击地压", path: "/rockburst" }, { label: "人员定位", path: "/personnel" }, { label: "粉尘防治", path: "/dust" }, { label: "防灭火", path: "/fireprevent" }, { label: "皮带运输", path: "/belt" }, { label: "提升系统", path: "/hoist" }, { label: "供电系统", path: "/power" }, { label: "应急救援", path: "/rescue" }, { label: "安全培训", path: "/training" }, { label: "入井管理", path: "/shift" }, { label: "爆破管理", path: "/explosive" }, { label: "巷道维修", path: "/roadway" }, { label: "监测分站", path: "/monitorstation" }, { label: "持证管理", path: "/certificate" }, { label: "应急演练", path: "/emergencydrill" }]
</script>
