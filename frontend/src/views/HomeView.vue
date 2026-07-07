<template>
  <section class="dashboard">
    <header class="dashboard-header">
      <div>
        <h1>欢迎回来，{{ displayName }} <span aria-hidden="true">👋</span></h1>
        <p>准备好了吗？今天也向理想岗位更进一步。</p>
      </div>
    </header>

    <div class="hero-grid">
      <section class="hero-card">
        <div class="hero-agent-stage" aria-hidden="true">
          <img class="hero-visual hero-visual-base" :src="dashboardHeroAgent" alt="" />
          <svg class="hero-hair-layer" viewBox="0 0 1672 941" preserveAspectRatio="xMidYMid slice">
            <defs>
              <clipPath id="dashboard-hero-hair-clip">
                <path
                  d="M1010 88 C1080 36 1188 48 1245 96 C1202 116 1164 162 1148 235 C1106 208 1070 189 1032 206 C978 230 952 306 956 388 C960 491 1018 596 1094 664 C984 637 892 556 884 446 C876 318 927 162 1010 88 Z"
                />
                <path
                  d="M1234 82 C1338 96 1408 202 1412 326 C1417 464 1365 596 1280 674 C1320 548 1306 424 1284 330 C1266 242 1244 165 1234 82 Z"
                />
                <path
                  d="M1084 82 C1128 62 1184 67 1220 96 C1178 116 1147 158 1132 230 C1102 192 1088 139 1084 82 Z"
                />
              </clipPath>
            </defs>
            <g class="hero-hair-sway" clip-path="url(#dashboard-hero-hair-clip)">
              <image
                :href="dashboardHeroAgent"
                x="0"
                y="0"
                width="1672"
                height="941"
                preserveAspectRatio="xMidYMid slice"
              />
            </g>
          </svg>
        </div>
        <div class="hero-copy">
          <h2>{{ greetingText }}，{{ displayName }} <span aria-hidden="true">✦</span></h2>
          <p>{{ heroHint }}</p>
        </div>

        <div class="hero-actions">
          <RouterLink class="primary-action" to="/interviews/new">
            开始新面试
            <span aria-hidden="true">▶</span>
          </RouterLink>
          <RouterLink v-if="latestInterview" class="secondary-action" :to="continueTarget">
            {{ continueActionText }}
            <span aria-hidden="true">›</span>
          </RouterLink>
        </div>

        <RouterLink v-if="latestInterview" class="resume-strip" :to="continueTarget">
          <span class="resume-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M6 7h12v13H6z" />
              <path d="M9 7V5h6v2" />
              <path d="M6 11h12" />
            </svg>
          </span>
          <span>
            <small>最近岗位</small>
            <strong>{{ latestPosition }}</strong>
            <em>{{ latestStatus }}</em>
          </span>
          <b aria-hidden="true">›</b>
        </RouterLink>
        <div v-else class="resume-strip resume-strip-static">
          <span class="resume-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M6 7h12v13H6z" />
              <path d="M9 7V5h6v2" />
              <path d="M6 11h12" />
            </svg>
          </span>
          <span>
            <small>最近岗位</small>
            <strong>{{ latestPosition }}</strong>
            <em>{{ latestStatus }}</em>
          </span>
        </div>
      </section>

      <section class="score-card">
        <div class="score-title">
          <span aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" />
              <path d="m12 8 3.5 2v4L12 16l-3.5-2v-4z" />
            </svg>
          </span>
          <h2>综合表现</h2>
        </div>
        <div class="score-body">
          <div class="score-copy">
            <strong>{{ overallScoreText }}</strong>
            <span>/ 100</span>
            <em>{{ trendText }} {{ trendArrow }}</em>
          </div>
          <div class="trend-chart" aria-hidden="true">
            <span v-for="mark in chartMarks" :key="mark">{{ mark }}</span>
            <div v-if="trendPoints.length" class="chart-grid">
              <i
                v-for="(point, index) in trendPoints"
                :key="`${index}-${point}`"
                :style="{ height: `${Math.min(point, 100)}%` }"
              ></i>
            </div>
            <div v-else class="chart-empty">暂无趋势</div>
          </div>
        </div>
      </section>
    </div>

    <div class="dashboard-grid">
      <section class="module ability-module">
        <div class="module-heading">
          <div class="module-title">
            <span aria-hidden="true">◎</span>
            <h2>四轮能力概览</h2>
          </div>
          <small>{{ summaryLoading ? "同步中" : "最近一次表现" }}</small>
        </div>
        <div v-if="abilities.length" class="ability-list">
          <div
            v-for="ability in abilities"
            :key="ability.name"
            class="ability-row"
            :style="{ '--ability-color': ability.color, '--ability-tint': ability.tint }"
          >
            <span class="ability-icon" aria-hidden="true">{{ ability.icon }}</span>
            <span class="ability-name">{{ ability.name }}</span>
            <div class="ability-track"><i :style="{ width: `${ability.progress}%` }"></i></div>
            <strong>{{ ability.value }}</strong>
          </div>
        </div>
        <p v-else class="module-empty">暂无四轮评分</p>
      </section>

      <section class="module weak-module">
        <div class="module-heading">
          <div class="module-title">
            <span aria-hidden="true">◉</span>
            <h2>当前薄弱项</h2>
          </div>
          <small>训练建议</small>
        </div>
        <div v-if="weakPoints.length" class="weak-list">
          <button
            v-for="(item, index) in weakPoints"
            :key="`${index}-${item.title}`"
            type="button"
            class="weak-row"
            :style="{ '--weak-color': item.color, '--weak-tint': item.tint }"
            @click="openWeakPointDetail(item)"
          >
            <span class="weak-icon" aria-hidden="true">{{ item.icon }}</span>
            <span class="weak-copy">
              <strong>{{ item.title }}</strong>
              <em>{{ item.text }}</em>
            </span>
            <b>{{ severityText(item.severity) }}</b>
          </button>
        </div>
        <p v-else class="module-empty">暂无薄弱项</p>
      </section>

      <section class="module status-module">
        <div class="module-heading">
          <div class="module-title">
            <span aria-hidden="true">⌁</span>
            <h2>系统状态</h2>
          </div>
          <small>轻量检查</small>
        </div>
        <ul>
          <li>
            <i class="ok"></i><span>记忆系统</span><strong>{{ memoryStatus }}</strong>
          </li>
          <li>
            <i class="info"></i>
            <span>Harness</span>
            <RouterLink class="status-detail-link" to="/harness">查看状态</RouterLink>
          </li>
          <li>
            <i class="info"></i><span>报告任务</span><strong>{{ reportTaskStatus }}</strong>
          </li>
        </ul>
      </section>
    </div>

    <div
      v-if="selectedWeakPoint"
      class="weak-modal-backdrop"
      role="presentation"
      @click.self="closeWeakPointDetail"
    >
      <section
        class="weak-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="weak-modal-title"
      >
        <header>
          <div>
            <small
              >{{ severityText(selectedWeakPoint.severity) }} ·
              {{ selectedWeakPoint.occurrence_count }} 次出现</small
            >
            <h2 id="weak-modal-title">{{ selectedWeakPoint.title }}</h2>
          </div>
          <button type="button" @click="closeWeakPointDetail">关闭</button>
        </header>

        <p class="weak-modal-summary">{{ selectedWeakPoint.summary || selectedWeakPoint.text }}</p>

        <div class="weak-modal-section">
          <h3>改进建议</h3>
          <p>
            {{
              selectedWeakPoint.suggestion ||
              "复盘对应问答，补充背景、行动、结果、技术取舍和量化数据。"
            }}
          </p>
        </div>

        <div v-if="selectedWeakPoint.evidence.length" class="weak-modal-section">
          <h3>记录证据</h3>
          <ul>
            <li v-for="item in selectedWeakPoint.evidence" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div v-if="selectedWeakPoint.sources.length" class="weak-modal-section">
          <h3>来源记录</h3>
          <ul class="weak-source-list">
            <li
              v-for="source in selectedWeakPoint.sources"
              :key="`${source.interview_id}-${source.round_type || 'report'}`"
            >
              <RouterLink :to="`/history/${source.interview_id}`">{{
                source.target_position
              }}</RouterLink>
              <span>{{ source.round_type ? roundName(source.round_type) : "最终报告" }}</span>
              <strong>{{ source.score === null ? "-" : source.score }}</strong>
              <time>{{ formatDate(source.occurred_at) }}</time>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import {
  ApiError,
  getDashboardSummary,
  type DashboardAbilitySummary,
  type DashboardSummary,
  type DashboardWeakPointSource,
  type DashboardWeakPointSummary
} from "../api";
import dashboardHeroAgent from "../assets/dashboard-hero-agent.png";
import { AUTH_CHANGED_EVENT, getUser, type AuthUser } from "../auth";

