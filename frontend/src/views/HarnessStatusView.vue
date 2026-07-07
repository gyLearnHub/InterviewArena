<template>
  <section class="harness-page">
    <header class="harness-hero">
      <div class="hero-copy">
        <p>系统运行与恢复状态</p>
        <h1>Harness 状态</h1>
        <span>追踪多 Agent 流程、规则评测、重试与恢复状态</span>
      </div>

      <div class="hero-visual" aria-hidden="true">
        <img class="hero-asset" :src="harnessAssets.hero" alt="" />
      </div>

      <button class="sync-button" type="button" :disabled="loading" @click="loadHarnessStatus">
        <img class="sync-asset" :src="harnessAssets.sync" alt="" aria-hidden="true" />
        {{ loading ? "同步中..." : "重新同步" }}
      </button>
    </header>

    <section v-if="loading && !harnessStatus" class="empty-state">
      <strong>正在读取 Harness 状态</strong>
      <span>会优先同步最近一次面试的状态字段和运行记录。</span>
    </section>

    <section v-else-if="!latestInterview" class="empty-state">
      <strong>暂无 Harness 状态</strong>
      <span>完成或开始一次多轮面试后，这里会显示运行状态、规则评测和恢复点。</span>
    </section>

    <template v-else>
      <p class="status-message" :class="{ error: hasError }">
        <span aria-hidden="true">i</span>
        {{ message || "当前展示后端返回的真实 Harness 运行明细。" }}
      </p>

      <section class="interview-switcher" aria-label="Harness 面试记录">
        <div>
          <span>当前面试</span>
          <strong>{{ selectedInterview?.target_position || "-" }}</strong>
          <small>{{ history.length }} 场面试记录</small>
        </div>
        <label>
          <span>切换记录</span>
          <select
            v-model.number="selectedInterviewId"
            :disabled="loading"
            @change="handleSelectedInterviewChange"
          >
            <option
              v-for="item in sortedHistory"
              :key="item.interview_id"
              :value="item.interview_id"
            >
              #{{ item.interview_id }} {{ item.target_position }} ·
              {{ statusLabel(item.overall_status || item.status) }}
            </option>
          </select>
        </label>
        <time :datetime="selectedInterviewActivityAt || undefined">
          {{ formatDate(selectedInterviewActivityAt) }}
        </time>
      </section>

      <section class="summary-grid" aria-label="Harness 状态总览">
        <article class="metric-card" :class="statusTone">
          <div class="metric-icon" aria-hidden="true">
            <img :src="harnessAssets.status" alt="" />
          </div>
          <div>
            <span>当前状态</span>
            <strong>{{ harnessStatusLabel }}</strong>
            <small>{{ selectedInterview?.target_position || "-" }}</small>
          </div>
          <i class="metric-dot"></i>
          <svg class="metric-wave" viewBox="0 0 220 42" aria-hidden="true">
            <path
              d="M0 32 C28 31 42 32 58 31 C77 30 74 22 94 24 C116 27 116 17 136 18 C158 20 164 32 188 30 C204 29 208 24 220 23"
            />
          </svg>
        </article>
        <article class="metric-card">
          <div class="metric-icon blue" aria-hidden="true">
            <img :src="harnessAssets.run" alt="" />
          </div>
          <div>
            <span>最近运行</span>
            <strong>{{ lastRunText }}</strong>
            <small>{{ latestInterviewTimeText }}</small>
          </div>
          <i class="metric-dot blue"></i>
        </article>
        <article class="metric-card">
          <div class="metric-icon violet" aria-hidden="true">
            <img :src="harnessAssets.rules" alt="" />
          </div>
          <div>
            <span>规则通过</span>
            <strong>{{ rulePassText }}</strong>
            <small>{{ ruleSummaryText }}</small>
          </div>
          <i class="metric-dot violet"></i>
        </article>
        <article class="metric-card warning">
          <div class="metric-icon orange" aria-hidden="true">
            <img :src="harnessAssets.retry" alt="" />
          </div>
          <div>
            <span>重试 / 降级</span>
            <strong>{{ retryCount }} / {{ degradationCount }}</strong>
            <small>{{ recoveryText }}</small>
          </div>
          <i class="metric-dot orange"></i>
        </article>
      </section>

      <div class="harness-grid">
        <section class="panel rules-panel">
          <div class="panel-heading">
            <div class="panel-title">
              <span class="panel-icon" aria-hidden="true">
                <img :src="harnessAssets.rulesEmpty" alt="" />
              </span>
              <h2>规则评测概览</h2>
            </div>
          </div>
          <div v-if="ruleRows.length" class="rule-list">
            <div v-for="rule in ruleRows" :key="rule.name" class="rule-row">
              <span>{{ rule.name }}</span>
              <div class="rule-track">
                <i :class="rule.tone" :style="{ width: `${rule.percent}%` }"></i>
              </div>
              <strong>{{ rule.label }}</strong>
            </div>
          </div>
          <div v-else class="illustrated-empty">
            <img
              class="empty-asset rules-empty-asset"
              :src="harnessAssets.rulesEmpty"
              alt=""
              aria-hidden="true"
            />
            <strong>暂无规则校验结果</strong>
            <p>后端尚未生成这场面试的规则评测结果</p>
            <div class="rule-chips">
              <span v-for="tag in ruleTags" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </section>

        <section class="panel trend-panel">
          <div class="panel-heading">
            <div class="panel-title">
              <span class="panel-icon" aria-hidden="true">
                <img :src="harnessAssets.health" alt="" />
              </span>
              <h2>运行分布</h2>
            </div>
            <small>最近 {{ traces.length }} 条 Trace</small>
          </div>
          <div class="distribution-board">
            <div class="status-bars">
              <div v-for="bar in distributionRows" :key="bar.status" class="status-bar">
                <strong>{{ bar.count }}</strong>
                <div><i :class="bar.tone" :style="{ height: `${bar.percent}%` }"></i></div>
                <span>{{ bar.label }}</span>
              </div>
            </div>
            <div class="donut-wrap">
              <div class="donut" :style="{ '--complete-percent': `${completionPercent}%` }">
                <strong>{{ totalRuns }}</strong>
                <span>总运行数</span>
              </div>
              <p>
                <i></i> 已完成 <strong>{{ completionPercent }}%</strong>
              </p>
            </div>
          </div>
        </section>

        <section class="panel trace-panel">
          <div class="panel-heading">
            <div class="panel-title">
              <span class="panel-icon" aria-hidden="true">
                <img :src="harnessAssets.traceEmpty" alt="" />
              </span>
              <h2>最近 Trace</h2>
            </div>
            <RouterLink :to="runDetailTarget">
              <img class="link-asset" :src="harnessAssets.traceEmpty" alt="" aria-hidden="true" />
              运行详情
            </RouterLink>
          </div>
          <div v-if="recentTraces.length" class="trace-table">
            <div class="trace-head">
              <span>Trace ID</span>
              <span>目标岗位</span>
              <span>状态</span>
              <span>开始时间</span>
              <span>持续时间</span>
            </div>
            <article v-for="trace in recentTraces" :key="trace.id">
              <strong>{{ trace.node_id }}</strong>
              <span>{{ selectedInterview?.target_position || "-" }}</span>
              <em :class="statusClass(trace.status)">{{ statusLabel(trace.status) }}</em>
              <small>{{ formatDate(trace.created_at || trace.updated_at) }}</small>
              <small>{{ formatElapsed(trace.elapsed_ms) }}</small>
            </article>
          </div>
          <div v-else class="table-empty">
            <img :src="harnessAssets.traceEmpty" alt="" aria-hidden="true" />
            暂无 Trace 记录
          </div>
        </section>

        <section class="panel checkpoint-panel">
          <div class="panel-heading">
            <div class="panel-title">
              <span class="panel-icon" aria-hidden="true">
                <img :src="harnessAssets.checkpoint" alt="" />
              </span>
              <h2>Checkpoint</h2>
            </div>
          </div>
          <div v-if="recentCheckpoints.length" class="checkpoint-list">
            <article v-for="checkpoint in recentCheckpoints" :key="checkpoint.id">
              <strong>{{ checkpointName(checkpoint.checkpoint_type) }}</strong>
              <span>{{ checkpoint.node_id }}</span>
              <small>{{ formatDate(checkpoint.created_at) }}</small>
              <em :class="statusClass(checkpoint.status)">{{
                checkpointStatusLabel(checkpoint.status)
              }}</em>
            </article>
          </div>
          <div v-else class="checkpoint-empty">
            <img :src="harnessAssets.checkpoint" alt="" aria-hidden="true" />
            <strong>暂无恢复点</strong>
            <p>当前未生成任何可恢复的 Checkpoint</p>
          </div>
        </section>
      </div>

      <footer class="health-strip" aria-label="系统健康度">
        <div>
          <span class="health-icon" aria-hidden="true">
            <img :src="harnessAssets.health" alt="" />
          </span>
          <strong>系统健康度</strong>
          <em :class="healthTone">{{ healthLabel }}</em>
        </div>
        <dl>
          <dt>服务可用性</dt>
          <dd>{{ serviceAvailability }}</dd>
          <dt>任务队列</dt>
          <dd>{{ pendingCount }}</dd>
          <dt>平均响应时间</dt>
          <dd>{{ averageLatencyText }}</dd>
          <dt>上次同步</dt>
          <dd>{{ lastSyncTimeText }}</dd>
        </dl>
        <button type="button" @click="showHealthDetails = !showHealthDetails">
          {{ showHealthDetails ? "收起健康详情" : "查看健康详情" }}
        </button>
      </footer>

      <section v-if="showHealthDetails" class="health-detail-panel" aria-label="健康详情">
        <article>
          <span>运行状态</span>
          <strong>{{ harnessStatusLabel }}</strong>
          <small>{{ selectedInterview?.target_position || "-" }}</small>
        </article>
        <article>
          <span>Trace 总数</span>
          <strong>{{ totalRuns }}</strong>
          <small>完成率 {{ completionPercent }}%</small>
        </article>
        <article>
          <span>失败 Trace</span>
          <strong>{{ distributionCounts.get("failed") || 0 }}</strong>
          <small>{{ ruleSummaryText }}</small>
        </article>
        <article>
          <span>重试 / 降级</span>
          <strong>{{ retryCount }} / {{ degradationCount }}</strong>
          <small>{{ recoveryText }}</small>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  ApiError,
  getInterviewHarnessStatus,
  listHistory,
  type HarnessCheckpointItem,
  type HarnessRuleEvaluationItem,
  type HarnessStatus,
  type HarnessTraceItem,
  type HistoryItem,
  type InterviewHarnessStatus
} from "../api";
import checkpointEmptyAsset from "../assets/harness/checkpoint-empty.png";
import healthIconAsset from "../assets/harness/health-icon.png";
import heroAsset from "../assets/harness/hero-character.png";
import metricRetryAsset from "../assets/harness/metric-retry.png";
import metricRulesAsset from "../assets/harness/metric-rules.png";
import metricRunAsset from "../assets/harness/metric-run.png";
import metricStatusAsset from "../assets/harness/metric-status.png";
import rulesEmptyAsset from "../assets/harness/rules-empty.png";
import syncGlyphAsset from "../assets/harness/sync-glyph.png";
import traceEmptyAsset from "../assets/harness/trace-empty.png";

