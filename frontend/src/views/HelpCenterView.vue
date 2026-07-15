<template>
  <section class="help-center" aria-label="帮助中心">
    <section class="help-hero" aria-label="帮助检索">
      <p class="help-lead">查找使用说明与常见问题。</p>

      <label class="search-box" for="help-search">
        <span>问题检索</span>
        <input
          id="help-search"
          v-model.trim="searchText"
          type="search"
          placeholder="搜索：简历、四轮面试、报告、记忆"
          autocomplete="off"
        />
      </label>
    </section>

    <section class="help-layout">
      <aside class="category-panel" aria-label="帮助分类">
        <button
          v-for="category in categories"
          :key="category"
          type="button"
          :class="{ active: activeCategory === category }"
          @click="activeCategory = category"
        >
          {{ category }}
        </button>
      </aside>

      <div class="document-area">
        <div class="result-summary" role="status">
          <strong>{{ resultTitle }}</strong>
          <span>{{ resultHint }}</span>
        </div>

        <section
          v-if="isFeedbackNavActive"
          class="feedback-panel"
          aria-labelledby="feedback-form-title"
        >
          <header class="feedback-panel-header">
            <div class="feedback-status-mark" aria-hidden="true">!</div>
            <div>
              <p>反馈提交</p>
              <h2 id="feedback-form-title">告诉我们哪里需要改进</h2>
              <span>题目、评分、报告和使用体验都可以反馈。</span>
            </div>
          </header>

          <form class="feedback-form" @submit.prevent="handleFeedbackSubmit">
            <div class="feedback-form-grid">
              <label class="feedback-field" for="feedback-type">
                <span>反馈类型</span>
                <select
                  id="feedback-type"
                  v-model="feedbackType"
                  :disabled="feedbackSubmitting"
                  @change="clearFeedbackMessage"
                >
                  <option v-for="item in feedbackTypeOptions" :key="item.value" :value="item.value">
                    {{ item.label }}
                  </option>
                </select>
              </label>

              <fieldset class="feedback-field rating-field">
                <legend>满意度</legend>
                <div class="rating-buttons" role="group" aria-label="满意度评分">
                  <button
                    v-for="score in ratingOptions"
                    :key="score"
                    type="button"
                    :class="{ active: feedbackRating === score }"
                    :aria-pressed="feedbackRating === score"
                    :disabled="feedbackSubmitting"
                    @click="selectFeedbackRating(score)"
                  >
                    {{ score }}
                  </button>
                </div>
              </fieldset>
            </div>

            <label class="feedback-field" for="feedback-content">
              <span>反馈内容</span>
              <textarea
                id="feedback-content"
                v-model="feedbackContent"
                :disabled="feedbackSubmitting"
                maxlength="2000"
                placeholder="例如：某道题和岗位不匹配、评分证据不足、报告建议太笼统。"
                @input="clearFeedbackMessage"
              ></textarea>
            </label>

            <div class="feedback-actions">
              <span>{{ feedbackContent.length }}/2000</span>
              <button type="submit" :disabled="!canSubmitFeedback">
                {{ feedbackSubmitting ? "提交中..." : "提交反馈" }}
              </button>
            </div>

            <p
              v-if="feedbackMessage"
              class="feedback-message"
              :class="{ error: feedbackHasError }"
              role="status"
            >
              {{ feedbackMessage }}
            </p>
          </form>
        </section>

        <div v-else-if="filteredArticles.length" class="article-list">
          <article v-for="article in filteredArticles" :key="article.id" class="help-article">
            <header>
              <span>{{ article.category }}</span>
              <h2>{{ article.title }}</h2>
              <p>{{ article.summary }}</p>
            </header>
            <ol v-if="article.steps.length">
              <li v-for="step in article.steps" :key="step">{{ step }}</li>
            </ol>
          </article>
        </div>

        <section v-else class="empty-result" aria-live="polite">
          <strong>没有找到匹配问题</strong>
          <p>换一个关键词试试，例如“报告”“暂停面试”或“清除记忆”。</p>
        </section>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { ApiError, submitFeedback, type FeedbackType } from "../api";

type HelpArticle = {
  id: string;
  category: string;
  title: string;
  summary: string;
  keywords: string[];
  steps: string[];
};

const ALL_CATEGORY = "全部文档";
const FEEDBACK_NAV = "反馈提交";

