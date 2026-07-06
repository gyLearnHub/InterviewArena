<template>
  <section class="workspace history-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">{{ pageCopy.eyebrow }}</p>
        <h1>{{ pageCopy.title }}</h1>
        <p class="history-lead">{{ pageCopy.lead }}</p>
      </div>
      <div class="header-actions">
        <button
          v-if="!isReportsMode"
          class="danger"
          type="button"
          :disabled="historyItems.length === 0 || deletingId !== null"
          @click="clearAll"
        >
          清除全部
        </button>
      </div>
    </header>

    <section class="history-toolbar" :class="{ 'report-toolbar': isReportsMode }" aria-label="历史筛选">
      <label class="search-box">
        <span aria-hidden="true">⌕</span>
        <input v-model.trim="searchText" :placeholder="pageCopy.searchPlaceholder" />
      </label>
      <select v-if="!isReportsMode" v-model="statusFilter" aria-label="状态筛选">
        <option value="">全部状态</option>
        <option value="created">已创建</option>
        <option value="in_progress">进行中</option>
        <option value="finished">已完成</option>
      </select>
      <select v-if="isReportsMode" v-model="scoreFilter" aria-label="评分区间">
        <option value="">全部评分</option>
        <option value="high">80 分以上</option>
        <option value="middle">60-79 分</option>
      </select>
      <select v-model="sortMode" aria-label="排序">
        <option value="recent">最近优先</option>
        <option v-if="isReportsMode" value="score-desc">评分从高到低</option>
        <option v-if="isReportsMode" value="score-asc">评分从低到高</option>
      </select>
      <div class="view-toggle" role="group" aria-label="视图切换">
        <button type="button" :class="{ active: viewMode === 'card' }" @click="setViewMode('card')">▦</button>
        <button type="button" :class="{ active: viewMode === 'list' }" @click="setViewMode('list')">☷</button>
      </div>
    </section>

    <p v-if="message" class="message" :class="{ error: hasError }">{{ message }}</p>
    <div v-if="!hasError && listItems.length === 0" class="empty history-empty">
      <strong>{{ pageCopy.emptyTitle }}</strong>
      <span>{{ pageCopy.emptyText }}</span>
    </div>
    <div v-else-if="!hasError" class="history-panel">
      <div class="history-summary">
        <span>{{ filteredItems.length }} / {{ listItems.length }} {{ pageCopy.countUnit }}</span>
        <span>{{ sortSummary }}</span>
      </div>
      <div v-if="viewMode === 'card'" class="history-cards">
        <article v-for="item in filteredItems" :key="item.interview_id" class="history-card">
          <header>
            <div>
              <h2>{{ item.target_position }}</h2>
              <time>{{ formatDate(isReportsMode ? item.created_at : item.updated_at || item.created_at) }}</time>
            </div>
            <span
              v-if="!isReportsMode"
              class="status-pill"
              :class="`status-${item.status}`"
            >
              {{ statusText(item.status) }}
            </span>
            <span
              v-if="reportReliabilityLabel(item)"
              class="report-pill"
              :class="`report-${item.report_reliability_status}`"
            >
              {{ reportReliabilityLabel(item) }}
            </span>
          </header>
          <div v-if="!isReportsMode" class="round-preview" aria-label="四轮状态预览">
            <span v-for="round in roundPreview(item)" :key="round.label" :class="{ done: round.done }">
              {{ round.label }}
            </span>
          </div>
          <div class="card-bottom">
            <div>
              <span>{{ isReportsMode ? "总评分" : "更新时间" }}</span>
              <strong v-if="isReportsMode">{{ formatScore(item.score) }}</strong>
              <strong v-else class="time-value">{{ formatDate(item.updated_at || item.created_at) }}</strong>
            </div>
            <div class="row-actions">
              <button
                v-if="!isReportsMode"
                class="table-action danger-action"
                type="button"
                :disabled="deletingId !== null"
                @click="deleteItem(item.interview_id)"
              >
                {{ deletingId === item.interview_id ? "删除中" : "删除" }}
              </button>
              <RouterLink v-if="isReportsMode" class="table-action" :to="`/history/${item.interview_id}`">
                查看报告
              </RouterLink>
              <RouterLink v-else class="table-action" :to="`/history/${item.interview_id}`">
                查看问答
              </RouterLink>
              <RouterLink
                v-if="!isReportsMode && item.status !== 'finished'"
                class="table-action primary-action"
                :to="`/interviews/multi/${item.interview_id}`"
              >
                继续
              </RouterLink>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="table-wrap" role="region" aria-label="历史记录表格" tabindex="0">
        <table class="history-table">
          <thead>
            <tr>
              <th scope="col">岗位</th>
              <th scope="col">{{ isReportsMode ? "报告状态" : "面试状态" }}</th>
              <th scope="col">{{ isReportsMode ? "总评分" : "创建时间" }}</th>
              <th scope="col">{{ isReportsMode ? "生成时间" : "更新时间" }}</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredItems" :key="item.interview_id">
              <td>
                <div class="position-cell">
                  <strong>{{ item.target_position }}</strong>
                  <span>#{{ item.interview_id }}</span>
                </div>
              </td>
              <td>
                <div class="status-cell">
                  <span v-if="!isReportsMode" class="status-pill" :class="`status-${item.status}`">
                    {{ statusText(item.status) }}
                  </span>
                  <span
                    v-if="reportReliabilityLabel(item)"
                    class="report-pill"
                    :class="`report-${item.report_reliability_status}`"
                  >
                    {{ reportReliabilityLabel(item) }}
                  </span>
                </div>
              </td>
              <td>
                <span v-if="isReportsMode" :class="item.score === null ? 'muted' : 'score-value'">
                  {{ formatScore(item.score) }}
                </span>
                <span v-else>{{ formatDate(item.created_at) }}</span>
              </td>
              <td>{{ formatDate(isReportsMode ? item.created_at : item.updated_at || item.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <RouterLink class="table-action" :to="`/history/${item.interview_id}`">
                    {{ isReportsMode ? "查看报告" : "查看问答" }}
                  </RouterLink>
                  <RouterLink
                    v-if="!isReportsMode && item.status !== 'finished'"
                    class="table-action primary-action"
                    :to="`/interviews/multi/${item.interview_id}`"
                  >
                    继续
                  </RouterLink>
                  <button
                    v-if="!isReportsMode"
                    class="table-action danger-action"
                    type="button"
                    :disabled="deletingId !== null"
                    @click="deleteItem(item.interview_id)"
                  >
                    {{ deletingId === item.interview_id ? "删除中" : "删除" }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <button
        v-if="hasMoreItems"
        class="load-more-button"
        type="button"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? "加载中..." : "加载更多" }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  ApiError,
  clearHistory,
  deleteHistoryItem,
  listHistoryPage,
  listReportsPage,
  type HistoryItem,
  type ReportListItem
} from "../api";

const props = withDefaults(defineProps<{ mode?: "history" | "reports" }>(), {
  mode: "history"
});

type DisplayItem = {
  interview_id: number;
  target_position: string;
  status: string;
  score: number | null;
  created_at: string | null;
  updated_at: string | null;
  report_reliability_status?: string;
};

const historyItems = ref<HistoryItem[]>([]);
const reportItems = ref<ReportListItem[]>([]);
const message = ref("");
const hasError = ref(false);
const deletingId = ref<number | null>(null);
const searchText = ref("");
const statusFilter = ref("");
const scoreFilter = ref("");
const sortMode = ref("recent");
const viewMode = ref<"card" | "list">((localStorage.getItem("interview_arena_history_view") as "card" | "list") || "card");
const PAGE_SIZE = 20;
const historyNextOffset = ref<number | null>(null);
const reportsNextOffset = ref<number | null>(null);
const loadingMore = ref(false);
const isReportsMode = computed(() => props.mode === "reports");
const hasMoreItems = computed(() =>
  isReportsMode.value ? reportsNextOffset.value !== null : historyNextOffset.value !== null
);
const pageCopy = computed(() =>
  isReportsMode.value
    ? {
        eyebrow: "面试报告",
        title: "查看已生成的评估报告",
        lead: "集中查看已完成面试的评分和建议。",
        searchPlaceholder: "搜索岗位或报告编号",
        emptyTitle: "暂无面试报告",
        emptyText: "完成一次面试并生成报告后，这里会显示评估结果。",
        countUnit: "份报告"
      }
    : {
        eyebrow: "历史记录",
        title: "回顾每一场面试",
        lead: "找到持续进步的证据。",
        searchPlaceholder: "搜索岗位或面试记录",
        emptyTitle: "暂无面试记录",
        emptyText: "完成一次面试后，这里会显示岗位、状态、评分和时间。",
        countUnit: "场面试"
      }
);
const items = computed<DisplayItem[]>(() =>
  isReportsMode.value
    ? reportItems.value.map((item) => ({
        interview_id: item.interview_id,
        target_position: item.target_position,
        status: "finished",
        score: item.score,
        created_at: item.created_at,
        updated_at: item.created_at,
        report_reliability_status: item.report_reliability_status
      }))
    : historyItems.value.map((item) => ({
        interview_id: item.interview_id,
        target_position: item.target_position,
        status: item.overall_status || item.status,
        score: null,
        created_at: item.created_at,
        updated_at: item.updated_at || item.ended_at || item.started_at || item.created_at,
        report_reliability_status: item.report_reliability_status
      }))
);
const listItems = computed(() => items.value);
const filteredItems = computed(() => {
  const keyword = searchText.value.toLowerCase();
  return [...listItems.value]
    .filter((item) => {
      const matchesKeyword =
        !keyword ||
        item.target_position.toLowerCase().includes(keyword) ||
        String(item.interview_id).includes(keyword);
      const matchesStatus = isReportsMode.value || !statusFilter.value || item.status === statusFilter.value;
      const matchesScore =
        !isReportsMode.value ||
        !scoreFilter.value ||
        (scoreFilter.value === "empty" && item.score === null) ||
        (scoreFilter.value === "high" && typeof item.score === "number" && item.score >= 80) ||
        (scoreFilter.value === "middle" && typeof item.score === "number" && item.score >= 60 && item.score < 80);
      return matchesKeyword && matchesStatus && matchesScore;
    })
    .sort((left, right) => {
      if (sortMode.value === "score-desc") {
        return scoreSortValue(right.score) - scoreSortValue(left.score);
      }
      if (sortMode.value === "score-asc") {
        return scoreSortValue(left.score) - scoreSortValue(right.score);
      }
      return dateSortValue(right.updated_at || right.created_at) - dateSortValue(left.updated_at || left.created_at);
    });
});
const sortSummary = computed(() => {
  const map: Record<string, string> = {
    recent: "按最近开始时间查看",
    "score-desc": "按评分从高到低",
    "score-asc": "按评分从低到高"
  };
  return map[sortMode.value] || "按最近开始时间查看";
});

onMounted(async () => {
  await refreshHistory();
});

async function refreshHistory(): Promise<boolean> {
  try {
    if (isReportsMode.value) {
      const response = await listReportsPage({ limit: PAGE_SIZE, offset: 0 });
      reportItems.value = response.items;
      reportsNextOffset.value = response.next_offset;
    } else {
      const response = await listHistoryPage({ limit: PAGE_SIZE, offset: 0 });
      historyItems.value = response.items;
      historyNextOffset.value = response.next_offset;
    }
    clearMessage();
    return true;
  } catch (error) {
    const fallbackMessage = isReportsMode.value ? "面试报告加载失败。" : "历史记录加载失败。";
    showError(error instanceof ApiError ? error.message : fallbackMessage);
    return false;
  }
}

async function loadMore() {
  if (loadingMore.value) {
    return;
  }
  const nextOffset = isReportsMode.value ? reportsNextOffset.value : historyNextOffset.value;
  if (nextOffset === null) {
    return;
  }

  loadingMore.value = true;
  try {
    if (isReportsMode.value) {
      const response = await listReportsPage({ limit: PAGE_SIZE, offset: nextOffset });
      reportItems.value = [...reportItems.value, ...response.items];
      reportsNextOffset.value = response.next_offset;
    } else {
      const response = await listHistoryPage({ limit: PAGE_SIZE, offset: nextOffset });
      historyItems.value = [...historyItems.value, ...response.items];
      historyNextOffset.value = response.next_offset;
    }
    clearMessage();
  } catch (error) {
    const fallbackMessage = isReportsMode.value ? "更多报告加载失败。" : "更多历史记录加载失败。";
    showError(error instanceof ApiError ? error.message : fallbackMessage);
  } finally {
    loadingMore.value = false;
  }
}

async function deleteItem(interviewId: number) {
  if (deletingId.value !== null || !confirmDeleteReminder("确认删除这条面试记录吗？删除后不可恢复。")) {
    return;
  }

  deletingId.value = interviewId;
  try {
    await deleteHistoryItem(interviewId);
    if (await refreshHistory()) {
      showInfo("面试记录已删除。");
    }
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "删除失败，请稍后重试。");
  } finally {
    deletingId.value = null;
  }
}

async function clearAll() {
  if (
    items.value.length === 0 ||
    deletingId.value !== null ||
    !confirmDeleteReminder("确认清除全部面试记录吗？删除后不可恢复。")
  ) {
    return;
  }

  deletingId.value = 0;
  try {
    await clearHistory();
    if (await refreshHistory()) {
      showInfo("历史记录已清除。");
    }
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "清除失败，请稍后重试。");
  } finally {
    deletingId.value = null;
  }
}