type RuleRow = {
  name: string;
  percent: number;
  label: string;
  tone: "ok" | "warning" | "danger";
};

type StatusBar = {
  status: string;
  label: string;
  count: number;
  percent: number;
  tone: "ok" | "info" | "warning" | "danger";
};

const history = ref<HistoryItem[]>([]);
const harnessStatus = ref<InterviewHarnessStatus | null>(null);
const traces = ref<HarnessTraceItem[]>([]);
const evaluations = ref<HarnessRuleEvaluationItem[]>([]);
const checkpoints = ref<HarnessCheckpointItem[]>([]);
const loading = ref(false);
const message = ref("");
const hasError = ref(false);
const selectedInterviewId = ref<number | null>(null);
const lastSyncedAt = ref<Date | null>(null);
const showHealthDetails = ref(false);
const ruleTags = ["流程完整性", "题目去重", "评分一致性", "Schema 合规"];
const distributionStatuses = ["completed", "retrying", "degraded", "failed"] as const;
const harnessAssets = {
  hero: heroAsset,
  status: metricStatusAsset,
  run: metricRunAsset,
  rules: metricRulesAsset,
  retry: metricRetryAsset,
  sync: syncGlyphAsset,
  rulesEmpty: rulesEmptyAsset,
  traceEmpty: traceEmptyAsset,
  checkpoint: checkpointEmptyAsset,
  health: healthIconAsset
};

