<template>
  <section class="memory-page" aria-label="我的记忆">
    <header class="memory-header">
      <p>系统保存的长期画像、薄弱项和训练线索。</p>
      <button class="refresh-button" type="button" :disabled="loading" @click="loadMemories">
        {{ loading ? "刷新中..." : "刷新" }}
      </button>
    </header>

    <section class="memory-summary" aria-label="记忆概览">
      <article>
        <span>全部</span>
        <strong>{{ summary.total }}</strong>
      </article>
      <article>
        <span>可用</span>
        <strong>{{ summary.active }}</strong>
      </article>
      <article>
        <span>待确认</span>
        <strong>{{ summary.pending }}</strong>
      </article>
      <article>
        <span>类型</span>
        <strong>{{ typeOptions.length }}</strong>
      </article>
    </section>

    <section class="memory-toolbar" aria-label="记忆筛选">
      <label class="search-box">
        <span aria-hidden="true">⌕</span>
        <input v-model.trim="searchText" placeholder="搜索标题、内容或证据" />
      </label>

      <label>
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="all">全部状态</option>
          <option value="active">可用</option>
          <option value="pending_review">待确认</option>
          <option value="superseded">已更新</option>
          <option value="archived">已归档</option>
        </select>
      </label>

      <label>
        <span>类型</span>
        <select v-model="typeFilter">
          <option value="">全部类型</option>
          <option v-for="type in typeOptions" :key="type" :value="type">
            {{ memoryTypeLabel(type) }}
          </option>
        </select>
      </label>
    </section>

    <p v-if="message" class="memory-message" :class="{ error: hasError }">{{ message }}</p>

    <section v-if="loading && memories.length === 0" class="memory-empty">
      <strong>正在读取记忆</strong>
      <span>稍等片刻。</span>
    </section>

    <section v-else-if="memories.length === 0" class="memory-empty">
      <strong>{{ hasActiveFilters ? "没有匹配记忆" : "暂无记忆" }}</strong>
      <span>{{
        hasActiveFilters ? "调整搜索或筛选条件。" : "完成面试后，系统会在这里沉淀长期记忆。"
      }}</span>
    </section>

    <section v-else class="memory-list" aria-label="记忆列表">
      <article v-for="memory in memories" :key="memory.id" class="memory-card">
        <header>
          <div>
            <div class="memory-card-tags">
              <span class="type-badge">{{ memoryTypeLabel(memory.memory_type) }}</span>
              <span class="status-badge" :class="`status-${memory.status}`">
                {{ statusLabel(memory.status) }}
              </span>
            </div>
            <h2>{{ memory.title }}</h2>
          </div>
          <strong>{{ confidenceText(memory.confidence) }}</strong>
        </header>

        <p class="memory-content">{{ memory.content }}</p>

        <ul v-if="memory.evidence.length" class="evidence-list">
          <li v-for="item in memory.evidence" :key="item">{{ item }}</li>
        </ul>

        <footer>
          <div class="memory-meta">
            <span>{{ memory.target_position || "未关联岗位" }}</span>
            <time :datetime="memory.updated_at || memory.created_at || undefined">
              {{ formatDate(memory.updated_at || memory.created_at) }}
            </time>
            <span>{{ indexStatusLabel(memory.index_status) }}</span>
          </div>

          <div class="memory-actions">
            <RouterLink
              v-if="memory.source_interview_id"
              class="source-link"
              :to="`/history/${memory.source_interview_id}`"
            >
              来源面试
            </RouterLink>
            <button
              class="delete-button"
              type="button"
              :disabled="deletingId === memory.id"
              @click="deleteMemory(memory)"
            >
              {{ deletingId === memory.id ? "删除中..." : "删除" }}
            </button>
          </div>
        </footer>
      </article>
    </section>

    <div v-if="nextOffset !== null && memories.length > 0" class="load-more-row">
      <button type="button" :disabled="loading" @click="loadMoreMemories">
        {{ loading ? "加载中..." : `加载更多（已显示 ${memories.length}/${summary.total}）` }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { ApiError, deleteManagedMemory, listManagedMemories, type ManagedMemoryItem } from "../api";
import { formatDate } from "../formatters";

const MEMORY_PAGE_SIZE = 100;
const memories = ref<ManagedMemoryItem[]>([]);
const loading = ref(false);
const deletingId = ref<number | null>(null);
const message = ref("");
const hasError = ref(false);
const searchText = ref("");
const statusFilter = ref("all");
const typeFilter = ref("");
const nextOffset = ref<number | null>(null);
const summaryState = ref({ total: 0, active: 0, pending: 0 });
const availableTypes = ref<string[]>([]);
let requestSequence = 0;
let searchTimer: number | null = null;

const typeOptions = computed(() => availableTypes.value);
const summary = computed(() => summaryState.value);
const hasActiveFilters = computed(
  () => Boolean(searchText.value.trim() || typeFilter.value || statusFilter.value !== "all")
);

async function loadMemories(): Promise<void> {
  await fetchMemories(0, true);
}

async function loadMoreMemories(): Promise<void> {
  if (nextOffset.value === null) {
    return;
  }
  await fetchMemories(nextOffset.value, false);
}

async function fetchMemories(offset: number, reset: boolean): Promise<void> {
  const sequence = ++requestSequence;
  loading.value = true;
  message.value = "";
  hasError.value = false;
  try {
    const response = await listManagedMemories(MEMORY_PAGE_SIZE, offset, {
      query: searchText.value.trim(),
      memoryType: typeFilter.value,
      status: statusFilter.value
    });
    if (sequence !== requestSequence) {
      return;
    }
    if (reset) {
      memories.value = response.items;
    } else {
      const existingIds = new Set(memories.value.map((memory) => memory.id));
      memories.value = [
        ...memories.value,
        ...response.items.filter((memory) => !existingIds.has(memory.id))
      ];
    }
    summaryState.value = {
      total: response.total,
      active: response.active_count,
      pending: response.pending_review_count
    };
    nextOffset.value = response.next_offset ?? null;
    availableTypes.value =
      response.memory_types ||
      Array.from(new Set(response.items.map((memory) => memory.memory_type))).sort();
  } catch (error) {
    if (sequence !== requestSequence) {
      return;
    }
    hasError.value = true;
    message.value = error instanceof ApiError ? error.message : "记忆加载失败。";
  } finally {
    if (sequence === requestSequence) {
      loading.value = false;
    }
  }
}

watch([statusFilter, typeFilter], () => {
  void loadMemories();
});

watch(searchText, () => {
  if (searchTimer !== null) {
    window.clearTimeout(searchTimer);
  }
  searchTimer = window.setTimeout(() => {
    searchTimer = null;
    void loadMemories();
  }, 300);
});

onUnmounted(() => {
  requestSequence += 1;
  if (searchTimer !== null) {
    window.clearTimeout(searchTimer);
  }
});

async function deleteMemory(memory: ManagedMemoryItem): Promise<void> {
  const confirmed = window.confirm(`删除记忆“${memory.title}”？`);
  if (!confirmed) {
    return;
  }

  deletingId.value = memory.id;
  message.value = "";
  hasError.value = false;
  try {
    await deleteManagedMemory(memory.id);
    memories.value = memories.value.filter((item) => item.id !== memory.id);
    decrementSummary(memory);
    if (nextOffset.value !== null) {
      nextOffset.value = Math.max(0, nextOffset.value - 1);
    }
    message.value = "记忆已删除。";
  } catch (error) {
    hasError.value = true;
    message.value = error instanceof ApiError ? error.message : "记忆删除失败。";
  } finally {
    deletingId.value = null;
  }
}

function decrementSummary(memory: ManagedMemoryItem): void {
  summaryState.value = {
    total: Math.max(0, summaryState.value.total - 1),
    active:
      memory.status === "active"
        ? Math.max(0, summaryState.value.active - 1)
        : summaryState.value.active,
    pending:
      memory.status === "pending_review"
        ? Math.max(0, summaryState.value.pending - 1)
        : summaryState.value.pending
  };
}

function memoryTypeLabel(type: string): string {
  const map: Record<string, string> = {
    technical_weakness: "技术薄弱项",
    past_wrong_answer: "历史回答问题",
    resume_key_fact: "简历关键信息",
    career_plan: "职业规划",
    collaboration: "协作表现",
    communication: "表达沟通"
  };
  return map[type] || type.replace(/_/g, " ");
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: "可用",
    pending_review: "待确认",
    superseded: "已更新",
    archived: "已归档",
    deleted: "已删除"
  };
  return map[status] || status;
}

