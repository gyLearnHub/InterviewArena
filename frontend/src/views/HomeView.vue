<template>
  <section class="dashboard">
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
            <span class="weak-copy">
              <strong>{{ item.title }}</strong>
              <em>{{ item.text }}</em>
            </span>
          </button>
        </div>
        <p v-else class="module-empty">暂无薄弱项</p>
      </section>

      <section class="module review-module">
        <div class="module-heading">
          <div class="module-title">
            <span aria-hidden="true">R</span>
            <h2>复盘收藏</h2>
          </div>
          <RouterLink class="review-more-link" to="/review-bookmarks">
            {{ reviewBookmarksLoading ? "同步中" : "查看全部" }}
          </RouterLink>
        </div>
        <div v-if="reviewBookmarkRows.length" class="review-list">
          <article v-for="item in reviewBookmarkRows" :key="item.id" class="review-row">
            <div>
              <small>{{ item.roundLabel }} · {{ item.score }}</small>
              <strong>{{ item.title }}</strong>
              <p>{{ item.issue }}</p>
              <em>{{ item.source }} · {{ formatDate(item.updatedAt) }}</em>
            </div>
            <button
              type="button"
              :disabled="
                activeReviewBookmarkId !== null ||
                (!item.practiceInterviewId && !item.sourceInterviewId)
              "
              @click="startReviewPractice(item)"
            >
              {{
                activeReviewBookmarkId === item.id
                  ? "创建中"
                  : item.practiceInterviewId
                    ? "继续练"
                    : item.sourceInterviewId
                      ? "专项练"
                      : "仅复盘"
              }}
            </button>
          </article>
        </div>
        <p v-else class="module-empty">暂无复盘收藏</p>
        <p v-if="reviewBookmarkError" class="review-error">{{ reviewBookmarkError }}</p>
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
              {{ selectedWeakPoint.occurrence_count }} 次出现 ·
              {{ practiceStatusText(selectedWeakPoint.practice_status) }}</small
            >
            <h2 id="weak-modal-title">{{ selectedWeakPoint.title }}</h2>
          </div>
          <button type="button" @click="closeWeakPointDetail">关闭</button>
        </header>

        <p class="weak-modal-summary">{{ selectedWeakPoint.summary || selectedWeakPoint.text }}</p>

        <div class="weak-modal-section">
          <h3>训练进度</h3>
          <p class="weak-practice-line">
            <span>{{ practiceStatusText(selectedWeakPoint.practice_status) }}</span>
            <span v-if="selectedWeakPoint.practice_count > 0">
              已完成 {{ selectedWeakPoint.practice_count }} 次专项
            </span>
            <span v-if="selectedWeakPoint.practice_score !== null">
              最近专项 {{ selectedWeakPoint.practice_score }} 分
            </span>
            <span v-if="selectedWeakPoint.last_practiced_at">
              {{ formatDate(selectedWeakPoint.last_practiced_at) }}
            </span>
          </p>
        </div>

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
import { useRouter } from "vue-router";

import {
  ApiError,
  getDashboardSummary,
  listReviewBookmarks,
  startReviewBookmarkPractice,
  type DashboardAbilitySummary,
  type DashboardSummary,
  type DashboardWeakPointSource,
  type DashboardWeakPointSummary,
  type ReviewBookmarkItem
} from "../api";
import dashboardHeroAgent from "../assets/dashboard-hero-agent.webp";
import { AUTH_CHANGED_EVENT, getUser, type AuthUser } from "../auth";

const user = ref<AuthUser | null>(getUser());
const router = useRouter();
const summary = ref<DashboardSummary | null>(null);
const summaryLoading = ref(false);
const summaryError = ref("");
const reviewBookmarks = ref<ReviewBookmarkItem[]>([]);
const reviewBookmarksLoading = ref(false);
const reviewBookmarkError = ref("");
const activeReviewBookmarkId = ref<number | null>(null);
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
const reviewBookmarkRows = computed(() => reviewBookmarks.value.slice(0, 4).map(toReviewRow));
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
  practice_status: string;
  practice_score: number | null;
  last_practiced_at: string | null;
  practice_count: number;
  evidence: string[];
  sources: DashboardWeakPointSource[];
  updated_at: string | null;
  color: string;
  tint: string;
  icon: string;
};

