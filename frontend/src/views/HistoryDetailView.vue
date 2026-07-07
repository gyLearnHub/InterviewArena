<template>
  <section class="detail-workspace">
    <header class="detail-heading">
      <div>
        <p class="detail-breadcrumb">
          <RouterLink to="/history">历史记录</RouterLink><span>/</span>面试详情
        </p>
        <h1>面试详情 <i aria-hidden="true">✦</i></h1>
      </div>
      <div class="header-actions">
        <RouterLink class="detail-button" to="/history"
          ><span aria-hidden="true">←</span> 返回历史</RouterLink
        >
      </div>
    </header>

    <p v-if="message" class="message" :class="{ error: hasError }">{{ message }}</p>

    <div v-if="detail" class="detail-page">
      <section class="overview-panel" aria-label="面试概览">
        <div class="overview-art" aria-hidden="true">
          <img :src="historyHeroBoy" alt="" />
          <span class="art-glow"></span>
          <span class="art-spark spark-one">✦</span>
          <span class="art-spark spark-two">✦</span>
        </div>
        <div class="position-copy">
          <span>面试岗位 <i aria-hidden="true">✦</i></span>
          <h2>{{ detail.target_position || "目标岗位" }}</h2>
          <p>代码筑基，系统赋能，创造无限可能 <b aria-hidden="true">✦</b></p>
        </div>
        <dl class="summary-metrics">
          <div class="score-metric">
            <dt>最终综合评分</dt>
            <dd>
              <span class="metric-icon trophy">♛</span
              ><strong class="final-score-value">{{ finalScoreNumber }}<em>/100</em></strong>
            </dd>
            <small>综合评分</small>
          </div>
          <div>
            <dt>状态</dt>
            <dd>
              <span class="metric-icon success">✓</span
              ><strong>{{ statusText(detail.overall_status || detail.status) }}</strong>
            </dd>
            <small>面试已完成</small>
          </div>
          <div>
            <dt>开始时间</dt>
            <dd>
              <span class="metric-icon">◫</span
              ><strong>{{ formatDatePart(detail.started_at) }}</strong>
            </dd>
            <small>{{ formatTimePart(detail.started_at) }}</small>
          </div>
          <div>
            <dt>结束时间</dt>
            <dd>
              <span class="metric-icon violet">◫</span
              ><strong>{{ formatDatePart(detail.ended_at) }}</strong>
            </dd>
            <small>{{ formatTimePart(detail.ended_at) }}</small>
          </div>
          <div>
            <dt>简历编号</dt>
            <dd>
              <span class="metric-icon document">▤</span><strong>#{{ detail.resume.id }}</strong>
            </dd>
            <small>本次投递简历</small>
          </div>
        </dl>
      </section>

      <section
        v-if="reportReliabilityNotice"
        class="reliability-alert"
        :class="reportReliabilityNotice.tone"
      >
        <span class="notice-icon" aria-hidden="true">✦</span>
        <div>
          <strong>{{ reportReliabilityNotice.title }}</strong>
          <p>{{ reportReliabilityNotice.text }}</p>
        </div>
        <div class="notice-character" aria-hidden="true">
          <img :src="historyNoticeGirl" alt="" />
        </div>
      </section>

      <section v-if="reportQuality" class="report-quality-panel" aria-label="报告可信度与得分依据">
        <header class="quality-heading">
          <div>
            <span>报告可信度</span>
            <h2>证据覆盖与得分依据</h2>
          </div>
          <strong>{{ reportQuality.score_coverage_percent }}%</strong>
        </header>
        <div class="quality-metrics">
          <article v-for="item in qualityMetrics" :key="item.label">
            <small>{{ item.label }}</small>
            <b>{{ item.value }}</b>
            <span>{{ item.note }}</span>
          </article>
        </div>
        <div class="quality-body">
          <section>
            <h3>可信度原因</h3>
            <ul>
              <li v-for="reason in reportQuality.reliability_reasons" :key="reason">
                {{ reason }}
              </li>
            </ul>
          </section>
          <section>
            <h3>轮次得分来源</h3>
            <div class="score-source-list">
              <article v-for="item in reportQuality.score_sources" :key="item.round_type">
                <strong>{{ roundLabel(item.round_type) }}</strong>
                <span>{{ scoreSourceText(item.source) }}</span>
                <b>{{ item.score === null ? "-" : formatScore(item.score) }} 分</b>
                <small
                  >{{ item.evaluated_question_count }}/{{
                    item.answered_question_count
                  }}
                  题已评分</small
                >
              </article>
            </div>
          </section>
        </div>
      </section>

      <section class="round-score-grid" aria-label="四轮评分">
        <article
          v-for="round in displayRounds"
          :key="round.type"
          class="round-score-card"
          :class="round.type"
        >
          <div class="round-avatar"><img :src="round.image" alt="" /></div>
          <div class="round-card-copy">
            <strong>{{ roundLabel(round.type) }}</strong>
            <p>
              <b>{{ round.scoreNumber }}</b
              ><span>分</span>
            </p>
            <small>{{ scoreSourceText(round.scoreSource) }}</small>
            <div class="score-track"><i :style="{ width: `${round.progress}%` }"></i></div>
          </div>
          <span class="round-watermark" aria-hidden="true">{{ round.icon }}</span>
        </article>
      </section>

      <section class="visual-grid" aria-label="能力画像和趋势">
        <article class="chart-card radar-card">
          <h2><span aria-hidden="true">◉</span> 能力画像</h2>
          <div class="radar-wrap">
            <svg viewBox="0 0 360 250" role="img" aria-label="五维能力雷达图">
              <g class="radar-guides">
                <polygon
                  v-for="level in [1, 0.75, 0.5, 0.25]"
                  :key="level"
                  :points="radarGuide(level)"
                />
                <line
                  v-for="point in radarOuterPoints"
                  :key="`${point.x}-${point.y}`"
                  x1="180"
                  y1="126"
                  :x2="point.x"
                  :y2="point.y"
                />
              </g>
              <polygon class="radar-fill" :points="radarDataPoints" />
              <circle
                v-for="point in radarValuePoints"
                :key="`dot-${point.x}-${point.y}`"
                :cx="point.x"
                :cy="point.y"
                r="4"
              />
            </svg>
            <span
              v-for="item in abilityLabels"
              :key="item.label"
              class="radar-label"
              :class="item.position"
            >
              {{ item.label }} <b>{{ item.value }}</b>
            </span>
          </div>
          <img class="radar-mascot" :src="historyChartMascot" alt="" aria-hidden="true" />
        </article>

        <article class="chart-card trend-card">
          <div class="chart-title-row">
            <h2><span aria-hidden="true">▥</span> 近期表现趋势</h2>
            <span>近 {{ trendValues.length }} 次面试⌄</span>
          </div>
          <div class="trend-wrap">
            <svg viewBox="0 0 640 238" role="img" aria-label="近期面试综合评分趋势">
              <defs>
                <linearGradient id="trend-area" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stop-color="#8b5cf6" stop-opacity=".26" />
                  <stop offset="1" stop-color="#8b5cf6" stop-opacity="0" />
                </linearGradient>
              </defs>
              <g class="trend-grid">
                <line
                  v-for="tick in trendTicks"
                  :key="tick.value"
                  x1="46"
                  x2="620"
                  :y1="tick.y"
                  :y2="tick.y"
                />
                <text
                  v-for="tick in trendTicks"
                  :key="`label-${tick.value}`"
                  x="12"
                  :y="tick.y + 4"
                >
                  {{ tick.value }}
                </text>
              </g>
              <polygon v-if="trendValues.length" class="trend-area" :points="trendAreaPoints" />
              <polyline v-if="trendValues.length" class="trend-line" :points="trendLinePoints" />
              <g v-for="point in trendChartPoints" :key="`trend-${point.x}`" class="trend-point">
                <circle :cx="point.x" :cy="point.y" r="5" />
                <text :x="point.x" :y="point.y - 14">{{ point.value.toFixed(1) }}</text>
                <text class="x-label" :x="point.x" y="230">第 {{ point.index + 1 }} 次</text>
              </g>
              <g v-if="lastTrendPoint" class="trend-current">
                <line :x1="lastTrendPoint.x" :x2="lastTrendPoint.x" y1="42" y2="206" />
                <rect
                  :x="lastTrendPoint.x - 28"
                  :y="lastTrendPoint.y - 42"
                  width="56"
                  height="26"
                  rx="12"
                />
                <text :x="lastTrendPoint.x" :y="lastTrendPoint.y - 24">
                  ★ {{ lastTrendPoint.value.toFixed(1) }}
                </text>
              </g>
            </svg>
            <img class="trend-mascot" :src="technicalInterviewer" alt="" aria-hidden="true" />
          </div>
        </article>
      </section>

      <section
        v-if="detail.feedback_report"
        class="report-detail-section"
        aria-label="面试报告详情"
      >
        <section class="report-insights" aria-label="综合结论">
          <article
            v-if="detail.feedback_report.recommendation || detail.feedback_report.final_conclusion"
            class="report-info-card conclusion-card"
          >
            <div class="report-card-heading">
              <span>✦</span>
              <div>
                <small>综合结论</small>
                <h2>录用建议</h2>
              </div>
            </div>
            <p>
              {{
                detail.feedback_report.final_conclusion ||
                detail.feedback_report.recommendation ||
                "暂无建议"
              }}
            </p>
            <div class="conclusion-meta">
              <span v-if="detail.feedback_report.confidence"
                >置信度 · {{ confidenceText(detail.feedback_report.confidence) }}</span
              >
              <span v-if="detail.feedback_report.job_match">{{
                detail.feedback_report.job_match
              }}</span>
            </div>
          </article>

          <article
            v-if="detail.feedback_report.ability_analysis?.length"
            class="report-info-card analysis-card"
          >
            <div class="report-card-heading">
              <span>◇</span>
              <div>
                <small>能力拆解</small>
                <h2>能力分析</h2>
              </div>
            </div>
            <ul>
              <li v-for="item in detail.feedback_report.ability_analysis" :key="item">
                {{ item }}
              </li>
            </ul>
          </article>
        </section>

        <section class="growth-grid" aria-label="优势与成长建议">
          <article class="growth-card strengths">
            <div class="growth-title">
              <span>✦</span>
              <h2>主要优势</h2>
            </div>
            <ul v-if="detail.feedback_report.strengths?.length">
              <li v-for="item in detail.feedback_report.strengths" :key="item">{{ item }}</li>
            </ul>
            <p v-else>报告中暂未返回优势项。</p>
          </article>
          <article class="growth-card weaknesses">
            <div class="growth-title">
              <span>!</span>
              <h2>主要不足</h2>
            </div>
            <ul v-if="detail.feedback_report.weaknesses?.length">
              <li v-for="item in detail.feedback_report.weaknesses" :key="item">{{ item }}</li>
            </ul>
            <p v-else>报告中暂未返回不足项。</p>
          </article>
          <article class="growth-card suggestions">
            <div class="growth-title">
              <span>↗</span>
              <h2>改进建议</h2>
            </div>
            <ul v-if="detail.feedback_report.suggestions?.length">
              <li v-for="item in detail.feedback_report.suggestions" :key="item">{{ item }}</li>
            </ul>
            <p v-else>报告中暂未返回建议项。</p>
          </article>
        </section>

        <section v-if="detailedFeedback" class="diagnosis-section" aria-label="详细问题诊断">
          <article class="diagnosis-panel">
            <div class="diagnosis-heading">
              <span>!</span>
              <div>
                <small>问题定位</small>
                <h2>详细问题诊断</h2>
              </div>
            </div>
            <div class="diagnosis-list">
              <article
                v-for="item in detailedFeedback.problem_diagnosis"
                :key="item.title"
                class="diagnosis-item"
                :class="item.severity"
              >
                <header>
                  <strong>{{ item.title }}</strong>
                  <span>{{ severityText(item.severity) }}</span>
                </header>
                <p><b>影响</b>{{ item.impact }}</p>
                <p><b>建议</b>{{ item.suggestion }}</p>
                <ul v-if="item.evidence?.length">
                  <li v-for="evidence in item.evidence" :key="evidence">{{ evidence }}</li>
                </ul>
              </article>
            </div>
          </article>

          <article class="diagnosis-panel">
            <div class="diagnosis-heading">
              <span>↗</span>
              <div>
                <small>行动方案</small>
                <h2>下一步改进计划</h2>
              </div>
            </div>
            <div class="action-plan-list">
              <article v-for="item in detailedFeedback.action_plan" :key="item.title">
                <header>
                  <strong>{{ item.title }}</strong>
                  <span>{{ priorityText(item.priority) }}</span>
                </header>
                <ol>
                  <li v-for="step in item.steps" :key="step">{{ step }}</li>
                </ol>
                <p v-if="item.expected_outcome">{{ item.expected_outcome }}</p>
              </article>
            </div>
          </article>

          <article class="diagnosis-panel round-review-panel">
            <div class="diagnosis-heading">
              <span>◇</span>
              <div>
                <small>逐轮复盘</small>
                <h2>轮次问题与证据</h2>
              </div>
            </div>
            <div class="round-review-list">
              <article v-for="item in detailedFeedback.round_reviews" :key="item.round_type">
                <header>
                  <strong>{{ roundLabel(item.round_type) }}</strong>
                  <span>{{
                    item.score === null || item.score === undefined
                      ? "暂无评分"
                      : `${formatScore(item.score)} 分`
                  }}</span>
                </header>
                <p v-if="item.issues?.length"><b>问题</b>{{ item.issues.join("；") }}</p>
                <p v-if="item.suggestions?.length"><b>建议</b>{{ item.suggestions.join("；") }}</p>
                <small
                  >{{ item.evaluated_question_count || 0 }}/{{
                    item.answered_question_count || 0
                  }}
                  题已评分</small
                >
              </article>
            </div>
          </article>

          <article
            v-if="detailedFeedback.follow_up_questions?.length"
            class="diagnosis-panel followup-panel"
          >
            <div class="diagnosis-heading">
              <span>?</span>
              <div>
                <small>复盘追问</small>
                <h2>下次应重点准备的问题</h2>
              </div>
            </div>
            <ul>
              <li v-for="question in detailedFeedback.follow_up_questions" :key="question">
                {{ question }}
              </li>
            </ul>
          </article>
        </section>

        <footer v-if="detail.feedback_report.used_candidate_memory" class="memory-footnote">
          <span aria-hidden="true">◈</span> 本次个性化反馈参考了你的历史面试表现。
        </footer>
      </section>

      <main class="round-section" aria-label="轮次明细">
        <template v-for="round in displayRounds" :key="round.type">
          <article class="round-row" :class="{ expanded: expandedRoundType === round.type }">
            <button
              class="round-toggle"
              type="button"
              :aria-expanded="expandedRoundType === round.type"
              @click="toggleRound(round.type)"
            >
              <span class="round-index">▣</span>
              <strong>{{ round.title }}</strong>
              <span
                ><small>轮次评分</small><b>{{ round.scoreNumber }} 分</b></span
              >
              <span
                ><small>面试官</small><b>{{ round.interviewer }}</b></span
              >
              <span
                ><small>开始时间</small><b>{{ formatDateTime(round.startedAt) }}</b></span
              >
              <span
                ><small>结束时间</small><b>{{ formatDateTime(round.endedAt) }}</b></span
              >
              <span
                ><small>时长</small><b>{{ formatDuration(round.elapsedSeconds) }}</b></span
              >
              <span
                ><small>表现评级</small><b class="rating">{{ round.rating }} ✦</b></span
              >
              <i aria-hidden="true">⌄</i>
            </button>
          </article>
          <section v-if="expandedRoundType === round.type" class="round-detail">
            <div v-if="round.qaEntries.length" class="qa-list">
              <article
                v-for="entry in round.qaEntries"
                :key="entry.id || `${entry.round_id}-${entry.sequence}`"
                class="qa-card"
              >
                <header class="qa-head">
                  <span>第 {{ entry.sequence || "-" }} 题</span
                  ><strong>{{ questionScoreText(entry) }}</strong>
                </header>
                <div class="qa-content">
                  <section>
                    <h3>面试官问题</h3>
                    <p>{{ questionText(entry) }}</p>
                  </section>
                  <section>
                    <h3>用户回答</h3>
                    <p>{{ answerText(entry) }}</p>
                  </section>
                  <section v-if="questionEvaluationText(entry)" class="qa-advice">
                    <h3>评价建议</h3>
                    <p>{{ questionEvaluationText(entry) }}</p>
                  </section>
                </div>
              </article>
            </div>
            <p v-else class="empty-text">{{ round.emptyText }}</p>
          </section>
        </template>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import {
  ApiError,
  getDashboardSummary,
  getHistoryDetail,
  type DashboardSummary,
  type HistoryDetail,
  type InterviewRound,
  type MultiRoundQaEntry,
  type QuestionEvaluation,
  type ReportQualitySummary,
  type RoundScore,
  type RoundType
} from "../api";
import historyChartMascot from "../assets/history-detail/history-chart-mascot.png";
import historyHeroBoy from "../assets/history-detail/history-hero-boy.png";
import historyNoticeGirl from "../assets/history-detail/history-notice-girl.png";
import hrInterviewer from "../assets/interviewers/hr-interviewer.png";
import managerInterviewer from "../assets/interviewers/manager-interviewer.png";
import resumeInterviewer from "../assets/interviewers/resume-interviewer.png";
import technicalInterviewer from "../assets/interviewers/technical-interviewer.png";