const user = ref<AuthUser | null>(getUser());
const summary = ref<DashboardSummary | null>(null);
const summaryLoading = ref(false);
const summaryError = ref("");
const displayName = computed(() => user.value?.display_name || user.value?.username || "武松");
const latestInterview = computed(() => summary.value?.latest_interview || null);
const latestReport = computed(() => summary.value?.latest_report || null);
const overallScore = computed(
  () => latestReport.value?.score ?? latestInterview.value?.score ?? null
);
const overallScoreText = computed(() => (overallScore.value === null ? 0 : overallScore.value));
const latestPosition = computed(() => latestInterview.value?.target_position || "暂无最近岗位");
const latestStatus = computed(() =>
  latestInterview.value
    ? `${statusText(latestInterview.value.status)} · ${formatDate(latestInterview.value.started_at || latestInterview.value.ended_at)}`
    : "开始一次模拟面试后，这里会显示最近进度"
);
const continueTarget = computed(() => {
  const interview = latestInterview.value;
  if (!interview) {
    return "/dashboard";
  }
  return interview.status === "finished"
    ? `/history/${interview.interview_id}`
    : `/interviews/multi/${interview.interview_id}`;
});
const continueActionText = computed(() => "继续上次面试");
const heroHint = computed(() =>
  !latestInterview.value
    ? "表现趋势与训练建议会同步到这里。"
    : latestInterview.value.status === "in_progress"
      ? "你的上次面试还在进行中，可以从当前轮次继续。"
      : "保持节奏，你的技术面表现正在稳步提升。"
);
const trendText = computed(() => {
  const delta = summary.value?.score_delta;
  if (typeof delta === "number") {
    return `较上次 ${delta > 0 ? "+" : ""}${delta}`;
  }
  return trendPoints.value.length ? "暂无上次对比" : "暂无趋势";
});
const trendArrow = computed(() => {
  const delta = summary.value?.score_delta;
  if (typeof delta !== "number" || delta === 0) {
    return "→";
  }
  return delta > 0 ? "↗" : "↘";
});
const memoryStatus = computed(() => {
  const status = summary.value?.memory_status;
  const count = summary.value?.candidate_memory_count ?? 0;
  if (status === "disabled") {
    return "已关闭";
  }
  if (status === "summarizing") {
    return "总结中";
  }
  if (status === "ready") {
    return count > 0 ? `已积累 ${count} 条` : "已积累";
  }
  if (status === "enabled") {
    return count > 0 ? `已启用 ${count} 条` : "已启用";
  }
  if (status === "failed") {
    return "待重试";
  }
  if (status === "unavailable") {
    return "需检查";
  }
  return summary.value?.personalized_feedback_used ? "已启用" : "待积累";
});
const reportTaskStatus = computed(() =>
  latestReport.value ? reportStatusText(latestReport.value.report_reliability_status) : "未生成"
);
const greetingText = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) {
    return "早上好";
  }
  if (hour < 18) {
    return "下午好";
  }
  return "晚上好";
});
const chartMarks = [100, 75, 50, 25, 0];
const trendPoints = computed(() => summary.value?.score_trend.map((point) => point.score) ?? []);
const abilities = computed(() => (summary.value?.abilities ?? []).map(toAbilityRow));
const weakPoints = computed(() => (summary.value?.weak_points ?? []).map(toWeakPointRow));
const selectedWeakPoint = ref<WeakPointRow | null>(null);
const roundMeta: Record<string, { name: string; color: string; tint: string; icon: string }> = {
  resume: { name: "简历面", color: "#5961ff", tint: "#eef1ff", icon: "▣" },
  technical: { name: "技术面", color: "#7a62ff", tint: "#f0edff", icon: "</>" },
  manager: { name: "主管面", color: "#ff8a00", tint: "#fff3e0", icon: "○" },
  hr: { name: "HR 面", color: "#f34f86", tint: "#ffedf4", icon: "HR" }
};
const weakMeta = [
  { color: "#5d73ff", tint: "#eef1ff", icon: "◇" },
  { color: "#8b5cf6", tint: "#f1ebff", icon: "▭" },
  { color: "#ff8a00", tint: "#fff3e0", icon: "?" }
];