const sortedHistory = computed(() =>
  [...history.value].sort((a, b) => latestTime(b) - latestTime(a))
);
const latestInterview = computed(() => sortedHistory.value[0] || null);
const selectedInterview = computed(() => {
  return (
    sortedHistory.value.find((item) => item.interview_id === selectedInterviewId.value) ||
    latestInterview.value
  );
});
const selectedInterviewActivityAt = computed(() =>
  selectedInterview.value ? latestActivityAt(selectedInterview.value) : null
);
const currentHarnessStatus = computed<HarnessStatus | string>(() => {
  if (traces.value.some((trace) => trace.status === "running")) {
    return "running";
  }
  if (traces.value.some((trace) => trace.status === "failed")) {
    return "failed";
  }
  return harnessStatus.value?.harness_status || "pending";
});
const statusTone = computed(() => statusClass(currentHarnessStatus.value));
const harnessStatusLabel = computed(() => statusLabel(currentHarnessStatus.value));
const retryCount = computed(() =>
  traces.value.reduce((total, trace) => total + (trace.retry_records?.length || 0), 0)
);
const degradationCount = computed(
  () =>
    traces.value.reduce((total, trace) => total + (trace.degradation_records?.length || 0), 0) +
    (harnessStatus.value?.had_degradation ? 1 : 0)
);
const recoveryText = computed(() => {
  const count = harnessStatus.value?.recovery_count || 0;
  return count > 0 ? `已恢复 ${count} 次` : "暂无恢复记录";
});
const lastRunText = computed(() => {
  const value = latestTraceTime(traces.value[0]);
  return value ? formatTime(value) : "暂无记录";
});
const latestInterviewTimeText = computed(() =>
  selectedInterviewActivityAt.value ? formatDate(selectedInterviewActivityAt.value) : "-"
);
const passedRuleCount = computed(
  () =>
    evaluations.value.filter((item) => ["passed", "pass"].includes(item.status.toLowerCase()))
      .length
);
const displayedRulePassCount = computed(
  () => ruleRows.value.filter((item) => item.tone === "ok").length
);
const rulePassText = computed(() => {
  if (evaluations.value.length) {
    return `${passedRuleCount.value} / ${evaluations.value.length}`;
  }
  return ruleRows.value.length ? `${displayedRulePassCount.value} / ${ruleRows.value.length}` : "-";
});
const ruleSummaryText = computed(() => {
  if (!evaluations.value.length) {
    if (traces.value.length) {
      return "可查看 Trace 校验状态";
    }
    return "后端暂无规则评测";
  }
  const failed = evaluations.value.filter((item) => item.status.toLowerCase() === "failed").length;
  return failed ? `${failed} 条需关注` : "规则校验稳定";
});
const ruleRows = computed<RuleRow[]>(() => {
  if (evaluations.value.length) {
    return evaluations.value.slice(0, 5).map((item) => ({
      name: ruleName(item.rule_name),
      percent:
        item.status.toLowerCase() === "failed"
          ? 44
          : item.status.toLowerCase() === "warning"
            ? 72
            : 100,
      label: evaluationStatusLabel(item.status),
      tone:
        item.status.toLowerCase() === "failed"
          ? "danger"
          : item.status.toLowerCase() === "warning"
            ? "warning"
            : "ok"
    }));
  }
  if (traces.value.length) {
    return traces.value.slice(0, 5).map((trace) => ({
      name: ruleName(trace.validation_status),
      percent:
        trace.validation_status === "failed"
          ? 48
          : trace.validation_status === "warning"
            ? 76
            : 100,
      label: validationStatusLabel(trace.validation_status),
      tone:
        trace.validation_status === "failed"
          ? "danger"
          : trace.validation_status === "warning"
            ? "warning"
            : "ok"
    }));
  }
  return [];
});
const distributionCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const trace of traces.value) {
    counts.set(trace.status, (counts.get(trace.status) || 0) + 1);
  }
  return counts;
});
const distributionRows = computed<StatusBar[]>(() => {
  const counts = distributionCounts.value;
  const max = Math.max(1, ...counts.values());
  return distributionStatuses.map((status) => {
    const count = counts.get(status) || (status === "completed" ? counts.get("succeeded") || 0 : 0);
    return {
      status,
      label: compactStatusLabel(status),
      count,
      percent: count > 0 ? Math.max(20, Math.round((count / max) * 100)) : 0,
      tone: statusClass(status)
    };
  });
});
const totalRuns = computed(() => {
  const total = [...distributionCounts.value.values()].reduce((sum, count) => sum + count, 0);
  return total;
});
const completedRunCount = computed(
  () =>
    (distributionCounts.value.get("completed") || 0) +
    (distributionCounts.value.get("succeeded") || 0)
);
const completionPercent = computed(() =>
  totalRuns.value > 0 ? Math.round((completedRunCount.value / totalRuns.value) * 100) : 0
);
const pendingCount = computed(
  () =>
    (distributionCounts.value.get("pending") || 0) + (distributionCounts.value.get("running") || 0)
);
const serviceAvailability = computed(() => {
  if (totalRuns.value === 0) {
    return "-";
  }
  const failed = distributionCounts.value.get("failed") || 0;
  return `${Math.round(((totalRuns.value - failed) / totalRuns.value) * 100)}%`;
});
const averageLatencyText = computed(() => {
  const elapsedValues = traces.value
    .map((trace) => trace.elapsed_ms)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!elapsedValues.length) {
    return "-";
  }
  const average = elapsedValues.reduce((sum, value) => sum + value, 0) / elapsedValues.length;
  return formatElapsed(average);
});
const lastSyncTimeText = computed(() => {
  return lastSyncedAt.value ? lastSyncedAt.value.toLocaleString() : "暂无时间";
});
const recentTraces = computed(() => traces.value.slice(0, 5));
const recentCheckpoints = computed(() => checkpoints.value.slice(0, 5));
const healthLabel = computed(() => {
  if (hasError.value) {
    return "需关注";
  }
  return ["failed", "retrying", "degraded", "paused"].includes(currentHarnessStatus.value)
    ? "观察中"
    : "健康";
});
const healthTone = computed(() => (hasError.value ? "danger" : statusTone.value));
const runDetailTarget = computed(() => {
  const interview = selectedInterview.value;
  if (!interview) {
    return "/history";
  }
  return interview.status === "finished"
    ? `/history/${interview.interview_id}`
    : `/interviews/multi/${interview.interview_id}`;
});