const route = useRoute();
const detail = ref<HistoryDetail | null>(null);
const dashboard = ref<DashboardSummary | null>(null);
const message = ref("");
const hasError = ref(false);
const expandedRoundType = ref<RoundType | null>(null);
const orderedRoundTypes: RoundType[] = ["resume", "technical", "manager", "hr"];
const roundMeta: Record<RoundType, { image: string; interviewer: string; icon: string }> = {
  resume: { image: resumeInterviewer, interviewer: "简历官小A", icon: "▤" },
  technical: { image: technicalInterviewer, interviewer: "技术官小T", icon: "</>" },
  manager: { image: managerInterviewer, interviewer: "主管官小M", icon: "♛" },
  hr: { image: hrInterviewer, interviewer: "HR 小H", icon: "♡" }
};

const rounds = computed<InterviewRound[]>(() => detail.value?.rounds || []);
const qaEntries = computed<MultiRoundQaEntry[]>(() => detail.value?.qa_history || []);
const reportQuality = computed<ReportQualitySummary | null>(
  () => detail.value?.report_quality || null
);
const detailedFeedback = computed(() => detail.value?.feedback_report?.detailed_feedback || null);
const finalScore = computed(() => normalizeScore(detail.value?.feedback_report?.score ?? null));
const finalScoreNumber = computed(() =>
  finalScore.value === null ? "-" : formatScore(finalScore.value)
);
const reportReliabilityNotice = computed(() => {
  const report = detail.value?.feedback_report;
  if (!report || report.report_reliability_status === "normal") return null;
  if (report.report_reliability_status === "unavailable") {
    return {
      title: "报告不可用",
      text: report.reference_note || "当前报告暂不可用，不建议作为判断依据。",
      tone: "error"
    };
  }
  return {
    title: "报告仅供参考",
    text: report.reference_note || "存在未完成或提前结束轮次，最终结论置信度已降低。",
    tone: "warning"
  };
});
const displayRounds = computed(() =>
  orderedRoundTypes.map((type, index) => {
    const round = rounds.value.find((item) => item.round_type === type) || null;
    const entries = qaEntries.value.filter((entry) => entryRoundType(entry) === type);
    const score = normalizeScore(
      firstNumber([scoreFromFinalReport(type), scoreFromRoundSummary(round), round?.score])
    );
    const source = reportQuality.value?.score_sources.find((item) => item.round_type === type);
    return {
      type,
      title: `${roundOrdinal(index)}：${roundLabel(type)}`,
      qaEntries: entries,
      scoreNumber: score === null ? "-" : formatScore(score),
      progress: score === null ? 0 : score,
      scoreSource: source?.source || "none",
      emptyText: round ? "暂无问答记录" : "该轮次未进行",
      startedAt: round?.started_at || null,
      endedAt: round?.ended_at || null,
      elapsedSeconds: round?.elapsed_seconds || 0,
      rating: ratingText(score),
      ...roundMeta[type]
    };
  })
);

