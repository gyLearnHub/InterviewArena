<template>
  <section class="review-page">
    <header class="review-header">
      <span>把面试现场暴露的问题沉淀成可反复训练的清单。</span>
      <RouterLink class="new-interview-link" to="/interviews/new">新建面试</RouterLink>
    </header>

    <section class="review-controls" aria-label="复盘筛选">
      <div class="control-group">
        <span>轮次</span>
        <div class="segmented-control">
          <button
            v-for="option in roundOptions"
            :key="option.value"
            type="button"
            :class="{ active: roundFilter === option.value }"
            @click="changeRoundFilter(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <div class="control-group">
        <span>状态</span>
        <div class="segmented-control status-control">
          <button
            v-for="option in statusOptions"
            :key="option.value"
            type="button"
            :class="{ active: statusFilter === option.value }"
            @click="changeStatusFilter(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
      <span class="result-count">当前显示 {{ bookmarks.length }} 条</span>
    </section>

    <p v-if="message" class="review-message" :class="{ error: hasError }">{{ message }}</p>

    <section class="review-list" aria-label="复盘收藏列表">
      <article v-if="loading && bookmarks.length === 0" class="review-empty">
        正在加载复盘收藏
      </article>
      <article v-else-if="bookmarks.length === 0" class="review-empty">
        暂无符合条件的复盘收藏
      </article>
      <template v-else>
        <article
          v-for="item in bookmarkRows"
          :key="item.id"
          class="review-item"
          :class="{ mastered: item.status === 'mastered' }"
        >
          <div class="review-item-main">
            <div class="review-item-meta">
              <span>{{ item.roundLabel }}</span>
              <span>{{ item.scoreLabel }}</span>
              <span class="status-tag" :class="`status-${item.status}`">{{
                item.statusLabel
              }}</span>
            </div>
            <h2>{{ item.title }}</h2>
            <p>{{ item.issue }}</p>
            <div class="source-row">
              <span>来源：{{ item.targetPosition }}</span>
              <RouterLink v-if="item.sourceInterviewId" :to="`/history/${item.sourceInterviewId}`">
                查看原面试
              </RouterLink>
              <span v-else>原面试已删除</span>
            </div>
            <div v-if="item.question || item.answer" class="evidence-details">
              <button
                class="evidence-toggle"
                type="button"
                :aria-expanded="expandedEvidenceIds.includes(item.id)"
                @click="toggleEvidence(item.id)"
              >
                {{ expandedEvidenceIds.includes(item.id) ? "收起原题与回答" : "查看原题与回答" }}
              </button>
              <dl v-if="expandedEvidenceIds.includes(item.id)">
                <div v-if="item.question">
                  <dt>原题</dt>
                  <dd>{{ item.question }}</dd>
                </div>
                <div v-if="item.answer">
                  <dt>回答片段</dt>
                  <dd>{{ item.answer }}</dd>
                </div>
              </dl>
            </div>
          </div>
          <aside class="review-actions" aria-label="复盘操作">
            <button
              class="primary-action"
              type="button"
              :disabled="
                activeActionId !== null || (!item.practiceInterviewId && !item.sourceInterviewId)
              "
              @click="startPractice(item)"
            >
              {{ practiceButtonText(item) }}
            </button>
            <button type="button" :disabled="activeActionId !== null" @click="toggleMastered(item)">
              {{ item.status === "mastered" ? "恢复待练" : "标为掌握" }}
            </button>
            <button
              class="danger"
              type="button"
              :disabled="activeActionId !== null"
              @click="removeBookmark(item)"
            >
              删除
            </button>
          </aside>
        </article>
      </template>
    </section>

    <button v-if="hasMore" class="load-more" type="button" :disabled="loading" @click="loadMore">
      {{ loading ? "加载中" : "加载更多" }}
    </button>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

import {
  ApiError,
  deleteReviewBookmark,
  listReviewBookmarks,
  startReviewBookmarkPractice,
  updateReviewBookmark,
  type ReviewBookmarkFilterStatus,
  type ReviewBookmarkItem,
  type RoundType
} from "../api";

