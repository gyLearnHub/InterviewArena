<template>
  <section class="workspace history-page">
    <header class="page-header">
      <div>
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

    <p v-if="message" class="message" :class="{ error: hasError }">{{ message }}</p>
    <section v-if="!hasError" class="history-panel" aria-label="历史记录">
      <div
        class="history-toolbar"
        :class="{ 'report-toolbar': isReportsMode }"
        aria-label="历史筛选"
      >
        <label class="search-box">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4 4" />
          </svg>
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
          <option value="recent">最近更新</option>
          <option v-if="isReportsMode" value="score-desc">评分从高到低</option>
          <option v-if="isReportsMode" value="score-asc">评分从低到高</option>
        </select>
      </div>

      <div v-if="listItems.length === 0" class="empty history-empty">
        <strong>{{ pageCopy.emptyTitle }}</strong>
        <span>{{ pageCopy.emptyText }}</span>
      </div>
      <template v-else>
        <div class="history-summary">
          <strong>{{ filteredItems.length }}</strong>
          <span>共 {{ listItems.length }} {{ pageCopy.countUnit }}</span>
          <span class="sort-summary">{{ sortSummary }}</span>
        </div>
        <div
          v-if="filteredItems.length > 0"
          class="table-wrap"
          role="region"
          aria-label="历史记录表格"
          tabindex="0"
        >
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
                <td data-label="岗位">
                  <div class="position-cell">
                    <strong>{{ item.target_position }}</strong>
                    <span>#{{ item.interview_id }}</span>
                  </div>
                </td>
                <td :data-label="isReportsMode ? '报告状态' : '面试状态'">
                  <div class="status-cell">
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
                  </div>
                </td>
                <td :data-label="isReportsMode ? '总评分' : '创建时间'">
                  <span v-if="isReportsMode" :class="item.score === null ? 'muted' : 'score-value'">
                    {{ formatScore(item.score) }}
                  </span>
                  <span v-else>{{ formatDate(item.created_at) }}</span>
                </td>
                <td :data-label="isReportsMode ? '生成时间' : '更新时间'">
                  {{
                    formatDate(isReportsMode ? item.created_at : item.updated_at || item.created_at)
                  }}
                </td>
                <td data-label="操作">
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
        <div v-else class="empty filter-empty">
          <strong>没有符合条件的记录</strong>
          <span>调整搜索词或筛选条件后再试。</span>
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
      </template>
    </section>
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
        lead: "集中查看已完成面试的评分和建议。",
        searchPlaceholder: "搜索岗位或报告编号",
        emptyTitle: "暂无面试报告",
        emptyText: "完成一次面试并生成报告后，这里会显示评估结果。",
        countUnit: "份报告"
      }
    : {
        lead: "查看面试进度与问答记录。",
        searchPlaceholder: "搜索岗位或面试记录",
        emptyTitle: "暂无面试记录",
        emptyText: "开始一次面试后，这里会显示岗位、状态和更新时间。",
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
      const matchesStatus =
        isReportsMode.value || !statusFilter.value || item.status === statusFilter.value;
      const matchesScore =
        !isReportsMode.value ||
        !scoreFilter.value ||
        (scoreFilter.value === "empty" && item.score === null) ||
        (scoreFilter.value === "high" && typeof item.score === "number" && item.score >= 80) ||
        (scoreFilter.value === "middle" &&
          typeof item.score === "number" &&
          item.score >= 60 &&
          item.score < 80);
      return matchesKeyword && matchesStatus && matchesScore;
    })
    .sort((left, right) => {
      if (sortMode.value === "score-desc") {
        return scoreSortValue(right.score) - scoreSortValue(left.score);
      }
      if (sortMode.value === "score-asc") {
        return scoreSortValue(left.score) - scoreSortValue(right.score);
      }
      return (
        dateSortValue(right.updated_at || right.created_at) -
        dateSortValue(left.updated_at || left.created_at)
      );
    });
});
const sortSummary = computed(() => {
  const map: Record<string, string> = {
    recent: "按最近更新时间",
    "score-desc": "按评分从高到低",
    "score-asc": "按评分从低到高"
  };
  return map[sortMode.value] || "按最近更新时间";
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
  if (
    deletingId.value !== null ||
    !confirmDeleteReminder("确认删除这条面试记录吗？删除后不可恢复。")
  ) {
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
  margin: 0;
  color: #758195;
}

.history-toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(132px, 156px) minmax(132px, 156px);
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid #e7edf5;
  background: #fff;
}

.search-box {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 9px;
  align-items: center;
  min-height: 40px;
  padding: 0 13px;
  border: 1px solid #dce4ee;
  border-radius: 10px;
  background: #f8fafc;
}

.search-box:focus-within {
  border-color: #86aef3;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(59, 156, 255, 0.1);
}

.search-box svg {
  width: 19px;
  height: 19px;
  fill: none;
  stroke: #8793a5;
  stroke-linecap: round;
  stroke-width: 1.8;
}

.search-box input,
.history-toolbar select {
  width: 100%;
  min-height: 40px;
  border: 1px solid #dce4ee;
  border-radius: 10px;
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

.history-panel {
  overflow: hidden;
  border: 1px solid #e1e8f0;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgba(31, 68, 120, 0.06);
}

.history-summary {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 15px 20px;
  border-bottom: 1px solid #e7edf5;
  color: #758195;
  font-size: 14px;
}

.history-summary strong {
  color: #172033;
  font-size: 18px;
}

.sort-summary {
  margin-left: auto;
}

.table-wrap {
  overflow-x: auto;
}

.history-table {
  width: 100%;
  min-width: 780px;
  border-collapse: collapse;
}

.history-table th,
.history-table td {
  padding: 15px 20px;
  border-bottom: 1px solid #edf1f5;
  text-align: left;
  vertical-align: middle;
}

.history-table th {
  color: #758195;
  background: #f8fafc;
  font-size: 13px;
  font-weight: 700;
}

.history-table tbody tr:last-child td {
  border-bottom: 0;
}

.history-table tbody tr:hover {
  background: #f8fbff;
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
  color: #425ee8;
  font-size: 16px;
  font-weight: 800;
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
  min-height: 32px;
  padding: 5px 11px;
  border: 1px solid #d5e0ef;
  border-radius: 8px;
  color: #336edc;
  background: #fff;
  font-size: 13px;
  font-weight: 700;
}

.primary-action {
  border-color: transparent;
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
  display: block;
  min-width: 132px;
  min-height: 40px;
  margin: 18px auto;
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
  min-height: 220px;
  place-content: center;
  text-align: center;
}

.history-empty span,
.filter-empty span {
  color: #758195;
}

.filter-empty {
  display: grid;
  gap: 6px;
  min-height: 180px;
  place-content: center;
  text-align: center;
}

@media (max-width: 760px) {
  .header-actions,
  .row-actions {
    flex-wrap: wrap;
  }

  .history-toolbar {
    grid-template-columns: 1fr;
    padding: 14px;
  }

  .history-summary {
    padding: 13px 16px;
  }

  .sort-summary {
    margin-left: auto;
  }

  .table-wrap {
    overflow: visible;
  }

  .history-table {
    min-width: 0;
  }

  .history-table thead {
    display: none;
  }

  .history-table,
  .history-table tbody,
  .history-table tr,
  .history-table td {
    display: block;
    width: 100%;
  }

  .history-table tr {
    padding: 14px 16px;
    border-bottom: 1px solid #e7edf5;
  }

  .history-table tbody tr:last-child {
    border-bottom: 0;
  }

  .history-table td {
    display: grid;
    grid-template-columns: 84px minmax(0, 1fr);
    gap: 12px;
    align-items: center;
    padding: 8px 0;
    border: 0;
  }

  .history-table td::before {
    color: #8792a2;
    font-size: 12px;
    font-weight: 700;
    content: attr(data-label);
  }

  .history-table td:last-child {
    align-items: start;
  }

  .history-table .row-actions {
    gap: 8px;
  }
}
</style>
