<template>
  <van-nav-bar title="云栖湖度假区 · 智能客服" fixed placeholder />

  <div ref="listRef" class="msg-list">
    <MessageBubble v-for="m in messages" :key="m.id" :msg="m" />
  </div>

  <!-- 快捷问题 -->
  <div v-if="showQuick" class="quick-bar">
    <van-tag
      v-for="q in quickQuestions"
      :key="q"
      round
      size="large"
      plain
      type="primary"
      class="quick-tag"
      @click="send(q)"
    >
      {{ q }}
    </van-tag>
  </div>

  <!-- 底部输入栏 -->
  <div class="input-bar">
    <van-field
      v-model="draft"
      placeholder="问问门票、演出、怎么玩..."
      class="input-field"
      @keyup.enter="send(draft)"
    />
    <van-button type="primary" size="small" :loading="sending" @click="send(draft)">
      发送
    </van-button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, reactive, ref } from 'vue'
import { showToast } from 'vant'
import MessageBubble from '../components/MessageBubble.vue'
import { getSessionId, streamChat } from '../api/sse'
import type { ChatMessage, StreamEvent } from '../types'

// 工具名 -> 中文进度文案
const TOOL_LABELS: Record<string, string> = {
  query_ticket_types: '查询票种价格',
  create_order: '创建门票订单',
  query_order: '查询订单详情',
  refund_order: '办理退票',
  query_poi_status: '查询项目开放状态',
  query_show_schedule: '查询演出场次',
  list_pois: '查询项目清单',
  get_weather: '查询当日天气',
  create_service_ticket: '创建服务工单',
  plan_data: '汇总天气与园区实况',
}

const quickQuestions = [
  '门票多少钱？',
  '帮我买两张明天的成人票',
  '明天带6岁孩子一日游怎么安排？',
  '飞鸟剧场几点开演？',
  '自驾怎么停车？',
]

const sessionId = getSessionId()
const listRef = ref<HTMLElement>()
const draft = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([
  {
    id: 'welcome',
    role: 'assistant',
    content:
      '您好，我是云栖湖度假区智能客服**小栖**，可以为您查询票务、演出和项目状态，帮忙买票、规划行程，也能转接人工服务。请问有什么可以帮您？',
  },
])

const showQuick = ref(true)
let toolSeq = 0

function scrollBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

async function send(text: string) {
  const content = text.trim()
  if (!content || sending.value) return

  showQuick.value = false
  draft.value = ''
  messages.value.push({ id: 'u' + Date.now(), role: 'user', content })
  scrollBottom()

  // 必须用 reactive 包裹:push 进响应式数组后,通过同一代理引用修改才能触发更新
  const assistant = reactive<ChatMessage>({
    id: 'a' + Date.now(),
    role: 'assistant',
    content: '',
    streaming: true,
    tools: [],
  })
  messages.value.push(assistant)
  scrollBottom()

  sending.value = true
  try {
    await streamChat(sessionId, content, (ev: StreamEvent) => handleEvent(ev, assistant))
  } catch (e: any) {
    assistant.content = e?.message || '网络异常,请稍后重试'
    showToast('连接失败')
  } finally {
    assistant.streaming = false
    sending.value = false
    scrollBottom()
  }
}

function handleEvent(ev: StreamEvent, msg: ChatMessage) {
  switch (ev.type) {
    case 'token':
      msg.content += ev.chunk ?? ''
      break
    case 'sources':
      msg.sources = ev.sources
      break
    case 'tool_start': {
      msg.tools!.push({
        id: ++toolSeq,
        tool: ev.tool ?? '',
        label: TOOL_LABELS[ev.tool ?? ''] ?? ev.tool ?? '',
        detail: '',
        done: false,
      })
      break
    }
    case 'tool_end': {
      const last = [...msg.tools!].reverse().find((t) => t.tool === ev.tool && !t.done)
      if (last) {
        last.done = true
        last.detail = ev.result ?? ''
      }
      break
    }
    case 'itinerary':
      if (ev.itinerary) msg.itinerary = ev.itinerary
      break
    case 'handoff':
      msg.handoff = {
        ticket_id: ev.ticket_id ?? '',
        category: ev.category ?? 'help',
        reason: ev.reason,
      }
      break
    case 'error':
      msg.content = ev.message || '服务暂时不可用'
      break
    case 'done':
      break
  }
  scrollBottom()
}
</script>

<style scoped>
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 12px;
  -webkit-overflow-scrolling: touch;
}

.quick-bar {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 8px 12px;
  background: transparent;
}

.quick-tag {
  flex-shrink: 0;
  padding: 0 12px;
  height: 32px;
  font-size: 13px;
}

.input-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  padding-bottom: calc(8px + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1px solid #ebedf0;
}

.input-field {
  flex: 1;
  background: #f4f5f7;
  border-radius: 18px;
  padding: 4px 12px;
}

.input-field :deep(.van-field__control) {
  font-size: 14px;
}
</style>