const qualityMetrics = computed(() => {
  const quality = reportQuality.value;
  if (!quality) return [];
  return [
    {
      label: "完成轮次",
      value: `${quality.completed_round_count}/${quality.selected_round_count}`,
      note: "已选择轮次"
    },
    {
      label: "有效回答",
      value: String(quality.answered_question_count),
      note: "参与报告判断"
    },
    {
      label: "题目评分",
      value: `${quality.evaluated_question_count}/${quality.answered_question_count}`,
      note: "评分覆盖"
    }
  ];
});

const abilityValues = computed(() => {
  const scoreByType = Object.fromEntries(
    displayRounds.value.map((item) => [
      item.type,
      item.scoreNumber === "-" ? null : Number(item.scoreNumber)
    ])
  );
  const fallback = finalScore.value ?? 0;
  return [
    scoreByType.technical ?? fallback,
    scoreByType.resume ?? fallback,
    scoreByType.manager ?? fallback,
    scoreByType.hr ?? fallback,
    finalScore.value ?? fallback
  ];
});
const abilityLabels = computed(() => [
  { label: "专业技能", value: formatScore(abilityValues.value[0]), position: "top" },
  { label: "问题解决", value: formatScore(abilityValues.value[1]), position: "right-top" },
  { label: "系统设计", value: formatScore(abilityValues.value[2]), position: "right-bottom" },
  { label: "沟通表达", value: formatScore(abilityValues.value[3]), position: "left-bottom" },
  { label: "学习能力", value: formatScore(abilityValues.value[4]), position: "left-top" }
]);
const radarOuterPoints = computed(() => radarPoints([100, 100, 100, 100, 100]));
const radarValuePoints = computed(() => radarPoints(abilityValues.value));
const radarDataPoints = computed(() => pointString(radarValuePoints.value));

const trendValues = computed(() => {
  const values = (dashboard.value?.score_trend || [])
    .map((point) => normalizeScore(point.score))
    .filter((score): score is number => score !== null);
  if (!values.length && finalScore.value !== null) return [finalScore.value];
  return values.slice(-6);
});
const trendChartPoints = computed(() =>
  trendValues.value.map((value, index, list) => ({
    value,
    index,
    x: list.length === 1 ? 330 : 58 + index * (548 / (list.length - 1)),
    y: 198 - value * 1.62
  }))
);
const trendLinePoints = computed(() => pointString(trendChartPoints.value));
const trendAreaPoints = computed(() =>
  trendChartPoints.value.length
    ? `58,206 ${trendLinePoints.value} ${trendChartPoints.value.at(-1)?.x},206`
    : ""
);
const trendTicks = [0, 20, 40, 60, 80, 100].map((value) => ({ value, y: 198 - value * 1.62 }));
const lastTrendPoint = computed(() => trendChartPoints.value.at(-1) || null);

onMounted(async () => {
  await Promise.all([loadDetail(), loadTrend()]);
});

async function loadDetail() {
  try {
    detail.value = await getHistoryDetail(Number(route.params.id));
    message.value = "";
    hasError.value = false;
  } catch (error) {
    message.value = error instanceof ApiError ? error.message : "历史详情加载失败。";
    hasError.value = true;
  }
}