type WeakPointRow = {
  title: string;
  text: string;
  summary: string;
  suggestion: string | null;
  severity: string;
  occurrence_count: number;
  evidence: string[];
  sources: DashboardWeakPointSource[];
  updated_at: string | null;
  color: string;
  tint: string;
  icon: string;
};

function refreshUser() {
  user.value = getUser();
  void loadDashboardSummary();
}

async function loadDashboardSummary() {
  summaryLoading.value = true;
  summaryError.value = "";
  try {
    summary.value = await getDashboardSummary();
  } catch (error) {
    summary.value = null;
    summaryError.value = error instanceof ApiError ? error.message : "工作台汇总加载失败。";
  } finally {
    summaryLoading.value = false;
  }
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    created: "已创建",
    in_progress: "进行中",
    finished: "已完成"
  };
  return map[status] || status;
}

function reportStatusText(status: string): string {
  const map: Record<string, string> = {
    normal: "已生成",
    reference_only: "仅供参考",
    unavailable: "不可用"
  };
  return map[status] || status;
}

function toAbilityRow(ability: DashboardAbilitySummary) {
  const meta = roundMeta[ability.round_type] || {
    name: ability.round_type,
    color: "#5961ff",
    tint: "#eef1ff",
    icon: "◎"
  };
  return {
    name: meta.name,
    value: ability.score ?? "-",
    progress: ability.score ?? 0,
    color: meta.color,
    tint: meta.tint,
    icon: meta.icon
  };
}