function confirmDeleteReminder(text: string): boolean {
  return window.confirm(text);
}

function statusText(status: string): string {
  const map: Record<string, string> = {
    created: "已创建",
    in_progress: "进行中",
    finished: "已结束"
  };
  return map[status] || status;
}

function reportReliabilityLabel(item: DisplayItem): string {
  if (item.report_reliability_status === "normal") {
    return "正常报告";
  }
  if (item.report_reliability_status === "reference_only") {
    return "仅供参考";
  }
  if (item.report_reliability_status === "unavailable") {
    return "报告不可用";
  }
  return "";
}

function formatScore(score: number | null): string {
  return score === null ? "未出分" : `${score} 分`;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "暂无时间";
}

function scoreSortValue(score: number | null): number {
  return typeof score === "number" ? score : -1;
}

function dateSortValue(value: string | null): number {
  if (!value) {
    return 0;
  }
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function setViewMode(mode: "card" | "list") {
  viewMode.value = mode;
}

function roundPreview(item: DisplayItem) {
  const doneCount = item.status === "finished" ? 4 : item.status === "in_progress" ? 2 : 0;
  return ["简历", "技术", "主管", "HR"].map((label, index) => ({
    label,
    done: index < doneCount
  }));
}

function showInfo(text: string) {
  message.value = text;
  hasError.value = false;
}

function showError(text: string) {
  message.value = text;
  hasError.value = true;
}

function clearMessage() {
  message.value = "";
  hasError.value = false;
}

watch(viewMode, (mode) => {
  localStorage.setItem("interview_arena_history_view", mode);
});

watch(isReportsMode, async () => {
  searchText.value = "";
  statusFilter.value = "";
  scoreFilter.value = "";
  await refreshHistory();
});
</script>

<style scoped>
.header-actions,
.row-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.history-page {
  color: #172033;
}

.history-lead {
  margin: 4px 0 0;
  color: #758195;
}

.history-toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 140px 160px auto;
  gap: 14px;
  padding: 16px 22px;
  border: 1px solid #e4edf7;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 18px 46px rgba(31, 68, 120, 0.08);
}

