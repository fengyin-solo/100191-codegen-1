<template>
  <section class="page" data-module="plan-detail">
    <header class="page-head">
      <div>
        <h2>
          <RouterLink class="link" to="/plan">故障处置预案库</RouterLink>
          <span class="title-sep">/</span>
          {{ detail.预案名称 || '预案详情' }}
        </h2>
        <p class="page-desc">
          {{ detail.预案编号 }} · {{ detail.版本 }} · 适用机型 {{ detail.适用机型 }} ·
          最近修订 {{ detail.最近修订 }}
        </p>
      </div>
      <div class="page-actions">
        <span :class="['status-tag', statusClass(detail.status)]">{{ detail.status }}</span>
      </div>
    </header>

    <div v-if="errorMessage" class="empty-block">{{ errorMessage }}</div>

    <template v-else>
      <div class="detail-grid">
        <div class="detail-main">
          <h3 class="block-title">处置步骤（共 {{ steps.length }} 步）</h3>
          <ol v-if="steps.length" class="step-list">
            <li v-for="step in steps" :key="step.seq" class="step-item">
              <div class="step-head">
                <span class="step-seq">{{ step.seq }}</span>
                <strong>{{ step.标题 }}</strong>
              </div>
              <p class="step-content">{{ step.内容 }}</p>
            </li>
          </ol>
          <p v-else class="empty-inline">该版本尚未补录处置步骤，请在下方录入第一步。</p>

          <form v-if="detail.status === '草稿'" class="add-panel" @submit.prevent="submitStep">
            <h3 class="block-title">补录处置步骤</h3>
            <label class="filter-item">
              <span>步骤标题</span>
              <input v-model="stepForm.标题" placeholder="例如：确认报警信息" />
            </label>
            <label class="filter-item">
              <span>步骤内容</span>
              <textarea v-model="stepForm.内容" rows="3" placeholder="描述具体的处置动作与注意事项"></textarea>
            </label>
            <div>
              <button class="btn primary" type="submit">补录到本版本</button>
            </div>
          </form>
          <p v-else class="empty-inline">仅草稿状态的预案可补录步骤；如需调整生效版本，请先修订出新版本。</p>
        </div>

        <aside class="detail-side">
          <h3 class="block-title">版本操作</h3>
          <div class="action-col">
            <button
              v-if="detail.status === '草稿'"
              class="btn primary"
              type="button"
              @click="runAction('发布生效')"
            >
              发布生效
            </button>
            <button
              v-if="detail.status === '生效'"
              class="btn"
              type="button"
              @click="runAction('停用')"
            >
              停用本版本
            </button>
            <button
              v-if="detail.status === '生效'"
              class="btn"
              type="button"
              @click="createRevision"
            >
              修订新版本
            </button>
            <p v-if="detail.status === '停用'" class="empty-inline">
              已停用版本不能再流转，也不会出现在值班入口。
            </p>
          </div>
          <p class="rule-note">版本只能按 草稿 → 生效 → 停用 单向推进，不允许回退。</p>
          <p v-if="actionMessage" :class="actionOk ? 'ok-text' : 'error-text'">{{ actionMessage }}</p>

          <h3 class="block-title history-title">历史修订</h3>
          <ul class="history-list">
            <li
              v-for="ver in history.versions"
              :key="ver.id"
              :class="['history-item', { active: ver.id === versionId }]"
            >
              <button class="history-btn" type="button" @click="goVersion(ver.id)">
                <span>{{ ver.版本 }}</span>
                <span :class="['status-tag', statusClass(ver.status)]">{{ ver.status }}</span>
              </button>
              <span class="history-meta">{{ ver.最近修订 }} · {{ ver.步骤数量 }} 步</span>
            </li>
          </ul>
          <p v-if="!history.versions.length" class="empty-inline">暂无历史版本信息。</p>
        </aside>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Step = { seq: number; 标题: string; 内容: string }
type PlanDetail = {
  id?: number
  预案编号?: string
  预案名称?: string
  适用机型?: string
  版本?: string
  status?: string
  最近修订?: string
  步骤?: Step[]
}
type HistoryVersion = {
  id: number
  版本: string
  status: string
  最近修订: string
  步骤数量: number
}

