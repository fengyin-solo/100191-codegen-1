<template>
  <section class="page" data-module="plan">
    <header class="page-head">
      <div>
        <h2>故障处置预案库（值班入口）</h2>
        <p class="page-desc">
          按适用机型分组呈现处置预案，列出预案版本、适用机型、处置步骤数量与最近修订日期；
          停用版本不再出现在值班入口，历史版本仍可进详情回看。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">新建草稿预案</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>适用机型</span>
        <select v-model="filters.model">
          <option value="">全部机型</option>
          <option v-for="m in modelOptions" :key="m" :value="m">{{ m }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>版本状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>关键词</span>
        <input v-model="filters.keyword" placeholder="按预案编号 / 名称检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="emptyText">
      <div class="empty-block">{{ emptyText }}</div>
    </template>
    <template v-else>
      <section v-for="group in groups" :key="group['适用机型']" class="plan-group">
        <h3 class="group-title">{{ group['适用机型'] }}（{{ group.items.length }} 条）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>预案编号</th>
              <th>预案名称</th>
              <th>预案版本</th>
              <th>适用机型</th>
              <th>处置步骤数量</th>
              <th>最近修订日期</th>
              <th>版本状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in group.items" :key="String(row.id)">
              <td>{{ row.plan_id }}</td>
              <td>{{ row['预案名称'] }}</td>
              <td>{{ row['版本号'] }}<span v-if="row['修订中']" class="tag tag-draft">修订中</span></td>
              <td>{{ row['适用机型'] }}</td>
              <td>{{ row['步骤数量'] }}</td>
              <td>{{ row['最近修订日期'] }}</td>
              <td><span class="tag" :class="row.status === '生效' ? 'tag-active' : 'tag-draft'">{{ row.status }}</span></td>
              <td class="row-actions">
                <RouterLink class="link" :to="`/plan/${row.id}`">查看详情</RouterLink>
                <button
                  v-if="row.status === '草稿'"
                  class="link"
                  type="button"
                  @click="runAction(row.id, '发布生效')"
                >
                  发布生效
                </button>
                <button
                  v-else
                  class="link link-danger"
                  type="button"
                  @click="runAction(row.id, '停用预案')"
                >
                  停用
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>

    <section class="plan-pending">
      <h3 class="group-title">待补充预案机型</h3>
      <div v-if="pendingModels.length" class="pending-list">
        <span v-for="m in pendingModels" :key="m" class="pending-chip">
          {{ m }}
          <em>待补充</em>
        </span>
      </div>
      <p v-else class="pending-done">{{ pendingMessage || '全部在册机型均已配置处置预案，暂无待补充机型。' }}</p>
    </section>

    <footer class="page-foot">
      <span>值班入口共 {{ total }} 条处置预案，与运营概览条数一致</span>
    </footer>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>新建草稿预案</h3>
        <p class="page-desc">新建后生成 V1.0 草稿，进入详情补录处置步骤，发布生效后才出现在值班入口。</p>
        <label class="filter-item">
          <span>预案名称</span>
          <input v-model="createForm['预案名称']" placeholder="例如：齿轮箱油温高处置预案" />
        </label>
        <label class="filter-item">
          <span>适用机型</span>
          <select v-model="createForm['适用机型']">
            <option value="" disabled>请选择在册机型</option>
            <option v-for="m in modelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="submit">创建草稿</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type PlanSummary = {
  id: number
  plan_id: string
  预案名称: string
  适用机型: string
  版本号: string
  status: string
  步骤数量: number
  最近修订日期: string
  修订中: boolean
}
type PlanGroup = { 适用机型: string; items: PlanSummary[] }
type PlanLibrary = {
  total: number
  groups: PlanGroup[]
  pending_models: string[]
  pending_message: string
  empty: string
  stats: Record<string, number>
}

const router = useRouter()
const modelOptions = ['GW-1.5MW', 'MY2.0-104', 'SE-12125', 'EN-141/2.5', 'GW-3.0MW']
const statusOptions = ['草稿', '生效']

const groups = ref<PlanGroup[]>([])
const pendingModels = ref<string[]>([])
const pendingMessage = ref('')
const emptyText = ref('')
const total = ref(0)
const stats = ref<Record<string, number>>({})
const errorMessage = ref('')
const filters = reactive({ keyword: '', model: '', status: '' })

const creating = ref(false)
const createForm = reactive<Record<string, string>>({ 预案名称: '', 适用机型: '' })
const createError = ref('')

const statCards = ref<{ label: string; value: number }[]>([])

function resetFilters() {
  filters.keyword = ''
  filters.model = ''
  filters.status = ''
  void reload()
}

function openCreate() {
  createForm.预案名称 = ''
  createForm.适用机型 = ''
  createError.value = ''
  creating.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request('/api/plan', {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      createError.value = payload.message || '草稿预案未创建成功'
      return
    }
    creating.value = false
    await router.push(`/plan/${payload.entry.id}`)
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '草稿预案创建失败'
  }
}

async function runAction(id: number, action: string) {
  errorMessage.value = ''
  try {
    const response = await request(`/api/plan/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '预案版本操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.model) query.set('model', filters.model)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`/api/plan?${query.toString()}`)
    if (!response.ok) throw new Error('处置预案库读取失败')
    const payload = (await response.json()) as PlanLibrary
    groups.value = payload.groups ?? []
    pendingModels.value = payload.pending_models ?? []
    pendingMessage.value = payload.pending_message ?? ''
    emptyText.value = payload.empty ?? ''
    total.value = payload.total ?? 0
    stats.value = payload.stats ?? {}
    statCards.value = [
      { label: '值班入口预案', value: stats.value['值班入口预案'] ?? 0 },
      { label: '生效中', value: stats.value['生效中'] ?? 0 },
      { label: '草稿', value: stats.value['草稿'] ?? 0 },
      { label: '待补充机型', value: stats.value['待补充机型'] ?? 0 },
    ]
  } catch (error) {
    emptyText.value = '处置预案库暂时加载失败，请稍后重试；接口未返回数据时页面不留空白。'
    groups.value = []
    pendingModels.value = []
    errorMessage.value = error instanceof Error ? error.message : '处置预案库读取失败'
  }
}

onMounted(reload)
</script>