function toWeakPointRow(item: DashboardWeakPointSummary, index: number) {
  const meta = weakMeta[index % weakMeta.length];
  const fallbackSuggestion = item.suggestion || "查看报告后继续针对性练习";
  const summary = item.summary || fallbackSuggestion;
  return {
    title: item.title,
    text: summary,
    summary,
    suggestion: item.suggestion,
    severity: item.severity || "medium",
    occurrence_count: item.occurrence_count ?? 1,
    evidence: Array.isArray(item.evidence) ? item.evidence : [],
    sources: Array.isArray(item.sources) ? item.sources : [],
    updated_at: item.updated_at || null,
    color: meta.color,
    tint: meta.tint,
    icon: meta.icon
  };
}

function openWeakPointDetail(item: WeakPointRow) {
  selectedWeakPoint.value = item;
}

function closeWeakPointDetail() {
  selectedWeakPoint.value = null;
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    closeWeakPointDetail();
  }
}

function handleWindowFocus() {
  void loadDashboardSummary();
}

function handleVisibilityChange() {
  if (document.visibilityState === "visible") {
    void loadDashboardSummary();
  }
}

function severityText(severity: string): string {
  const map: Record<string, string> = {
    high: "高优先级",
    medium: "中优先级",
    low: "低优先级"
  };
  return map[severity] || severity;
}