async function loadHarnessStatus() {
  loading.value = true;
  message.value = "";
  hasError.value = false;
  try {
    history.value = await listHistory();
    const interview = ensureSelectedInterview();
    if (!interview) {
      resetHarnessDetails();
      return;
    }

    await loadSelectedInterviewDetails(interview.interview_id);
    lastSyncedAt.value = new Date();
  } catch (error) {
    resetHarnessDetails();
    hasError.value = true;
    message.value = error instanceof ApiError ? error.message : "Harness 状态加载失败。";
  } finally {
    loading.value = false;
  }
}

async function handleSelectedInterviewChange() {
  if (!selectedInterviewId.value) {
    return;
  }
  loading.value = true;
  message.value = "";
  hasError.value = false;
  try {
    await loadSelectedInterviewDetails(selectedInterviewId.value);
    lastSyncedAt.value = new Date();
  } catch (error) {
    resetHarnessDetails();
    hasError.value = true;
    message.value = error instanceof ApiError ? error.message : "Harness 状态加载失败。";
  } finally {
    loading.value = false;
  }
}

async function loadSelectedInterviewDetails(interviewId: number) {
  resetHarnessDetails();
  const detail = await getInterviewHarnessStatus(interviewId);
  harnessStatus.value = detail;
  traces.value = detail.traces;
  evaluations.value = detail.evaluations;
  checkpoints.value = detail.checkpoints;
  if (!detail.traces.length && !detail.evaluations.length && !detail.checkpoints.length) {
    message.value = "后端暂无这场面试的 Harness 运行明细。";
  }
}

function resetHarnessDetails() {
  harnessStatus.value = null;
  traces.value = [];
  evaluations.value = [];
  checkpoints.value = [];
}

function ensureSelectedInterview(): HistoryItem | null {
  if (!sortedHistory.value.length) {
    selectedInterviewId.value = null;
    return null;
  }
  const current = sortedHistory.value.find(
    (item) => item.interview_id === selectedInterviewId.value
  );
  if (current) {
    return current;
  }
  const latest = sortedHistory.value[0];
  selectedInterviewId.value = latest.interview_id;
  return latest;
}

function latestTime(item: HistoryItem): number {
  const value = latestActivityAt(item);
  return value ? new Date(value).getTime() : 0;
}

function latestActivityAt(item: HistoryItem): string | null {
  return item.updated_at || item.ended_at || item.started_at || item.created_at;
}

function latestTraceTime(trace?: HarnessTraceItem): string | null {
  if (!trace) {
    return null;
  }
  return trace.updated_at || trace.created_at || null;
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "等待启动",
    running: "运行正常",
    retrying: "自动重试中",
    degraded: "备用流程",
    paused: "已暂停",
    failed: "步骤失败",
    completed: "已完成",
    succeeded: "已完成",
    available: "可恢复"
  };
  return map[status] || status;
}

function compactStatusLabel(status: string): string {
  const map: Record<string, string> = {
    completed: "已完成",
    succeeded: "已完成",
    retrying: "重试中",
    degraded: "降级",
    failed: "失败"
  };
  return map[status] || statusLabel(status);
}

function statusClass(status: string): "ok" | "info" | "warning" | "danger" {
  if (["failed", "error"].includes(status)) {
    return "danger";
  }
  if (["retrying", "degraded", "paused", "warning"].includes(status)) {
    return "warning";
  }
  if (["running", "pending"].includes(status)) {
    return "info";
  }
  return "ok";
}

function evaluationStatusLabel(status: string): string {
  const map: Record<string, string> = {
    passed: "通过",
    pass: "通过",
    warning: "警告",
    failed: "未通过",
    fail: "未通过"
  };
  return map[status.toLowerCase()] || status;
}

function validationStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "待校验",
    passed: "通过",
    warning: "警告",
    failed: "失败"
  };
  return map[status] || status;
}

function checkpointStatusLabel(status: string): string {
  const map: Record<string, string> = {
    available: "可恢复",
    saved: "已保存",
    completed: "已保存",
    failed: "失败"
  };
  return map[status] || status;
}

function checkpointName(type: string): string {
  const map: Record<string, string> = {
    interview_created: "面试创建",
    question_generated: "问题生成",
    answer_saved: "回答保存",
    round_finished: "轮次完成",
    interview_finished: "总评生成"
  };
  return map[type] || type;
}

function ruleName(name: string): string {
  const map: Record<string, string> = {
    context_isolation: "上下文隔离",
    score_evidence: "评分证据",
    round_completeness: "四轮完整性",
    owner_isolation: "用户隔离",
    checkpoint_created: "恢复点创建",
    passed: "输出校验",
    warning: "输出校验",
    failed: "输出校验",
    pending: "输出校验"
  };
  return map[name] || name;
}

