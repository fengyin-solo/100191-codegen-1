<template>
  <section class="page" data-module="plan">
    <header class="page-head">
      <div>
        <h2>故障处置预案库</h2>
        <p class="page-desc">值班入口：处置预案按适用机型分组呈现；停用版本不在此入口出现，可在单条预案的历史修订中回看。</p>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div v-if="errorMessage" class="board-error">{{ errorMessage }}</div>

    <template v-else>
      <div v-if="!groups.length" class="empty-block">
        {{ board.note || '当前没有可用于值班的预案，请先登记处置预案' }}
      </div>

      <div v-for="group in groups" :key="group['适用机型']" class="model-group">
        <h3 class="group-title">
          {{ group['适用机型'] }}
          <span class="group-meta">
            预案 {{ group['预案数量'] }} 条 · 生效 {{ group['生效数量'] }} · 草稿 {{ group['草稿数量'] }}
          </span>
        </h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>预案编号</th>
              <th>预案名称</th>
              <th>版本</th>
              <th>版本状态</th>
              <th>处置步骤数量</th>
              <th>最近修订日期</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in group.items" :key="String(row.id)">
              <td>{{ row['预案编号'] }}</td>
              <td>{{ row['预案名称'] }}</td>
              <td>{{ row['版本'] }}</td>
              <td><span :class="['status-tag', statusClass(row.status)]">{{ row.status }}</span></td>
              <td>{{ row['步骤数量'] }}</td>
              <td>{{ row['最近修订'] }}</td>
              <td><RouterLink class="link" :to="`/plan/${row.id}`">查看处置步骤</RouterLink></td>
            </tr>
          </tbody>
        </table>
      </div>

      <section class="pending-block">
        <h3 class="group-title">
          待补充机型
          <span class="group-meta">{{ board.pending_model_count }} 个机型尚未配置可用预案</span>
        </h3>
        <div v-if="pendingModels.length" class="pending-list">
          <div v-for="model in pendingModels" :key="model" class="pending-item">
            <span class="pending-name">{{ model }}</span>
            <span class="pending-flag">待补充</span>
            <button class="btn" type="button" @click="openCreate(model)">登记预案</button>
          </div>
        </div>
        <p v-else class="empty-inline">{{ board.pending_note || '全部机型均已配置预案' }}</p>
      </section>

      <div v-if="createOpen" class="create-panel">
        <h3 class="group-title">为「{{ form.适用机型 }}」登记处置预案</h3>
        <p class="page-desc">登记后进入草稿，补录处置步骤并发布生效后才会在值班入口生效。</p>
        <form class="filter-bar" @submit.prevent="submitCreate">
          <label class="filter-item">
            <span>适用机型</span>
            <input v-model="form.适用机型" readonly />
          </label>
          <label class="filter-item">
            <span>预案名称</span>
            <input v-model="form.预案名称" placeholder="例如：主轴轴承温升处置预案" />
          </label>
          <button class="btn primary" type="submit">保存草稿</button>
          <button class="btn ghost" type="button" @click="createOpen = false">取消</button>
        </form>
        <p v-if="actionMessage" class="error-text">{{ actionMessage }}</p>
      </div>
    </template>

    <footer class="page-foot">
      <span>值班入口共 {{ board.total }} 条可用预案，与运营概览「故障处置预案库」条数一致</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Summary = {
  id: number
  预案编号: string
  预案名称: string
  适用机型: string
  版本: string
  status: string
  步骤数量: number
  最近修订: string
}
type Group = { 适用机型: string; 预案数量: number; 生效数量: number; 草稿数量: number; items: Summary[] }
type Board = {
  total: number
  active_count: number
  draft_count: number
  pending_model_count: number
  groups: Group[]
  pending_models: string[]
  note: string
  pending_note: string
}

const EMPTY_BOARD: Board = {
  total: 0,
  active_count: 0,
  draft_count: 0,
  pending_model_count: 0,
  groups: [],
  pending_models: [],
  note: '',
  pending_note: '',
}

const router = useRouter()
const board = ref<Board>(EMPTY_BOARD)
const errorMessage = ref('')
const actionMessage = ref('')
const createOpen = ref(false)
const form = reactive({ 适用机型: '', 预案名称: '' })

const groups = computed(() => board.value.groups)
const pendingModels = computed(() => board.value.pending_models)
const stats = computed(() => [
  { label: '值班可用预案', value: board.value.total },
  { label: '生效中', value: board.value.active_count },
  { label: '草稿待生效', value: board.value.draft_count },
  { label: '待补充机型', value: board.value.pending_model_count },
])

function statusClass(status: string) {
  return { 生效: 'st-active', 草稿: 'st-draft', 停用: 'st-retired' }[status] ?? ''
}

function openCreate(model: string) {
  form.适用机型 = model
  form.预案名称 = ''
  actionMessage.value = ''
  createOpen.value = true
}

async function submitCreate() {
  actionMessage.value = ''
  try {
    const response = await request('/api/plan', {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      actionMessage.value = payload.message || '预案登记失败'
      return
    }
    createOpen.value = false
    await reload()
    await router.push(`/plan/${payload.entry.id}`)
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '预案登记失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request('/api/plan/duty-board')
    if (!response.ok) {
      throw new Error('故障处置预案库读取失败')
    }
    board.value = await response.json()
  } catch (error) {
    board.value = EMPTY_BOARD
    errorMessage.value = error instanceof Error ? error.message : '故障处置预案库读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.model-group,
.pending-block,
.create-panel,
.board-error {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.group-title {
  margin: 0 0 8px;
  font-size: 14px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.group-meta {
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
}
.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.st-active {
  background: #e7f6ec;
  color: #1a7f37;
}
.st-draft {
  background: #fef3e2;
  color: #b45309;
}
.st-retired {
  background: #eef0f3;
  color: var(--muted);
}
.pending-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pending-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.pending-name {
  min-width: 120px;
}
.pending-flag {
  color: #b42318;
  border: 1px solid #f0a9a2;
  background: #fef3f2;
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 12px;
}
.empty-block,
.empty-inline {
  color: var(--muted);
  font-size: 13px;
  padding: 16px;
  text-align: center;
  background: #fff;
  border: 1px dashed var(--border);
  border-radius: 8px;
  margin-bottom: 12px;
}
.empty-inline {
  margin: 0;
  border-style: solid;
  text-align: left;
}
</style>