function roundName(roundType: string): string {
  return roundMeta[roundType]?.name || roundType;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "暂无时间";
}

onMounted(() => {
  window.addEventListener(AUTH_CHANGED_EVENT, refreshUser);
  window.addEventListener("keydown", handleKeydown);
  window.addEventListener("focus", handleWindowFocus);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  void loadDashboardSummary();
});

onUnmounted(() => {
  window.removeEventListener(AUTH_CHANGED_EVENT, refreshUser);
  window.removeEventListener("keydown", handleKeydown);
  window.removeEventListener("focus", handleWindowFocus);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
});
</script>

<style scoped>
.dashboard {
  display: grid;
  gap: 30px;
  width: 100%;
  min-width: 0;
  max-width: min(1560px, 100%);
  margin: 0 auto;
  color: #080d31;
}

.dashboard-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.dashboard-header h1 {
  margin: 0;
  color: #080d31;
  font-size: 44px;
  font-weight: 950;
  line-height: 1.16;
}

.dashboard-header p {
  margin: 10px 0 0;
  color: #66728f;
  font-size: 21px;
  font-weight: 700;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(420px, 0.93fr);
  gap: 30px;
  min-width: 0;
}

.hero-card,
.score-card,
.module {
  min-width: 0;
  border: 1px solid rgb(207 216 235 / 78%);
  border-radius: 22px;
  background: rgb(255 255 255 / 78%);
  box-shadow: 0 28px 56px rgb(45 68 116 / 9%);
}

.hero-card {
  position: relative;
  min-height: 442px;
  overflow: hidden;
  padding: 54px 60px 36px;
  background:
    linear-gradient(
      90deg,
      rgb(238 243 255 / 92%) 0%,
      rgb(239 243 255 / 70%) 38%,
      rgb(255 255 255 / 8%) 100%
    ),
    #edf2ff;
}

.hero-agent-stage {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
}

.hero-visual {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center center;
  filter: saturate(1.04);
}