type RoundFilter = RoundType | "all";
type BookmarkRow = {
  id: number;
  title: string;
  issue: string;
  question: string;
  answer: string;
  status: string;
  statusLabel: string;
  roundLabel: string;
  scoreLabel: string;
  targetPosition: string;
  sourceInterviewId: number | null;
  practiceInterviewId: number | null;
};

const PAGE_SIZE = 20;
const router = useRouter();
const bookmarks = ref<ReviewBookmarkItem[]>([]);
const loading = ref(false);
const hasMore = ref(false);
const message = ref("");
const hasError = ref(false);
const activeActionId = ref<number | null>(null);
const expandedEvidenceIds = ref<number[]>([]);
const roundFilter = ref<RoundFilter>("all");
const statusFilter = ref<ReviewBookmarkFilterStatus>("open");
let bookmarkRequestSequence = 0;

const roundOptions: Array<{ value: RoundFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "resume", label: "简历面" },
  { value: "technical", label: "技术面" },
  { value: "manager", label: "主管面" },
  { value: "hr", label: "HR 面" }
];
const statusOptions: Array<{ value: ReviewBookmarkFilterStatus; label: string }> = [
  { value: "open", label: "待复盘" },
  { value: "mastered", label: "已掌握" },
  { value: "all", label: "全部" }
];

const bookmarkRows = computed<BookmarkRow[]>(() => bookmarks.value.map(toBookmarkRow));
onMounted(() => {
  void loadBookmarks(true);
});

async function loadBookmarks(reset: boolean) {
  if (!reset && loading.value) {
    return;
  }
  const requestSequence = ++bookmarkRequestSequence;
  const selectedRound = roundFilter.value;
  const selectedStatus = statusFilter.value;
  loading.value = true;
  clearMessage();
  try {
    const offset = reset ? 0 : bookmarks.value.length;
    const items = await listReviewBookmarks({
      limit: PAGE_SIZE + 1,
      offset,
      roundType: selectedRound,
      status: selectedStatus
    });
    if (
      requestSequence !== bookmarkRequestSequence ||
      selectedRound !== roundFilter.value ||
      selectedStatus !== statusFilter.value
    ) {
      return;
    }
    const pageItems = items.slice(0, PAGE_SIZE);
    bookmarks.value = reset
      ? pageItems
      : [
          ...bookmarks.value,
          ...pageItems.filter(
            (item) => !bookmarks.value.some((existing) => existing.id === item.id)
          )
        ];
    hasMore.value = items.length > PAGE_SIZE;
  } catch (error) {
    if (requestSequence !== bookmarkRequestSequence) {
      return;
    }
    showError(error instanceof ApiError ? error.message : "复盘收藏加载失败。");
  } finally {
    if (requestSequence === bookmarkRequestSequence) {
      loading.value = false;
    }
  }
}

function loadMore() {
  void loadBookmarks(false);
}

function toggleEvidence(itemId: number) {
  expandedEvidenceIds.value = expandedEvidenceIds.value.includes(itemId)
    ? expandedEvidenceIds.value.filter((id) => id !== itemId)
    : [...expandedEvidenceIds.value, itemId];
}

function changeRoundFilter(value: RoundFilter) {
  if (roundFilter.value === value) {
    return;
  }
  roundFilter.value = value;
  void loadBookmarks(true);
}

function changeStatusFilter(value: ReviewBookmarkFilterStatus) {
  if (statusFilter.value === value) {
    return;
  }
  statusFilter.value = value;
  void loadBookmarks(true);
}

onUnmounted(() => {
  bookmarkRequestSequence += 1;
});

async function startPractice(item: BookmarkRow) {
  if (activeActionId.value !== null) {
    return;
  }
  if (item.practiceInterviewId) {
    await router.push({ name: "multi-round-interview", params: { id: item.practiceInterviewId } });
    return;
  }
  if (!item.sourceInterviewId) {
    showError("原面试已删除，收藏内容仍可复盘，但不能新建专项练习。");
    return;
  }
  activeActionId.value = item.id;
  clearMessage();
  try {
    const interview = await startReviewBookmarkPractice(item.id);
    await router.push({ name: "multi-round-interview", params: { id: interview.id } });
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "专项练习创建失败。");
  } finally {
    activeActionId.value = null;
  }
}

