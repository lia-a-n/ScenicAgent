<template>
  <div class="bubble-row" :class="msg.role">
    <div v-if="msg.role === 'assistant'" class="avatar">小栖</div>

    <div class="bubble">
      <!-- 工具调用进度 -->
      <div v-if="msg.tools?.length" class="tool-list">
        <div v-for="t in msg.tools" :key="t.id" class="tool-item">
          <van-loading v-if="!t.done" size="14px" class="tool-ico" />
          <van-icon v-else name="passed" color="#07c160" class="tool-ico" />
          <span class="tool-label">{{ t.label }}</span>
        </div>
      </div>

      <!-- 转人工横幅 -->
      <div v-if="msg.handoff" class="handoff-box">
        <van-icon name="service-o" size="18px" />
        <div>
          <div class="handoff-title">
            {{ msg.handoff.category === 'complaint' ? '投诉已受理' : '已为您转接人工客服' }}
          </div>
          <div class="handoff-id">工单 {{ msg.handoff.ticket_id }} · 客服将在 30 分钟内联系您</div>
        </div>
      </div>

      <!-- 行程卡片 -->
      <ItineraryCard v-if="msg.itinerary" :data="msg.itinerary" />

      <!-- 文本回答(markdown 轻量渲染) -->
      <div
        v-if="msg.content"
        class="content markdown-body"
        :class="{ streaming: msg.streaming }"
        v-html="rendered"
      />
      <van-loading v-else-if="msg.streaming" size="16px">思考中</van-loading>

      <!-- 知识来源 -->
      <div v-if="msg.sources?.length" class="sources">
        <span class="sources-title">参考:</span>
        <van-tag
          v-for="(s, i) in msg.sources"
          :key="i"
          plain
          type="primary"
          size="medium"
          class="src-tag"
        >
          {{ s.title }}
        </van-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import ItineraryCard from './ItineraryCard.vue'
import type { ChatMessage } from '../types'

marked.setOptions({ breaks: true })

const props = defineProps<{ msg: ChatMessage }>()

const rendered = computed(() => marked.parse(props.msg.content, { async: false }) as string)
</script>

<style scoped>
.bubble-row {
  display: flex;
  gap: 8px;
  margin: 12px 0;
  padding: 0 12px;
  align-items: flex-start;
}

.bubble-row.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2b8ff5, #18c29c);
  color: #fff;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.bubble {
  max-width: 78%;
  padding: 10px 12px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  font-size: 14px;
  line-height: 1.6;
  color: #23303f;
  word-break: break-word;
}

.bubble-row.user .bubble {
  background: #d9ecff;
  color: #143d6b;
}

.content.streaming::after {
  content: '▍';
  color: #2b8ff5;
  animation: blink 1s infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

/* 工具进度 */
.tool-list {
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #5b6b80;
  background: #f5f8fc;
  border-radius: 6px;
  padding: 4px 8px;
}

.tool-ico {
  flex-shrink: 0;
}

.tool-label {
  white-space: nowrap;
  font-size: 12px;
}

/* 转人工 */
.handoff-box {
  display: flex;
  gap: 10px;
  align-items: center;
  background: #eef6ff;
  border: 1px solid #cfe3fb;
  border-radius: 10px;
  padding: 10px;
  margin-bottom: 8px;
  color: #1f6fd6;
}

.handoff-title {
  font-size: 14px;
  font-weight: 600;
}

.handoff-id {
  font-size: 12px;
  color: #6b85a3;
  margin-top: 2px;
}

/* 知识来源 */
.sources {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e5eaf1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.sources-title {
  font-size: 12px;
  color: #97a4b5;
}

.src-tag {
  border-radius: 6px;
}

/* markdown 排版 */
.markdown-body :deep(p) {
  margin: 4px 0;
}

.markdown-body :deep(strong) {
  color: #d45f12;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 18px;
  margin: 4px 0;
}
</style>