.hero-hair-layer {
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.hero-hair-sway {
  transform-box: fill-box;
  transform-origin: 72% 18%;
  animation: heroine-hair-sway 5.8s ease-in-out infinite;
  filter: saturate(1.06) drop-shadow(0 8px 18px rgb(56 43 94 / 8%));
  will-change: transform;
}

.hero-card::after {
  position: absolute;
  inset: 0;
  z-index: 1;
  background:
    linear-gradient(90deg, rgb(239 244 255 / 94%) 0%, rgb(239 244 255 / 74%) 36%, transparent 58%),
    radial-gradient(circle at 33% 17%, rgb(120 113 255 / 18%), transparent 28%);
  content: "";
}

.hero-copy,
.hero-actions,
.resume-strip {
  position: relative;
  z-index: 3;
}

.hero-copy h2 {
  max-width: 520px;
  margin: 0;
  color: #050a2f;
  font-size: 43px;
  font-weight: 950;
  line-height: 1.12;
}

.hero-copy h2 span {
  color: #5c61ff;
  font-size: 32px;
}

.hero-copy p {
  max-width: 390px;
  margin: 18px 0 0;
  color: #4e5b77;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.45;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 32px;
}

.primary-action,
.secondary-action {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  min-width: 204px;
  min-height: 62px;
  padding: 0 26px;
  border-radius: 14px;
  font-size: 20px;
  font-weight: 950;
  line-height: 1;
}

.primary-action {
  border: 0;
  background: linear-gradient(135deg, #5961ff 0%, #6d58ff 100%);
  box-shadow: 0 18px 34px rgb(89 97 255 / 26%);
  color: #fff;
}

.secondary-action {
  border: 1px solid #6670ff;
  background: rgb(255 255 255 / 76%);
  color: #5961ff;
}

.resume-strip {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) 20px;
  gap: 20px;
  align-items: center;
  width: min(448px, 100%);
  min-height: 126px;
  margin-top: 38px;
  padding: 20px 24px;
  border-radius: 20px;
  background: rgb(255 255 255 / 84%);
  box-shadow: 0 18px 40px rgb(45 68 116 / 10%);
}

.resume-icon {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  border-radius: 999px;
  background: #eef1ff;
  color: #5961ff;
}

.resume-icon svg,
.score-title svg {
  width: 34px;
  height: 34px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.resume-strip small,
.resume-strip em {
  display: block;
  color: #66728f;
  font-style: normal;
  font-weight: 700;
}

.resume-strip small {
  font-size: 16px;
}

.resume-strip strong {
  display: block;
  overflow: hidden;
  margin: 3px 0;
  color: #10163d;
  font-size: 25px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-strip em {
  font-size: 16px;
}

.resume-strip b {
  color: #7b87a8;
  font-size: 34px;
  font-weight: 500;
}

.score-card {
  display: grid;
  align-content: start;
  min-height: 442px;
  overflow: hidden;
  padding: 40px 36px 36px;
}

.score-title,
.module-title {
  display: flex;
  align-items: center;
}

.score-title {
  gap: 18px;
}

.score-title span,
.module-title span {
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #eef1ff;
  color: #5961ff;
  font-weight: 950;
}

.score-title span {
  width: 54px;
  height: 54px;
}

.score-title h2,
.module-heading h2 {
  margin: 0;
  color: #0a1038;
  font-size: 26px;
  font-weight: 950;
}

.score-body {
  display: grid;
  grid-template-columns: minmax(128px, 0.7fr) minmax(0, 1fr);
  gap: clamp(18px, 2vw, 30px);
  align-items: end;
  margin-top: 32px;
  min-width: 0;
}

.score-copy,
.trend-chart {
  min-width: 0;
}

.score-copy strong {
  color: #03082e;
  font-size: clamp(60px, 4.5vw, 82px);
  font-weight: 950;
  line-height: 0.95;
}

.score-copy span {
  color: #66728f;
  font-size: 25px;
  font-weight: 800;
}

.score-copy em {
  display: block;
  width: fit-content;
  margin-top: 24px;
  padding: 10px 20px;
  border-radius: 999px;
  background: #dff8e9;
  color: #09924d;
  font-size: 19px;
  font-style: normal;
  font-weight: 950;
}

.trend-chart {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  grid-template-rows: repeat(5, 1fr);
  align-items: center;
  min-height: 292px;
  color: #647094;
  font-size: 18px;
  font-weight: 700;
}

.trend-chart span {
  grid-column: 1;
}

.chart-grid {
  grid-row: 1 / -1;
  grid-column: 2;
  display: grid;
  grid-template-columns: repeat(8, minmax(8px, 1fr));
  gap: clamp(8px, 1vw, 18px);
  align-items: end;
  height: 100%;
  min-width: 0;
  overflow: hidden;
  padding: 8px 0 2px;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent calc(25% - 1px),
    #dce3f2 calc(25% - 1px),
    #dce3f2 25%
  );
}

.chart-grid i {
  display: block;
  min-height: 18px;
  max-height: 100%;
  border-radius: 9px 9px 2px 2px;
  background: linear-gradient(180deg, #6ea3ff 0%, #7c55ff 100%);
  box-shadow: 0 12px 22px rgb(99 105 255 / 18%);
}

.chart-empty {
  grid-row: 1 / -1;
  grid-column: 2;
  display: grid;
  place-items: center;
  min-height: 292px;
  border: 1px dashed #cbd5e8;
  border-radius: 14px;
  color: #66728f;
  font-size: 18px;
  font-weight: 800;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(0, 1.03fr) minmax(0, 0.96fr);
  gap: 30px;
  min-width: 0;
}

.module {
  min-height: 320px;
  padding: 28px 36px 30px;
}

.module-heading {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 26px;
}

.module-title {
  gap: 16px;
}

.module-title span {
  width: 46px;
  height: 46px;
  font-size: 24px;
}

.module-heading small {
  color: #6f7897;
  font-size: 17px;
  font-weight: 800;
}

.ability-list {
  display: grid;
  gap: 18px;
}

.module-empty {
  display: grid;
  place-items: center;
  min-height: 188px;
  margin: 0;
  border: 1px dashed #d6deeb;
  border-radius: 14px;
  color: #66728f;
  font-size: 18px;
  font-weight: 800;
}

.ability-row {
  display: grid;
  grid-template-columns: 46px 90px minmax(120px, 1fr) 34px;
  gap: 18px;
  align-items: center;
}

.ability-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: var(--ability-tint);
  color: var(--ability-color);
  font-size: 17px;
  font-weight: 950;
}

.ability-name {
  color: #53607d;
  font-size: 20px;
  font-weight: 800;
}

.ability-track {
  height: 15px;
  overflow: hidden;
  border-radius: 999px;
  background: #eef1f8;
}

.ability-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--ability-color);
  box-shadow: 0 10px 20px rgb(89 97 255 / 18%);
}

