<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <p v-if="safetyFund" class="sf-balance-note">
      安全费用当前结余 <strong>{{ safetyFund.balanceYuan }}</strong> 元
      （截至 {{ safetyFund.asOfMonth ?? '—' }}，最近结转 {{ safetyFund.latestClosedMonth ?? '尚未结转' }}），
      数值与台账页、月度对账文件同源。
    </p>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number | string }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  safetyFund?: { balanceYuan: string; latestClosedMonth: string | null; asOfMonth: string | null }
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const safetyFund = ref<NonNullable<Overview['safetyFund']> | null>(null)

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    safetyFund.value = payload.safetyFund ?? null
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "矿区台账", "created": 0, "pending": 0, "abnormal": 0}, {"name": "瓦斯监测", "created": 0, "pending": 0, "abnormal": 0}, {"name": "通风系统", "created": 0, "pending": 0, "abnormal": 0}, {"name": "顶板管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "水害防治", "created": 0, "pending": 0, "abnormal": 0}, {"name": "冲击地压", "created": 0, "pending": 0, "abnormal": 0}, {"name": "人员定位", "created": 0, "pending": 0, "abnormal": 0}, {"name": "粉尘防治", "created": 0, "pending": 0, "abnormal": 0}, {"name": "防灭火", "created": 0, "pending": 0, "abnormal": 0}, {"name": "皮带运输", "created": 0, "pending": 0, "abnormal": 0}, {"name": "提升系统", "created": 0, "pending": 0, "abnormal": 0}, {"name": "供电系统", "created": 0, "pending": 0, "abnormal": 0}, {"name": "应急救援", "created": 0, "pending": 0, "abnormal": 0}, {"name": "安全培训", "created": 0, "pending": 0, "abnormal": 0}, {"name": "入井管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "爆破管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "巷道维修", "created": 0, "pending": 0, "abnormal": 0}, {"name": "监测分站", "created": 0, "pending": 0, "abnormal": 0}, {"name": "持证管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "应急演练", "created": 0, "pending": 0, "abnormal": 0}]
  }
})
</script>