.search-box {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid #dfe5ec;
  border-radius: 12px;
  background: #f7f9fc;
}

.search-box input,
.history-toolbar select {
  width: 100%;
  min-height: 42px;
  border: 1px solid #dfe5ec;
  border-radius: 12px;
  background: #fff;
  color: #172033;
}

.search-box input {
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  outline: 0;
}

.history-toolbar select {
  padding: 0 12px;
}

.view-toggle {
  display: inline-flex;
  gap: 8px;
}

.view-toggle button {
  width: 44px;
  min-height: 42px;
  border: 0;
  border-radius: 12px;
  background: #f2f8ff;
  color: #247de8;
  font-weight: 900;
}

.view-toggle button.active {
  background: #e4f1ff;
}

.history-panel {
  overflow: hidden;
  border: 1px solid #e4edf7;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 18px 46px rgba(31, 68, 120, 0.08);
}

.history-summary {
  display: flex;
  gap: 16px;
  justify-content: space-between;
  padding: 18px 26px;
  border-bottom: 1px solid #e4edf7;
  color: #758195;
  font-size: 14px;
}

.history-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 28px;
  padding: 34px 28px;
}

.history-card {
  display: grid;
  gap: 28px;
  min-height: 250px;
  padding: 28px;
  border: 1px solid #e4edf7;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 14px 32px rgba(31, 68, 120, 0.06);
}