const articles: HelpArticle[] = [
  {
    id: "create-interview",
    category: "面试流程",
    title: "如何开始一次多轮模拟面试？",
    summary:
      "从新建面试进入配置页，选择岗位方向、简历、轮次和目标；进入面试后再配置每轮难度与限时。",
    keywords: ["新建面试", "岗位", "简历", "轮次", "开始面试"],
    steps: [
      "进入左侧导航的“新建面试”。",
      "选择面试方向，上传或选择已有简历，并补充岗位 JD。",
      "确认要练习的轮次和面试目标，点击“开始面试”。进入每轮前，在弹窗中选择本轮难度与限时。"
    ]
  },
  {
    id: "rounds",
    category: "面试流程",
    title: "四轮面试分别关注什么？",
    summary: "系统按简历面、技术面、主管面和 HR 面组织问题，每轮使用对应面试官视角。",
    keywords: ["四轮", "简历面", "技术面", "主管面", "HR"],
    steps: [
      "简历面主要核验经历真实性、项目背景和个人贡献。",
      "技术面关注技术能力、工程判断和问题分析。",
      "主管面关注协作、项目推进和业务理解；HR 面关注动机、稳定性和价值观匹配。"
    ]
  },
  {
    id: "pause-interview",
    category: "面试流程",
    title: "面试中可以暂停或继续吗？",
    summary: "面试页的操作菜单提供暂停、继续、结束当前轮、跳过问题和退出面试等动作。",
    keywords: ["暂停", "继续", "退出", "跳过", "重新生成"],
    steps: [
      "在面试页点击输入框旁的操作按钮展开菜单。",
      "选择“暂停面试”后，当前问题和回答草稿会保留在页面状态中。",
      "再次进入当前面试时，可点击“继续面试”恢复作答。"
    ]
  },
  {
    id: "report",
    category: "报告与历史",
    title: "在哪里查看面试报告？",
    summary: "完成面试并生成总评后，可在历史记录或报告入口查看评分、建议和轮次复盘。",
    keywords: ["报告", "评分", "历史记录", "总评", "复盘"],
    steps: [
      "完成所选轮次后，在面试页点击“生成总评”。",
      "进入“历史记录”，切换或搜索对应面试记录。",
      "打开详情页查看综合评分、优势、不足、建议和每轮问答证据。"
    ]
  },
  {
    id: "report-quality",
    category: "报告与历史",
    title: "报告为什么会显示仅供参考或不可用？",
    summary: "如果面试提前退出、流程降级或评分链路不完整，报告会标记可信度提示。",
    keywords: ["报告可信度", "仅供参考", "不可用", "提前退出", "降级"],
    steps: [
      "正常完成所有选择的轮次后，报告通常会按正常状态展示。",
      "提前退出或存在恢复降级时，报告会提示“仅供参考”。",
      "关键评分证据缺失时，页面会显示“报告不可用”。"
    ]
  },
  {
    id: "memory",
    category: "账号与设置",
    title: "个性化记忆如何开启、关闭或清除？",
    summary: "账号菜单的设置页提供记忆开关和清除入口，不会删除历史面试记录。",
    keywords: ["记忆", "个性化", "清除记忆", "设置", "历史表现"],
    steps: [
      "点击左下角账号区域，进入“设置”。",
      "在“个性化”里开启或关闭记忆使用。",
      "点击“清除记忆”只会删除长期记忆，不会删除历史面试记录。"
    ]
  },
  {
    id: "notifications",
    category: "账号与设置",
    title: "消息中心在哪里？",
    summary: "顶部工具栏的消息按钮可查看通知详情，并支持筛选未读和全部通知。",
    keywords: ["消息", "通知", "未读", "消息中心"],
    steps: [
      "在顶部工具栏点击消息按钮。",
      "使用“全部”和“未读”切换通知范围。",
      "打开单条通知可查看详情，必要时返回列表继续处理。"
    ]
  },
  {
    id: "harness",
    category: "高级功能",
    title: "高级诊断有什么用？",
    summary: "高级诊断用于排查面试运行、规则校验、重试和恢复记录。",
    keywords: ["Harness", "状态", "Trace", "恢复点", "规则评测"],
    steps: [
      "点击左下角账号区域，选择“高级诊断”。",
      "选择面试记录后查看运行状态和同步结果。",
      "当后端生成 Trace、规则或恢复点后，页面会展示对应明细。"
    ]
  }
];