async function loadTrend() {
  try {
    dashboard.value = await getDashboardSummary();
  } catch {
    dashboard.value = null;
  }
}

function toggleRound(type: RoundType) {
  expandedRoundType.value = expandedRoundType.value === type ? null : type;
}
function statusText(status: string): string {
  return (
    (
      {
        created: "已创建",
        in_progress: "进行中",
        finished: "已结束",
        completed: "已结束"
      } as Record<string, string>
    )[status] || status
  );
}
function roundLabel(type: string): string {
  return (
    (
      { resume: "简历面", technical: "技术面", manager: "主管面", hr: "HR 面" } as Record<
        string,
        string
      >
    )[type] || "未分组"
  );
}
function roundOrdinal(index: number): string {
  return ["第一轮", "第二轮", "第三轮", "第四轮"][index] || `第 ${index + 1} 轮`;
}
function scoreFromRoundSummary(round: InterviewRound | null): number | null {
  return typeof round?.summary?.score === "number" ? round.summary.score : null;
}
function scoreFromFinalReport(type: RoundType): number | null {
  const item = detail.value?.feedback_report?.round_scores?.find(
    (score: RoundScore) => score.round_type === type
  );
  return typeof item?.score === "number" ? item.score : null;
}
function firstNumber(values: Array<number | null | undefined>): number | null {
  const value = values.find((item) => typeof item === "number");
  return typeof value === "number" ? value : null;
}
function normalizeScore(score: number | null): number | null {
  if (typeof score !== "number") return null;
  return Math.max(0, Math.min(100, score));
}
function formatScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}
function ratingText(score: number | null): string {
  if (score === null) return "待评";
  if (score >= 85) return "优秀";
  if (score >= 70) return "良好";
  if (score >= 60) return "合格";
  return "待提升";
}
function confidenceText(value: string): string {
  return (
    ({ high: "高置信度", medium: "中等置信度", low: "低置信度" } as Record<string, string>)[
      value
    ] || value
  );
}
function severityText(value: string): string {
  return (
    ({ high: "高风险", medium: "中风险", low: "低风险" } as Record<string, string>)[value] || value
  );
}
function priorityText(value: string): string {
  return (
    ({ high: "高优先级", medium: "中优先级", low: "低优先级" } as Record<string, string>)[value] ||
    value
  );
}
function scoreSourceText(value: string): string {
  return (
    (
      { final_report: "总评报告", round_summary: "轮次评分", none: "暂无评分" } as Record<
        string,
        string
      >
    )[value] || value
  );
}

function radarPoints(values: number[]) {
  return values.map((value, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / values.length;
    const radius = (82 * Math.max(0, Math.min(100, value))) / 100;
    return {
      x: Number((180 + Math.cos(angle) * radius).toFixed(1)),
      y: Number((126 + Math.sin(angle) * radius).toFixed(1))
    };
  });
}
function radarGuide(level: number): string {
  return pointString(
    radarPoints([100 * level, 100 * level, 100 * level, 100 * level, 100 * level])
  );
}
function pointString(points: Array<{ x: number; y: number }>): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function questionScoreText(entry: MultiRoundQaEntry): string {
  const score =
    typeof entry.question_evaluation?.total_score === "number"
      ? entry.question_evaluation.total_score
      : null;
  return score === null ? "本题暂未评分" : `本题评分：${formatScore(score)} / 100`;
}
function questionEvaluationText(entry: MultiRoundQaEntry): string {
  const evaluation = entry.question_evaluation;
  if (!evaluation) return "";
  return evaluationText(evaluation);
}
function evaluationText(evaluation: QuestionEvaluation): string {
  return (
    evaluation.strengths?.find(Boolean) ||
    evaluation.issues?.find(Boolean) ||
    evaluation.follow_up_direction ||
    ""
  );
}
function entryRoundType(entry: MultiRoundQaEntry): RoundType | null {
  return (
    entry.round_type || rounds.value.find((item) => item.id === entry.round_id)?.round_type || null
  );
}
function questionText(entry: MultiRoundQaEntry): string {
  return entry.question || entry.question_text || entry.prompt || "暂无问题内容";
}
function answerText(entry: MultiRoundQaEntry): string {
  return entry.answer || entry.answer_text || entry.user_answer || "暂无回答";
}
function formatDatePart(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("zh-CN") : "暂无";
}
function formatTimePart(value: string | null): string {
  return value ? new Date(value).toLocaleTimeString("zh-CN", { hour12: false }) : "暂无时间";
}
function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "暂无";
}
function formatDuration(seconds: number): string {
  if (!seconds) return "-";
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `${minutes} 分钟`;
}
</script>