type ReviewBookmarkRow = {
  id: number;
  title: string;
  issue: string;
  source: string;
  score: string;
  roundLabel: string;
  sourceInterviewId: number | null;
  practiceInterviewId: number | null;
  updatedAt: string | null;
};

function refreshUser() {
  user.value = getUser();
  void loadDashboardSummary();
  void loadReviewBookmarks();
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

async function loadReviewBookmarks() {
  reviewBookmarksLoading.value = true;
  reviewBookmarkError.value = "";
  try {
    reviewBookmarks.value = await listReviewBookmarks({ limit: 4 });
  } catch (error) {
    reviewBookmarks.value = [];
    reviewBookmarkError.value = error instanceof ApiError ? error.message : "复盘收藏加载失败。";
  } finally {
    reviewBookmarksLoading.value = false;
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
    practice_status: item.practice_status || "not_started",
    practice_score: item.practice_score ?? null,
    last_practiced_at: item.last_practiced_at || null,
    practice_count: item.practice_count ?? 0,
    evidence: Array.isArray(item.evidence) ? item.evidence : [],
    sources: Array.isArray(item.sources) ? item.sources : [],
    updated_at: item.updated_at || null,
    color: meta.color,
    tint: meta.tint,
    icon: meta.icon
  };
}

function toReviewRow(item: ReviewBookmarkItem): ReviewBookmarkRow {
  return {
    id: item.id,
    title: item.title,
    issue: item.suggestion || item.issue,
    source: item.target_position,
    score: typeof item.source_score === "number" ? `${item.source_score} 分` : "结构复盘",
    roundLabel: item.round_type ? roundName(String(item.round_type)) : "综合复盘",
    sourceInterviewId: item.source_interview_id,
    practiceInterviewId: item.practice_interview_id || null,
    updatedAt: item.updated_at || null
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
  void loadReviewBookmarks();
}

function handleVisibilityChange() {
  if (document.visibilityState === "visible") {
    void loadDashboardSummary();
    void loadReviewBookmarks();
  }
}

async function startReviewPractice(item: ReviewBookmarkRow) {
  if (activeReviewBookmarkId.value !== null) {
    return;
  }
  if (item.practiceInterviewId) {
    router.push({ name: "multi-round-interview", params: { id: item.practiceInterviewId } });
    return;
  }
  if (!item.sourceInterviewId) {
    reviewBookmarkError.value = "原面试已删除，收藏内容仍可复盘，但不能新建专项练习。";
    return;
  }
  activeReviewBookmarkId.value = item.id;
  reviewBookmarkError.value = "";
  try {
    const interview = await startReviewBookmarkPractice(item.id);
    await router.push({ name: "multi-round-interview", params: { id: interview.id } });
  } catch (error) {
    reviewBookmarkError.value =
      error instanceof ApiError ? error.message : "专项练习创建失败，请稍后重试。";
  } finally {
    activeReviewBookmarkId.value = null;
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

function practiceStatusText(status: string): string {
  const map: Record<string, string> = {
    not_started: "待练",
    pending: "待练",
    practiced: "已练",
    improving: "改善中",
    needs_work: "仍需加强"
  };
  return map[status] || "待练";
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
  void loadReviewBookmarks();
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
  gap: 24px;
  width: 100%;
  min-width: 0;
  max-width: min(1560px, 100%);
  margin: 0 auto;
  color: #080d31;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.32fr) minmax(360px, 0.8fr);
  gap: 24px;
  min-width: 0;
}

.hero-card,
.score-card,
.module {
  min-width: 0;
  border: 1px solid rgb(207 216 235 / 78%);
  border-radius: 18px;
  background: rgb(255 255 255 / 78%);
  box-shadow: 0 18px 40px rgb(45 68 116 / 8%);
}

.hero-card {
  position: relative;
  min-height: 368px;
  overflow: hidden;
  padding: 38px 42px 30px;
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
  max-width: 480px;
  margin: 0;
  color: #050a2f;
  font-size: clamp(32px, 3vw, 38px);
  font-weight: 950;
  line-height: 1.12;
}

.hero-copy h2 span {
  color: #5c61ff;
  font-size: 26px;
}

.hero-copy p {
  max-width: 360px;
  margin: 12px 0 0;
  color: #4e5b77;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.45;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 24px;
}

.primary-action,
.secondary-action {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  min-width: 168px;
  min-height: 50px;
  padding: 0 20px;
  border-radius: 12px;
  font-size: 16px;
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
  grid-template-columns: 56px minmax(0, 1fr) 18px;
  gap: 14px;
  align-items: center;
  width: min(410px, 100%);
  min-height: 94px;
  margin-top: 24px;
  padding: 14px 18px;
  border-radius: 14px;
  background: rgb(255 255 255 / 84%);
  box-shadow: 0 12px 28px rgb(45 68 116 / 9%);
}

.resume-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 999px;
  background: #eef1ff;
  color: #5961ff;
}

.resume-icon svg,
.score-title svg {
  width: 28px;
  height: 28px;
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
  font-size: 13px;
}

.resume-strip strong {
  display: block;
  overflow: hidden;
  margin: 3px 0;
  color: #10163d;
  font-size: 20px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-strip em {
  font-size: 13px;
}

.resume-strip b {
  color: #7b87a8;
  font-size: 28px;
  font-weight: 500;
}

.score-card {
  display: grid;
  align-content: start;
  min-height: 368px;
  overflow: hidden;
  padding: 30px 28px 26px;
}

.score-title,
.module-title {
  display: flex;
  align-items: center;
}

.score-title {
  gap: 14px;
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
  width: 46px;
  height: 46px;
}

.score-title h2,
.module-heading h2 {
  margin: 0;
  color: #0a1038;
  font-size: 22px;
  font-weight: 950;
}

.score-body {
  display: grid;
  grid-template-columns: minmax(128px, 0.7fr) minmax(0, 1fr);
  gap: clamp(14px, 1.5vw, 24px);
  align-items: end;
  margin-top: 24px;
  min-width: 0;
}

.score-copy,
.trend-chart {
  min-width: 0;
}

.score-copy strong {
  color: #03082e;
  font-size: clamp(52px, 4vw, 68px);
  font-weight: 950;
  line-height: 0.95;
}

.score-copy span {
  color: #66728f;
  font-size: 20px;
  font-weight: 800;
}

.score-copy em {
  display: block;
  width: fit-content;
  margin-top: 18px;
  padding: 7px 14px;
  border-radius: 999px;
  background: #dff8e9;
  color: #09924d;
  font-size: 15px;
  font-style: normal;
  font-weight: 950;
}

.trend-chart {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  grid-template-rows: repeat(5, 1fr);
  align-items: center;
  min-height: 226px;
  color: #647094;
  font-size: 14px;
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
  min-height: 226px;
  border: 1px dashed #cbd5e8;
  border-radius: 14px;
  color: #66728f;
  font-size: 15px;
  font-weight: 800;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(0, 1.03fr) minmax(0, 0.96fr);
  gap: 24px;
  align-items: stretch;
  min-width: 0;
}

.module {
  min-height: 0;
  padding: 24px;
}

.module-heading {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.module-title {
  gap: 12px;
}

.module-title span {
  width: 40px;
  height: 40px;
  font-size: 20px;
}

.module-heading small {
  color: #6f7897;
  font-size: 14px;
  font-weight: 800;
}

.ability-list {
  display: grid;
  gap: 14px;
}

.module-empty {
  display: grid;
  place-items: center;
  min-height: 148px;
  margin: 0;
  border: 1px dashed #d6deeb;
  border-radius: 14px;
  color: #66728f;
  font-size: 15px;
  font-weight: 800;
}

.ability-row {
  display: grid;
  grid-template-columns: 40px 76px minmax(100px, 1fr) 32px;
  gap: 12px;
  align-items: center;
}

.ability-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--ability-tint);
  color: var(--ability-color);
  font-size: 15px;
  font-weight: 950;
}

.ability-name {
  color: #53607d;
  font-size: 16px;
  font-weight: 800;
}

.ability-track {
  height: 12px;
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
  font-size: 18px;
  font-weight: 950;
  text-align: right;
}

.ability-module {
  min-height: 318px;
}

.review-module .module-empty {
  min-height: 178px;
}

.weak-list {
  display: grid;
  gap: 12px;
}

.weak-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  width: 100%;
  min-height: 74px;
  padding: 14px 18px;
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

.weak-copy {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.weak-copy strong {
  display: -webkit-box;
  overflow: hidden;
  color: #10163d;
  font-size: 18px;
  font-weight: 950;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.weak-copy em {
  display: -webkit-box;
  overflow: hidden;
  color: #66728f;
  font-size: 15px;
  font-style: normal;
  font-weight: 700;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.review-list {
  display: grid;
  gap: 14px;
}

.review-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  min-height: 92px;
  padding: 16px 18px;
  border: 1px solid #e1e7f3;
  border-radius: 16px;
  background: linear-gradient(180deg, rgb(255 255 255 / 92%), rgb(246 249 255 / 92%));
}

.review-row div {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.review-row small {
  color: #5961ff;
  font-size: 13px;
  font-weight: 950;
}

.review-row strong {
  overflow: hidden;
  color: #10163d;
  font-size: 18px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-row p {
  display: -webkit-box;
  overflow: hidden;
  margin: 0;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: #66728f;
  font-size: 15px;
  font-weight: 750;
  line-height: 1.45;
}

.review-row em {
  overflow: hidden;
  color: #8a94ad;
  font-size: 13px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-row button {
  min-width: 86px;
  min-height: 40px;
  border: 0;
  border-radius: 12px;
  background: #10163d;
  color: #fff;
  font-size: 15px;
  font-weight: 950;
  cursor: pointer;
}

.review-row button:hover,
.review-row button:focus-visible {
  background: #5961ff;
  outline: 2px solid #c8d3ff;
  outline-offset: 2px;
}

.review-row button:disabled {
  cursor: not-allowed;
  opacity: 0.66;
}

.review-error {
  margin: 14px 0 0;
  color: #c0364a;
  font-size: 14px;
  font-weight: 800;
}

.review-more-link {
  color: #5961ff;
  font-size: 15px;
  font-weight: 950;
  text-decoration: none;
}

.review-more-link:hover,
.review-more-link:focus-visible {
  color: #1f64bf;
  outline: none;
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

.weak-practice-line {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.weak-practice-line span {
  padding-right: 10px;
  border-right: 1px solid #d8e0ef;
}

.weak-practice-line span:last-child {
  padding-right: 0;
  border-right: 0;
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

@media (max-width: 1480px) {
  .dashboard-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .review-module {
    grid-column: 1 / -1;
  }
}

@media (max-width: 1100px) {
  .hero-grid,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .review-module {
    grid-column: auto;
  }
}

@media (max-width: 760px) {
  .dashboard {
    gap: 20px;
  }

  .hero-copy p {
    font-size: 16px;
  }

  .hero-card,
  .score-card,
  .module {
    border-radius: 18px;
  }

  .hero-card {
    min-height: 470px;
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
  .weak-row,
  .review-row {
    grid-template-columns: 1fr;
  }

  .resume-strip {
    grid-template-columns: 56px minmax(0, 1fr);
  }

  .resume-strip b {
    display: none;
  }

  .ability-row {
    grid-template-columns: 40px minmax(0, 1fr) 32px;
    gap: 12px;
  }

  .ability-track {
    grid-column: 2 / -1;
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