const articleCategories = Array.from(new Set(articles.map((article) => article.category)));
const advancedToolsIndex = articleCategories.indexOf("高级功能");
const categories = [
  ALL_CATEGORY,
  ...articleCategories.slice(0, advancedToolsIndex + 1),
  FEEDBACK_NAV,
  ...articleCategories.slice(advancedToolsIndex + 1)
];
const activeCategory = ref(ALL_CATEGORY);
const searchText = ref("");
const feedbackType = ref<FeedbackType>("general");
const feedbackRating = ref<number | null>(null);
const feedbackContent = ref("");
const feedbackSubmitting = ref(false);
const feedbackMessage = ref("");
const feedbackHasError = ref(false);

const feedbackTypeOptions: { value: FeedbackType; label: string }[] = [
  { value: "general", label: "通用建议" },
  { value: "bug", label: "功能异常" },
  { value: "question", label: "题目问题" },
  { value: "scoring", label: "评分问题" },
  { value: "report", label: "报告建议" },
  { value: "experience", label: "使用体验" }
];
const ratingOptions = [1, 2, 3, 4, 5];

const normalizedSearchText = computed(() => searchText.value.toLowerCase());
const isFeedbackNavActive = computed(() => activeCategory.value === FEEDBACK_NAV);
const canSubmitFeedback = computed(
  () => feedbackContent.value.trim().length >= 5 && !feedbackSubmitting.value
);

const filteredArticles = computed(() => {
  const query = normalizedSearchText.value;

  return articles.filter((article) => {
    const matchesCategory =
      activeCategory.value === ALL_CATEGORY || article.category === activeCategory.value;
    const searchableText = [
      article.title,
      article.summary,
      article.category,
      ...article.keywords,
      ...article.steps
    ]
      .join(" ")
      .toLowerCase();
    const matchesSearch = !query || searchableText.includes(query);
    return matchesCategory && matchesSearch;
  });
});

const resultTitle = computed(() => {
  if (isFeedbackNavActive.value) {
    return "反馈提交";
  }

  if (searchText.value) {
    return `找到 ${filteredArticles.value.length} 条相关文档`;
  }

  if (activeCategory.value !== ALL_CATEGORY) {
    return `${activeCategory.value} · ${filteredArticles.value.length} 条文档`;
  }

  return `全部帮助文档 · ${filteredArticles.value.length} 条`;
});

const resultHint = computed(() =>
  isFeedbackNavActive.value
    ? "提交后会记录到反馈列表，便于后续排查与优化。"
    : searchText.value
      ? `当前关键词：${searchText.value}`
      : "选择分类或输入关键词，可快速定位问题。"
);

function selectFeedbackRating(score: number): void {
  feedbackRating.value = feedbackRating.value === score ? null : score;
  clearFeedbackMessage();
}

function clearFeedbackMessage(): void {
  feedbackMessage.value = "";
  feedbackHasError.value = false;
}

async function handleFeedbackSubmit(): Promise<void> {
  if (!canSubmitFeedback.value) {
    return;
  }

  feedbackSubmitting.value = true;
  feedbackMessage.value = "";
  feedbackHasError.value = false;
  try {
    const response = await submitFeedback({
      feedback_type: feedbackType.value,
      content: feedbackContent.value.trim(),
      rating: feedbackRating.value
    });
    feedbackContent.value = "";
    feedbackRating.value = null;
    feedbackMessage.value = `反馈已提交，编号 #${response.id}。`;
  } catch (error) {
    feedbackHasError.value = true;
    feedbackMessage.value =
      error instanceof ApiError ? error.message : "反馈提交失败，请稍后重试。";
  } finally {
    feedbackSubmitting.value = false;
  }
}
</script>

