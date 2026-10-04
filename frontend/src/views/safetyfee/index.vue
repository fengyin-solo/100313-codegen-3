<template>
  <section class="page" data-module="safetyfee">
    <header class="page-head">
      <div>
        <h2>安全生产费用台账</h2>
        <p class="page-desc">按月度原煤产量和当时适用比例计提，逐笔登记专项使用；月末使用登记与结余结转同一事务落地。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportCsv">导出月度对账文件</button>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>账期</span>
        <input v-model="month" placeholder="YYYY-MM" />
      </label>
      <button class="btn primary" type="submit">查询台账</button>
    </form>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">期初结余（元）</span>
        <strong class="stat-value">{{ formatAmount(summary['期初结余']) }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">本月计提（元）</span>
        <strong class="stat-value">{{ formatAmount(summary['本月计提']) }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">本月使用（元）</span>
        <strong class="stat-value">{{ formatAmount(summary['本月使用']) }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">期末结余（元）</span>
        <strong class="stat-value">{{ formatAmount(summary['期末结余']) }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">结转状态</span>
        <strong class="stat-value">{{ summary['已结转'] ? '已结转' : '未结转' }}</strong>
      </article>
    </div>

    <div class="safety-panels">
      <form class="safety-form" @submit.prevent="submitRate">
        <h3>登记提取比例</h3>
        <label><span>生效账期</span><input v-model="rateForm.effective_month" placeholder="YYYY-MM" /></label>
        <label><span>提取比例（%）</span><input v-model="rateForm.rate" inputmode="decimal" /></label>
        <button class="btn" type="submit">留档比例</button>
      </form>

      <form class="safety-form" @submit.prevent="submitAccrual">
        <h3>月度计提</h3>
        <label><span>账期</span><input v-model="accrualForm.month" placeholder="YYYY-MM" /></label>
        <label><span>原煤产量（吨）</span><input v-model="accrualForm.output" inputmode="decimal" /></label>
        <button class="btn" type="submit">计算应提金额</button>
      </form>

      <form class="safety-form" @submit.prevent="submitUsage">
        <h3>登记专项使用</h3>
        <label><span>账期</span><input v-model="usageForm.month" placeholder="YYYY-MM" /></label>
        <label><span>财务支出凭证号</span><input v-model="usageForm.voucher" /></label>
        <label><span>专项用途</span><input v-model="usageForm.purpose" /></label>
        <label><span>支出日期</span><input v-model="usageForm.spent_at" placeholder="YYYY-MM-DD" /></label>
        <label><span>使用金额（元）</span><input v-model="usageForm.amount" inputmode="decimal" /></label>
        <button class="btn" type="submit">登记使用</button>
      </form>

      <form class="safety-form" @submit.prevent="submitClose">
        <h3>月末结转</h3>
        <p class="form-hint">如当月尚未计提，可填写原煤产量；下方使用明细随结转同一事务提交。</p>
        <label><span>账期</span><input v-model="closeForm.month" placeholder="YYYY-MM" /></label>
        <label><span>原煤产量（吨，可选）</span><input v-model="closeForm.output" inputmode="decimal" /></label>
        <label><span>凭证号（可选）</span><input v-model="closeForm.voucher" /></label>
        <label><span>专项用途（可选）</span><input v-model="closeForm.purpose" /></label>
        <label><span>使用金额（元，可选）</span><input v-model="closeForm.amount" inputmode="decimal" /></label>
        <button class="btn primary" type="submit">事务结转</button>
      </form>
    </div>

    <section class="rate-list">
      <h3>历史提取比例</h3>
      <table class="data-table">
        <thead><tr><th>生效账期</th><th>提取比例（%）</th><th>登记时间</th></tr></thead>
        <tbody>
          <tr v-for="rate in rates" :key="String(rate.id)">
            <td>{{ rate['生效账期'] }}</td>
            <td>{{ rate['提取比例（%）'] }}</td>
            <td>{{ rate.created_at }}</td>
          </tr>
          <tr v-if="!rates.length"><td colspan="3" class="empty-state">暂无比例版本</td></tr>
        </tbody>
      </table>
    </section>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in ledgerColumns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in ledgerRows" :key="String(row.id)">
          <td v-for="column in ledgerColumns" :key="column">{{ row[column] ?? '—' }}</td>
        </tr>
        <tr v-if="!ledgerRows.length">
          <td :colspan="ledgerColumns.length" class="empty-state">该账期暂无计提或使用明细</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ ledgerRows.length }} 条对账明细，导出文件与本表使用同一份台账快照</span>
      <span v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type FormState = Record<string, string>
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
type ActionPayload = {
  ok: boolean
  message: string
  entry?: Row | null
  received?: Row | null
  existing?: Row | null
}
type ClosePayload = {
  ok: boolean
  message: string
  rejected?: { message: string }[]
}

const ENDPOINT = '/api/safetyfee'
const currentMonth = new Date().toISOString().slice(0, 7)
const month = ref(currentMonth)
const summary = ref<Row>({})
const ledgerRows = ref<Row[]>([])
const rates = ref<Row[]>([])
const message = ref('')
const messageOk = ref(false)

const ledgerColumns = ['明细编号', '类型', '账期', '财务支出凭证号', '支出日期', '专项用途', '原煤产量（吨）', '提取比例（%）', '计提金额（元）', '使用金额（元）', '结余（元）', '登记时间', '结转状态']
const rateForm = ref<FormState>({ effective_month: currentMonth, rate: '' })
const accrualForm = ref<FormState>({ month: currentMonth, output: '' })
const usageForm = ref<FormState>({ month: currentMonth, voucher: '', purpose: '', spent_at: '', amount: '' })
const closeForm = ref<FormState>({ month: currentMonth, output: '', voucher: '', purpose: '', amount: '' })

function formatAmount(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '0.00'
  const amount = Number(value)
  return Number.isFinite(amount) ? amount.toFixed(2) : String(value)
}

function setResult(ok: boolean, text: string) {
  messageOk.value = ok
  message.value = text
}

async function post(path: string, body: unknown): Promise<ActionPayload> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  return (await response.json()) as ActionPayload
}

async function reload() {
  message.value = ''
  const query = new URLSearchParams({ month: month.value })
  try {
    const [ledgerResponse, rateResponse] = await Promise.all([
      request(`${ENDPOINT}/ledger?${query}`),
      request(`${ENDPOINT}/rates`),
    ])
    const ledgerPayload = await ledgerResponse.json()
    const ratePayload = await rateResponse.json()
    summary.value = ledgerPayload.summary ?? {}
    ledgerRows.value = ledgerPayload.items ?? []
    rates.value = ratePayload.items ?? []
  } catch (error) {
    setResult(false, error instanceof Error ? error.message : '安全费用台账读取失败')
  }
}

async function submitRate() {
  const payload = await post(`${ENDPOINT}/rates`, {
    values: {
      生效账期: rateForm.value.effective_month,
      '提取比例（%）': rateForm.value.rate,
    },
  })
  setResult(payload.ok, payload.message)
  if (payload.ok) await reload()
}

async function submitAccrual() {
  const payload = await post(`${ENDPOINT}/accruals`, {
    values: {
      账期: accrualForm.value.month,
      '原煤产量（吨）': accrualForm.value.output,
    },
  })
  setResult(payload.ok, payload.message)
  if (payload.ok) {
    month.value = accrualForm.value.month
    await reload()
  }
}

async function submitUsage() {
  const payload = await post(`${ENDPOINT}/usages`, {
    values: {
      账期: usageForm.value.month,
      财务支出凭证号: usageForm.value.voucher,
      专项用途: usageForm.value.purpose,
      支出日期: usageForm.value.spent_at,
      '使用金额（元）': usageForm.value.amount,
    },
  })
  if (payload.ok) {
    setResult(true, payload.message)
    month.value = usageForm.value.month
    await reload()
  } else {
    setResult(false, payload.message)
  }
}

async function submitClose() {
  const usages: JsonValue[] = []
  if (closeForm.value.voucher || closeForm.value.purpose || closeForm.value.amount) {
    usages.push({
      财务支出凭证号: closeForm.value.voucher,
      专项用途: closeForm.value.purpose,
      '使用金额（元）': closeForm.value.amount,
    })
  }
  const body: Record<string, JsonValue> = { 账期: closeForm.value.month, 使用明细: usages }
  if (closeForm.value.output) body['原煤产量（吨）'] = closeForm.value.output
  const response = await request(`${ENDPOINT}/closures`, { method: 'POST', body: JSON.stringify(body) })
  const payload = (await response.json()) as ClosePayload
  if (payload.ok) {
    month.value = closeForm.value.month
    const rejected = payload.rejected?.length ? `；${payload.rejected.length} 笔重复凭证已退回` : ''
    setResult(true, `${payload.message}${rejected}`)
    await reload()
  } else {
    setResult(false, payload.message)
  }
}

function exportCsv() {
  const query = new URLSearchParams({ month: month.value, format: 'csv' })
  window.open(`${ENDPOINT}/export?${query}`, '_blank')
}

onMounted(reload)
</script>

<style scoped>
.safety-panels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin: 16px 0;
}

.safety-form,
.rate-list {
  border: 1px solid var(--border, #d9e2ec);
  border-radius: 10px;
  padding: 14px;
  background: #fff;
}

.safety-form h3,
.rate-list h3 {
  margin: 0 0 12px;
}

.safety-form label {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
}

.form-hint {
  margin: 0 0 10px;
  color: #64748b;
  font-size: 13px;
}

.success-text {
  color: #15803d;
}
</style>
