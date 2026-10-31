<template>
  <div class="itinerary-card">
    <div class="it-header">
      <div class="it-title">{{ data.date }} 游玩行程</div>
      <div class="it-weather">{{ data.weather_summary }}</div>
    </div>

    <div class="it-tags">
      <van-tag v-if="data.has_elder" plain type="primary" size="medium">含老人 · 缓坡少排队</van-tag>
      <van-tag v-for="age in data.child_ages" :key="age" plain type="warning" size="medium">
        {{ age }} 岁儿童
      </van-tag>
    </div>

    <div class="it-timeline">
      <div v-for="(step, i) in data.steps" :key="i" class="it-step">
        <div class="it-dot" :class="{ last: i === data.steps.length - 1 }" />
        <div class="it-body">
          <div class="it-time">{{ step.time }}</div>
          <div class="it-name">{{ step.poi_name }}</div>
          <div class="it-activity">{{ step.activity }}</div>
          <div v-if="step.tip" class="it-tip">提示:{{ step.tip }}</div>
        </div>
      </div>
    </div>

    <div v-if="data.warnings?.length" class="it-warnings">
      <div v-for="(w, i) in data.warnings" :key="i" class="it-warning">{{ w }}</div>
    </div>

    <div v-if="data.rainy_fallback" class="it-fallback">雨天预案:{{ data.rainy_fallback }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Itinerary } from '../types'

defineProps<{ data: Itinerary }>()
</script>

<style scoped>
.itinerary-card {
  background: linear-gradient(160deg, #ffffff 0%, #f3f9ff 100%);
  border-radius: 12px;
  padding: 12px;
  margin-top: 8px;
  border: 1px solid #e3eefb;
}

.it-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.it-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f6fd6;
}

.it-weather {
  font-size: 12px;
  color: #7a8aa0;
}

.it-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 8px 0;
}

.it-timeline {
  position: relative;
}

.it-step {
  display: flex;
  gap: 10px;
}

.it-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1f6fd6;
  margin-top: 5px;
  position: relative;
  flex-shrink: 0;
}

.it-dot:not(.last)::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 12px;
  transform: translateX(-50%);
  width: 2px;
  height: calc(100% + 14px);
  background: #c7def7;
}

.it-body {
  flex: 1;
  padding-bottom: 14px;
}

.it-time {
  font-size: 12px;
  color: #1f6fd6;
  font-weight: 600;
}

.it-name {
  font-size: 14px;
  font-weight: 600;
  color: #23303f;
  margin: 2px 0;
}

.it-activity {
  font-size: 13px;
  color: #4b5a6e;
}

.it-tip {
  font-size: 12px;
  color: #c08a1e;
  margin-top: 2px;
}

.it-fallback {
  margin-top: 4px;
  padding: 8px;
  background: #fff7e8;
  border-radius: 8px;
  font-size: 12px;
  color: #a8741a;
}

.it-warnings {
  margin-top: 4px;
  padding: 8px;
  background: #fff1f0;
  border-radius: 8px;
  font-size: 12px;
  color: #c0453c;
  line-height: 1.5;
}

.it-warning + .it-warning {
  margin-top: 4px;
}
</style>