function formatDate(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "暂无时间";
}

function formatTime(value?: string | null): string {
  if (!value) {
    return "暂无记录";
  }
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatElapsed(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`;
  }
  return `${(value / 1000).toFixed(1)}s`;
}

onMounted(() => {
  void loadHarnessStatus();
});
</script>

<style scoped>
.harness-page {
  display: grid;
  gap: 28px;
  width: 100%;
  max-width: min(1360px, 100%);
  margin: 0 auto;
  color: var(--gray-900, #172033);
}

.harness-hero {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
}

.harness-hero p {
  margin: 0 0 8px;
  color: var(--brand-700, #1f64bf);
  font-size: 13px;
  font-weight: 800;
}

.harness-hero h1 {
  margin: 0;
  color: var(--gray-900, #172033);
  font-size: 42px;
  line-height: 1.12;
}

.harness-hero span {
  display: block;
  margin-top: 8px;
  color: var(--gray-500, #758195);
  font-size: 17px;
  font-weight: 700;
}

.harness-hero button,
.panel-heading a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 0 16px;
  border: 1px solid var(--brand-200, #c8e3ff);
  border-radius: 10px;
  background: var(--gray-0, #fff);
  color: var(--brand-700, #1f64bf);
  font-weight: 800;
}

.harness-hero button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.empty-state {
  display: grid;
  place-items: center;
  gap: 10px;
  min-height: 360px;
  padding: 32px;
  border: 1px dashed var(--gray-200, #dfe5ec);
  border-radius: 18px;
  background: rgb(255 255 255 / 78%);
  text-align: center;
}

.empty-state strong {
  color: var(--gray-900, #172033);
  font-size: 24px;
}

.empty-state span,
.panel-empty {
  color: var(--gray-500, #758195);
  font-size: 16px;
}

.status-message {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--brand-200, #c8e3ff);
  border-radius: 12px;
  background: var(--brand-50, #f2f8ff);
  color: var(--brand-700, #1f64bf);
  font-weight: 700;
}

.status-message.error {
  border-color: rgb(223 77 95 / 30%);
  background: rgb(223 77 95 / 8%);
  color: var(--danger, #df4d5f);
}

.summary-grid,
.harness-grid {
  display: grid;
  gap: 24px;
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.harness-grid {
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.98fr);
}

.metric-card,
.panel {
  min-width: 0;
  border: 1px solid rgb(207 216 235 / 78%);
  border-radius: 18px;
  background: rgb(255 255 255 / 82%);
  box-shadow: 0 24px 48px rgb(45 68 116 / 8%);
}

.metric-card {
  display: grid;
  gap: 12px;
  min-height: 142px;
  padding: 24px;
}

.metric-card span,
.metric-card small,
.panel-heading small,
.trace-list span,
.trace-list small,
.checkpoint-list span,
.checkpoint-list small {
  color: var(--gray-500, #758195);
  font-weight: 700;
}

.metric-card span {
  position: relative;
  padding-left: 22px;
}

.metric-card span::before {
  position: absolute;
  top: 5px;
  left: 0;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--status-color, #3b9cff);
  content: "";
}

.metric-card strong {
  color: var(--gray-900, #172033);
  font-size: 29px;
  line-height: 1.12;
}

.ok {
  --status-color: #22a06b;
}

.info {
  --status-color: #3b9cff;
}

.warning {
  --status-color: #ff9a3d;
}

.danger {
  --status-color: #df4d5f;
}

.panel {
  display: grid;
  align-content: start;
  gap: 22px;
  min-height: 306px;
  padding: 28px 32px;
}

.panel-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.panel-heading h2 {
  margin: 0;
  color: var(--gray-900, #172033);
  font-size: 24px;
}

.rule-list,
.trace-list,
.checkpoint-list {
  display: grid;
  gap: 14px;
}

.rule-row {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr) 64px;
  gap: 18px;
  align-items: center;
}

.rule-row span {
  color: var(--gray-700, #3b4658);
  font-weight: 800;
}

.rule-track {
  height: 14px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--gray-100, #eef2f7);
}

.rule-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--status-color, #22a06b);
}

.rule-row strong {
  color: var(--status-color, #22a06b);
  text-align: right;
}

.status-bars {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  align-items: end;
  min-height: 210px;
}

.status-bar {
  display: grid;
  grid-template-rows: auto 150px auto;
  gap: 10px;
  min-width: 0;
  text-align: center;
}

.status-bar span,
.status-bar strong {
  overflow: hidden;
  color: var(--gray-700, #3b4658);
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-bar div {
  display: grid;
  align-items: end;
  overflow: hidden;
  border-radius: 12px;
  background: var(--gray-100, #eef2f7);
}

.status-bar i {
  display: block;
  min-height: 18px;
  border-radius: 12px 12px 0 0;
  background: var(--status-color, #3b9cff);
}

.trace-list article,
.checkpoint-list article {
  display: grid;
  gap: 12px;
  align-items: center;
  min-height: 68px;
  padding: 14px 16px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgb(250 252 255 / 94%), rgb(244 247 252 / 94%));
}

.trace-list article {
  grid-template-columns: minmax(0, 1fr) auto 138px;
}

.checkpoint-list article {
  grid-template-columns: minmax(112px, 0.95fr) minmax(0, 1fr) 132px auto;
}

.trace-list strong,
.checkpoint-list strong {
  display: block;
  overflow: hidden;
  color: var(--gray-900, #172033);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-list span,
.checkpoint-list span,
.trace-list small,
.checkpoint-list small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-list em,
.checkpoint-list em {
  padding: 6px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--status-color) 12%, white);
  color: var(--status-color);
  font-style: normal;
  font-weight: 800;
  white-space: nowrap;
}

.panel-empty {
  display: grid;
  place-items: center;
  min-height: 184px;
  margin: 0;
  border: 1px dashed var(--gray-200, #dfe5ec);
  border-radius: 14px;
  font-weight: 800;
}

@media (max-width: 1180px) {
  .summary-grid,
  .harness-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 760px) {
  .harness-hero {
    align-items: stretch;
    flex-direction: column;
  }

  .harness-hero h1 {
    font-size: 32px;
  }

  .summary-grid,
  .harness-grid,
  .trace-list article,
  .checkpoint-list article,
  .rule-row {
    grid-template-columns: 1fr;
  }

  .panel {
    padding: 22px;
  }

  .status-bars {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .rule-row strong {
    text-align: left;
  }
}
</style>

<style scoped>
.harness-page {
  --harness-ink: #111a31;
  --harness-muted: #67748a;
  --harness-line: #dbe5f4;
  --harness-soft: #f5f8ff;
  --harness-green: #28b978;
  --harness-blue: #3d87f7;
  --harness-violet: #7a62ee;
  --harness-orange: #ff923d;
  --harness-red: #df4d5f;

  display: grid;
  gap: 18px;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  color: var(--harness-ink);
}

.harness-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 430px) auto;
  gap: 22px;
  align-items: center;
  min-height: 150px;
  overflow: hidden;
  padding: 26px 28px;
  border: 1px solid rgb(215 224 242 / 72%);
  border-radius: 8px;
  background:
    linear-gradient(
      100deg,
      rgb(255 255 255 / 96%) 0%,
      rgb(248 251 255 / 94%) 48%,
      rgb(238 242 255 / 88%) 100%
    ),
    radial-gradient(circle at 76% 10%, rgb(124 108 255 / 18%), transparent 30%);
  box-shadow: 0 22px 48px rgb(50 67 109 / 8%);
}

.hero-copy {
  position: relative;
  z-index: 1;
}

.hero-copy p {
  margin: 0 0 8px;
  color: #2638da;
  font-size: 14px;
  font-weight: 900;
}

.hero-copy h1 {
  margin: 0;
  color: var(--harness-ink);
  font-size: clamp(34px, 4vw, 52px);
  line-height: 1.04;
}

.hero-copy span {
  display: block;
  margin-top: 10px;
  color: #53627a;
  font-size: 17px;
  font-weight: 700;
}

.hero-visual {
  position: relative;
  align-self: stretch;
  min-height: 126px;
  overflow: hidden;
}

.spark {
  position: absolute;
  width: 16px;
  height: 16px;
  z-index: 4;
}

.spark::before,
.spark::after {
  position: absolute;
  inset: 0;
  margin: auto;
  background: rgb(122 98 238 / 38%);
  content: "";
}

.spark::before {
  width: 2px;
  height: 16px;
}

.spark::after {
  width: 16px;
  height: 2px;
}

.spark-one {
  top: 20px;
  right: 18px;
}

.spark-two {
  right: 204px;
  bottom: 18px;
  transform: scale(0.7);
}

.sync-button {
  position: relative;
  z-index: 1;
  display: inline-flex;
  gap: 9px;
  align-items: center;
  justify-content: center;
  min-width: 138px;
  min-height: 48px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, #6654ff, #3f32df);
  box-shadow: 0 16px 30px rgb(83 71 235 / 34%);
  color: #fff;
  font-weight: 900;
}

.sync-button:hover:not(:disabled) {
  box-shadow: 0 18px 34px rgb(83 71 235 / 38%);
  color: #fff;
}

.harness-hero .sync-button {
  border-color: transparent;
  background: linear-gradient(135deg, #6654ff, #3f32df);
  box-shadow: 0 16px 30px rgb(83 71 235 / 34%);
  color: #fff;
}

.harness-hero .sync-button:hover:not(:disabled) {
  box-shadow: 0 18px 34px rgb(83 71 235 / 38%);
  color: #fff;
}

.status-message {
  display: flex;
  gap: 12px;
  align-items: center;
  min-height: 52px;
  margin: 0;
  padding: 0 20px;
  border: 1px solid #bed4ff;
  border-radius: 8px;
  background: rgb(246 249 255 / 88%);
  color: #2843ce;
  font-weight: 800;
}

.status-message > span {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #4568e8;
  color: #fff;
  font-family: Georgia, serif;
}

.status-message.error {
  border-color: rgb(223 77 95 / 32%);
  background: rgb(223 77 95 / 8%);
  color: var(--harness-red);
}

.interview-switcher {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 320px) auto;
  gap: 16px;
  align-items: center;
  min-height: 72px;
  padding: 14px 18px;
  border: 1px solid rgb(217 225 241 / 82%);
  border-radius: 8px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 14px 28px rgb(52 65 105 / 6%);
}

.interview-switcher > div,
.interview-switcher label {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.interview-switcher span,
.interview-switcher small,
.interview-switcher time {
  color: var(--harness-muted);
  font-size: 13px;
  font-weight: 800;
}

.interview-switcher strong {
  overflow: hidden;
  color: var(--harness-ink);
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.interview-switcher select {
  width: 100%;
  min-height: 38px;
  padding: 0 12px;
  border: 1px solid #dbe5f4;
  border-radius: 8px;
  background: #fff;
  color: var(--harness-ink);
  font-weight: 800;
}

.interview-switcher time {
  justify-self: end;
  white-space: nowrap;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
}

.metric-card {
  position: relative;
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
  min-height: 132px;
  overflow: hidden;
  padding: 24px;
  border: 1px solid rgb(217 225 241 / 82%);
  border-radius: 8px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 18px 38px rgb(52 65 105 / 7%);
}

.metric-icon {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  border-radius: 14px;
  background: linear-gradient(135deg, #27c47a, #21a763);
  box-shadow: 0 14px 28px rgb(40 185 120 / 28%);
  color: #fff;
}

.metric-icon.blue {
  background: linear-gradient(135deg, #55a6ff, #276fe7);
  box-shadow: 0 14px 28px rgb(61 135 247 / 28%);
}

.metric-icon.violet {
  background: linear-gradient(135deg, #957cff, #6546e9);
  box-shadow: 0 14px 28px rgb(122 98 238 / 26%);
}

.metric-icon.orange {
  background: linear-gradient(135deg, #ffb15b, #ff7c35);
  box-shadow: 0 14px 28px rgb(255 146 61 / 24%);
}

.metric-card span,
.metric-card small {
  display: block;
  overflow: hidden;
  color: var(--harness-muted);
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card strong {
  display: block;
  overflow: hidden;
  margin: 4px 0 2px;
  color: var(--harness-ink);
  font-size: clamp(24px, 2.1vw, 32px);
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-dot {
  position: absolute;
  top: 28px;
  right: 26px;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--harness-green);
}

.metric-dot.blue {
  background: var(--harness-blue);
}

.metric-dot.violet {
  background: #c6bcff;
}

.metric-dot.orange {
  background: var(--harness-orange);
}

.metric-wave {
  position: absolute;
  right: 12px;
  bottom: 10px;
  width: 45%;
  height: 34px;
  fill: none;
  stroke: rgb(40 185 120 / 42%);
  stroke-width: 3;
}

.harness-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.96fr) minmax(0, 1.04fr);
  gap: 18px;
}

.panel {
  display: grid;
  align-content: start;
  min-width: 0;
  min-height: 244px;
  padding: 22px;
  border: 1px solid rgb(217 225 241 / 82%);
  border-radius: 8px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 18px 38px rgb(52 65 105 / 7%);
}

.panel-heading {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.panel-title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.panel-title h2 {
  overflow: hidden;
  margin: 0;
  color: var(--harness-ink);
  font-size: 20px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-heading small {
  color: #5e6b83;
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
}

.panel-icon,
.health-icon {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: rgb(122 98 238 / 12%);
  color: #5f52ed;
}

.rule-list {
  display: grid;
  gap: 13px;
}

.rule-row {
  display: grid;
  grid-template-columns: minmax(106px, 0.78fr) minmax(0, 1fr) 70px;
  gap: 14px;
  align-items: center;
  min-height: 34px;
}

.rule-row span {
  overflow: hidden;
  color: #44516a;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-track {
  height: 11px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf2fb;
}

.rule-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--status-color, var(--harness-green));
}

.rule-row strong {
  color: var(--status-color, var(--harness-green));
  font-size: 14px;
  text-align: right;
}

.ok {
  --status-color: var(--harness-green);
}

.info {
  --status-color: var(--harness-blue);
}

.warning {
  --status-color: var(--harness-orange);
}

.danger {
  --status-color: var(--harness-red);
}

.illustrated-empty {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 10px;
  min-height: 214px;
  color: var(--harness-muted);
  text-align: center;
}

.illustrated-empty strong,
.checkpoint-empty strong {
  color: var(--harness-ink);
  font-size: 16px;
}

.illustrated-empty p,
.checkpoint-empty p {
  margin: 0;
  color: var(--harness-muted);
  font-weight: 700;
}

.rule-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  margin-top: 6px;
}

.rule-chips span {
  min-width: 92px;
  padding: 6px 12px;
  border-radius: 999px;
  background: #f0f3fa;
  color: #556178;
  font-size: 13px;
  font-weight: 800;
}

.distribution-board {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 168px;
  gap: 28px;
  align-items: center;
}

.status-bars {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 22px;
  align-items: end;
  min-height: 166px;
  padding: 8px 0 0;
  border-right: 1px solid #e6ebf4;
}

.status-bar {
  display: grid;
  grid-template-rows: 22px 124px 24px;
  gap: 8px;
  min-width: 0;
  text-align: center;
}

.status-bar strong {
  color: #0f8260;
  font-size: 14px;
}

.status-bar div {
  display: grid;
  align-items: end;
  overflow: hidden;
  border-bottom: 1px solid #dbe4ef;
  background: linear-gradient(
    180deg,
    transparent 0 32%,
    #edf2f7 32% 33%,
    transparent 33% 65%,
    #edf2f7 65% 66%,
    transparent 66%
  );
}

.status-bar i {
  display: block;
  min-height: 4px;
  border-radius: 7px 7px 0 0;
  background: var(--status-color, var(--harness-blue));
}

.status-bar span {
  overflow: hidden;
  color: #53617a;
  font-size: 13px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.donut-wrap {
  display: grid;
  justify-items: center;
  gap: 14px;
}

.donut {
  position: relative;
  display: grid;
  place-items: center;
  width: 116px;
  height: 116px;
  border-radius: 999px;
  background: conic-gradient(var(--harness-green) var(--complete-percent, 0%), #dcefe7 0);
}

.donut::after {
  position: absolute;
  inset: 22px;
  border-radius: inherit;
  background: #fff;
  content: "";
}

.donut strong,
.donut span {
  position: relative;
  z-index: 1;
}

.donut strong {
  align-self: end;
  color: var(--harness-ink);
  font-size: 24px;
  line-height: 1;
}

.donut span {
  align-self: start;
  color: #7b879a;
  font-size: 12px;
  font-weight: 800;
}

.donut-wrap p {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  color: #53617a;
  font-weight: 800;
}

.donut-wrap p i {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--harness-green);
}

.trace-panel a,
.health-strip a,
.health-strip button {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid #d7e2ff;
  border-radius: 8px;
  background: #fff;
  color: #315eea;
  font-size: 14px;
  font-weight: 900;
}

.health-strip button {
  cursor: pointer;
  font-family: inherit;
}

.trace-table {
  display: grid;
  overflow: hidden;
  border: 1px solid #e2e8f2;
  border-radius: 8px;
}

.trace-head,
.trace-table article {
  display: grid;
  grid-template-columns: minmax(150px, 1.2fr) minmax(96px, 0.8fr) 92px minmax(140px, 1fr) 92px;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 11px 16px;
}

.trace-head {
  min-height: 36px;
  background: #f6f8fc;
  color: #65728a;
  font-size: 12px;
  font-weight: 900;
}

.trace-table article {
  min-height: 56px;
  border-top: 1px solid #edf1f7;
  background: #fff;
}

.trace-table strong,
.trace-table span,
.trace-table small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-table strong {
  color: var(--harness-ink);
}

.trace-table span,
.trace-table small {
  color: var(--harness-muted);
  font-weight: 700;
}

.trace-table em,
.checkpoint-list em,
.health-strip em {
  justify-self: start;
  padding: 4px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--status-color, var(--harness-green)) 12%, white);
  color: var(--status-color, var(--harness-green));
  font-style: normal;
  font-size: 12px;
  font-weight: 900;
  white-space: nowrap;
}

.table-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 92px;
  border: 1px solid #e2e8f2;
  border-radius: 8px;
  color: var(--harness-muted);
  font-weight: 800;
}

.checkpoint-list {
  display: grid;
  gap: 10px;
}

.checkpoint-list article {
  display: grid;
  grid-template-columns: minmax(98px, 0.8fr) minmax(0, 1fr) minmax(132px, 0.92fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 54px;
  padding: 10px 12px;
  border: 1px solid #edf1f7;
  border-radius: 8px;
  background: linear-gradient(180deg, #fff, #fafcff);
}

.checkpoint-list strong,
.checkpoint-list span,
.checkpoint-list small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.checkpoint-list strong {
  color: var(--harness-ink);
}

.checkpoint-list span,
.checkpoint-list small {
  color: var(--harness-muted);
  font-weight: 700;
}

.checkpoint-empty {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 8px;
  min-height: 156px;
  text-align: center;
}

.health-strip {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  min-height: 58px;
  padding: 10px 14px;
  border: 1px solid rgb(217 225 241 / 82%);
  border-radius: 8px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 14px 28px rgb(52 65 105 / 6%);
}

.health-strip > div {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.health-strip strong {
  color: var(--harness-ink);
}

.health-strip dl {
  display: grid;
  grid-template-columns: repeat(4, auto auto);
  gap: 8px 18px;
  align-items: center;
  margin: 0;
  min-width: 0;
}

.health-strip dt,
.health-strip dd {
  margin: 0;
  white-space: nowrap;
}

.health-strip dt {
  color: #65728a;
  font-weight: 700;
}

.health-strip dd {
  color: #1d9b67;
  font-weight: 900;
}

.health-detail-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
  border: 1px solid rgb(217 225 241 / 82%);
  border-radius: 8px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 14px 28px rgb(52 65 105 / 6%);
}

.health-detail-panel article {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #edf1f7;
  border-radius: 8px;
  background: #fbfcff;
}

.health-detail-panel span,
.health-detail-panel small {
  overflow: hidden;
  color: var(--harness-muted);
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health-detail-panel strong {
  overflow: hidden;
  color: var(--harness-ink);
  font-size: 22px;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-state {
  min-height: 360px;
  border: 1px dashed #cbd7ea;
  border-radius: 8px;
  background: rgb(255 255 255 / 80%);
}

@media (max-width: 1220px) {
  .harness-hero {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .hero-visual {
    display: none;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .harness-grid {
    grid-template-columns: 1fr;
  }

  .health-strip,
  .health-strip dl {
    grid-template-columns: 1fr;
  }

  .interview-switcher {
    grid-template-columns: minmax(0, 1fr) minmax(220px, 300px);
  }

  .interview-switcher time {
    justify-self: start;
  }

  .health-strip a,
  .health-strip button {
    justify-self: start;
  }
}

@media (max-width: 760px) {
  .harness-page {
    gap: 14px;
  }

  .harness-hero,
  .interview-switcher,
  .summary-grid,
  .distribution-board,
  .health-strip {
    grid-template-columns: 1fr;
  }

  .health-detail-panel {
    grid-template-columns: 1fr;
  }

  .harness-hero {
    padding: 22px;
  }

  .sync-button {
    justify-self: start;
  }

  .metric-card {
    grid-template-columns: 54px minmax(0, 1fr);
    padding: 18px;
  }

  .metric-icon {
    width: 50px;
    height: 50px;
  }

  .panel {
    padding: 18px;
  }

  .status-bars {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-right: 0;
  }

  .trace-head {
    display: none;
  }

  .trace-table article,
  .checkpoint-list article,
  .rule-row {
    grid-template-columns: 1fr;
    align-items: start;
  }

  .candidate-list p {
    grid-column: auto;
  }

  .rule-row strong {
    text-align: left;
  }

  .health-strip dl {
    gap: 6px;
  }
}

.hero-asset {
  position: absolute;
  right: 0;
  bottom: -8px;
  z-index: 3;
  width: min(430px, 100%);
  max-height: 154px;
  object-fit: contain;
  object-position: right bottom;
  filter: drop-shadow(0 18px 28px rgb(67 79 137 / 14%));
}

.sync-asset {
  width: 22px;
  height: 22px;
  object-fit: contain;
  filter: drop-shadow(0 2px 3px rgb(28 24 93 / 16%));
}

.metric-icon {
  width: 70px;
  height: 70px;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.metric-icon img {
  width: 70px;
  height: 70px;
  object-fit: contain;
  filter: drop-shadow(0 14px 18px rgb(31 68 120 / 14%));
}

.panel-icon,
.health-icon {
  overflow: visible;
  background: transparent;
  color: inherit;
}

.panel-icon img,
.health-icon img,
.link-asset {
  display: block;
  width: 30px;
  height: 30px;
  object-fit: contain;
}

.trace-panel a .link-asset {
  width: 20px;
  height: 20px;
}

.empty-asset {
  display: block;
  object-fit: contain;
  filter: drop-shadow(0 14px 22px rgb(122 98 238 / 13%));
}

.rules-empty-asset {
  width: min(230px, 70%);
  max-height: 148px;
}

.table-empty img {
  width: 44px;
  height: 44px;
  object-fit: contain;
  opacity: 0.78;
}

.checkpoint-empty img {
  width: 118px;
  height: 88px;
  object-fit: contain;
  filter: drop-shadow(0 12px 18px rgb(122 98 238 / 14%));
}

.health-icon img {
  width: 32px;
  height: 32px;
}

@media (max-width: 1220px) {
  .hero-asset {
    display: none;
  }
}
</style>
