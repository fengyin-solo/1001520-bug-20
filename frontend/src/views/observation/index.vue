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
      <article v-for="item in statItems" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="filters.记录编号" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>所属站点</span>
        <input v-model="filters.所属站点" placeholder="按所属站点检索" />
      </label>
      <label class="filter-item">
        <span>观测要素</span>
        <input v-model="filters.观测要素" placeholder="按观测要素检索" />
      </label>
      <label class="filter-item">
        <span>记录状态</span>
        <select v-model="filters.记录状态">
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
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :class="{ 'row-void': row.记录状态 === '已作废' }"
          @click="openDetail(row)"
        >
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions" @click.stop>
            <template v-if="row.记录状态 !== '已作废'">
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
            <span v-else class="void-tag">已作废</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的观测记录，可调整筛选条件或先登记观测记录</td>
        </tr>
      </tbody>
    </table>

    <div class="pager">
      <button class="btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
      <span>第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn" type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测记录（已作废不计入有效统计）</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <h3>观测记录详情</h3>
        <dl class="detail-grid">
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

    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记观测记录</h3>
        <label v-for="field in createFields" :key="field" class="form-row">
          <span>{{ field }}<em v-if="requiredFields.includes(field)" class="required-mark">*</em></span>
          <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit">提交登记</button>
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/observation'
const columns = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
const actions = ["提交质控", "标记疑误", "作废记录"]
const statuses = ["待质控", "质控通过", "疑误标记", "已作废"]
const requiredFields = ["记录编号", "所属站点", "观测要素"]
const createFields = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识"]
const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const stats = ref<Record<string, number>>({})
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ 记录编号: '', 所属站点: '', 观测要素: '', 记录状态: '' })
const detail = ref<Row | null>(null)
const showCreate = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

const statItems = computed(() => [
  { label: '有效记录', value: stats.value['有效记录'] ?? 0 },
  { label: '待质控', value: stats.value['待质控'] ?? 0 },
  { label: '疑误标记', value: stats.value['疑误标记'] ?? 0 },
  { label: '已作废（不计入有效）', value: stats.value['已作废'] ?? 0 },
])

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function filterParams(): URLSearchParams {
  // 前端筛选条件与后端参数一一对应，保证过滤真正落到查询里
  const params = new URLSearchParams()
  if (filters.value.记录编号.trim()) params.set('keyword', filters.value.记录编号.trim())
  if (filters.value.所属站点.trim()) params.set('station', filters.value.所属站点.trim())
  if (filters.value.观测要素.trim()) params.set('element', filters.value.观测要素.trim())
  if (filters.value.记录状态) params.set('status', filters.value.记录状态)
  return params
}

async function reload() {
  errorMessage.value = ''
  // 过滤条件和页码写进地址栏：翻页后返回、刷新页面都停留在同一步
  const query = filterParams()
  query.set('page', String(page.value))
  void router.replace({ query: Object.fromEntries(query) })
  query.set('size', String(PAGE_SIZE))
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('观测记录列表读取失败')
    }
    const payload = await response.json()
    const items: Row[] = payload.items ?? []
    const totalCount: number = payload.total ?? items.length
    if (!items.length && page.value > 1 && totalCount > 0) {
      // 当前页被过滤/流转掏空时回到第一页，而不是停在空页
      page.value = 1
      return reload()
    }
    rows.value = items
    total.value = totalCount
    stats.value = payload.stats ?? {}
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录列表读取失败'
  }
}

function search() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.value = { 记录编号: '', 所属站点: '', 观测要素: '', 记录状态: '' }
  page.value = 1
  void reload()
}

function goPage(target: number) {
  page.value = Math.min(Math.max(1, target), totalPages.value)
  void reload()
}

function exportRows() {
  // 清单与当前列表走同一份过滤条件，条数自然对得上
  window.open(`${ENDPOINT}/export?${filterParams().toString()}`, '_blank')
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('观测记录详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

function openCreate() {
  createForm.value = Object.fromEntries(createFields.map((field) => [field, '']))
  createError.value = ''
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 缺字段、记录编号重复等原因由后端给出，原样展示
      createError.value = payload.message ?? '观测记录登记失败'
      return
    }
    showCreate.value = false
    noticeMessage.value = payload.message ?? '观测记录已登记'
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '观测记录登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message ?? '观测记录动作未生效，请稍后重试'
      return
    }
    noticeMessage.value = payload.message ?? `观测记录已${action}`
    await reload()
    // 详情若正开着同一条记录，同步刷新，保证详情与列表是同一份状态
    if (detail.value && detail.value.id === row.id) {
      await openDetail(row)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录操作失败'
  }
}

onMounted(() => {
  // 从地址栏恢复过滤条件和页码，刷新后查询现场不丢
  const pick = (key: string): string => {
    const value = route.query[key]
    return typeof value === 'string' ? value : ''
  }
  filters.value = {
    记录编号: pick('keyword'),
    所属站点: pick('station'),
    观测要素: pick('element'),
    记录状态: pick('status'),
  }
  const rawPage = Number(pick('page'))
  page.value = Number.isFinite(rawPage) && rawPage > 0 ? Math.floor(rawPage) : 1
  void reload()
})
</script>