<style scoped>
.detail-workspace {
  display: grid;
  gap: 22px;
  width: 100%;
  max-width: 1560px;
  margin: 0 auto;
  color: #11183f;
}
.detail-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}
.detail-breadcrumb {
  display: flex;
  gap: 10px;
  margin: 0 0 8px;
  color: #737d9b;
  font-size: 14px;
  font-weight: 700;
}
.detail-breadcrumb a:hover {
  color: #5961ff;
}
.detail-heading h1 {
  margin: 0;
  color: #080e38;
  font-size: 34px;
  font-weight: 950;
  letter-spacing: -1px;
}
.detail-heading h1 i,
.position-copy span i {
  color: #d990ff;
  font-style: normal;
}
.header-actions {
  display: flex;
  gap: 14px;
}
.detail-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-width: 138px;
  min-height: 46px;
  border: 1px solid #8391ff;
  border-radius: 12px;
  background: #fff;
  color: #283068;
  font-weight: 900;
}
.detail-button.report {
  border-color: transparent;
  background: linear-gradient(135deg, #5e72ff, #9753f6);
  box-shadow: 0 12px 24px rgb(96 93 255 / 20%);
  color: #fff;
}
.detail-page {
  display: grid;
  gap: 20px;
}
.overview-panel {
  position: relative;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  align-items: center;
  min-height: 150px;
  overflow: hidden;
  border: 1px solid #dfe6f7;
  border-radius: 18px;
  background: linear-gradient(105deg, #f6f8ff 0%, #fff 46%, #fbfaff 100%);
  box-shadow: 0 14px 40px rgb(64 78 129 / 8%);
}
.overview-art {
  position: absolute;
  inset: 0 auto 0 0;
  width: 370px;
  overflow: hidden;
}
.overview-art::after {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent 48%, #f8f9ff 100%);
  content: "";
}
.overview-art img {
  position: absolute;
  inset: -18% -20% -12% -28%;
  width: 150%;
  height: 140%;
  object-fit: cover;
  transform: scaleX(-1);
  filter: saturate(0.9) brightness(1.08);
  animation: hero-breathe 6s ease-in-out infinite;
}
.art-glow {
  position: absolute;
  left: 90px;
  bottom: 16px;
  width: 150px;
  height: 34px;
  border-radius: 50%;
  background: rgb(113 105 255 / 24%);
  filter: blur(20px);
  animation: glow-pulse 3.6s ease-in-out infinite;
}
.art-spark {
  position: absolute;
  z-index: 2;
  color: #c97cff;
  animation: spark-float 3.2s ease-in-out infinite;
}
.spark-one {
  top: 22px;
  right: 42px;
}
.spark-two {
  right: 78px;
  bottom: 18px;
  animation-delay: -1.1s;
}
.position-copy {
  position: relative;
  z-index: 3;
  grid-column: 1;
  padding-left: 185px;
}
.position-copy span {
  color: #6682ff;
  font-size: 14px;
  font-weight: 800;
}
.position-copy h2 {
  margin: 4px 0 4px;
  color: #08113e;
  font-size: 29px;
  font-weight: 950;
  white-space: nowrap;
}
.position-copy p {
  margin: 0;
  color: #65708d;
  font-size: 13px;
  white-space: nowrap;
}
.position-copy p b {
  color: #ffb35d;
}
.summary-metrics {
  position: relative;
  z-index: 3;
  grid-column: 2;
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  margin: 16px 16px 16px 0;
  border: 1px solid #e4e9f5;
  border-radius: 16px;
  background: rgb(255 255 255 / 88%);
  box-shadow: 0 10px 30px rgb(57 72 119 / 7%);
}
.summary-metrics > div {
  display: grid;
  align-content: center;
  min-height: 112px;
  padding: 16px 18px;
}
.summary-metrics > div + div {
  border-left: 1px solid #edf0f7;
}
.summary-metrics dt {
  color: #78819d;
  font-size: 13px;
  font-weight: 800;
}
.summary-metrics dd {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 8px 0 1px;
  color: #10163e;
}
.summary-metrics dd strong {
  font-size: 18px;
  font-weight: 950;
  white-space: nowrap;
}
.summary-metrics dd em {
  font-style: normal;
  font-weight: 900;
}
.summary-metrics small {
  padding-left: 36px;
  color: #717b96;
  font-size: 12px;
}
.metric-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  background: #e9efff;
  color: #6178ff;
  font-weight: 950;
}
.metric-icon.trophy {
  background: #eee9ff;
  color: #7c58ff;
}
.metric-icon.success {
  border-radius: 50%;
  background: #43c99b;
  color: #fff;
}
.metric-icon.violet {
  background: #eee8ff;
  color: #955df8;
}
.metric-icon.document {
  background: #eef4ff;
  color: #698bff;
}
.reliability-alert {
  position: relative;
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) 104px;
  gap: 14px;
  align-items: center;
  min-height: 78px;
  overflow: hidden;
  padding: 10px 22px;
  border: 1px solid #f2c26d;
  border-radius: 15px;
  background: linear-gradient(90deg, #fffaf0, #fffdf9);
  color: #764416;
}
.reliability-alert.error {
  border-color: #f0b4ae;
  background: #fff7f6;
  color: #8a2d1b;
}
.notice-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 13px;
  background: #ffb94f;
  color: #fff;
  font-size: 20px;
}
.reliability-alert strong {
  font-size: 17px;
}
.reliability-alert p {
  margin: 2px 0 0;
  color: #766452;
  font-size: 13px;
}
.notice-character {
  position: absolute;
  right: 16px;
  bottom: -54px;
  width: 100px;
  height: 132px;
  overflow: hidden;
  border-radius: 50% 50% 0 0;
}
.notice-character img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 10%;
  animation: character-bob 4s ease-in-out infinite;
}
.round-score-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.round-score-card {
  --round: #596dff;
  --tint: #eef2ff;
  position: relative;
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  min-height: 112px;
  overflow: hidden;
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--round) 24%, white);
  border-radius: 17px;
  background: linear-gradient(135deg, #fff, var(--tint));
  box-shadow: 0 10px 28px rgb(55 68 112 / 6%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}
.round-score-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 34px color-mix(in srgb, var(--round) 16%, transparent);
}
.round-score-card.technical {
  --round: #8061f4;
  --tint: #f4f0ff;
}
.round-score-card.manager {
  --round: #e8912f;
  --tint: #fff6e8;
}
.round-score-card.hr {
  --round: #ef6d9d;
  --tint: #fff0f6;
}
.round-avatar {
  position: relative;
  z-index: 2;
  width: 76px;
  height: 76px;
  overflow: hidden;
  border: 3px solid var(--round);
  border-radius: 50%;
  background: var(--tint);
  box-shadow: 0 5px 14px color-mix(in srgb, var(--round) 20%, transparent);
  transition: transform 0.3s ease;
}
.round-score-card:hover .round-avatar {
  transform: scale(1.06) rotate(-2deg);
}
.round-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 18%;
  animation: portrait-breathe 5s ease-in-out infinite;
}
.round-card-copy {
  position: relative;
  z-index: 2;
}
.round-card-copy > strong {
  font-size: 17px;
  font-weight: 950;
}
.round-card-copy p {
  margin: 1px 0 8px;
  color: #0d1647;
}
.round-card-copy p b {
  font-size: 27px;
  line-height: 1;
}
.round-card-copy p span {
  margin-left: 5px;
  font-size: 15px;
  font-weight: 900;
}
.score-track {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--round) 12%, white);
}
.score-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, color-mix(in srgb, var(--round) 68%, white), var(--round));
  box-shadow: 0 4px 10px color-mix(in srgb, var(--round) 30%, transparent);
}
.round-watermark {
  position: absolute;
  right: 18px;
  top: 20px;
  color: color-mix(in srgb, var(--round) 18%, transparent);
  font-size: 42px;
  font-weight: 950;
}
.visual-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}
.chart-card {
  position: relative;
  min-height: 274px;
  overflow: hidden;
  padding: 18px 24px;
  border: 1px solid #e1e6f3;
  border-radius: 18px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 12px 34px rgb(51 65 111 / 6%);
}
.chart-card h2 {
  margin: 0;
  color: #11183f;
  font-size: 18px;
  font-weight: 950;
}
.chart-card h2 span {
  color: #7b60ff;
}
.radar-wrap {
  position: relative;
  width: min(430px, 100%);
  height: 226px;
  margin: -4px auto 0;
}
.radar-wrap svg {
  width: 100%;
  height: 100%;
}
.radar-guides polygon,
.radar-guides line {
  fill: none;
  stroke: #dfe4f2;
  stroke-width: 1;
}
.radar-fill {
  fill: url(#none);
  fill: #7369f2;
  fill-opacity: 0.46;
  stroke: #655bf1;
  stroke-width: 2;
}
.radar-wrap circle {
  fill: #fff;
  stroke: #6875f7;
  stroke-width: 2;
}
.radar-label {
  position: absolute;
  color: #5f6984;
  font-size: 12px;
  font-weight: 700;
  text-align: center;
}
.radar-label b {
  display: block;
  color: #11183f;
  font-size: 13px;
}
.radar-label.top {
  top: 3px;
  left: 50%;
  transform: translateX(-50%);
}
.radar-label.right-top {
  top: 73px;
  right: 0;
}
.radar-label.right-bottom {
  right: 18px;
  bottom: 13px;
}
.radar-label.left-bottom {
  left: 18px;
  bottom: 13px;
}
.radar-label.left-top {
  top: 73px;
  left: 0;
}
.radar-mascot,
.trend-mascot {
  position: absolute;
  z-index: 3;
  object-fit: cover;
  object-position: 50% 12%;
  filter: drop-shadow(0 7px 7px rgb(53 52 113 / 14%));
  pointer-events: none;
  animation: character-bob 4.4s ease-in-out infinite;
}
.radar-mascot {
  left: -8px;
  bottom: -44px;
  width: 70px;
  height: 90px;
  border-radius: 50% 50% 0 0;
}
.chart-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.chart-title-row > span {
  padding: 5px 12px;
  border: 1px solid #e1e5ef;
  border-radius: 9px;
  color: #65708c;
  font-size: 12px;
  font-weight: 800;
}
.trend-wrap {
  position: relative;
  height: 222px;
}
.trend-wrap svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}
.trend-grid line {
  stroke: #e8ebf4;
  stroke-dasharray: 4 4;
}
.trend-grid text {
  fill: #818aa3;
  font-size: 10px;
}
.trend-area {
  fill: url(#trend-area);
}
.trend-line {
  fill: none;
  stroke: #7657f4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}
.trend-point circle {
  fill: #805cf4;
  stroke: #fff;
  stroke-width: 2;
}
.trend-point text {
  fill: #313a60;
  font-size: 10px;
  font-weight: 800;
  text-anchor: middle;
}
.trend-point .x-label {
  fill: #7a839c;
  font-weight: 700;
}
.trend-mascot {
  right: -16px;
  bottom: -30px;
  width: 72px;
  height: 92px;
  border-radius: 50% 50% 0 0;
  animation-delay: -1.4s;
}
.round-section {
  display: grid;
  gap: 9px;
}
.round-row {
  overflow: hidden;
  border: 1px solid #e0e6f2;
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(49 63 109 / 5%);
}
.round-row.expanded {
  border-radius: 15px 15px 0 0;
}
.round-toggle {
  display: grid;
  grid-template-columns:
    30px minmax(130px, 1.2fr) repeat(2, minmax(100px, 0.75fr)) repeat(2, minmax(140px, 1fr))
    minmax(72px, 0.55fr) minmax(90px, 0.6fr) 20px;
  gap: 14px;
  align-items: center;
  width: 100%;
  min-height: 76px;
  padding: 10px 20px;
  border: 0;
  border-radius: 0;
  background: #fff;
  text-align: left;
}
.round-toggle:hover {
  background: #fafbff;
}
.round-index {
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border-radius: 9px;
  background: #eaf2ff;
  color: #5f84ff;
}
.round-toggle > strong {
  font-size: 15px;
  font-weight: 950;
}
.round-toggle > span:not(.round-index) {
  display: grid;
  gap: 1px;
}
.round-toggle small {
  color: #78819a;
  font-size: 11px;
}
.round-toggle b {
  color: #263050;
  font-size: 12px;
  white-space: nowrap;
}
.round-toggle .rating {
  width: max-content;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef4ff;
  color: #3d69f0;
}
.round-toggle > i {
  font-style: normal;
  transition: transform 0.2s ease;
}
.round-row.expanded .round-toggle > i {
  transform: rotate(180deg);
}
.round-detail {
  margin-top: -9px;
  padding: 14px;
  border: 1px solid #e0e6f2;
  border-top: 0;
  border-radius: 0 0 15px 15px;
  background: #f8faff;
}
.qa-list {
  display: grid;
  gap: 10px;
}
.qa-card {
  padding: 15px;
  border: 1px solid #e3e8f2;
  border-radius: 12px;
  background: #fff;
}
.qa-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 9px;
  border-bottom: 1px solid #edf0f6;
  color: #69738f;
  font-size: 12px;
}
.qa-head strong {
  color: #4e5ee8;
}
.qa-content {
  display: grid;
  gap: 11px;
  padding-top: 11px;
}
.qa-content h3 {
  margin: 0 0 3px;
  color: #727c96;
  font-size: 12px;
}
.qa-content p {
  margin: 0;
  color: #29334e;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}
.qa-advice {
  padding: 9px 11px;
  border-radius: 9px;
  background: #f2f5ff;
}
.empty-text {
  margin: 0;
  color: #727c96;
  font-size: 13px;
}
.message.error {
  color: #df4d5f;
}
@keyframes hero-breathe {
  0%,
  100% {
    transform: scaleX(-1) scale(1);
  }
  50% {
    transform: scaleX(-1) scale(1.025) translateY(-3px);
  }
}
@keyframes character-bob {
  0%,
  100% {
    transform: translateY(0) rotate(0);
  }
  50% {
    transform: translateY(-5px) rotate(0.8deg);
  }
}
@keyframes portrait-breathe {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.035);
  }
}
@keyframes glow-pulse {
  0%,
  100% {
    opacity: 0.45;
    transform: scale(0.9);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}
@keyframes spark-float {
  0%,
  100% {
    opacity: 0.35;
    transform: translateY(0) rotate(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-7px) rotate(16deg);
  }
}
@media (max-width: 1280px) {
  .overview-panel {
    grid-template-columns: 300px minmax(0, 1fr);
  }
  .position-copy {
    padding-left: 150px;
  }
  .summary-metrics {
    grid-template-columns: repeat(3, 1fr);
  }
  .summary-metrics > div {
    min-height: 90px;
  }
  .summary-metrics > div:nth-child(4) {
    border-left: 0;
    border-top: 1px solid #edf0f7;
  }
  .summary-metrics > div:nth-child(5) {
    border-top: 1px solid #edf0f7;
  }
  .round-toggle {
    grid-template-columns: 30px minmax(140px, 1fr) repeat(3, minmax(90px, 0.7fr)) 20px;
  }
  .round-toggle > span:nth-of-type(4),
  .round-toggle > span:nth-of-type(5),
  .round-toggle > span:nth-of-type(7) {
    display: none;
  }
}
@media (max-width: 980px) {
  .overview-panel {
    grid-template-columns: 1fr;
    padding-top: 130px;
  }
  .overview-art {
    width: 100%;
    height: 140px;
  }
  .position-copy {
    grid-column: 1;
    padding: 0 24px 16px;
  }
  .summary-metrics {
    grid-column: 1;
    margin: 0 16px 16px;
  }
  .round-score-grid,
  .visual-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .visual-grid .chart-card {
    min-width: 0;
  }
  .detail-heading {
    align-items: flex-start;
  }
}
@media (max-width: 700px) {
  .detail-heading {
    display: grid;
  }
  .header-actions,
  .detail-button {
    width: 100%;
  }
  .overview-panel {
    padding-top: 120px;
  }
  .summary-metrics,
  .round-score-grid,
  .visual-grid {
    grid-template-columns: 1fr;
  }
  .summary-metrics > div + div {
    border-top: 1px solid #edf0f7;
    border-left: 0;
  }
  .position-copy {
    padding-left: 20px;
  }
  .round-toggle {
    grid-template-columns: 28px minmax(0, 1fr) auto;
  }
  .round-toggle > span:not(.round-index) {
    display: none !important;
  }
  .round-score-grid {
    gap: 10px;
  }
  .chart-card {
    padding: 16px 12px;
  }
  .reliability-alert {
    grid-template-columns: 40px 1fr;
  }
  .notice-character {
    display: none;
  }
}
@media (max-width: 700px) {
  .round-review-list {
    grid-template-columns: 1fr;
  }
  .diagnosis-panel {
    padding: 18px;
  }
  .diagnosis-item header,
  .action-plan-list header,
  .round-review-list header {
    display: grid;
  }
}
@media (prefers-reduced-motion: reduce) {
  .overview-art img,
  .art-glow,
  .art-spark,
  .notice-character img,
  .round-avatar img,
  .radar-mascot,
  .trend-mascot {
    animation: none;
  }
  .round-score-card,
  .round-avatar,
  .round-toggle > i {
    transition: none;
  }
}
.overview-art img {
  inset: 0;
  width: 100%;
  height: 100%;
  object-position: 82% 30%;
}

.detail-workspace {
  position: relative;
  max-width: none;
  min-height: 100vh;
  padding: 36px 32px 34px;
  overflow: hidden;
  background:
    radial-gradient(circle at 78% 4%, rgb(161 185 255 / 34%), transparent 25%),
    radial-gradient(circle at 12% 20%, rgb(112 181 255 / 18%), transparent 27%),
    linear-gradient(180deg, #f8fbff 0%, #ffffff 36%, #fbfcff 100%);
}

.detail-workspace::before,
.detail-workspace::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: "";
}

.detail-workspace::before {
  background:
    radial-gradient(circle at 16% 86%, rgb(128 140 255 / 10%) 0 2px, transparent 3px),
    radial-gradient(circle at 34% 10%, rgb(237 138 255 / 16%) 0 4px, transparent 5px),
    radial-gradient(circle at 92% 16%, rgb(255 184 218 / 20%) 0 5px, transparent 6px);
  animation: ambient-drift 16s ease-in-out infinite alternate;
}

.detail-workspace::after {
  top: 0;
  height: 150px;
  background:
    linear-gradient(115deg, transparent 0 38%, rgb(255 255 255 / 55%) 52%, transparent 66%),
    radial-gradient(ellipse at 86% 10%, rgb(142 179 255 / 26%), transparent 36%);
  transform: translate3d(0, 0, 0);
  animation: sky-sheen 18s ease-in-out infinite;
}

.detail-heading,
.detail-page,
.message {
  position: relative;
  z-index: 1;
}

.detail-heading {
  min-height: 96px;
  align-items: flex-start;
  padding: 6px 0 0;
}

.detail-breadcrumb {
  margin-top: 2px;
}

.header-actions {
  padding-top: 46px;
  padding-right: 8px;
}

.detail-button {
  min-height: 50px;
  border-radius: 12px;
  box-shadow: 0 10px 26px rgb(61 82 160 / 8%);
}

.detail-button:hover {
  transform: translateY(-2px);
}

.detail-button.report {
  background: linear-gradient(135deg, #6677ff, #9d52f5);
}

.overview-panel {
  grid-template-columns: 430px minmax(0, 1fr);
  min-height: 156px;
  border-radius: 17px;
  background: linear-gradient(
    105deg,
    rgb(239 246 255 / 94%) 0%,
    rgb(255 255 255 / 96%) 47%,
    #ffffff 100%
  );
  animation: card-arrive 520ms ease both;
}

.overview-art {
  width: 380px;
}

.overview-art::after {
  background: linear-gradient(90deg, transparent 42%, rgb(248 251 255 / 88%) 88%);
}

.overview-art img {
  inset: -20px auto -16px -58px;
  width: 440px;
  height: calc(100% + 36px);
  object-position: 30% 42%;
  animation: hero-drift 8s ease-in-out infinite;
}

.art-glow {
  left: 118px;
  bottom: 10px;
}

.position-copy {
  padding-left: 196px;
}

.position-copy h2 {
  font-size: 32px;
}

.summary-metrics {
  margin: 18px 18px 18px 0;
  border-radius: 16px;
  backdrop-filter: blur(10px);
}

.summary-metrics > div {
  min-height: 114px;
}

.score-metric dd strong {
  font-size: 29px;
}

.score-metric dd .final-score-value {
  display: inline-flex;
  gap: 2px;
  align-items: baseline;
}

.score-metric dd em {
  align-self: end;
  margin-bottom: 3px;
  color: #11183f;
  font-size: 15px;
}

.reliability-alert {
  min-height: 82px;
  border-radius: 14px;
  background:
    linear-gradient(90deg, rgb(255 249 239 / 96%), rgb(255 254 250 / 96%)),
    radial-gradient(circle at 96% 16%, rgb(255 183 93 / 22%), transparent 18%);
  animation: card-arrive 560ms 80ms ease both;
}

.notice-character {
  right: 28px;
  bottom: -46px;
  width: 126px;
  height: 136px;
}

.notice-character img {
  object-position: 72% 42%;
  animation: soft-float 5.8s ease-in-out infinite;
}

.round-score-card,
.chart-card,
.round-row {
  animation: card-arrive 560ms ease both;
}

.round-score-card:nth-child(1) {
  animation-delay: 90ms;
}
.round-score-card:nth-child(2) {
  animation-delay: 140ms;
}
.round-score-card:nth-child(3) {
  animation-delay: 190ms;
}
.round-score-card:nth-child(4) {
  animation-delay: 240ms;
}

.round-score-card {
  border-radius: 15px;
}

.round-score-card:hover {
  transform: translateY(-3px);
}

.score-track i {
  transform-origin: left center;
  animation: score-grow 900ms 260ms ease-out both;
}

.chart-card {
  border-radius: 17px;
}

.radar-fill {
  transform-origin: 180px 126px;
  animation: radar-breathe 6.8s ease-in-out infinite;
}

.radar-wrap circle {
  animation: dot-pulse 4.6s ease-in-out infinite;
}

.radar-mascot {
  left: -2px;
  bottom: -44px;
  width: 86px;
  height: 96px;
  border-radius: 0;
  object-position: 50% 56%;
  animation: soft-float 6.2s ease-in-out infinite;
}

.trend-line {
  stroke-dasharray: 760;
  stroke-dashoffset: 760;
  animation: trend-draw 1.2s 220ms ease-out forwards;
}

.trend-area {
  animation: area-rise 1s 360ms ease-out both;
}

.trend-point circle {
  transform-box: fill-box;
  transform-origin: center;
  animation: point-pop 520ms ease both;
}

.trend-point:nth-of-type(1) circle {
  animation-delay: 260ms;
}
.trend-point:nth-of-type(2) circle {
  animation-delay: 330ms;
}
.trend-point:nth-of-type(3) circle {
  animation-delay: 400ms;
}
.trend-point:nth-of-type(4) circle {
  animation-delay: 470ms;
}
.trend-point:nth-of-type(5) circle {
  animation-delay: 540ms;
}
.trend-point:nth-of-type(6) circle {
  animation-delay: 610ms;
}

.trend-current line {
  stroke: #a277ff;
  stroke-dasharray: 4 5;
  stroke-width: 1.5;
  animation: current-line 2.8s ease-in-out infinite;
}

.trend-current rect {
  fill: #855cf6;
  filter: drop-shadow(0 8px 14px rgb(117 87 244 / 22%));
}

.trend-current text {
  fill: #fff;
  font-size: 12px;
  font-weight: 900;
  text-anchor: middle;
}

.trend-mascot {
  width: 80px;
  height: 102px;
  animation: soft-float 6s -1.4s ease-in-out infinite;
}

.round-row:nth-of-type(1) {
  animation-delay: 180ms;
}
.round-row:nth-of-type(3) {
  animation-delay: 230ms;
}
.round-row:nth-of-type(5) {
  animation-delay: 280ms;
}
.round-row:nth-of-type(7) {
  animation-delay: 330ms;
}

@keyframes hero-drift {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, -5px, 0) scale(1.018);
  }
}