function indexStatusLabel(status: string): string {
  const map: Record<string, string> = {
    indexed: "已索引",
    pending_index: "待索引",
    index_failed: "索引失败",
    pending_delete: "待清理"
  };
  return map[status] || status;
}

function confidenceText(confidence: number): string {
  return `${Math.round(Math.max(0, Math.min(confidence, 1)) * 100)}%`;
}

onMounted(() => {
  void loadMemories();
});
</script>

<style scoped>
.memory-page {
  display: grid;
  gap: 18px;
  width: min(1180px, 100%);
  margin: 0 auto;
  color: var(--gray-900, #172033);
}

.memory-header {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border: 1px solid rgb(207 216 235 / 82%);
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgb(255 255 255 / 94%), rgb(244 249 255 / 88%)), var(--gray-0, #fff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.memory-header p {
  margin: 0;
  color: var(--gray-500, #758195);
  font-weight: 700;
  line-height: 1.7;
}

.refresh-button {
  min-width: 106px;
}

.memory-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.memory-summary article,
.memory-toolbar,
.memory-card,
.memory-empty {
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: var(--gray-0, #fff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.memory-summary article {
  display: grid;
  gap: 6px;
  min-height: 92px;
  padding: 16px;
}

.memory-summary span,
.memory-meta,
.memory-toolbar label span {
  color: var(--gray-500, #758195);
  font-size: 13px;
  font-weight: 800;
}

.memory-summary strong {
  color: var(--gray-900, #172033);
  font-size: 28px;
  font-weight: 950;
}

.memory-toolbar {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 180px 220px;
  gap: 12px;
  align-items: end;
  padding: 14px;
}

.memory-toolbar label,
.search-box {
  display: grid;
  gap: 7px;
}

.search-box {
  position: relative;
}

.search-box > span {
  position: absolute;
  left: 14px;
  bottom: 13px;
  color: var(--gray-500, #758195);
}

.search-box input {
  padding-left: 38px;
}

.memory-toolbar input,
.memory-toolbar select {
  width: 100%;
  min-height: 44px;
  border-radius: 8px;
  font-weight: 700;
}

.memory-message {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid rgb(34 160 107 / 24%);
  border-radius: 8px;
  background: #ecf8f4;
  color: #1f7a5b;
  font-weight: 800;
}

.memory-message.error {
  border-color: rgb(223 77 95 / 28%);
  background: rgb(223 77 95 / 7%);
  color: var(--danger, #df4d5f);
}

.memory-empty {
  display: grid;
  gap: 8px;
  min-height: 220px;
  place-items: center;
  align-content: center;
  padding: 24px;
  text-align: center;
}

.memory-empty strong {
  color: var(--gray-900, #172033);
  font-size: 20px;
}

.memory-empty span {
  color: var(--gray-500, #758195);
  font-weight: 700;
}

.memory-list {
  display: grid;
  gap: 12px;
}

.load-more-row {
  display: flex;
  justify-content: center;
}

.load-more-row button {
  min-width: 220px;
}

.memory-card {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.memory-card header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: start;
}

.memory-card h2 {
  margin: 10px 0 0;
  color: var(--gray-900, #172033);
  font-size: 20px;
  line-height: 1.35;
}

.memory-card header > strong {
  padding: 8px 10px;
  border-radius: 8px;
  background: #eef1ff;
  color: #5961ff;
  font-size: 18px;
  font-weight: 950;
}

.memory-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.type-badge,
.status-badge {
  display: inline-grid;
  place-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 900;
}

.type-badge {
  background: #eef1ff;
  color: #5961ff;
}

.status-badge {
  background: #ecf8f4;
  color: #1f7a5b;
}

.status-pending_review {
  background: #fff4e3;
  color: #9a5a00;
}

.status-superseded,
.status-archived {
  background: #f3f6fa;
  color: var(--gray-600, #5d687a);
}

.memory-content {
  margin: 0;
  color: var(--gray-700, #3b4658);
  font-weight: 700;
  line-height: 1.75;
  white-space: pre-wrap;
}

.evidence-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--gray-100, #eef2f7);
  border-radius: 8px;
  background: var(--gray-50, #f7f9fc);
  list-style-position: inside;
}

.evidence-list li {
  color: var(--gray-600, #5d687a);
  font-weight: 700;
  line-height: 1.65;
}

.memory-card footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.memory-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.memory-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.source-link,
.delete-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: var(--gray-0, #fff);
  color: var(--gray-700, #3b4658);
  font-weight: 800;
}

.source-link:hover {
  border-color: var(--brand-200, #c8e3ff);
  background: var(--brand-50, #f2f8ff);
  color: var(--brand-700, #1f64bf);
}

.delete-button {
  border-color: rgb(223 77 95 / 34%);
  color: var(--danger, #df4d5f);
}

.delete-button:hover:not(:disabled) {
  background: rgb(223 77 95 / 8%);
}

@media (max-width: 860px) {
  .memory-header {
    display: grid;
    grid-template-columns: 1fr;
  }

  .memory-card header,
  .memory-card footer {
    grid-template-columns: 1fr;
  }

  .memory-header,
  .memory-card footer {
    align-items: start;
  }

  .memory-summary,
  .memory-toolbar {
    grid-template-columns: 1fr 1fr;
  }

  .search-box {
    grid-column: 1 / -1;
  }
}

@media (max-width: 560px) {
  .memory-summary,
  .memory-toolbar {
    grid-template-columns: 1fr;
  }

  .search-box {
    grid-column: auto;
  }

  .memory-actions {
    justify-content: stretch;
    width: 100%;
  }

  .source-link,
  .delete-button {
    flex: 1 1 120px;
  }
}
</style>
