<template>
  <section class="reanswer-shell">
    <button class="reanswer-toggle" type="button" :aria-expanded="isOpen" @click="togglePanel">
      <span>
        <strong>重新作答与对比</strong>
        <small>保留原回答，用新的表达验证改进效果</small>
      </span>
      <i aria-hidden="true">{{ isOpen ? "收起" : "开始" }}</i>
    </button>

    <div v-if="isOpen" class="reanswer-panel">
      <p v-if="message" class="reanswer-message" :class="{ error: hasError }" role="status">
        {{ message }}
      </p>

      <div v-if="loading" class="reanswer-loading">正在读取历史尝试...</div>
      <template v-else>
        <form class="reanswer-form" @submit.prevent="submitReanswer">
          <label :for="editorId">这一次，你会怎么回答？</label>
          <textarea
            :id="editorId"
            v-model="reanswerText"
            rows="5"
            maxlength="8000"
            :disabled="submitting"
            placeholder="结合原评价补充证据、结果和思考过程..."
          />
          <div>
            <span>{{ reanswerText.trim().length }} / 8000 字</span>
            <button type="submit" :disabled="submitting || !reanswerText.trim()">
              {{ submitting ? "正在评分" : "提交新回答" }}
            </button>
          </div>
        </form>

        <section class="original-snapshot" aria-label="原回答快照">
          <header>
            <span>基准回答</span>
            <strong>{{ scoreText(originalEvaluationValue) }}</strong>
          </header>
          <p>{{ originalAnswerValue }}</p>
        </section>

        <section v-if="attempts.length" class="attempt-list" aria-label="重新作答尝试历史">
          <article v-for="attempt in attempts" :key="attempt.id" class="attempt-card">
            <header class="attempt-head">
              <div>
                <span>第 {{ attempt.attempt_number }} 次尝试</span>
                <time :datetime="attempt.created_at">{{ formatDateTime(attempt.created_at) }}</time>
              </div>
              <div class="attempt-score">
                <strong>{{ scoreText(attempt.evaluation) }}</strong>
                <em :class="deltaTone(attempt.score_delta)">{{
                  deltaText(attempt.score_delta)
                }}</em>
              </div>
            </header>

            <div class="answer-comparison">
              <section>
                <h4>原回答</h4>
                <p>{{ originalAnswerValue }}</p>
              </section>
              <section class="new-answer">
                <h4>本次回答</h4>
                <p>{{ attempt.answer }}</p>
              </section>
            </div>

            <div v-if="dimensionRows(attempt).length" class="dimension-comparison">
              <div class="dimension-row dimension-heading" aria-hidden="true">
                <span>评分维度</span><b>原回答</b><b>本次</b><b>变化</b>
              </div>
              <div
                v-for="dimension in dimensionRows(attempt)"
                :key="dimension.name"
                class="dimension-row"
              >
                <span>{{ dimension.name }}</span>
                <b>{{ dimension.originalScore ?? "-" }}</b>
                <b>{{ dimension.attemptScore ?? "-" }}</b>
                <em :class="deltaTone(dimension.delta)">{{ deltaText(dimension.delta) }}</em>
              </div>
            </div>

            <div class="feedback-comparison">
              <section>
                <h4>原回答亮点</h4>
                <ul v-if="feedbackList(originalEvaluationValue, 'strengths').length">
                  <li
                    v-for="item in feedbackList(originalEvaluationValue, 'strengths')"
                    :key="item"
                  >
                    {{ item }}
                  </li>
                </ul>
                <p v-else>暂无明确亮点记录</p>
              </section>
              <section>
                <h4>本次亮点</h4>
                <ul v-if="feedbackList(attempt.evaluation, 'strengths').length">
                  <li v-for="item in feedbackList(attempt.evaluation, 'strengths')" :key="item">
                    {{ item }}
                  </li>
                </ul>
                <p v-else>暂无明确亮点记录</p>
              </section>
              <section class="issue-block">
                <h4>原回答不足</h4>
                <ul v-if="feedbackList(originalEvaluationValue, 'issues').length">
                  <li v-for="item in feedbackList(originalEvaluationValue, 'issues')" :key="item">
                    {{ item }}
                  </li>
                </ul>
                <p v-else>暂无明确不足记录</p>
              </section>
              <section class="issue-block">
                <h4>本次仍需改进</h4>
                <ul v-if="feedbackList(attempt.evaluation, 'issues').length">
                  <li v-for="item in feedbackList(attempt.evaluation, 'issues')" :key="item">
                    {{ item }}
                  </li>
                </ul>
                <p v-else>暂无明确不足记录</p>
              </section>
            </div>

            <div class="suggestion-comparison">
              <section>
                <h4>原改进建议</h4>
                <p>{{ suggestionText(originalEvaluationValue) }}</p>
              </section>
              <section>
                <h4>本次改进建议</h4>
                <p>{{ suggestionText(attempt.evaluation) }}</p>
              </section>
            </div>
          </article>
        </section>
        <p v-else class="attempt-empty">还没有重新作答记录。提交后会在这里对比两版回答。</p>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import {
  ApiError,
  listQuestionReanswers,
  submitQuestionReanswer,
  type QuestionEvaluation,
  type QuestionReanswerResponse,
  type ReanswerAttempt
} from "../api";