.ability-row strong {
  color: var(--ability-color);
  font-size: 20px;
  font-weight: 950;
  text-align: right;
}

.weak-list {
  display: grid;
  gap: 16px;
}

.weak-row {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  width: 100%;
  min-height: 68px;
  padding: 0 20px;
  border: 0;
  border-radius: 16px;
  background: linear-gradient(180deg, rgb(250 252 255 / 92%), rgb(244 247 252 / 92%));
  cursor: pointer;
  text-align: left;
}

.weak-row:hover,
.weak-row:focus-visible {
  box-shadow: 0 16px 28px rgb(60 83 142 / 12%);
  outline: 2px solid var(--weak-color);
  outline-offset: 2px;
}

.weak-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: var(--weak-tint);
  color: var(--weak-color);
  font-size: 22px;
  font-weight: 950;
}

.weak-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.weak-copy strong {
  color: #10163d;
  font-size: 20px;
  font-weight: 950;
}

.weak-copy em {
  overflow: hidden;
  color: #66728f;
  font-size: 17px;
  font-style: normal;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weak-row b {
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--weak-tint);
  color: var(--weak-color);
  font-size: 14px;
  font-weight: 950;
  white-space: nowrap;
}

.weak-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(8 13 49 / 46%);
}

.weak-modal {
  width: min(760px, 100%);
  max-height: min(760px, calc(100vh - 48px));
  overflow: auto;
  padding: 30px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 30px 80px rgb(8 13 49 / 22%);
}

.weak-modal header {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  justify-content: space-between;
}

.weak-modal small {
  color: #5961ff;
  font-size: 15px;
  font-weight: 950;
}

.weak-modal h2,
.weak-modal h3,
.weak-modal p {
  margin: 0;
}

.weak-modal h2 {
  margin-top: 6px;
  color: #080d31;
  font-size: 28px;
  font-weight: 950;
  line-height: 1.25;
}

.weak-modal header button {
  flex: 0 0 auto;
  min-height: 42px;
  padding: 0 18px;
  border: 1px solid #cbd5e8;
  border-radius: 12px;
  background: #fff;
  color: #53607d;
  font-size: 16px;
  font-weight: 900;
  cursor: pointer;
}

.weak-modal-summary {
  margin-top: 18px;
  color: #53607d;
  font-size: 18px;
  font-weight: 800;
  line-height: 1.6;
}

