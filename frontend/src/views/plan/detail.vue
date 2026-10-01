<template>
  <section class="page" data-module="plan-detail">
    <header class="page-head">
      <div>
        <h2>
          {{ plan?.预案名称 ?? '处置预案详情' }}
          <span v-if="plan" class="tag" :class="plan.version.status === '生效' ? 'tag-active' : plan.version.status === '停用' ? 'tag-off' : 'tag-draft'">
            {{ plan.version.版本号 }} · {{ plan.version.status }}
          </span>
        </h2>
        <p class="page-desc">
          预案编号 {{ plan?.plan_id }} ｜ 适用机型 {{ plan?.适用机型 }} ｜ 当前查看版本修订于
          {{ plan?.version.修订日期 }}
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/plan">返回预案列表</RouterLink>
      </div>
    </header>

    <p v-if="notFound" class="empty-block">该预案版本不存在或已被清理，请返回预案列表重新选择。</p>

    <template v-else-if="plan">
      <p v-if="plan.readonly" class="hint-bar">
        <template v-if="plan.version.status === '停用'">
          当前版本已停用：只读回看，步骤为当时口径的历史快照，不能再补录或重新生效。
        </template>
        <template v-else>
          当前查看的是历史版本，处置步骤按当时口径保留只读；如需调整请切回最新版本或基于生效版补录生成新草稿。
        </template>
      </p>

      <div class="detail-grid">
        <article class="detail-main">
          <h3 class="group-title">处置步骤（{{ plan.steps.length }} 步）</h3>
          <ol v-if="plan.steps.length" class="step-list">
            <li v-for="step in plan.steps" :key="step.序号" class="step-item">
              <span class="step-no">{{ step.序号 }}</span>
              <div>
                <p class="step-text">{{ step.内容 }}</p>
                <span class="step-time">补充时间：{{ step.补充时间 }}</span>
              </div>
            </li>
          </ol>
          <p v-else class="empty-inline">{{ plan.steps_empty }}</p>

          <section v-if="!plan.readonly" class="step-add">
            <h3 class="group-title">补录处置步骤</h3>
            <p class="page-desc">
              {{ plan.version.status === '生效'
                ? '当前为生效版本：补录会复制本版口径开出下一版草稿，发布生效后才替换值班入口版本。'
                : '当前为草稿：补录直接追加到本版，列表页步骤数量随补录实时变化。' }}
            </p>
            <textarea v-model="stepText" rows="4" placeholder="一次可补录多条，每行一条步骤"></textarea>
            <p v-if="stepMessage" :class="stepOk ? 'ok-text' : 'error-text'">{{ stepMessage }}</p>
            <div class="modal-actions">
              <button class="btn primary" type="button" :disabled="submitting" @click="submitSteps">
                {{ submitting ? '提交中…' : '提交补录' }}
              </button>
            </div>
          </section>
        </article>

        <aside class="detail-side">
          <h3 class="group-title">历史修订版本（按修订时间）</h3>
          <ul class="version-list">
            <li v-for="v in plan.versions" :key="v.id">
              <button
                class="version-item"
                :class="{ active: v.id === plan.version.id }"
                type="button"
                @click="switchVersion(v.id)"
              >
                <span>{{ v.版本号 }}（{{ v.status }}）</span>
                <span class="version-meta">{{ v.步骤数量 }} 步 · {{ v.修订日期 }}</span>
                <span v-if="v.修订说明" class="version-note">{{ v.修订说明 }}</span>
              </button>
            </li>
          </ul>

          <div v-if="canAct" class="version-actions">
            <button v-if="plan.version.status === '草稿'" class="btn primary" type="button" @click="runAction('发布生效')">
              发布生效
            </button>
            <button v-else class="btn" type="button" @click="runAction('停用预案')">停用本版本</button>
            <p v-if="actionMessage" class="error-text">{{ actionMessage }}</p>
            <p class="page-desc">版本只能按 草稿 → 生效 → 停用 单向推进，停用后不能重新生效。</p>
          </div>
        </aside>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type VersionMeta = {
  id: number
  版本号: string
  status: string
  修订日期: string
  步骤数量: number
  修订说明: string
}
type StepView = { 序号: number; 内容: string; 补充时间: string }
type PlanDetail = {
  plan_id: string
  预案名称: string
  适用机型: string
  head_id: number | null
  version: VersionMeta
  steps: StepView[]
  versions: VersionMeta[]
  readonly: boolean
  steps_empty: string
}

const route = useRoute()
const plan = ref<PlanDetail | null>(null)
const notFound = ref(false)
const stepText = ref('')
const stepMessage = ref('')
const stepOk = ref(false)
const actionMessage = ref('')
const submitting = ref(false)

const canAct = computed(() => plan.value && !plan.value.readonly)

async function load(versionId: string | number) {
  notFound.value = false
  actionMessage.value = ''
  stepMessage.value = ''
  try {
    const response = await request(`/api/plan/${versionId}`)
    if (response.status === 404) {
      notFound.value = true
      plan.value = null
      return
    }
    if (!response.ok) throw new Error('预案详情读取失败')
    plan.value = (await response.json()) as PlanDetail
  } catch (error) {
    notFound.value = true
    plan.value = null
  }
}

function switchVersion(id: number) {
  stepMessage.value = ''
  void load(id)
}

async function submitSteps() {
  if (!plan.value) return
  const contents = stepText.value.split('\n').map((line) => line.trim()).filter(Boolean)
  if (!contents.length) {
    stepOk.value = false
    stepMessage.value = '请填写至少一条处置步骤（每行一条）'
    return
  }
  submitting.value = true
  stepMessage.value = ''
  try {
    const response = await request(`/api/plan/${plan.value.version.id}/steps`, {
      method: 'POST',
      body: JSON.stringify({ contents }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      stepOk.value = false
      stepMessage.value = payload.message
      return
    }
    stepOk.value = true
    stepMessage.value = payload.message
    stepText.value = ''
    // 生效版补录会开出新草稿：跳到新草稿；草稿补录直接刷新当前版，列表数量随之更新
    await load(payload.entry.id)
  } catch (error) {
    stepOk.value = false
    stepMessage.value = error instanceof Error ? error.message : '步骤补录失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string) {
  if (!plan.value) return
  actionMessage.value = ''
  try {
    const response = await request(`/api/plan/${plan.value.version.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      actionMessage.value = payload.message
      return
    }
    await load(plan.value.version.id)
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '预案版本操作失败'
  }
}

watch(() => route.params.id, (id) => {
  if (id) void load(Array.isArray(id) ? id[0] : id)
})

onMounted(() => {
  const id = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id
  if (id) void load(id)
})
</script>