.history-card header {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.history-card h2 {
  margin: 0 0 10px;
  color: #172033;
  font-size: 24px;
}

.history-card time,
.card-bottom span {
  color: #758195;
}

.round-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
}

.round-preview span {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #758195;
}

.round-preview span::before {
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: #dfe5ec;
  content: "";
}

.round-preview span.done::before {
  background: #3b9cff;
}

.round-preview span:nth-child(2).done::before {
  background: #7567f8;
}

.round-preview span:nth-child(3).done::before {
  background: #f59b45;
}

.round-preview span:nth-child(4).done::before {
  background: #f06f9b;
}

.card-bottom {
  display: flex;
  gap: 18px;
  align-items: end;
  justify-content: space-between;
}

.card-bottom strong {
  display: block;
  margin-top: 4px;
  color: #172033;
  font-size: 34px;
}

.card-bottom .time-value {
  max-width: 260px;
  font-size: 18px;
  line-height: 1.35;
}

.table-wrap {
  overflow-x: auto;
}

.history-table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
}

.history-table th,
.history-table td {
  padding: 16px 18px;
  border-bottom: 1px solid #e4edf7;
  text-align: left;
  vertical-align: middle;
}

.history-table th {
  color: #758195;
  background: #f7f9fc;
  font-size: 13px;
  font-weight: 700;
}

