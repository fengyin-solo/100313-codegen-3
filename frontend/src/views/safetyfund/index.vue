<template>
  <section class="page" data-module="safety-fund">
    <header class="page-head">
      <div>
        <h2>安全生产费用台账</h2>
        <p class="page-desc">
          按月度原煤产量套用当时提取比例登记应提，逐笔登记专项使用；月末同事务结转结余。
          历史账期按当时比例留档，对账导出与台账明细同一口径。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="showRateForm = !showRateForm">调整提取比例</button>
        <button class="btn" type="button" @click="showAccrualForm = !showAccrualForm">登记月度计提</button>
        <button class="btn primary" type="button" @click="showExpenseForm = !showExpenseForm">登记专项使用</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">当前结余（元）</span>
        <strong class="stat-value">{{ balance.balanceYuan ?? '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">最近结转账期</span>
        <strong class="stat-value">{{ balance.latestClosedMonth ?? '尚未结转' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">最新账期</span>
        <strong class="stat-value">{{ balance.asOfMonth ?? '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">当前生效比例</span>
        <strong class="stat-value">{{ currentRate ? `${currentRate.rateYuan} 元/吨` : '—' }}</strong>
      </article>
    </div>

    <p v-if="message" class="form-note" :class="{ 'form-error': !messageOk }">{{ message }}</p>

    <!-- 调整提取比例 -->
    <form v-if="showRateForm" class="inline-form" @submit.prevent="submitRate">
      <h3>调整提取比例（只对之后的账期生效，历史账期数字不变）</h3>
      <div class="form-grid">
        <label><span>生效账期</span><input v-model="rateForm.effectiveMonth" placeholder="YYYY-MM，如 2026-10" /></label>
        <label><span>提取比例（元/吨）</span><input v-model="rateForm.rateYuan" placeholder="如 35" /></label>
        <label class="span-2"><span>说明</span><input v-model="rateForm.note" placeholder="调整原因（选填）" /></label>
      </div>
      <div class="form-actions">
        <button class="btn primary" type="submit">提交比例</button>
        <button class="btn ghost" type="button" @click="showRateForm = false">取消</button>
      </div>
    </form>

    <!-- 登记月度计提 -->
    <form v-if="showAccrualForm" class="inline-form" @submit.prevent="submitAccrual">
      <h3>登记月度计提（应提 = 原煤产量 × 当时比例，比例随账快照）</h3>
      <div class="form-grid">
        <label><span>账期</span><input v-model="accrualForm.month" placeholder="YYYY-MM" /></label>
        <label><span>原煤产量（吨）</span><input v-model="accrualForm.outputTonnes" placeholder="如 120000" /></label>
      </div>
      <div class="form-actions">
        <button class="btn primary" type="submit">计提入账</button>
        <button class="btn ghost" type="button" @click="showAccrualForm = false">取消</button>
      </div>
    </form>

    <!-- 登记专项使用 -->
    <form v-if="showExpenseForm" class="inline-form" @submit.prevent="submitExpense">
      <h3>逐笔登记专项使用（凭证号唯一，重复登记原样退回、不计结余）</h3>
      <div class="form-grid">
        <label><span>入账账期</span><input v-model="expenseForm.month" placeholder="YYYY-MM" /></label>
        <label><span>财务凭证号</span><input v-model="expenseForm.voucherNo" placeholder="如 PZ-202609-004" /></label>
        <label><span>支出日期</span><input v-model="expenseForm.usedAt" placeholder="YYYY-MM-DD" /></label>
        <label><span>专项类别</span><input v-model="expenseForm.category" placeholder="如 瓦斯综合治理" /></label>
        <label><span>金额（元）</span><input v-model="expenseForm.amountYuan" placeholder="如 265000.00" /></label>
        <label class="span-2"><span>支出摘要</span><input v-model="expenseForm.summary" placeholder="支出内容说明" /></label>
      </div>
      <div class="form-actions">
        <button class="btn primary" type="submit">登记使用</button>
        <button class="btn ghost" type="button" @click="showExpenseForm = false">取消</button>
      </div>
    </form>

    <div class="ledger-layout">
      <!-- 左：月度台账 -->
      <div class="ledger-main">
        <div class="filter-bar">
          <label class="filter-item">
            <span>选择账期</span>
            <select v-model="selectedMonth" @change="onSelectMonth">
              <option value="">请选择账期</option>
              <option v-for="m in months" :key="m.month" :value="m.month">
                {{ m.month }}{{ m.status === 'closed' ? '（已结转）' : '（未结转）' }}
              </option>
            </select>
          </label>
          <button class="btn" type="button" :disabled="!selectedMonth" @click="exportRecon('csv')">导出对账 CSV</button>
          <button class="btn" type="button" :disabled="!selectedMonth" @click="exportRecon('json')">查看对账 JSON</button>
          <button
            class="btn primary"
            type="button"
            :disabled="!selectedMonth || currentDetail?.status === 'closed'"
            @click="closeCurrentMonth"
          >
            月末结转
          </button>
        </div>

        <table v-if="currentDetail" class="data-table">
          <tbody>
            <tr><th>账期</th><td>{{ currentDetail.month }}</td><th>状态</th><td>{{ currentDetail.status === 'closed' ? '已结转封档' : '未结转' }}</td></tr>
            <tr>
              <th>原煤产量（吨）</th>
              <td>{{ currentDetail.accrual ? currentDetail.accrual.outputTonnes : '未计提' }}</td>
              <th>当时比例</th>
              <td>{{ currentDetail.accrual ? `${currentDetail.accrual.rateYuan} 元/吨（留档）` : '—' }}</td>
            </tr>
            <tr><th>期初结余（元）</th><td>{{ currentDetail.openingYuan }}</td><th>本月应提（元）</th><td>{{ currentDetail.accruedYuan }}</td></tr>
            <tr><th>本月使用（元）</th><td>{{ currentDetail.usedYuan }}</td><th>期末结余（元）</th><td><strong>{{ currentDetail.balanceYuan }}</strong></td></tr>
          </tbody>
        </table>

        <h3 class="block-title">使用明细（逐笔）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>凭证号</th><th>支出日期</th><th>专项类别</th><th>支出摘要</th><th>金额（元）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in currentDetail?.items ?? []" :key="String(item.id)">
              <td>{{ item.voucherNo }}</td>
              <td>{{ item.usedAt }}</td>
              <td>{{ item.category }}</td>
              <td>{{ item.summary }}</td>
              <td>{{ item.amountYuan }}</td>
            </tr>
            <tr v-if="currentDetail && currentDetail.items.length === 0">
              <td colspan="5" class="empty-state">该账期暂无使用明细</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 右：比例留档 -->
      <aside class="ledger-side">
        <h3 class="block-title">提取比例留档</h3>
        <table class="data-table">
          <thead><tr><th>生效账期</th><th>比例（元/吨）</th></tr></thead>
          <tbody>
            <tr v-for="rate in rates" :key="String(rate.id)">
              <td>{{ rate.effectiveMonth }}</td>
              <td>{{ rate.rateYuan }}</td>
            </tr>
            <tr v-if="rates.length === 0"><td colspan="2" class="empty-state">暂无比例记录</td></tr>
          </tbody>
        </table>
        <p class="side-note">
          调整比例只新增生效记录；已登记账期的应提金额按当时快照保留，不重算、不覆盖。
        </p>
      </aside>
    </div>

    <footer class="page-foot">
      <span>结余、台账明细、对账导出共用同一套落库口径</span>
      <span v-if="currentDetail" class="hash-note">明细指纹 {{ currentDetail.detailHash.slice(0, 12) }}…</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type MonthDetail = {
  month: string
  status: 'open' | 'closed'
  openingYuan: string
  accruedYuan: string
  usedYuan: string
  balanceYuan: string
  detailHash: string
  accrual: { outputTonnes: number; rateYuan: string } | null
  items: { id: number; voucherNo: string; usedAt: string; category: string; summary: string; amountYuan: string }[]
}

type Rate = { id: number; effectiveMonth: string; rateYuan: string }
type Balance = { balanceYuan: string; latestClosedMonth: string | null; asOfMonth: string | null }

const API = '/api/safety-fund'

const months = ref<MonthDetail[]>([])
const selectedMonth = ref('')
const currentDetail = ref<MonthDetail | null>(null)
const rates = ref<Rate[]>([])
const balance = ref<Balance>({ balanceYuan: '', latestClosedMonth: null, asOfMonth: null })
const currentRate = ref<Rate | null>(null)

const message = ref('')
const messageOk = ref(true)
const showRateForm = ref(false)
const showAccrualForm = ref(false)
const showExpenseForm = ref(false)

const rateForm = ref({ effectiveMonth: '', rateYuan: '', note: '' })
const accrualForm = ref({ month: '', outputTonnes: '' })
const expenseForm = ref({ month: '', voucherNo: '', category: '', summary: '', amountYuan: '', usedAt: '' })

function flash(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

async function postJson(path: string, body: unknown): Promise<{ ok: boolean; [key: string]: unknown }> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : '操作未生效')
  }
  return data
}

async function reloadAll() {
  const [monthsResp, ratesResp, balanceResp] = await Promise.all([
    request(`${API}/months`), request(`${API}/rates`), request(`${API}/balance`),
  ])
  if (monthsResp.ok) months.value = (await monthsResp.json()).items
  if (ratesResp.ok) rates.value = (await ratesResp.json()).items
  if (balanceResp.ok) {
    balance.value = await balanceResp.json()
    const resp = await request(`${API}/rates`)
    const all: Rate[] = (await resp.json()).items
    const effective = all
      .filter((r) => !balance.value.asOfMonth || r.effectiveMonth <= balance.value.asOfMonth)
      .sort((a, b) => a.effectiveMonth.localeCompare(b.effectiveMonth))
      .at(-1)
    currentRate.value = effective ?? null
  }
  if (selectedMonth.value) await loadDetail(selectedMonth.value)
}

async function loadDetail(month: string) {
  const resp = await request(`${API}/months/${month}`)
  if (resp.ok) currentDetail.value = await resp.json()
}

function onSelectMonth() {
  if (selectedMonth.value) void loadDetail(selectedMonth.value)
}

async function submitRate() {
  try {
    await postJson(`${API}/rates`, rateForm.value)
    showRateForm.value = false
    rateForm.value = { effectiveMonth: '', rateYuan: '', note: '' }
    flash('提取比例已登记，自生效账期起适用，历史账期保持不变')
    await reloadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '比例登记失败', false)
  }
}

async function submitAccrual() {
  try {
    await postJson(`${API}/accruals`, accrualForm.value)
    showAccrualForm.value = false
    accrualForm.value = { month: '', outputTonnes: '' }
    flash('当月应提金额已按当时比例登记并快照')
    await reloadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '计提失败', false)
  }
}

async function submitExpense() {
  try {
    await postJson(`${API}/expenditures`, expenseForm.value)
    showExpenseForm.value = false
    expenseForm.value = { month: '', voucherNo: '', category: '', summary: '', amountYuan: '', usedAt: '' }
    flash('专项使用已逐笔登记')
    await reloadAll()
  } catch (error) {
    // 重复凭证被退回等业务拒绝都在这里原样呈现
    flash(error instanceof Error ? error.message : '使用登记失败', false)
  }
}

async function closeCurrentMonth() {
  if (!selectedMonth.value) return
  if (!window.confirm(`确认结转账期 ${selectedMonth.value}？结转后封档，使用与结余同一事务落地。`)) return
  try {
    await postJson(`${API}/close`, { month: selectedMonth.value, expenditures: [] })
    flash(`账期 ${selectedMonth.value} 已结转封档`)
    await reloadAll()
  } catch (error) {
    flash(error instanceof Error ? error.message : '月末结转失败', false)
  }
}

async function exportRecon(format: 'csv' | 'json') {
  if (!selectedMonth.value) return
  const url = `${API}/reconciliation/${selectedMonth.value}?format=${format}`
  if (format === 'csv') {
    window.open(url, '_blank')
    return
  }
  const resp = await request(url)
  const data = await resp.json()
  if (resp.ok) flash(`对账 JSON 与台账明细一致：${data.items.length} 笔，结余 ${data.balanceYuan} 元`)
}

onMounted(async () => {
  await reloadAll()
  if (months.value.length) {
    selectedMonth.value = months.value[months.value.length - 1].month
    await loadDetail(selectedMonth.value)
  }
})
</script>