type FeedbackKey = "strengths" | "issues";
type DimensionRow = {
  name: string;
  originalScore: number | null;
  attemptScore: number | null;
  delta: number | null;
};

const props = defineProps<{
  interviewId: number;
  questionId: number;
  question: string;
  originalAnswer: string;
  originalEvaluation?: QuestionEvaluation | null;
}>();

const isOpen = ref(false);
const loading = ref(false);
const loaded = ref(false);
const submitting = ref(false);
const reanswerText = ref("");
const message = ref("");
const hasError = ref(false);
const record = ref<QuestionReanswerResponse | null>(null);

const editorId = computed(() => `reanswer-${props.interviewId}-${props.questionId}`);
const originalAnswerValue = computed(
  () => record.value?.original_answer || props.originalAnswer || "暂无原回答"
);
const originalEvaluationValue = computed(
  () => record.value?.original_evaluation ?? props.originalEvaluation ?? null
);
const attempts = computed(() =>
  [...(record.value?.attempts || [])].sort(
    (left, right) => right.attempt_number - left.attempt_number
  )
);

async function togglePanel() {
  isOpen.value = !isOpen.value;
  if (isOpen.value && !loaded.value) {
    await loadAttempts();
  }
}

async function loadAttempts() {
  loading.value = true;
  clearMessage();
  try {
    record.value = await listQuestionReanswers(props.interviewId, props.questionId);
    loaded.value = true;
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "重新作答记录加载失败，请稍后重试。");
  } finally {
    loading.value = false;
  }
}

async function submitReanswer() {
  const answer = reanswerText.value.trim();
  if (!answer || submitting.value) {
    return;
  }
  submitting.value = true;
  clearMessage();
  try {
    const response = await submitQuestionReanswer(props.interviewId, props.questionId, answer);
    record.value = {
      interview_id: response.interview_id,
      question_id: response.question_id,
      question: response.question,
      original_answer: response.original_answer,
      original_evaluation: response.original_evaluation,
      attempts: [
        ...(record.value?.attempts || []).filter((item) => item.id !== response.attempt.id),
        response.attempt
      ]
    };
    loaded.value = true;
    reanswerText.value = "";
    message.value = `第 ${response.attempt.attempt_number} 次作答已完成评分。`;
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "重新作答提交失败，请稍后重试。");
  } finally {
    submitting.value = false;
  }
}

function dimensionRows(attempt: ReanswerAttempt): DimensionRow[] {
  const original = dimensionMap(originalEvaluationValue.value);
  const current = dimensionMap(attempt.evaluation);
  const names = [...new Set([...original.keys(), ...current.keys()])];
  return names.map((name) => {
    const originalScore = original.get(name) ?? null;
    const attemptScore = current.get(name) ?? null;
    return {
      name,
      originalScore,
      attemptScore,
      delta:
        originalScore === null || attemptScore === null
          ? null
          : Number((attemptScore - originalScore).toFixed(1))
    };
  });
}

function dimensionMap(evaluation: QuestionEvaluation | null): Map<string, number> {
  return new Map(
    (evaluation?.dimension_scores || [])
      .filter((item) => item.dimension && typeof item.score === "number")
      .map((item) => [item.dimension, item.score])
  );
}

function feedbackList(evaluation: QuestionEvaluation | null, key: FeedbackKey): string[] {
  return [...new Set((evaluation?.[key] || []).map((item) => item.trim()).filter(Boolean))].slice(
    0,
    6
  );
}

function scoreText(evaluation: QuestionEvaluation | null): string {
  return typeof evaluation?.total_score === "number"
    ? `${formatScore(evaluation.total_score)} 分`
    : "暂未评分";
}

function suggestionText(evaluation: QuestionEvaluation | null): string {
  return evaluation?.follow_up_direction?.trim() || "暂无额外建议";
}

function deltaText(delta: number | null): string {
  if (typeof delta !== "number") {
    return "—";
  }
  if (delta === 0) {
    return "持平";
  }
  return `${delta > 0 ? "+" : ""}${formatScore(delta)} 分`;
}

function deltaTone(delta: number | null): string {
  if (typeof delta !== "number" || delta === 0) return "delta-flat";
  return delta > 0 ? "delta-up" : "delta-down";
}

