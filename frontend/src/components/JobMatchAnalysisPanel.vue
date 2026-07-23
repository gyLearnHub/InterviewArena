<template>
  <section class="job-match-panel" aria-labelledby="job-match-title">
    <header class="job-match-heading">
      <div>
        <p class="job-match-eyebrow">可选分析</p>
        <h3 id="job-match-title">简历与 JD 匹配分析</h3>
        <p>提前识别匹配项、能力缺口和高风险追问，不影响直接开始面试。</p>
      </div>
      <button
        class="job-match-action"
        type="button"
        :disabled="!canGenerate || loading"
        @click="$emit('generate')"
      >
        {{ loading ? "分析中..." : analysis ? "刷新分析" : "生成分析" }}
      </button>
    </header>

    <p v-if="loading" class="job-match-state" role="status">
      正在结合简历和岗位要求生成匹配分析，请稍候...
    </p>
    <div v-else-if="error" class="job-match-error" role="alert">
      <strong>分析失败</strong>
      <span>{{ error }}</span>
    </div>
    <div v-else-if="analysis" class="job-match-result">
      <div class="job-match-summary">
        <span>综合结论</span>
        <p>{{ analysis.summary }}</p>
      </div>

      <div class="job-match-grid">
        <section class="job-match-group matched">
          <h4>已匹配要求</h4>
          <p v-if="analysis.matched_requirements.length === 0" class="job-match-empty">
            暂未识别到明确匹配项。
          </p>
          <ul v-else>
            <li v-for="item in analysis.matched_requirements" :key="item.requirement">
              <strong>{{ item.requirement }}</strong>
              <span>{{ item.evidence }}</span>
            </li>
          </ul>
        </section>

        <section class="job-match-group missing">
          <h4>待补足要求</h4>
          <p v-if="analysis.missing_requirements.length === 0" class="job-match-empty">
            暂未识别到明显能力缺口。
          </p>
          <ul v-else>
            <li v-for="item in analysis.missing_requirements" :key="item.requirement">
              <strong>{{ item.requirement }}</strong>
              <span>{{ item.evidence_gap }}</span>
            </li>
          </ul>
        </section>

        <section class="job-match-group risk">
          <h4>高风险追问</h4>
          <p v-if="analysis.risk_questions.length === 0" class="job-match-empty">
            暂未识别到高风险追问。
          </p>
          <ul v-else>
            <li v-for="item in analysis.risk_questions" :key="item.question">
              <strong>{{ item.question }}</strong>
              <span>关联要求：{{ item.related_requirement }}</span>
            </li>
          </ul>
        </section>

        <section class="job-match-group preparation">
          <h4>准备建议</h4>
          <p v-if="analysis.preparation_suggestions.length === 0" class="job-match-empty">
            暂无额外准备建议。
          </p>
          <ul v-else>
            <li v-for="item in analysis.preparation_suggestions" :key="item.suggestion">
              <strong>{{ item.suggestion }}</strong>
              <span>关联要求：{{ item.related_requirement }}</span>
            </li>
          </ul>
        </section>
      </div>

      <p class="job-match-basis">分析依据：{{ analysis.analysis_basis }}</p>
    </div>
    <p v-else class="job-match-state">{{ unavailableReason || "尚未生成匹配分析。" }}</p>
  </section>
</template>

<script setup lang="ts">
import type { JobMatchAnalysis } from "../jobMatchApi";

defineProps<{
  analysis: JobMatchAnalysis | null;
  loading: boolean;
  error: string;
  canGenerate: boolean;
  unavailableReason: string;
}>();

defineEmits<{
  generate: [];
}>();
</script>

<style scoped>
.job-match-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid #dbe7f3;
  border-radius: 12px;
  background: #fff;
}

.job-match-heading {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.job-match-heading > div {
  display: grid;
  gap: 4px;
}

.job-match-eyebrow,
.job-match-heading h3,
.job-match-heading p,
.job-match-summary p,
.job-match-group h4,
.job-match-group ul,
.job-match-group li,
.job-match-state,
.job-match-empty,
.job-match-basis {
  margin: 0;
}

.job-match-eyebrow {
  color: #247de8;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.job-match-heading h3 {
  color: #17212f;
  font-size: 17px;
}

.job-match-heading p,
.job-match-state,
.job-match-empty,
.job-match-basis {
  color: #687384;
  font-size: 13px;
  line-height: 1.55;
}

.job-match-action {
  flex: 0 0 auto;
  min-width: 100px;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid #3b9cff;
  border-radius: 8px;
  background: #f2f8ff;
  color: #247de8;
  font-weight: 800;
}

.job-match-action:disabled {
  border-color: #d8e0e8;
  background: #f3f5f7;
  color: #8a94a1;
  cursor: not-allowed;
}

.job-match-error {
  display: grid;
  gap: 3px;
  padding: 11px 12px;
  border: 1px solid #f3caca;
  border-radius: 8px;
  background: #fff6f6;
  color: #a83d3d;
  font-size: 13px;
}

.job-match-result {
  display: grid;
  gap: 12px;
}

.job-match-summary {
  display: grid;
  gap: 5px;
  padding: 12px;
  border-radius: 9px;
  background: #f2f8ff;
}

.job-match-summary > span {
  color: #247de8;
  font-size: 12px;
  font-weight: 900;
}

.job-match-summary p {
  color: #293548;
  line-height: 1.65;
}

.job-match-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.job-match-group {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e4ebf0;
  border-radius: 9px;
  background: #f8fafc;
}

.job-match-group h4 {
  margin-bottom: 8px;
  color: #17212f;
  font-size: 14px;
}

.job-match-group ul {
  display: grid;
  gap: 9px;
  padding: 0;
  list-style: none;
}

.job-match-group li {
  display: grid;
  gap: 3px;
  padding-left: 10px;
  border-left: 3px solid #67b99a;
}

.job-match-group.missing li {
  border-left-color: #f0a35e;
}

.job-match-group.risk li {
  border-left-color: #e76f7a;
}

.job-match-group.preparation li {
  border-left-color: #7567f8;
}

.job-match-group strong {
  color: #293548;
  font-size: 13px;
  line-height: 1.45;
}

.job-match-group span {
  color: #687384;
  font-size: 12px;
  line-height: 1.5;
}

.job-match-basis {
  padding-top: 2px;
}

@media (max-width: 760px) {
  .job-match-heading {
    display: grid;
  }

  .job-match-action {
    width: 100%;
  }

  .job-match-grid {
    grid-template-columns: 1fr;
  }
}
</style>