.history-table tbody tr:last-child td {
  border-bottom: 0;
}

.history-table tbody tr:hover {
  background: #f7fbff;
}

.position-cell {
  display: grid;
  gap: 4px;
}

.position-cell strong {
  color: #1f2328;
}

.position-cell span,
.muted {
  color: #758195;
  font-size: 13px;
}

.score-value {
  color: #1f2328;
  font-weight: 700;
}

.status-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.status-pill,
.report-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border: 1px solid #c8e3ff;
  border-radius: 999px;
  color: #247de8;
  background: #e4f1ff;
  font-size: 13px;
  font-weight: 700;
}

.report-pill {
  border-color: #e1c891;
  color: #73510f;
  background: #fff8e6;
}

.report-normal {
  border-color: #bdebd4;
  color: #17704c;
  background: #e8f8ef;
}

.report-unavailable {
  border-color: #efc7bd;
  color: #8a2d1b;
  background: #fff7f5;
}

.status-finished {
  border-color: #bdebd4;
  color: #17704c;
  background: #e8f8ef;
}

.status-in_progress {
  border-color: #d8b15f;
  color: #73510f;
  background: #fff7dc;
}

.status-created {
  border-color: #dfe5ec;
  color: #758195;
  background: #f7f9fc;
}

.table-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 6px 12px;
  border: 1px solid #c8e3ff;
  border-radius: 10px;
  color: #247de8;
  font-weight: 700;
}

.primary-action {
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
}

.danger-action {
  border-color: #a13f28;
  color: #a13f28;
  background: #fffefb;
}

.table-action:hover,
.table-action:focus-visible {
  background: #e4f1ff;
  color: #247de8;
}

.load-more-button {
  justify-self: center;
  min-width: 132px;
  min-height: 40px;
  padding: 0 18px;
  border: 1px solid #c8e3ff;
  border-radius: 10px;
  background: #fff;
  color: #247de8;
  font-weight: 800;
}

.load-more-button:disabled {
  cursor: wait;
  opacity: 0.7;
}

.history-empty {
  display: grid;
  gap: 6px;
}

.history-empty span {
  color: #758195;
}

@media (max-width: 760px) {
  .header-actions,
  .row-actions {
    flex-wrap: wrap;
  }

  .history-toolbar,
  .history-cards {
    grid-template-columns: 1fr;
  }

  .history-summary {
    display: grid;
    gap: 4px;
  }
}
</style>