const route = useRoute()
const router = useRouter()

const detail = ref<PlanDetail>({})
const history = ref<{ versions: HistoryVersion[] }>({ versions: [] })
const errorMessage = ref('')
const actionMessage = ref('')
const actionOk = ref(true)
const stepForm = reactive({ 标题: '', 内容: '' })

const versionId = computed(() => Number(route.params.id))
const steps = computed(() => detail.value.步骤 ?? [])

function statusClass(status?: string) {
  return { 生效: 'st-active', 草稿: 'st-draft', 停用: 'st-retired' }[status ?? ''] ?? ''
}

function goVersion(id: number) {
  if (id !== versionId.value) {
    void router.push(`/plan/${id}`)
  }
}

async function load() {
  errorMessage.value = ''
  actionMessage.value = ''
  try {
    const response = await request(`/api/plan/${versionId.value}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: '预案详情读取失败' }))
      throw new Error(payload.detail || '预案详情读取失败')
    }
    detail.value = await response.json()

    const historyResponse = await request(`/api/plan/${versionId.value}/history`)
    if (historyResponse.ok) {
      history.value = await historyResponse.json()
    }
  } catch (error) {
    detail.value = {}
    history.value = { versions: [] }
    errorMessage.value = error instanceof Error ? error.message : '预案详情读取失败'
  }
}

async function postAction(path: string, body: Record<string, unknown>, successText: string) {
  actionMessage.value = ''
  try {
    const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
    const payload = await response.json()
    if (!payload.ok) {
      actionOk.value = false
      actionMessage.value = payload.message || '操作未生效'
      return
    }
    actionOk.value = true
    actionMessage.value = payload.message || successText
    stepForm.标题 = ''
    stepForm.内容 = ''
    await load()
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '操作未生效'
  }
}

function submitStep() {
  void postAction(
    `/api/plan/${versionId.value}/steps`,
    { values: { 标题: stepForm.标题, 内容: stepForm.内容 } },
    '处置步骤已补录',
  )
}

function runAction(action: string) {
  void postAction(`/api/plan/${versionId.value}/actions`, { values: { action } }, '操作已生效')
}

function createRevision() {
  void postAction(`/api/plan/${versionId.value}/revision`, {}, '修订版本已创建').then(async () => {
    // 修订成功后跳转到新草稿版本继续补录
    const response = await request(`/api/plan/${versionId.value}/history`)
    if (response.ok) {
      const payload = await response.json()
      const draft = [...(payload.versions as HistoryVersion[])].reverse().find((v) => v.status === '草稿')
      if (draft) {
        goVersion(draft.id)
      }
    }
  })
}

watch(versionId, () => void load())
onMounted(load)
</script>

<style scoped>
.title-sep {
  color: var(--muted);
  margin: 0 6px;
}
.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 12px;
}
.detail-main,
.detail-side {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.block-title {
  margin: 0 0 10px;
  font-size: 14px;
}
.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.step-item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
}
.step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.step-seq {
  display: inline-flex;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--brand);
  color: #fff;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
.step-content {
  margin: 6px 0 0 30px;
  color: #374151;
  font-size: 13px;
}
.add-panel {
  margin-top: 14px;
  border-top: 1px dashed var(--border);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.add-panel textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
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
.action-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rule-note {
  font-size: 12px;
  color: var(--muted);
  margin: 10px 0 0;
}
.history-title {
  margin-top: 14px;
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.history-item.active {
  border-color: var(--brand);
}
.history-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.history-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  border: none;
  background: none;
  cursor: pointer;
  padding: 0;
  font-size: 13px;
}
.history-meta {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}
.empty-block,
.empty-inline {
  color: var(--muted);
  font-size: 13px;
}
.empty-block {
  padding: 24px;
  text-align: center;
  background: #fff;
  border: 1px dashed var(--border);
  border-radius: 8px;
}
.ok-text {
  color: #1a7f37;
  font-size: 12px;
}
</style>