async function toggleMastered(item: BookmarkRow) {
  if (activeActionId.value !== null) {
    return;
  }
  activeActionId.value = item.id;
  clearMessage();
  try {
    const updated = await updateReviewBookmark(item.id, {
      status: item.status === "mastered" ? "active" : "mastered"
    });
    replaceBookmark(updated);
    message.value = updated.status === "mastered" ? "已标记为掌握。" : "已恢复到待练。";
    hasError.value = false;
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "复盘状态更新失败。");
  } finally {
    activeActionId.value = null;
  }
}

async function removeBookmark(item: BookmarkRow) {
  if (activeActionId.value !== null) {
    return;
  }
  const confirmed = window.confirm("确定删除这条复盘收藏吗？");
  if (!confirmed) {
    return;
  }
  activeActionId.value = item.id;
  clearMessage();
  try {
    await deleteReviewBookmark(item.id);
    bookmarks.value = bookmarks.value.filter((bookmark) => bookmark.id !== item.id);
    message.value = "已删除复盘收藏。";
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "删除失败，请稍后重试。");
  } finally {
    activeActionId.value = null;
  }
}

function replaceBookmark(updated: ReviewBookmarkItem) {
  bookmarks.value = bookmarks.value.map((item) => (item.id === updated.id ? updated : item));
  if (statusFilter.value === "open" && updated.status === "mastered") {
    bookmarks.value = bookmarks.value.filter((item) => item.id !== updated.id);
  }
  if (statusFilter.value === "mastered" && updated.status !== "mastered") {
    bookmarks.value = bookmarks.value.filter((item) => item.id !== updated.id);
  }
}

function toBookmarkRow(item: ReviewBookmarkItem): BookmarkRow {
  return {
    id: item.id,
    title: item.title,
    issue: item.suggestion || item.issue,
    question: item.question || "",
    answer: clipText(item.answer || ""),
    status: item.status,
    statusLabel: statusText(item.status),
    roundLabel: item.round_type ? roundName(String(item.round_type)) : "综合复盘",
    scoreLabel: typeof item.source_score === "number" ? `${item.source_score} 分` : "结构复盘",
    targetPosition: item.target_position,
    sourceInterviewId: item.source_interview_id,
    practiceInterviewId: item.practice_interview_id || null
  };
}

function practiceButtonText(item: BookmarkRow): string {
  if (activeActionId.value === item.id) {
    return "处理中";
  }
  if (!item.practiceInterviewId && !item.sourceInterviewId) {
    return "仅保留收藏";
  }
  return item.practiceInterviewId ? "继续专项" : "开始专项";
}

function roundName(value: string): string {
  return (
    (
      {
        resume: "简历面",
        technical: "技术面",
        manager: "主管面",
        hr: "HR 面"
      } as Record<string, string>
    )[value] || value
  );
}

function statusText(value: string): string {
  return (
    (
      {
        active: "待复盘",
        practice_created: "已创建专项",
        mastered: "已掌握"
      } as Record<string, string>
    )[value] || value
  );
}

function clipText(value: string): string {
  return value.length > 120 ? `${value.slice(0, 120)}...` : value;
}

function clearMessage() {
  message.value = "";
  hasError.value = false;
}

function showError(value: string) {
  message.value = value;
  hasError.value = true;
}
</script>

<style scoped>
.review-page {
  display: grid;
  gap: 18px;
  width: min(1280px, 100%);
  margin: 0 auto;
  color: #111827;
}

.review-header {
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
}

.review-header span {
  margin: 0;
  color: #66728f;
  font-size: 15px;
  font-weight: 700;
}

.new-interview-link,
.review-actions button,
.load-more {
  display: inline-grid;
  place-items: center;
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid #cfd8ea;
  border-radius: 9px;
  background: #fff;
  color: #2f3a56;
  font-size: 15px;
  font-weight: 900;
  text-decoration: none;
  cursor: pointer;
}

