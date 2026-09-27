<template>
  <section class="page" data-module="observation">
    <header class="page-head">
      <div>
        <h2>观测记录管理</h2>
        <p class="page-desc">维护观测记录，围绕记录编号、所属站点、观测要素、观测时刻做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记观测记录</button>
        <button class="btn" type="button" @click="exportRows">导出观测记录清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>记录状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-voided': row.status === '已作废' }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <template v-if="row.status !== '已作废'">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="voided-tag">不再流转</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的观测记录，可调整筛选条件或先登记观测记录</td>
        </tr>
      </tbody>
    </table>

    <div class="pager">
      <button class="btn" type="button" :disabled="page <= 1" @click="gotoPage(page - 1)">上一页</button>
      <span class="pager-info">第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn" type="button" :disabled="page >= totalPages" @click="gotoPage(page + 1)">下一页</button>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测记录<template v-if="voidedCount">，其中已作废 {{ voidedCount }} 条不计入统计</template></span>
      <span v-if="notice" class="notice-text">{{ notice }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <h3>观测记录详情</h3>
        <dl class="detail-list">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </template>
        </dl>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记观测记录</h3>
        <label v-for="field in createFields" :key="field" class="form-item">
          <span>{{ field }}<em v-if="requiredFields.includes(field)" class="required-mark">*</em></span>
          <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit">提交登记</button>
          <button class="btn ghost" type="button" @click="creating = false">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: number }

const ENDPOINT = '/api/observation'
const columns = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
const actions = ["提交质控", "标记疑误", "作废记录"]
const statuses = ["待质控", "质控通过", "疑误标记", "已作废"]
const filterFields = columns.slice(0, 3)
const requiredFields = filterFields
const createFields = columns.slice(0, 6)
const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const voidedCount = ref(0)
const stats = ref<StatCard[]>([
  { label: '有效观测记录（不含已作废）', value: 0 },
  { label: '待质控记录', value: 0 },
  { label: '疑误标记数', value: 0 },
  { label: '已作废（不计入统计）', value: 0 },
])
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const errorMessage = ref('')
const notice = ref('')
const detail = ref<Row | null>(null)
const creating = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function queryText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

// 地址栏 query 是筛选状态的唯一事实来源：刷新、前进后退、翻页后返回都能还原同一份条件
watch(
  () => route.query,
  (query) => {
    const next: Record<string, string> = {}
    for (const field of filterFields) {
      next[field] = queryText(query[field])
    }
    filters.value = next
    statusFilter.value = queryText(query.status)
    const rawPage = Number.parseInt(queryText(query.page), 10)
    page.value = Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1
    void loadAll()
  },
  { immediate: true },
)

function syncUrl() {
  const query: Record<string, string> = {}
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) query[field] = value
  }
  if (statusFilter.value) query.status = statusFilter.value
  if (page.value > 1) query.page = String(page.value)
  void router.replace({ query })
}

function filterParams(): URLSearchParams {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) params.set(field, value)
  }
  if (statusFilter.value) params.set('status', statusFilter.value)
  return params
}

async function loadAll() {
  errorMessage.value = ''
  const params = filterParams()
  params.set('page', String(page.value))
  params.set('size', String(PAGE_SIZE))
  const query = params.toString()
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats?${query}`),
    ])
    if (!listResponse.ok) throw new Error('观测记录列表读取失败')
    if (!statsResponse.ok) throw new Error('观测记录统计读取失败')
    const payload = await listResponse.json()
    const summary = await statsResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    voidedCount.value = summary.voided ?? 0
    const byStatus = (summary.by_status ?? {}) as Record<string, number>
    stats.value = [
      { label: '有效观测记录（不含已作废）', value: summary.valid ?? 0 },
      { label: '待质控记录', value: byStatus['待质控'] ?? 0 },
      { label: '疑误标记数', value: byStatus['疑误标记'] ?? 0 },
      { label: '已作废（不计入统计）', value: summary.voided ?? 0 },
    ]
    if (page.value > totalPages.value) {
      // 过滤后总数变少、当前页码超出范围时回到最后一页，避免停在空页
      page.value = totalPages.value
      syncUrl()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录数据读取失败'
  }
}

function applyFilters() {
  page.value = 1
  syncUrl()
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  page.value = 1
  syncUrl()
}

function gotoPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) return
  page.value = target
  syncUrl()
}

function exportRows() {
  // 清单与列表走同一份过滤条件，条数自然对得上
  window.open(`${ENDPOINT}/export?${filterParams().toString()}`, '_blank')
}

async function readResult(response: Response): Promise<Record<string, unknown>> {
  return (await response.json().catch(() => ({}))) as Record<string, unknown>
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  notice.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readResult(response)
    if (!response.ok || result.ok !== true) {
      throw new Error(String(result.message ?? result.detail ?? '观测记录动作未生效，请稍后重试'))
    }
    notice.value = String(result.message ?? `观测记录已${action}`)
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录操作失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('观测记录详情读取失败')
    detail.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  creating.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const result = await readResult(response)
    if (!response.ok || result.ok !== true) {
      // 缺字段、记录编号重复等原因由后端统一给出，原样提示
      throw new Error(String(result.message ?? result.detail ?? '观测记录登记失败'))
    }
    creating.value = false
    notice.value = String(result.message ?? '观测记录已登记')
    await loadAll()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '观测记录登记失败'
  }
}
</script>