.weak-modal-section {
  display: grid;
  gap: 12px;
  margin-top: 24px;
}

.weak-modal-section h3 {
  color: #10163d;
  font-size: 18px;
  font-weight: 950;
}

.weak-modal-section p,
.weak-modal-section li {
  color: #53607d;
  font-size: 16px;
  font-weight: 750;
  line-height: 1.55;
}

.weak-modal-section ul {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.weak-source-list li {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) auto auto minmax(150px, auto);
  gap: 14px;
  align-items: center;
  min-height: 52px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f7f9fd;
}

.weak-source-list a {
  overflow: hidden;
  color: #5961ff;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.weak-source-list span,
.weak-source-list time {
  color: #66728f;
}

.weak-source-list strong {
  color: #10163d;
}

.status-module ul {
  display: grid;
  gap: 0;
  padding: 0;
  margin: 0;
  list-style: none;
}

.status-module li {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  gap: 22px;
  align-items: center;
  min-height: 70px;
  border-bottom: 1px solid #e2e7f1;
  color: #10163d;
  font-size: 20px;
  font-weight: 800;
}

.status-module li:last-child {
  border-bottom: 0;
}

.status-module i {
  width: 18px;
  height: 18px;
  border-radius: 999px;
}

.status-module .ok {
  background: #20b76a;
}

.status-module .info {
  background: #5183ff;
}

.status-module strong {
  color: #66728f;
  font-size: 18px;
  font-weight: 800;
}

.status-detail-link {
  color: #5961ff;
  font-size: 18px;
  font-weight: 950;
}

.status-detail-link:hover {
  color: #1f64bf;
}

@media (max-width: 1320px) {
  .hero-grid,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .dashboard {
    gap: 20px;
  }

  .dashboard-header h1 {
    font-size: 30px;
  }

  .dashboard-header p,
  .hero-copy p {
    font-size: 16px;
  }

  .hero-card,
  .score-card,
  .module {
    border-radius: 18px;
  }

  .hero-card {
    min-height: 520px;
    padding: 30px 22px 24px;
  }

  .hero-visual {
    object-position: center center;
  }

  .hero-card::after {
    background:
      linear-gradient(
        180deg,
        rgb(239 244 255 / 96%) 0%,
        rgb(239 244 255 / 84%) 48%,
        transparent 100%
      ),
      radial-gradient(circle at 32% 15%, rgb(120 113 255 / 18%), transparent 30%);
  }

  .hero-copy h2 {
    font-size: 30px;
  }

  .hero-actions,
  .primary-action,
  .secondary-action {
    width: 100%;
  }

  .resume-strip,
  .score-body,
  .ability-row,
  .weak-row {
    grid-template-columns: 1fr;
  }

  .score-card,
  .module {
    padding: 24px 20px;
  }

  .score-body {
    gap: 22px;
  }

  .trend-chart {
    min-height: 220px;
  }

  .chart-grid {
    gap: 12px;
  }

  .weak-copy em {
    white-space: normal;
  }

  .weak-row b {
    width: fit-content;
  }

  .weak-modal {
    padding: 24px 18px;
  }

  .weak-modal header,
  .weak-source-list li {
    grid-template-columns: 1fr;
  }

  .weak-modal header {
    display: grid;
  }

  .status-module li {
    grid-template-columns: 18px minmax(0, 1fr);
  }

  .status-module strong {
    grid-column: 2;
  }
}

@keyframes heroine-hair-sway {
  0%,
  100% {
    transform: translate3d(0, 0, 0) rotate(0deg) skewX(0deg);
  }

  42% {
    transform: translate3d(-3px, 2px, 0) rotate(-0.35deg) skewX(-0.7deg);
  }

  72% {
    transform: translate3d(2px, -1px, 0) rotate(0.25deg) skewX(0.45deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-hair-sway {
    animation: none;
  }
}
</style>