.new-interview-link,
.review-actions .primary-action {
  border-color: transparent;
  background: linear-gradient(135deg, #3b7ee8, #6f63ec);
  color: #fff;
}

.review-controls {
  display: grid;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid #e1e7f3;
  border-radius: 14px;
  background: #fff;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 0.8fr);
}

.control-group {
  display: grid;
  gap: 10px;
}

.control-group > span {
  color: #66728f;
  font-size: 14px;
  font-weight: 900;
}

.segmented-control {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px;
  border: 1px solid #dfe6f2;
  border-radius: 13px;
  background: #f5f8fd;
}

.segmented-control button {
  flex: 1 1 auto;
  min-height: 38px;
  padding: 0 13px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #53607d;
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
}

.segmented-control button.active {
  background: #fff;
  color: #5961ff;
  box-shadow: 0 4px 12px rgb(45 68 116 / 8%);
}

.result-count {
  grid-column: 1 / -1;
  justify-self: end;
  color: #66728f;
  font-size: 13px;
  font-weight: 700;
}

.review-message {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid #b7e4ca;
  border-radius: 12px;
  background: #edf9f2;
  color: #16814f;
  font-weight: 850;
}

.review-message.error {
  border-color: #ffd0b5;
  background: #fff4ed;
  color: #c55218;
}

.review-list {
  display: grid;
  gap: 16px;
}

.review-empty {
  display: grid;
  place-items: center;
  min-height: 220px;
  border: 1px dashed #cfd8ea;
  border-radius: 16px;
  background: #fff;
  color: #66728f;
  font-size: 18px;
  font-weight: 900;
}

.review-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 18px;
  align-items: start;
  padding: 20px 22px 16px;
  border: 1px solid #e1e7f3;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(45 68 116 / 5%);
}

.review-item.mastered {
  background: linear-gradient(135deg, #fbfffd, #ffffff);
}

.review-item-main {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.review-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.review-item-meta span {
  padding: 4px 9px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4856d9;
  font-size: 12px;
  font-weight: 800;
}

.review-item-meta .status-tag {
  background: #fff5da;
  color: #805c12;
}

.review-item-meta .status-mastered {
  background: #e9f7ef;
  color: #19704d;
}

.review-item-meta .status-practice_created {
  background: #eaf2ff;
  color: #336ac5;
}

.review-item h2 {
  margin: 0;
  color: #080d31;
  font-size: 20px;
  font-weight: 950;
  line-height: 1.3;
}

.review-item p {
  margin: 0;
  color: #53607d;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.6;
}

.source-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: center;
  color: #737e93;
  font-size: 13px;
}

.source-row a {
  color: #3971d2;
  font-weight: 800;
}

.evidence-details {
  margin-top: 2px;
  border-top: 1px solid #edf1f6;
}

.evidence-toggle {
  width: fit-content;
  padding-top: 11px;
  border: 0;
  background: transparent;
  color: #53617b;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.review-item dl {
  display: grid;
  gap: 10px;
  margin: 10px 0 0;
}

.review-item dl div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f7f9fd;
}

.review-item dt,
.review-item dd {
  margin: 0;
  color: #66728f;
  font-size: 14px;
  line-height: 1.5;
}

.review-item dt {
  font-weight: 950;
}

.review-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 14px;
  border-top: 1px solid #edf1f6;
}

.review-actions button {
  min-height: 36px;
  padding: 0 13px;
  font-size: 13px;
}

.review-actions button:disabled,
.load-more:disabled {
  cursor: not-allowed;
  opacity: 0.66;
}

.review-actions .danger {
  border-color: #ffd0b5;
  color: #c55218;
}

.load-more {
  justify-self: center;
  min-width: 140px;
}

@media (max-width: 900px) {
  .review-controls {
    grid-template-columns: 1fr;
  }

  .review-header {
    align-items: flex-start;
  }

  .result-count {
    grid-column: 1;
  }
}

@media (max-width: 560px) {
  .review-page {
    gap: 16px;
  }

  .review-controls,
  .review-item {
    padding: 16px;
  }

  .review-header {
    gap: 12px;
    align-items: center;
  }

  .review-item dl div {
    grid-template-columns: 1fr;
  }

  .review-actions {
    justify-content: stretch;
  }

  .review-actions button {
    flex: 1 1 calc(50% - 4px);
  }
}
</style>