function formatScore(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
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
.reanswer-shell {
  display: grid;
  gap: 10px;
  margin-top: 2px;
  padding-top: 12px;
  border-top: 1px solid #edf0f6;
}

.reanswer-toggle {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 54px;
  padding: 10px 13px;
  border: 1px solid #dce4f5;
  border-radius: 11px;
  background: linear-gradient(135deg, #f7f9ff, #fbf8ff);
  color: #273253;
  text-align: left;
}

.reanswer-toggle > span {
  display: grid;
  gap: 3px;
}

.reanswer-toggle strong {
  font-size: 14px;
}

.reanswer-toggle small {
  color: #737e98;
  font-size: 12px;
}

.reanswer-toggle i {
  color: #5c66e8;
  font-size: 12px;
  font-style: normal;
  font-weight: 900;
}

.reanswer-panel {
  display: grid;
  gap: 13px;
  padding: 14px;
  border: 1px solid #dfe5f3;
  border-radius: 12px;
  background: #f9fbff;
}

.reanswer-form {
  display: grid;
  gap: 8px;
}

.reanswer-form label {
  color: #273253;
  font-size: 13px;
  font-weight: 900;
}

.reanswer-form textarea {
  width: 100%;
  min-height: 116px;
  padding: 11px 12px;
  border: 1px solid #d9e1ef;
  border-radius: 10px;
  background: #fff;
  color: #29334e;
  font: inherit;
  line-height: 1.65;
  resize: vertical;
}

.reanswer-form textarea:focus {
  border-color: #6677ff;
  outline: 3px solid rgb(102 119 255 / 13%);
}

.reanswer-form > div {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
}

.reanswer-form > div span {
  color: #7a849b;
  font-size: 12px;
}

.reanswer-form button {
  min-height: 38px;
  padding: 0 16px;
  border: 0;
  border-radius: 9px;
  background: linear-gradient(135deg, #526fff, #8061ef);
  color: #fff;
  font-weight: 900;
}

.reanswer-form button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.reanswer-message,
.reanswer-loading,
.attempt-empty {
  margin: 0;
  padding: 10px 12px;
  border-radius: 9px;
  background: #edf9f2;
  color: #16814f;
  font-size: 13px;
  font-weight: 750;
}

.reanswer-message.error {
  background: #fff2ee;
  color: #c55218;
}

.reanswer-loading,
.attempt-empty {
  background: #f1f4fa;
  color: #6c7690;
}

.original-snapshot,
.attempt-card {
  border: 1px solid #e0e6f1;
  border-radius: 11px;
  background: #fff;
}

.original-snapshot {
  display: grid;
  gap: 8px;
  padding: 12px 13px;
}

.original-snapshot header,
.attempt-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.original-snapshot header span,
.attempt-head span {
  color: #65708d;
  font-size: 12px;
  font-weight: 900;
}

.original-snapshot header strong {
  color: #5364e7;
  font-size: 13px;
}

.original-snapshot p,
.answer-comparison p,
.feedback-comparison p,
.suggestion-comparison p {
  margin: 0;
  color: #303a55;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.attempt-list {
  display: grid;
  gap: 12px;
}

.attempt-card {
  display: grid;
  gap: 13px;
  padding: 14px;
  box-shadow: 0 8px 22px rgb(49 63 109 / 5%);
}

.attempt-head > div:first-child,
.attempt-score {
  display: grid;
  gap: 3px;
}

.attempt-head time {
  color: #8991a5;
  font-size: 11px;
}

.attempt-score {
  justify-items: end;
}

.attempt-score strong {
  color: #29334e;
  font-size: 18px;
}

.attempt-score em,
.dimension-row em {
  font-size: 11px;
  font-style: normal;
  font-weight: 900;
}

.delta-up {
  color: #17845a;
}

.delta-down {
  color: #cf4d58;
}

.delta-flat {
  color: #78819a;
}

.answer-comparison,
.feedback-comparison,
.suggestion-comparison {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.answer-comparison section,
.feedback-comparison section,
.suggestion-comparison section {
  min-width: 0;
  padding: 11px 12px;
  border-radius: 9px;
  background: #f6f8fc;
}

.answer-comparison .new-answer {
  background: #f2f3ff;
  box-shadow: inset 3px 0 #6a6cf2;
}

.answer-comparison h4,
.feedback-comparison h4,
.suggestion-comparison h4 {
  margin: 0 0 6px;
  color: #636e89;
  font-size: 12px;
}

.dimension-comparison {
  overflow: hidden;
  border: 1px solid #e3e8f2;
  border-radius: 9px;
}

.dimension-row {
  display: grid;
  grid-template-columns: minmax(100px, 1fr) repeat(3, minmax(58px, 0.45fr));
  gap: 8px;
  align-items: center;
  min-height: 38px;
  padding: 7px 10px;
  border-top: 1px solid #edf0f5;
  background: #fff;
  font-size: 12px;
}

.dimension-row:first-child {
  border-top: 0;
}

.dimension-heading {
  background: #f1f4fa;
  color: #707a93;
}

.dimension-row b,
.dimension-row em {
  text-align: right;
}

.feedback-comparison ul {
  display: grid;
  gap: 5px;
  padding-left: 17px;
  margin: 0;
  color: #34405b;
  font-size: 12px;
  line-height: 1.55;
}

.feedback-comparison .issue-block {
  background: #fff7f5;
}

.suggestion-comparison section {
  background: #f4f3ff;
}

@media (max-width: 720px) {
  .answer-comparison,
  .feedback-comparison,
  .suggestion-comparison {
    grid-template-columns: 1fr;
  }

  .dimension-row {
    grid-template-columns: minmax(86px, 1fr) repeat(3, minmax(48px, 0.45fr));
    padding-inline: 8px;
  }
}
</style>