<style scoped>
.help-center {
  display: grid;
  gap: 22px;
  width: min(1180px, 100%);
  margin: 0 auto;
  color: var(--gray-900, #172033);
}

.help-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 440px);
  gap: 24px;
  align-items: center;
  padding: 18px 22px;
  border: 1px solid rgb(207 216 235 / 82%);
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgb(255 255 255 / 94%), rgb(242 248 255 / 88%)), var(--gray-0, #fff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.help-lead,
.result-summary span,
.empty-result p {
  color: var(--gray-500, #758195);
  font-weight: 700;
  line-height: 1.7;
}

.help-lead {
  margin: 0;
}

.search-box {
  display: grid;
  gap: 8px;
  margin: 0;
}

.search-box span {
  color: var(--gray-700, #3b4658);
  font-size: 14px;
  font-weight: 900;
}

.search-box input {
  width: 100%;
  min-height: 50px;
  border-radius: 8px;
  font-weight: 700;
}

.help-layout {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.category-panel {
  position: sticky;
  top: 18px;
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: rgb(255 255 255 / 90%);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.category-panel button {
  justify-content: start;
  min-height: 40px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--gray-700, #3b4658);
  text-align: left;
}

.category-panel button.active {
  background: var(--brand-50, #f2f8ff);
  color: var(--brand-700, #1f64bf);
  box-shadow: inset 3px 0 0 var(--brand-500, #3b9cff);
}

.document-area {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.result-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
  padding: 12px 16px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: var(--gray-0, #fff);
}

.result-summary strong {
  color: var(--gray-900, #172033);
  font-size: 16px;
  font-weight: 950;
}

.article-list {
  display: grid;
  gap: 12px;
}

.help-article {
  display: grid;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: var(--gray-0, #fff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.help-article header {
  display: grid;
  gap: 8px;
}

.help-article header span {
  justify-self: start;
  padding: 3px 8px;
  border-radius: 999px;
  background: #ecf8f4;
  color: #1f7a5b;
  font-size: 12px;
  font-weight: 900;
}

.help-article h2 {
  margin: 0;
  color: var(--gray-900, #172033);
  font-size: 20px;
  line-height: 1.35;
}

.help-article p {
  margin: 0;
  color: var(--gray-600, #5d687a);
  font-weight: 700;
  line-height: 1.75;
}

.help-article ol {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 22px;
  color: var(--gray-700, #3b4658);
  font-weight: 700;
  line-height: 1.75;
}

.feedback-panel {
  display: grid;
  gap: 18px;
  padding: 18px;
  border: 1px solid rgb(31 122 91 / 24%);
  border-radius: 8px;
  background: linear-gradient(135deg, #ffffff, #f7fffb);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.feedback-panel-header {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}

.feedback-status-mark {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 8px;
  background: #ecf8f4;
  color: #1f7a5b;
  font-size: 24px;
  font-weight: 950;
}

.feedback-panel p {
  margin: 0 0 4px;
  color: #1f7a5b;
  font-size: 13px;
  font-weight: 950;
}

.feedback-panel h2 {
  margin: 0;
  color: var(--gray-900, #172033);
  font-size: 20px;
  line-height: 1.35;
}

.feedback-panel-header span {
  color: var(--gray-500, #758195);
  font-weight: 700;
  line-height: 1.7;
}

.feedback-form {
  display: grid;
  gap: 14px;
}

.feedback-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);
  gap: 14px;
}

.feedback-field {
  display: grid;
  gap: 8px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.feedback-field span,
.feedback-field legend {
  color: var(--gray-700, #3b4658);
  font-size: 14px;
  font-weight: 900;
}

.feedback-field select,
.feedback-field textarea {
  width: 100%;
  border-radius: 8px;
  font-weight: 700;
}

.feedback-field textarea {
  min-height: 148px;
  resize: vertical;
  line-height: 1.7;
}

.rating-buttons {
  display: grid;
  grid-template-columns: repeat(5, 44px);
  gap: 8px;
}

.rating-buttons button {
  width: 44px;
  min-height: 44px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: var(--gray-0, #fff);
  color: var(--gray-700, #3b4658);
  font-weight: 950;
}

.rating-buttons button.active {
  border-color: #8dd8bc;
  background: #ecf8f4;
  color: #1f7a5b;
  box-shadow: inset 0 0 0 2px rgb(31 122 91 / 16%);
}

.feedback-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.feedback-actions span {
  color: var(--gray-500, #758195);
  font-size: 13px;
  font-weight: 800;
}

.feedback-actions button {
  min-width: 118px;
}

.feedback-message {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid rgb(31 122 91 / 24%);
  border-radius: 8px;
  background: #ecf8f4;
  color: #1f7a5b;
  font-weight: 800;
  line-height: 1.6;
}

.feedback-message.error {
  border-color: rgb(192 57 43 / 28%);
  background: #fff1ef;
  color: #a93226;
}

.empty-result {
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 8px;
  background: var(--gray-0, #fff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.empty-result {
  display: grid;
  gap: 8px;
  min-height: 180px;
  align-content: center;
  padding: 24px;
  text-align: center;
}

.empty-result strong {
  font-size: 20px;
}

.empty-result p {
  margin: 0;
}

@media (max-width: 860px) {
  .help-hero,
  .help-layout {
    grid-template-columns: 1fr;
  }

  .category-panel {
    position: static;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .help-hero {
    padding: 20px;
  }

  .category-panel {
    grid-template-columns: 1fr;
  }

  .feedback-panel-header,
  .feedback-form-grid {
    grid-template-columns: 1fr;
  }

  .rating-buttons {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .rating-buttons button {
    width: 100%;
  }
}
</style>