@keyframes soft-float {
  0%,
  100% {
    transform: translate3d(0, 0, 0) rotate(0);
  }
  50% {
    transform: translate3d(0, -7px, 0) rotate(0.7deg);
  }
}

@keyframes card-arrive {
  from {
    opacity: 0;
    transform: translate3d(0, 12px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes score-grow {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}

@keyframes trend-draw {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes area-rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes point-pop {
  from {
    opacity: 0;
    transform: scale(0.45);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes radar-breathe {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.42;
  }
  50% {
    transform: scale(1.018);
    opacity: 0.56;
  }
}

@keyframes dot-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.12);
  }
}

@keyframes current-line {
  0%,
  100% {
    opacity: 0.48;
  }
  50% {
    opacity: 0.95;
  }
}

@keyframes ambient-drift {
  from {
    transform: translate3d(-10px, 0, 0);
  }
  to {
    transform: translate3d(12px, 8px, 0);
  }
}

@keyframes sky-sheen {
  0%,
  100% {
    opacity: 0.48;
    transform: translate3d(-18px, 0, 0);
  }
  50% {
    opacity: 0.82;
    transform: translate3d(22px, 0, 0);
  }
}

.report-detail-section {
  display: grid;
  gap: 16px;
}

.report-quality-panel {
  display: grid;
  gap: 16px;
  padding: 22px;
  border: 1px solid #dfe5f4;
  border-radius: 17px;
  background:
    linear-gradient(135deg, rgb(255 255 255 / 96%), rgb(245 248 255 / 96%)),
    radial-gradient(circle at 94% 12%, rgb(118 97 244 / 16%), transparent 26%);
  box-shadow: 0 12px 34px rgb(51 65 111 / 6%);
  animation: card-arrive 560ms 120ms ease both;
}

.quality-heading {
  display: flex;
  gap: 16px;
  align-items: start;
  justify-content: space-between;
}

.quality-heading span {
  color: #65708c;
  font-size: 12px;
  font-weight: 900;
}

.quality-heading h2 {
  margin: 2px 0 0;
  color: #10183f;
  font-size: 20px;
  font-weight: 950;
}

.quality-heading strong {
  display: grid;
  place-items: center;
  width: 74px;
  height: 74px;
  border: 1px solid #dcdfff;
  border-radius: 50%;
  background: #fff;
  color: #675cf0;
  font-size: 22px;
  font-weight: 950;
}

.quality-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.quality-metrics article {
  display: grid;
  gap: 3px;
  min-height: 92px;
  padding: 15px;
  border: 1px solid #e7ebf5;
  border-radius: 14px;
  background: #fff;
}

.quality-metrics small,
.score-source-list small {
  color: #75809a;
  font-size: 12px;
  font-weight: 800;
}

.quality-metrics b {
  color: #10183f;
  font-size: 24px;
}

.quality-metrics span {
  color: #7b849d;
  font-size: 12px;
}

.quality-body {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: 16px;
}

.quality-body section {
  min-width: 0;
  padding: 16px;
  border: 1px solid #e7ebf5;
  border-radius: 14px;
  background: rgb(255 255 255 / 82%);
}

.quality-body h3 {
  margin: 0 0 10px;
  color: #202a4d;
  font-size: 14px;
  font-weight: 950;
}

.quality-body ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.quality-body li {
  position: relative;
  padding-left: 16px;
  color: #4d5874;
  font-size: 13px;
  line-height: 1.55;
}

.quality-body li::before {
  position: absolute;
  top: 8px;
  left: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #7664f2;
  content: "";
}

.score-source-list {
  display: grid;
  gap: 8px;
}

.score-source-list article {
  display: grid;
  grid-template-columns: minmax(76px, 0.7fr) minmax(72px, 0.7fr) minmax(58px, 0.45fr) minmax(
      98px,
      0.8fr
    );
  gap: 8px;
  align-items: center;
  min-height: 38px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f7f9ff;
}

.score-source-list strong,
.score-source-list b {
  color: #202a4d;
  font-size: 12px;
}

.score-source-list span {
  color: #5f6ef0;
  font-size: 12px;
  font-weight: 900;
}

.report-insights {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  gap: 16px;
}

.report-info-card,
.growth-card {
  border: 1px solid #e1e6f2;
  border-radius: 17px;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 12px 34px rgb(51 65 111 / 6%);
  animation: card-arrive 560ms ease both;
}

.report-info-card {
  min-height: 188px;
  padding: 24px;
}

.conclusion-card {
  background: linear-gradient(135deg, #f2f5ff, #f7f1ff);
}

.report-card-heading,
.growth-title {
  display: flex;
  gap: 13px;
  align-items: center;
}

.report-card-heading > span,
.growth-title span {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: #e8e9ff;
  color: #655cf0;
  font-weight: 950;
}

.report-card-heading small {
  display: block;
  color: #7a849e;
  font-size: 11px;
  font-weight: 800;
}

.report-card-heading h2,
.growth-title h2 {
  margin: 0;
  color: #11183f;
  font-size: 18px;
  font-weight: 950;
}

.conclusion-card > p {
  margin: 18px 0 16px;
  color: #303957;
  font-size: 14px;
  line-height: 1.75;
}

.conclusion-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.conclusion-meta span {
  padding: 5px 10px;
  border-radius: 999px;
  background: #fff;
  color: #5d65a1;
  font-size: 12px;
  font-weight: 800;
}

.round-card-copy > small {
  display: inline-flex;
  width: max-content;
  max-width: 100%;
  margin-bottom: 8px;
  padding: 3px 8px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--round) 10%, #fff);
  color: var(--round);
  font-size: 11px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diagnosis-section {
  display: grid;
  gap: 16px;
}

.diagnosis-panel {
  display: grid;
  gap: 15px;
  padding: 22px;
  border: 1px solid #e1e6f2;
  border-radius: 17px;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 12px 34px rgb(51 65 111 / 6%);
  animation: card-arrive 560ms ease both;
}

.diagnosis-heading {
  display: flex;
  gap: 13px;
  align-items: center;
}

.diagnosis-heading > span {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: #fff2ec;
  color: #dc6a37;
  font-weight: 950;
}

.diagnosis-heading small {
  display: block;
  color: #7a849e;
  font-size: 11px;
  font-weight: 800;
}

.diagnosis-heading h2 {
  margin: 0;
  color: #11183f;
  font-size: 18px;
  font-weight: 950;
}

.diagnosis-list,
.action-plan-list,
.round-review-list {
  display: grid;
  gap: 10px;
}

.diagnosis-item,
.action-plan-list article,
.round-review-list article {
  display: grid;
  gap: 9px;
  padding: 15px;
  border: 1px solid #e7ebf5;
  border-radius: 13px;
  background: #f9fbff;
}

.diagnosis-item.high {
  border-color: #f1b6ad;
  background: #fff8f7;
}
.diagnosis-item.medium {
  border-color: #f0cf8b;
  background: #fffaf0;
}
.diagnosis-item.low {
  border-color: #cbd8ff;
  background: #f7f9ff;
}

.diagnosis-item header,
.action-plan-list header,
.round-review-list header {
  display: flex;
  gap: 12px;
  align-items: start;
  justify-content: space-between;
}

.diagnosis-item strong,
.action-plan-list strong,
.round-review-list strong {
  color: #1d2748;
  font-size: 15px;
}

.diagnosis-item header span,
.action-plan-list header span,
.round-review-list header span {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: #fff;
  color: #626ef0;
  font-size: 11px;
  font-weight: 900;
}

.diagnosis-item p,
.action-plan-list p,
.round-review-list p {
  margin: 0;
  color: #3d4864;
  font-size: 13px;
  line-height: 1.65;
}

.diagnosis-item b,
.round-review-list b {
  margin-right: 8px;
  color: #7a849e;
  font-size: 12px;
}

.diagnosis-item ul,
.followup-panel ul {
  display: grid;
  gap: 7px;
  margin: 0;
  padding-left: 18px;
  color: #4d5874;
  font-size: 13px;
  line-height: 1.55;
}

.action-plan-list ol {
  display: grid;
  gap: 7px;
  margin: 0;
  padding-left: 18px;
  color: #3d4864;
  font-size: 13px;
  line-height: 1.6;
}

.round-review-panel,
.followup-panel {
  background: linear-gradient(135deg, rgb(255 255 255 / 96%), rgb(246 249 255 / 94%));
}

.round-review-list {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.round-review-list small {
  color: #7a849e;
  font-size: 12px;
  font-weight: 800;
}

.analysis-card ul,
.growth-card ul {
  display: grid;
  gap: 9px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.analysis-card li,
.growth-card li {
  position: relative;
  padding-left: 18px;
  color: #3d465f;
  font-size: 13px;
  line-height: 1.65;
}

.analysis-card li::before,
.growth-card li::before {
  position: absolute;
  top: 8px;
  left: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent, #7664f2);
  content: "";
}

.growth-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.growth-card {
  --accent: #5e75ef;
  min-height: 190px;
  padding: 22px;
}

.growth-card.weaknesses {
  --accent: #ef9a3c;
}

.growth-card.suggestions {
  --accent: #e96394;
}

.growth-title span {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 12%, white);
  color: var(--accent);
}

.growth-card > p {
  margin: 16px 0 0;
  color: #7a849c;
  font-size: 13px;
}

.memory-footnote {
  display: flex;
  gap: 9px;
  align-items: center;
  min-height: 50px;
  padding: 14px 20px;
  border: 1px solid #e5e9f2;
  border-radius: 14px;
  background: rgb(250 251 254 / 94%);
  color: #75809a;
  font-size: 13px;
}

@media (max-width: 980px) {
  .quality-body,
  .report-insights,
  .growth-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .quality-metrics,
  .score-source-list article {
    grid-template-columns: 1fr;
  }

  .quality-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .quality-heading strong {
    width: 100%;
    height: auto;
    min-height: 52px;
    border-radius: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .detail-workspace::before,
  .detail-workspace::after,
  .overview-art img,
  .notice-character img,
  .round-score-card,
  .chart-card,
  .round-row,
  .report-quality-panel,
  .score-track i,
  .radar-fill,
  .radar-wrap circle,
  .radar-mascot,
  .trend-line,
  .trend-area,
  .trend-point circle,
  .trend-current line,
  .trend-mascot {
    animation: none;
  }
}
</style>
