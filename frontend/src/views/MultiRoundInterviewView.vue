<template>
  <section
    class="multi-stage"
    :class="{ 'is-dark': isDarkRoom, 'info-collapsed': isInfoPanelCollapsed }"
    @click="closeActionMenu"
  >
    <header class="room-header">
      <div class="room-title">
        <h1>{{ state?.target_position || "模拟面试" }} · 模拟面试</h1>
      </div>

      <div class="room-actions">
        <button class="theme-toggle" type="button" @click.stop="toggleRoomTheme">
          {{ isDarkRoom ? "浅色模式" : "深色模式" }}
        </button>
        <button
          class="panel-toggle"
          type="button"
          :aria-expanded="!isInfoPanelCollapsed"
          @click.stop="toggleInfoPanel"
        >
          {{ isInfoPanelCollapsed ? "显示信息" : "隐藏信息" }}
        </button>
      </div>
    </header>

    <section class="round-zone" aria-label="四轮面试">
      <div class="round-board" :class="{ 'has-current': Boolean(currentRoundType) }">
        <button
          v-for="round in displayRounds"
          :key="round.type"
          type="button"
          class="round-card"
          :class="[
            round.status,
            {
              'is-current': round.type === currentRoundType,
              'is-active-view': round.type === activeRoundType,
              'is-switching': round.type === switchingRoundType
            }
          ]"
          :data-round="round.type"
          :aria-current="round.type === currentRoundType ? 'step' : undefined"
          :aria-disabled="!canSelectRoundCard(round)"
          @click.stop="selectRound(round)"
        >
          <img :src="round.avatar" :alt="`${round.label}面试官`" />
          <div class="round-title">
            <strong>{{ round.label }}</strong>
            <span>{{ round.interviewer }}</span>
          </div>
          <div class="round-state">
            <i class="status-dot" :class="round.status" aria-hidden="true"></i>
            <span>{{ roundCardStatusText(round.status) }}</span>
          </div>
          <strong class="round-time">{{ formatDuration(roundElapsedSeconds(round)) }}</strong>
        </button>
      </div>
    </section>

    <section v-if="userFlowNotice" class="state-strip" :class="userFlowNotice.tone">
      <div>
        <strong>{{ userFlowNotice.title }}</strong>
        <span>{{ userFlowNotice.text }}</span>
      </div>
      <button
        v-if="userFlowNotice.canRefresh"
        type="button"
        :disabled="isBusy"
        @click.stop="loadState"
      >
        重新检查
      </button>
    </section>

    <main v-if="activeRound" class="room-main">
      <section class="conversation-panel">
        <div
          :ref="setActiveMessagesEl"
          class="round-messages conversation-messages"
          aria-live="polite"
          :aria-busy="busyRoundType === activeRound.type || streamingRoundType === activeRound.type"
        >
          <template v-for="item in activeRound.messages" :key="item.id">
            <article class="message-row" :class="item.role">
              <img
                v-if="item.role === 'assistant'"
                :src="activeRound.avatar"
                alt=""
                aria-hidden="true"
              />
              <div class="bubble" :class="item.role">
                <small v-if="item.roundLabel">{{ item.roundLabel }}</small>
                <p>{{ item.text }}</p>
              </div>
            </article>

            <section
              v-if="item.answerEvaluation"
              class="answer-quality-panel answer-quality-inline"
              :class="answerQualityTone(item.answerEvaluation)"
              :data-question-id="item.answerEvaluation.question_id"
            >
              <div class="answer-quality-score">
                <span>即时回答提示</span>
                <strong v-if="typeof item.answerEvaluation.total_score === 'number'">
                  {{ item.answerEvaluation.total_score }} 分
                </strong>
                <strong v-else>结构提示</strong>
                <em>{{ answerQualityLabel(item.answerEvaluation) }}</em>
              </div>
              <p>{{ answerQualityLead(item.answerEvaluation) }}</p>
              <section
                v-if="answerQualityDimensions(item.answerEvaluation).length"
                class="answer-quality-section answer-quality-dimensions"
              >
                <h4>维度表现</h4>
                <div class="answer-quality-dimension-grid">
                  <article
                    v-for="dimension in answerQualityDimensions(item.answerEvaluation)"
                    :key="dimension.dimension"
                  >
                    <div>
                      <strong>{{ dimension.dimension }}</strong>
                      <span>{{ dimension.score }} 分</span>
                    </div>
                    <p v-if="dimension.reason">{{ dimension.reason }}</p>
                  </article>
                </div>
              </section>
              <div class="answer-quality-detail-grid">
                <section
                  v-if="answerQualityStrengths(item.answerEvaluation).length"
                  class="answer-quality-section quality-strengths"
                >
                  <h4>做得好的</h4>
                  <ul>
                    <li
                      v-for="strength in answerQualityStrengths(item.answerEvaluation)"
                      :key="strength"
                    >
                      {{ strength }}
                    </li>
                  </ul>
                </section>
                <section
                  v-if="answerQualityIssues(item.answerEvaluation).length"
                  class="answer-quality-section quality-issues"
                >
                  <h4>优先改进</h4>
                  <ul>
                    <li v-for="issue in answerQualityIssues(item.answerEvaluation)" :key="issue">
                      {{ issue }}
                    </li>
                  </ul>
                </section>
              </div>
              <section
                v-if="item.answerEvaluation.follow_up_direction"
                class="answer-quality-next-step"
              >
                <strong>下一步怎么答</strong>
                <span>{{ item.answerEvaluation.follow_up_direction }}</span>
              </section>
              <details v-if="answerQualityEvidence(item.answerEvaluation).length">
                <summary>查看判断依据</summary>
                <ul>
                  <li
                    v-for="evidence in answerQualityEvidence(item.answerEvaluation)"
                    :key="evidence"
                  >
                    {{ evidence }}
                  </li>
                </ul>
              </details>
              <p v-if="!hasAnswerQualityDetails(item.answerEvaluation)" class="quality-empty">
                暂未生成详细建议，本题回答已正常记录。
              </p>
              <div class="answer-quality-actions">
                <span
                  v-if="answerBookmarkQuestionId === item.answerEvaluation.question_id"
                  :class="{ error: answerBookmarkError }"
                >
                  {{ answerBookmarkMessage }}
                </span>
                <button
                  type="button"
                  :disabled="
                    !canBookmarkAnswer(item.answerEvaluation) ||
                    isSavingAnswerBookmark(item.answerEvaluation)
                  "
                  @click.stop="bookmarkAnswerEvaluation(item.answerEvaluation)"
                >
                  {{ answerBookmarkButtonText(item.answerEvaluation) }}
                </button>
              </div>
            </section>
          </template>

          <article
            v-if="isThinkingVisible && busyRoundType === activeRound.type"
            class="message-row assistant"
          >
            <img :src="activeRound.avatar" alt="" aria-hidden="true" />
            <div class="bubble assistant thinking">
              <small>{{ activeRound.label }}</small>
              <p>{{ thinkingText }}<span class="dot-trail" aria-hidden="true">...</span></p>
            </div>
          </article>

          <div
            v-if="activeRound.messages.length === 0 && busyRoundType !== activeRound.type"
            class="message-empty"
          >
            {{ emptyMessage(activeRound) }}
          </div>
        </div>

        <div
          v-if="operationFailed && busyErrorRoundType === activeRound.type"
          class="failure-strip"
        >
          <span>{{ roundFailureMessage }}</span>
          <button type="button" :disabled="isBusy" @click.stop="retryLastAction">重试</button>
        </div>

        <section v-if="activeRoundSummary" class="summary-panel">
          <div class="summary-score">
            <span>本轮评估</span>
            <strong>{{ activeRoundSummary.score ?? "-" }} 分</strong>
            <em>{{ resultText(activeRoundSummary.result) }}</em>
          </div>
          <p v-if="roundSummaryText(activeRoundSummary)">
            {{ roundSummaryText(activeRoundSummary) }}
          </p>
          <div v-if="activeRoundSummary.question_evaluations?.length" class="question-score-list">
            <article
              v-for="item in activeRoundSummary.question_evaluations"
              :key="item.question_id || `${activeRound.type}-${item.total_score}`"
            >
              <strong>{{ item.total_score ?? "-" }} 分</strong>
              <p>{{ questionEvaluationText(item) }}</p>
            </article>
          </div>
        </section>

        <div
          v-if="currentActionRound && activeRound.type !== currentActionRound.type"
          class="current-round-bar"
        >
          <span>{{ currentActionRound.label }}进行中，当前正在查看 {{ activeRound.label }}</span>
          <div>
            <button type="button" :disabled="isBusy" @click.stop="selectRound(currentActionRound)">
              回到当前轮
            </button>
            <button
              class="primary-action"
              type="button"
              :disabled="!canFinishRound(currentActionRound)"
              @click.stop="finishRoundFromMenu(currentActionRound)"
            >
              结束当前轮
            </button>
          </div>
        </div>

        <form class="round-composer" @submit.prevent="submitRoundAnswer(activeRound)">
          <div v-if="openMenuRound === activeRound.type" class="action-menu" @click.stop>
            <button
              type="button"
              :disabled="!canStartRound(activeRound)"
              @click="startRound(activeRound)"
            >
              开始本轮
            </button>
            <button
              type="button"
              :disabled="!canToggleInterviewPause"
              @click="toggleInterviewPause"
            >
              {{ isInterviewPaused ? "继续面试" : "暂停面试" }}
            </button>
            <button
              type="button"
              :disabled="!canFinishRound(activeRound)"
              @click="finishRoundFromMenu(activeRound)"
            >
              结束当前轮
            </button>
            <button
              type="button"
              :disabled="!canRegenerateQuestion(activeRound)"
              @click="regenerateQuestionFromMenu(activeRound)"
            >
              重新生成当前问题
            </button>
            <button
              type="button"
              :disabled="!canSkipQuestion(activeRound)"
              @click="skipQuestionFromMenu(activeRound)"
            >
              跳过当前问题
            </button>
            <button class="danger-item" type="button" :disabled="isBusy" @click="exitInterview">
              退出面试
            </button>
          </div>

          <button
            class="composer-plus"
            type="button"
            aria-label="打开面试操作菜单"
            :disabled="isBusy || isReadOnlyRound(activeRound)"
            @click.stop="toggleActionMenu(activeRound)"
          >
            ⋯
          </button>
          <textarea
            :ref="setActiveTextareaEl"
            v-model="draftTexts[activeRound.type]"
            :disabled="!canTypeInRound(activeRound)"
            :placeholder="answerPlaceholder(activeRound)"
            rows="1"
            @keydown="handleComposerKeydown($event, activeRound)"
            @input="onDraftInput(activeRound.type)"
          />
          <span
            v-if="draftStatusMessage"
            class="draft-status"
            :class="`draft-status-${draftSaveStatus}`"
          >
            {{ draftStatusMessage }}
          </span>
          <button
            class="send-button"
            type="submit"
            aria-label="提交回答"
            :disabled="!canSubmitRound(activeRound)"
          >
            ↑
          </button>
        </form>
      </section>

      <aside v-if="!isInfoPanelCollapsed" class="info-panel">
        <header class="info-head">
          <div>
            <span>面试进度</span>
            <strong :class="{ danger: isRoundTimeExpired }">{{ roundTimerLabel }}</strong>
          </div>
          <button type="button" @click.stop="toggleInfoPanel">隐藏</button>
        </header>

        <div class="progress-meter">
          <span :style="{ width: `${completionPercent}%` }"></span>
        </div>

        <dl class="info-list">
          <div>
            <dt>岗位与简历</dt>
            <dd>{{ state?.target_position || "待恢复" }}</dd>
          </div>
          <div>
            <dt>面试策略</dt>
            <dd>{{ strategyLabel }}</dd>
          </div>
          <div>
            <dt>剩余时间</dt>
            <dd :class="{ danger: isRoundTimeExpired }">{{ remainingTimeLabel }}</dd>
          </div>
          <div>
            <dt>当前 Agent</dt>
            <dd>{{ activeRound.interviewer }}</dd>
          </div>
          <div>
            <dt>当前轮次</dt>
            <dd>{{ roundStatusText(activeRound.status) }}</dd>
          </div>
        </dl>
      </aside>
    </main>

    <p v-if="message" class="toast" :class="{ error: hasError }">{{ message }}</p>

    <section v-if="!state && !hasError" class="empty-panel">
      <strong>正在恢复面试</strong>
      <span>正在读取当前轮次、问题和历史回答。</span>
    </section>

    <div
      v-if="canFinishOverall"
      class="overall-bar"
      :class="{ 'is-generating': isGeneratingOverall }"
    >
      <div class="overall-copy">
        <span>{{ overallBarText }}</span>
        <div
          v-if="isGeneratingOverall"
          class="overall-progress"
          role="progressbar"
          aria-label="总评生成进度"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span></span>
        </div>
      </div>
      <button
        class="primary"
        type="button"
        :disabled="isBusy || isGeneratingOverall"
        @click="finishOverall"
      >
        {{ isGeneratingOverall ? "生成中" : "生成总评" }}
      </button>
    </div>

    <div v-if="roundConfigTarget" class="round-config-backdrop" @click.self="closeRoundConfig">
      <section
        class="round-config-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="round-config-title"
      >
        <header>
          <div>
            <span>开始本轮</span>
            <h2 id="round-config-title">{{ roundConfigTarget.label }}</h2>
          </div>
          <button type="button" aria-label="关闭" @click="closeRoundConfig">×</button>
        </header>
        <p class="round-config-focus">{{ roundConfigTarget.focus }}</p>

        <fieldset>
          <legend>本轮难度</legend>
          <div class="round-config-options">
            <button
              v-for="option in roundDifficultyOptions"
              :key="option.value"
              type="button"
              :class="{ active: roundDifficulty === option.value }"
              @click="roundDifficulty = option.value"
            >
              <strong>{{ option.label }}</strong>
              <small>{{ option.note }}</small>
            </button>
          </div>
        </fieldset>

        <fieldset>
          <legend>本轮限时</legend>
          <div class="round-config-options">
            <button
              v-for="option in roundTimeLimitOptions"
              :key="option.value"
              type="button"
              :class="{ active: roundTimeLimitMinutes === option.value }"
              @click="roundTimeLimitMinutes = option.value"
            >
              <strong>{{ option.label }}</strong>
              <small>{{ option.note }}</small>
            </button>
          </div>
        </fieldset>

        <p class="round-config-note">
          Agent 会根据回答质量、主题覆盖和剩余时间动态调整题量，并在最后 3 分钟自然收尾。
        </p>
        <footer>
          <button type="button" @click="closeRoundConfig">取消</button>
          <button class="primary" type="button" :disabled="isBusy" @click="confirmStartRound">
            {{ isBusy ? "正在开始" : "开始本轮" }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  type ComponentPublicInstance,
  watch
} from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  ApiError,
  deleteRoundAnswerDraft,
  finishInterviewRound,
  finishMultiRoundInterview,
  getRoundAnswerDraft,
  getMultiRoundState,
  pauseMultiRoundInterview,
  regenerateRoundQuestion,
  saveRoundAnswerDraft,
  saveReviewBookmark,
  type HarnessStatus,
  resumeMultiRoundInterview,
  skipRoundQuestion,
  startInterviewRound,
  submitRoundAnswer as submitRoundAnswerApi,
  type InterviewRound,
  type InterviewDifficulty,
  type MultiRoundQaEntry,
  type MultiRoundQuestion,
  type MultiRoundState,
  type RoundAnswerResponse,
  type RoundSummary,
  type RoundType,
  type TimeLimitMinutes,
  type QuestionEvaluation
} from "../api";
import {
  orderedRoundTypes,
  resultText,
  roundCardStatusText,
  roundMetas,
  roundStatusText
} from "../interviewRounds";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  roundLabel?: string;
  answerEvaluation?: QuestionEvaluation;
};

type RoundCard = {
  type: RoundType;
  id: number | null;
  status: InterviewRound["status"];
  label: string;
  interviewer: string;
  avatar: string;
  focus: string;
  messages: ChatMessage[];
  elapsedSeconds: number;
  difficulty: InterviewDifficulty;
  timeLimitMinutes: TimeLimitMinutes;
  summary: RoundSummary | null;
};

type UserFlowNotice = {
  title: string;
  text: string;
  tone: "info" | "warning" | "error";
  canRefresh?: boolean;
};

type FailedRoundAction = {
  roundType: RoundType;
  action: () => Promise<void>;
  retryAction?: () => Promise<void>;
  thinkingOptions?: { initialText?: string; delayedText?: string };
  showThinking?: boolean;
};

type DraftSaveStatus = "idle" | "saving" | "saved" | "restored" | "error";

type DraftContext = {
  interviewId: number;
  roundId: number;
  questionId: number;
  roundType: RoundType;
};

const DRAFT_SAVE_DELAY_MS = 700;
const interviewGoalLabels: Record<string, string> = {
  internship: "实习",
  campus: "校招",
  big_tech: "冲刺大厂"
};
const difficultyLabels: Record<string, string> = {
  easy: "简单",
  normal: "普通",
  pressure: "压力"
};
const roundDifficultyOptions: {
  value: InterviewDifficulty;
  label: string;
  note: string;
}[] = [
  { value: "easy", label: "简单", note: "友好引导" },
  { value: "normal", label: "普通", note: "真实校招节奏" },
  { value: "pressure", label: "压力", note: "高密度追问" }
];
const roundTimeLimitOptions: { value: TimeLimitMinutes; label: string; note: string }[] = [
  { value: 30, label: "30 分钟", note: "快速摸底" },
  { value: 45, label: "45 分钟", note: "标准节奏" },
  { value: 60, label: "60 分钟", note: "完整模拟" }
];

const route = useRoute();
const router = useRouter();
const interviewId = computed(() => Number(route.params.id));
const state = ref<MultiRoundState | null>(null);
const currentQuestion = ref<MultiRoundQuestion | null>(null);
const message = ref("");
const hasError = ref(false);
const busyRoundType = ref<RoundType | null>(null);
const busyErrorRoundType = ref<RoundType | null>(null);
const operationFailed = ref(false);
const thinkingText = ref("面试官正在思考");
const isThinkingVisible = ref(false);
const isGeneratingOverall = ref(false);
const latestRoundSummary = ref<RoundSummary | null>(null);
const latestRoundSummaryRoundType = ref<RoundType | null>(null);
const savingBookmarkQuestionId = ref<number | null>(null);
const savedBookmarkQuestionIds = ref<Set<number>>(new Set());
const answerBookmarkMessage = ref("");
const answerBookmarkError = ref(false);
const answerBookmarkQuestionId = ref<number | null>(null);
const streamingRoundType = ref<RoundType | null>(null);
const messagesByRound = ref<Record<RoundType, ChatMessage[]>>(emptyMessagesByRound());
const draftTexts = ref<Record<RoundType, string>>(emptyDrafts());
const messageEls = ref<Partial<Record<RoundType, HTMLElement | null>>>({});
const textareaEls = ref<Partial<Record<RoundType, HTMLTextAreaElement | null>>>({});
const selectedRoundType = ref<RoundType | null>(null);
const openMenuRound = ref<RoundType | null>(null);
const elapsedTick = ref(Date.now());
const stateLoadedAt = ref(Date.now());
const lastFailedAction = ref<FailedRoundAction | null>(null);
const switchingRoundType = ref<RoundType | null>(null);
const roomTheme = ref<"light" | "dark">("light");
const isInfoPanelCollapsed = ref(window.matchMedia("(max-width: 900px)").matches);
const draftSaveStatus = ref<DraftSaveStatus>("idle");
const draftStatusQuestionId = ref<number | null>(null);
const roundConfigTarget = ref<RoundCard | null>(null);
const roundDifficulty = ref<InterviewDifficulty>("normal");
const roundTimeLimitMinutes = ref<TimeLimitMinutes>(45);
const timeoutFinishingRoundId = ref<number | null>(null);
let elapsedTimer: number | null = null;
let thinkingTimer: number | null = null;
let roundSwitchTimer: number | null = null;
let draftSaveTimer: number | null = null;
let draftLoadToken = 0;
let draftSaveToken = 0;
let roundAnimationReady = false;

const inProgressRound = computed(
  () => state.value?.rounds.find((round) => round.status === "in_progress") || null
);
const currentRoundType = computed<RoundType | null>(
  () => inProgressRound.value?.round_type || null
);
const displayRounds = computed(() =>
  orderedRoundTypes.map((type) => {
    const round = state.value?.rounds.find((item) => item.round_type === type);
    return {
      type,
      id: round?.id || null,
      status: round?.status || "skipped",
      label: roundMetas[type].label,
      interviewer: roundMetas[type].interviewer,
      avatar: roundMetas[type].avatar,
      focus: roundMetas[type].focus,
      messages: messagesByRound.value[type],
      elapsedSeconds: round?.elapsed_seconds || 0,
      difficulty: round?.difficulty || "normal",
      timeLimitMinutes: round?.time_limit_minutes || 45,
      summary: round?.summary || null
    } satisfies RoundCard;
  })
);
const nextStartableRound = computed(
  () => state.value?.rounds.find((round) => round.status === "pending") || null
);
const selectedRounds = computed(
  () => state.value?.rounds.filter((round) => round.status !== "skipped") || []
);
const activeRoundType = computed<RoundType | null>(
  () =>
    selectedRoundType.value ||
    inProgressRound.value?.round_type ||
    nextStartableRound.value?.round_type ||
    selectedRounds.value[0]?.round_type ||
    null
);
const activeRound = computed(
  () => displayRounds.value.find((round) => round.type === activeRoundType.value) || null
);
const currentActionRound = computed(() => {
  const type = currentRoundType.value;
  return type ? displayRounds.value.find((round) => round.type === type) || null : null;
});
const isBusy = computed(() => busyRoundType.value !== null || streamingRoundType.value !== null);
const roundFailureMessage = computed(
  () => message.value || "问题生成失败，可以重试或先结束当前轮。"
);
const isInterviewPaused = computed(() => state.value?.overall_status === "paused");
const isInteractionPaused = computed(() => isInterviewPaused.value || isFlowPaused.value);
const canToggleInterviewPause = computed(() => {
  if (!state.value || isBusy.value || isFlowPaused.value) {
    return false;
  }
  if (isInterviewPaused.value) {
    return true;
  }
  return Boolean(inProgressRound.value);
});
const roundLimitSeconds = computed(() => (inProgressRound.value?.time_limit_minutes || 45) * 60);
const elapsedRoundSeconds = computed(() => {
  if (!inProgressRound.value) {
    return 0;
  }
  const extraSeconds =
    currentRoundType.value && !isInterviewPaused.value
      ? Math.floor((elapsedTick.value - stateLoadedAt.value) / 1000)
      : 0;
  return (inProgressRound.value.elapsed_seconds || 0) + extraSeconds;
});
const remainingSeconds = computed(() =>
  Math.max(0, roundLimitSeconds.value - elapsedRoundSeconds.value)
);
const isInterviewClosed = computed(() =>
  ["finished", "completed", "cancelled"].includes(state.value?.overall_status || "")
);
const isRoundTimeExpired = computed(
  () => Boolean(inProgressRound.value) && !isInterviewClosed.value && remainingSeconds.value <= 0
);
const remainingTimeLabel = computed(() =>
  isRoundTimeExpired.value ? "已到限时" : formatDuration(remainingSeconds.value)
);
const strategyLabel = computed(() => {
  const goal = state.value?.interview_goal || "campus";
  const difficulty = activeRound.value?.difficulty || "normal";
  const minutes = activeRound.value?.timeLimitMinutes || 45;
  return `${interviewGoalLabels[goal] || goal} · 本轮${difficultyLabels[difficulty] || difficulty} · ${minutes} 分钟`;
});
const canFinishOverall = computed(() => {
  if (!state.value || selectedRounds.value.length === 0) {
    return false;
  }

  if (isInterviewPaused.value) {
    return false;
  }

  return selectedRounds.value.every((round) =>
    ["completed", "finished_early", "cancelled"].includes(round.status)
  );
});
const currentTimerRound = computed(() => {
  const type = activeRoundType.value || nextStartableRound.value?.round_type || "resume";
  return displayRounds.value.find((round) => round.type === type) || null;
});
const roundTimerLabel = computed(() => {
  if (!state.value) {
    return "等待开始";
  }
  if (isRoundTimeExpired.value) {
    return "已到限时";
  }
  if (!inProgressRound.value && currentTimerRound.value) {
    return `${currentTimerRound.value.label} · 尚未开始`;
  }
  if (currentTimerRound.value) {
    return `${currentTimerRound.value.label} · 剩余 ${remainingTimeLabel.value}`;
  }
  return `剩余 ${remainingTimeLabel.value}`;
});
const overallBarText = computed(() => {
  if (isGeneratingOverall.value) {
    return "正在生成总评报告";
  }
  return "已完成所有选择的轮次，可以生成总评报告。";
});
const activeRoundSummary = computed(() => {
  if (!activeRound.value) {
    return null;
  }
  if (latestRoundSummaryRoundType.value === activeRound.value.type && latestRoundSummary.value) {
    return latestRoundSummary.value;
  }
  return activeRound.value.summary;
});
const isDarkRoom = computed(() => roomTheme.value === "dark");
const completionPercent = computed(() => {
  if (selectedRounds.value.length === 0) {
    return 0;
  }
  const finishedCount = selectedRounds.value.filter((round) =>
    ["completed", "finished_early", "cancelled"].includes(round.status)
  ).length;
  return Math.round((finishedCount / selectedRounds.value.length) * 100);
});
const flowStatus = computed<HarnessStatus | null>(() => state.value?.harness_status || null);
const isFlowPaused = computed(() => flowStatus.value === "paused");
const userFlowNotice = computed<UserFlowNotice | null>(() => {
  if (!state.value) {
    return null;
  }

  if (isRoundTimeExpired.value) {
    const hasDraft = Boolean(
      currentRoundType.value && draftTexts.value[currentRoundType.value].trim()
    );
    return {
      title: "本轮已到限时",
      text: hasDraft
        ? "请提交正在作答的当前回答，提交后本轮将自动结束。"
        : "面试官正在结束本轮并生成评价。",
      tone: "warning"
    };
  }

  if (currentQuestion.value?.is_last_question) {
    return {
      title: "这是本轮最后一个问题",
      text: "提交本题后，本轮面试将结束并生成评价。",
      tone: "info"
    };
  }

  if (isInterviewPaused.value) {
    return {
      title: "面试已暂停",
      text: "当前问题和回答草稿已保留，点击操作菜单里的继续面试即可恢复。",
      tone: "warning"
    };
  }

  const recovered = (state.value.recovery_count || 0) > 0;
  const degraded = Boolean(state.value.had_degradation);

  if (flowStatus.value === "retrying") {
    return {
      title: "正在自动重试",
      text: "系统正在重新处理当前步骤，请稍候。",
      tone: "info"
    };
  }
  if (flowStatus.value === "degraded") {
    return {
      title: "已切换备用流程",
      text: "当前面试可继续，后续结果会按实际情况提示可信度。",
      tone: "warning"
    };
  }
  if (flowStatus.value === "paused") {
    return {
      title: "面试已暂停",
      text: "正在保存恢复点，请稍后重新检查后继续。",
      tone: "warning",
      canRefresh: true
    };
  }
  if (flowStatus.value === "failed") {
    return {
      title: "当前步骤失败",
      text: "可以稍后重试，已完成的回答会尽量保留。",
      tone: "error",
      canRefresh: true
    };
  }
  if (degraded) {
    return {
      title: "已使用备用流程",
      text: recovered
        ? "面试已恢复并可继续，报告会标注需要参考的内容。"
        : "面试可继续，报告会标注需要参考的内容。",
      tone: "warning"
    };
  }
  if (recovered) {
    return {
      title: "面试已恢复",
      text: "可以继续作答。",
      tone: "info"
    };
  }
  return null;
});

const draftStatusMessage = computed(() => {
  const questionId = currentQuestion.value?.id ?? null;
  if (!questionId || draftStatusQuestionId.value !== questionId) {
    return "";
  }
  if (draftSaveStatus.value === "saving") {
    return "草稿保存中";
  }
  if (draftSaveStatus.value === "saved") {
    return "草稿已保存";
  }
  if (draftSaveStatus.value === "restored") {
    return "已恢复上次草稿";
  }
  if (draftSaveStatus.value === "error") {
    return "草稿保存失败，刷新前请先保留答案";
  }
  return "";
});

watch(currentQuestion, (question, previous) => {
  if (previous && previous.id !== question?.id) {
    clearPendingDraftSave();
    clearDraft(previous.id);
  }
  if (question) {
    const type = roundTypeById(state.value, question.round_id);
    if (type) {
      const localDraft = localStorage.getItem(draftKey(question.id)) || "";
      draftTexts.value[type] = localDraft;
      if (localDraft.trim()) {
        setDraftStatus("restored", question.id);
        const context = draftContextForQuestion(question, type);
        if (context) {
          scheduleRemoteDraftSave(context);
        }
      } else {
        resetDraftStatus();
      }
      resizeTextareaAfterRender(type);
      void loadRemoteDraft(question, type, localDraft);
    }
  } else {
    resetDraftStatus();
  }
});

watch(currentRoundType, (nextType, previousType) => {
  if (!roundAnimationReady || !nextType || nextType === previousType) {
    return;
  }
  playRoundSwitchAnimation(nextType);
});

watch(isRoundTimeExpired, (expired) => {
  if (expired) {
    void finishExpiredRoundIfReady();
  }
});

onMounted(async () => {
  elapsedTimer = window.setInterval(() => {
    elapsedTick.value = Date.now();
    if (isRoundTimeExpired.value) {
      void finishExpiredRoundIfReady();
    }
  }, 1000);
  await loadState();
  await nextTick();
  roundAnimationReady = true;
});

onBeforeUnmount(() => {
  if (elapsedTimer !== null) {
    window.clearInterval(elapsedTimer);
  }
  if (roundSwitchTimer !== null) {
    window.clearTimeout(roundSwitchTimer);
  }
  clearPendingDraftSave();
  stopThinkingTimer();
});

async function loadState() {
  clearMessage();
  try {
    const nextState = await getMultiRoundState(interviewId.value);
    applyState(nextState);
  } catch (error) {
    showError(error instanceof ApiError ? error.message : "面试状态恢复失败。");
  }
}

async function startRound(round: RoundCard) {
  if (!canStartRound(round) || round.id === null) {
    return;
  }

  openMenuRound.value = null;
  selectedRoundType.value = round.type;
  roundDifficulty.value = round.difficulty || "normal";
  roundTimeLimitMinutes.value = round.timeLimitMinutes || 45;
  roundConfigTarget.value = round;
}

function closeRoundConfig() {
  if (isBusy.value) {
    return;
  }
  roundConfigTarget.value = null;
}

async function confirmStartRound() {
  const round = roundConfigTarget.value;
  if (!round || !canStartRound(round) || round.id === null) {
    return;
  }

  resetAnswerBookmarkState();
  roundConfigTarget.value = null;
  markRoundInProgress(round.id, round.type, roundDifficulty.value, roundTimeLimitMinutes.value);
  await runRoundAction(round.type, async () => {
    const payload = await startInterviewRound(interviewId.value, round.id!, {
      difficulty: roundDifficulty.value,
      timeLimitMinutes: roundTimeLimitMinutes.value
    });
    await applyActionPayload(payload, round.type);
  });
}

async function submitRoundAnswer(round: RoundCard) {
  if (!canSubmitRound(round) || !currentQuestion.value || round.id === null) {
    return;
  }

  const question = currentQuestion.value;
  const submittedAnswer = draftTexts.value[round.type].trim();
  clearPendingDraftSave();
  resetDraftStatus();
  pushMessage(round.type, {
    id: `answer-${question.id}-${Date.now()}`,
    role: "user",
    text: submittedAnswer
  });
  draftTexts.value[round.type] = "";
  resizeTextareaAfterRender(round.type);

  await runRoundAction(
    round.type,
    async () => {
      const payload = await submitRoundAnswerApi(
        interviewId.value,
        round.id!,
        question.id,
        submittedAnswer
      );
      await applyActionPayload(payload, round.type);
    },
    undefined,
    {
      retryAction: () => refreshAfterSubmitFailure(round.type)
    }
  );
  if (operationFailed.value && currentQuestion.value?.id === question.id) {
    draftTexts.value[round.type] = submittedAnswer;
    localStorage.setItem(draftKey(question.id), submittedAnswer);
    setDraftStatus("restored", question.id);
    resizeTextareaAfterRender(round.type);
  }
}

function handleComposerKeydown(event: KeyboardEvent, round: RoundCard) {
  if (event.key !== "Enter" || event.shiftKey) {
    return;
  }
  if (event.isComposing || event.keyCode === 229 || event.altKey) {
    return;
  }

  event.preventDefault();
  submitRoundAnswer(round);
}

async function finishRoundFromMenu(round: RoundCard) {
  if (!canFinishRound(round) || round.id === null) {
    return;
  }

  const question = currentQuestion.value;
  const confirmed = window.confirm(finishRoundConfirmMessage(round));
  if (!confirmed) {
    return;
  }

  openMenuRound.value = null;
  if (question?.round_id === round.id) {
    clearPendingDraftSave();
    resetDraftStatus();
  }
  await runRoundAction(
    round.type,
    async () => {
      const payload = await finishInterviewRound(interviewId.value, round.id!, "early");
      await applyActionPayload(payload, round.type);
      await loadState();
    },
    { initialText: "面试官正在评分，请稍后", delayedText: "面试官正在评分，请稍后" }
  );
}

async function finishExpiredRoundIfReady() {
  const round = inProgressRound.value;
  if (
    !round ||
    isInterviewPaused.value ||
    isBusy.value ||
    timeoutFinishingRoundId.value === round.id
  ) {
    return;
  }
  const roundType = round.round_type;
  if (currentQuestion.value?.round_id === round.id && draftTexts.value[roundType].trim()) {
    return;
  }

  timeoutFinishingRoundId.value = round.id;
  const question = currentQuestion.value;
  if (question?.round_id === round.id) {
    clearPendingDraftSave();
    resetDraftStatus();
  }
  try {
    await runRoundAction(
      roundType,
      async () => {
        const payload = await finishInterviewRound(interviewId.value, round.id, "timeout");
        await applyActionPayload(payload, roundType);
      },
      { initialText: "面试官正在自然收尾", delayedText: "正在生成本轮评价" }
    );
  } finally {
    timeoutFinishingRoundId.value = null;
  }
}

async function regenerateQuestionFromMenu(round: RoundCard) {
  if (!canRegenerateQuestion(round) || !currentQuestion.value || round.id === null) {
    return;
  }

  const oldQuestion = currentQuestion.value;
  const confirmed = window.confirm("确定重新生成当前问题吗？旧问题会保留为审计记录，不参与评分。");
  if (!confirmed) {
    return;
  }

  openMenuRound.value = null;
  clearPendingDraftSave();
  resetDraftStatus();
  await runRoundAction(
    round.type,
    async () => {
      const payload = await regenerateRoundQuestion(interviewId.value, round.id!, oldQuestion.id);
      await loadState();
      await applyActionPayload(payload, round.type);
    },
    { initialText: "面试官正在重新出题", delayedText: "面试官正在重新出题" }
  );
}

async function skipQuestionFromMenu(round: RoundCard) {
  if (!canSkipQuestion(round) || !currentQuestion.value || round.id === null) {
    return;
  }

  const oldQuestion = currentQuestion.value;
  const confirmed = window.confirm("确定跳过当前问题吗？旧问题会保留为审计记录，不参与评分。");
  if (!confirmed) {
    return;
  }

  openMenuRound.value = null;
  clearPendingDraftSave();
  resetDraftStatus();
  await runRoundAction(
    round.type,
    async () => {
      const payload = await skipRoundQuestion(interviewId.value, round.id!, oldQuestion.id);
      await loadState();
      await applyActionPayload(payload, round.type);
    },
    { initialText: "面试官正在切换问题", delayedText: "面试官正在切换问题" }
  );
}

async function toggleInterviewPause() {
  if (!canToggleInterviewPause.value) {
    return;
  }

  const actionType = currentRoundType.value || activeRoundType.value || "resume";
  openMenuRound.value = null;
  await runRoundAction(actionType, async () => {
    const payload = isInterviewPaused.value
      ? await resumeMultiRoundInterview(interviewId.value)
      : await pauseMultiRoundInterview(interviewId.value);
    applyState(payload);
  });
}

async function finishOverall() {
  if (isInterviewPaused.value) {
    showError("面试已暂停，请先继续面试。");
    return;
  }

  isGeneratingOverall.value = true;
  await runRoundAction(
    activeRoundType.value || "resume",
    async () => {
      const report = await finishMultiRoundInterview(interviewId.value, "normal");
      router.push(`/history/${report.interview_id}`);
    },
    undefined,
    { showThinking: false }
  );
  isGeneratingOverall.value = false;
}

async function exitInterview() {
  const confirmed = window.confirm(exitInterviewConfirmMessage());
  if (!confirmed) {
    return;
  }

  const actionType = activeRoundType.value || inProgressRound.value?.round_type || "resume";
  await runRoundAction(
    actionType,
    async () => {
      const question = currentQuestion.value;
      if (question) {
        clearPendingDraftSave();
        resetDraftStatus();
      }
      const report = await finishMultiRoundInterview(interviewId.value, "early");
      if (question) {
        clearDraft(question.id);
      }
      router.push(`/history/${report.interview_id}`);
    },
    undefined,
    { showThinking: false }
  );
}

async function retryLastAction() {
  const failedAction = lastFailedAction.value;
  if (!failedAction) {
    return;
  }
  await runRoundAction(
    failedAction.roundType,
    failedAction.retryAction || failedAction.action,
    failedAction.thinkingOptions,
    { showThinking: failedAction.showThinking }
  );
}

async function runRoundAction(
  roundType: RoundType,
  action: () => Promise<void>,
  thinkingOptions?: { initialText?: string; delayedText?: string },
  options: { retryAction?: () => Promise<void>; showThinking?: boolean } = {}
) {
  const showThinking = options.showThinking !== false;
  busyRoundType.value = roundType;
  busyErrorRoundType.value = null;
  operationFailed.value = false;
  isThinkingVisible.value = showThinking;
  lastFailedAction.value = {
    roundType,
    action,
    retryAction: options.retryAction,
    thinkingOptions,
    showThinking
  };
  clearMessage();
  if (showThinking) {
    startThinkingTimer(thinkingOptions);
  } else {
    stopThinkingTimer();
  }
  try {
    await action();
    operationFailed.value = false;
    lastFailedAction.value = null;
  } catch (error) {
    operationFailed.value = true;
    busyErrorRoundType.value = roundType;
    showError(error instanceof ApiError ? error.message : "问题生成失败，请稍后重试。");
  } finally {
    busyRoundType.value = null;
    isThinkingVisible.value = false;
    stopThinkingTimer();
  }
}

async function refreshAfterSubmitFailure(roundType: RoundType) {
  const nextState = await getMultiRoundState(interviewId.value);
  applyState(nextState);
  selectedRoundType.value = nextState.current_question
    ? roundTypeById(nextState, nextState.current_question.round_id) || roundType
    : roundType;
}

async function applyActionPayload(
  payload: RoundAnswerResponse | MultiRoundState,
  fallbackType: RoundType
) {
  if (isStatePayload(payload)) {
    applyState(payload);
    return;
  }

  latestRoundSummary.value = payload.round_summary || null;
  latestRoundSummaryRoundType.value = fallbackType;
  if (payload.answer_evaluation) {
    attachAnswerEvaluation(fallbackType, payload.answer_evaluation);
    answerBookmarkMessage.value = "";
    answerBookmarkError.value = false;
    answerBookmarkQuestionId.value = null;
  }
  if (payload.question) {
    const questionRoundType = roundTypeById(state.value, payload.question.round_id) || fallbackType;
    currentQuestion.value = payload.question;
    busyRoundType.value = null;
    isThinkingVisible.value = false;
    stopThinkingTimer();
    await pushQuestion(payload.question);
    focusRoundInput(questionRoundType);
    return;
  }

  if (payload.action === "finish_round") {
    currentQuestion.value = null;
    selectedRoundType.value = null;
    await loadState();
  }
}

function applyState(nextState: MultiRoundState) {
  state.value = nextState;
  stateLoadedAt.value = Date.now();
  elapsedTick.value = Date.now();
  currentQuestion.value = nextState.current_question;
  latestRoundSummary.value = null;
  latestRoundSummaryRoundType.value = null;
  hydrateMessages(nextState);
  const runningRound = nextState.rounds.find((round) => round.status === "in_progress");
  if (runningRound) {
    selectedRoundType.value = runningRound.round_type;
  } else {
    selectedRoundType.value = null;
  }
  clearMessage();
}

function markRoundInProgress(
  roundId: number,
  roundType: RoundType,
  difficulty: InterviewDifficulty,
  timeLimitMinutes: TimeLimitMinutes
) {
  if (!state.value) {
    return;
  }

  const nextRounds = state.value.rounds.map((item) =>
    item.id === roundId
      ? {
          ...item,
          status: "in_progress" as const,
          elapsed_seconds: 0,
          difficulty,
          time_limit_minutes: timeLimitMinutes
        }
      : item
  );
  state.value = {
    ...state.value,
    overall_status: "in_progress",
    current_round: roundType,
    rounds: nextRounds
  };
  stateLoadedAt.value = Date.now();
  elapsedTick.value = Date.now();
}

function hydrateMessages(source: MultiRoundState) {
  const hydrated = emptyMessagesByRound();
  const currentQuestionId = source.current_question?.id ?? null;
  for (const entry of source.qa_history || []) {
    if (entry.question_status && entry.question_status !== "active") {
      continue;
    }
    if (entry.id === currentQuestionId && !readAnswerText(entry)) {
      continue;
    }
    const question = readQuestionText(entry);
    if (!question) {
      continue;
    }
    const roundType =
      entry.round_type || (entry.round_id ? roundTypeById(source, entry.round_id) : null);
    if (!roundType) {
      continue;
    }
    const questionMessageIndex = hydrated[roundType].length;
    hydrated[roundType].push({
      id: `q-${entry.id || `${roundType}-${entry.sequence || questionMessageIndex}`}`,
      role: "assistant",
      text: question,
      roundLabel: roundMetas[roundType].label
    });
    const answer = readAnswerText(entry);
    if (answer) {
      const answerMessageIndex = hydrated[roundType].length;
      hydrated[roundType].push({
        id: `a-${entry.id || `${roundType}-${entry.sequence || answerMessageIndex}`}`,
        role: "user",
        text: answer,
        answerEvaluation: entry.question_evaluation || undefined
      });
    }
  }

  messagesByRound.value = hydrated;
  if (source.current_question) {
    void pushQuestion(source.current_question, false);
  }
  scrollAllMessagesToEnd();
}

async function pushQuestion(question: MultiRoundQuestion, append = true) {
  const type =
    roundTypeById(state.value, question.round_id) || state.value?.current_round || "resume";
  const nextMessage = {
    id: `current-${question.id}`,
    role: "assistant" as const,
    text: append ? "" : question.question,
    roundLabel: roundMetas[type].label
  };

  if (messagesByRound.value[type].some((item) => item.id === nextMessage.id)) {
    return;
  }

  if (append) {
    pushMessage(type, nextMessage);
    await streamQuestionMessage(type, nextMessage.id, question.question);
  } else {
    messagesByRound.value[type].push(nextMessage);
  }
}

async function streamQuestionMessage(roundType: RoundType, messageId: string, text: string) {
  streamingRoundType.value = roundType;
  const characters = Array.from(text);

  try {
    for (const character of characters) {
      const targetMessage = messagesByRound.value[roundType].find((item) => item.id === messageId);
      if (!targetMessage) {
        return;
      }

      targetMessage.text += character;
      scrollMessagesToEnd(roundType);
      await delay(character.trim() ? 32 : 12);
    }
  } finally {
    streamingRoundType.value = null;
  }
}

function pushMessage(roundType: RoundType, item: ChatMessage) {
  messagesByRound.value[roundType].push(item);
  scrollMessagesToEnd(roundType);
}

function attachAnswerEvaluation(roundType: RoundType, evaluation: QuestionEvaluation) {
  const questionId = evaluation.question_id;
  const messages = messagesByRound.value[roundType];
  const target =
    typeof questionId === "number"
      ? [...messages]
          .reverse()
          .find((item) => item.role === "user" && item.id.startsWith(`answer-${questionId}-`))
      : [...messages].reverse().find((item) => item.role === "user");
  if (target) {
    target.answerEvaluation = evaluation;
  }
}

function roundTypeById(source: MultiRoundState | null, roundId: number): RoundType | null {
  return source?.rounds.find((round) => round.id === roundId)?.round_type || null;
}

function readQuestionText(entry: MultiRoundQaEntry): string {
  return entry.question || entry.question_text || entry.prompt || "";
}

function readAnswerText(entry: MultiRoundQaEntry): string {
  return entry.answer || entry.answer_text || entry.user_answer || "";
}

function selectRound(round: RoundCard) {
  if (!state.value) {
    return;
  }
  if (!canSelectRoundCard(round)) {
    return;
  }
  selectedRoundType.value = round.type;
  openMenuRound.value = null;
}

function canSelectRoundCard(round: RoundCard) {
  if (round.status === "in_progress") {
    return true;
  }
  if (!currentRoundType.value && nextStartableRound.value?.id === round.id) {
    return true;
  }
  if (!isReviewableRound(round)) {
    return false;
  }
  if (!currentRoundType.value) {
    return true;
  }
  return roundOrderIndex(round.type) < roundOrderIndex(currentRoundType.value);
}

function playRoundSwitchAnimation(type: RoundType) {
  if (roundSwitchTimer !== null) {
    window.clearTimeout(roundSwitchTimer);
  }
  switchingRoundType.value = type;
  roundSwitchTimer = window.setTimeout(() => {
    switchingRoundType.value = null;
    roundSwitchTimer = null;
  }, 560);
}

function canStartRound(round: RoundCard) {
  return (
    !isBusy.value &&
    !isInteractionPaused.value &&
    !isRoundTimeExpired.value &&
    round.id !== null &&
    round.status === "pending" &&
    nextStartableRound.value?.id === round.id
  );
}

function isReviewableRound(round: RoundCard) {
  return ["completed", "finished_early", "cancelled"].includes(round.status);
}

function roundOrderIndex(type: RoundType) {
  return orderedRoundTypes.indexOf(type);
}

function canFinishRound(round: RoundCard) {
  return (
    !isBusy.value &&
    !isInteractionPaused.value &&
    round.id !== null &&
    round.status === "in_progress"
  );
}

function canRegenerateQuestion(round: RoundCard) {
  return canTypeInRound(round) && Boolean(currentQuestion.value);
}

function canSkipQuestion(round: RoundCard) {
  return canRegenerateQuestion(round);
}

function canTypeInRound(round: RoundCard) {
  const maySubmitExpiredAnswer =
    isRoundTimeExpired.value &&
    currentQuestion.value?.round_id === round.id &&
    Boolean(draftTexts.value[round.type].trim());
  return (
    !isBusy.value &&
    !isInteractionPaused.value &&
    (!isRoundTimeExpired.value || maySubmitExpiredAnswer) &&
    round.status === "in_progress" &&
    currentQuestion.value?.round_id === round.id
  );
}

function canSubmitRound(round: RoundCard) {
  return canTypeInRound(round) && Boolean(draftTexts.value[round.type].trim());
}

function finishRoundConfirmMessage(round: RoundCard) {
  const lines = ["确定结束当前轮吗？"];
  if (currentQuestion.value?.round_id === round.id) {
    lines.push("当前未回答问题会记为跳过，不参与评分。");
  }
  if (draftTexts.value[round.type].trim()) {
    lines.push("当前输入框草稿不会提交。");
  }
  lines.push("本轮计时会立即暂停，本轮评价会标记为仅供参考。");
  return lines.join("\n");
}

function exitInterviewConfirmMessage() {
  const lines = ["确定退出整场面试吗？"];
  if (currentQuestion.value) {
    lines.push("当前未回答问题会记为跳过，不参与评分。");
  }
  if (hasAnyDraft()) {
    lines.push("当前草稿不会提交。");
  }
  lines.push("未开始轮次会标记为未完成。");
  lines.push("总评报告会标记为仅供参考，结论置信度会降低。");
  return lines.join("\n");
}

function hasAnyDraft() {
  return Object.values(draftTexts.value).some((value) => Boolean(value.trim()));
}

function answerPlaceholder(round: RoundCard) {
  if (isInterviewPaused.value) {
    return "面试已暂停，继续后可作答";
  }
  if (isFlowPaused.value) {
    return "面试已暂停，请稍后继续";
  }
  if (isRoundTimeExpired.value) {
    return draftTexts.value[round.type].trim()
      ? "请提交当前回答，提交后本轮自动结束"
      : "本轮已到限时，正在生成评价";
  }
  if (round.status === "pending") {
    return "点击 + 开始本轮";
  }
  if (round.status === "in_progress") {
    return currentQuestion.value?.round_id === round.id ? "输入你的回答..." : "等待当前问题";
  }
  if (round.status === "completed" || round.status === "finished_early") {
    return "本轮已结束";
  }
  if (round.status === "cancelled") {
    return "本轮未完成";
  }
  return "本轮未选择";
}

function emptyMessage(round: RoundCard) {
  if (round.status === "pending") {
    return "本轮尚未开始";
  }
  if (round.status === "skipped") {
    return "本轮未选择";
  }
  if (round.status === "cancelled") {
    return "整场面试已退出，本轮未完成";
  }
  return "暂无消息";
}

function toggleActionMenu(round: RoundCard) {
  if (isReadOnlyRound(round)) {
    return;
  }
  openMenuRound.value = openMenuRound.value === round.type ? null : round.type;
  selectedRoundType.value = round.type;
}

function toggleRoomTheme() {
  roomTheme.value = isDarkRoom.value ? "light" : "dark";
  isInfoPanelCollapsed.value = roomTheme.value === "dark";
}

function toggleInfoPanel() {
  isInfoPanelCollapsed.value = !isInfoPanelCollapsed.value;
}

function closeActionMenu() {
  openMenuRound.value = null;
}

function roundElapsedSeconds(round: RoundCard) {
  const extraSeconds =
    round.status === "in_progress" && !isInterviewPaused.value
      ? Math.floor((elapsedTick.value - stateLoadedAt.value) / 1000)
      : 0;
  return round.elapsedSeconds + extraSeconds;
}

function isReadOnlyRound(round: RoundCard) {
  return ["completed", "finished_early", "cancelled", "skipped"].includes(round.status);
}

function roundSummaryText(summary: RoundSummary) {
  const issues = summary.main_issues?.filter(Boolean) || [];
  if (issues.length > 0) {
    return issues.join("；");
  }
  const suggestions = summary.suggestions?.filter(Boolean) || [];
  if (suggestions.length > 0) {
    return suggestions[0];
  }
  return summary.reference_note || "";
}

function questionEvaluationText(evaluation: QuestionEvaluation) {
  const strengths = evaluation.strengths?.filter(Boolean) || [];
  if (strengths.length > 0) {
    return strengths[0];
  }
  const issues = evaluation.issues?.filter(Boolean) || [];
  if (issues.length > 0) {
    return issues[0];
  }
  return evaluation.follow_up_direction || "已完成本题评分。";
}

function answerQualityTone(evaluation: QuestionEvaluation): string {
  if (evaluation.status === "fallback" || evaluation.total_score === null) {
    return "quality-hint";
  }
  const score = evaluation.total_score ?? 0;
  if (score >= 80) {
    return "quality-strong";
  }
  if (score >= 60) {
    return "quality-steady";
  }
  return "quality-needs-work";
}

function answerQualityLabel(evaluation: QuestionEvaluation): string {
  if (evaluation.status === "fallback" || evaluation.total_score === null) {
    return "结构建议";
  }
  const score = evaluation.total_score ?? 0;
  if (score >= 80) {
    return "表现较好";
  }
  if (score >= 60) {
    return "可以打磨";
  }
  return "需要补强";
}

function answerQualityLead(evaluation: QuestionEvaluation): string {
  if (evaluation.status === "fallback" || evaluation.total_score === null) {
    return "本次未生成可靠分数，以下建议仅用于检查回答结构。";
  }
  const score = evaluation.total_score ?? 0;
  if (score >= 80) {
    return "回答整体扎实，可以继续强化证据和岗位相关性。";
  }
  if (score >= 60) {
    return "回答方向基本成立，建议优先补足下面的关键信息。";
  }
  return "回答仍有明显缺口，建议按下面的提示补充后再复盘。";
}

function answerQualityStrengths(evaluation: QuestionEvaluation): string[] {
  return uniqueEvaluationText(evaluation.strengths).slice(0, 3);
}

function answerQualityIssues(evaluation: QuestionEvaluation): string[] {
  return uniqueEvaluationText(evaluation.issues).slice(0, 4);
}

function answerQualityEvidence(evaluation: QuestionEvaluation): string[] {
  return uniqueEvaluationText(evaluation.evidence).slice(0, 3);
}

function answerQualityDimensions(evaluation: QuestionEvaluation) {
  return (evaluation.dimension_scores || []).filter(
    (item) =>
      item &&
      typeof item.dimension === "string" &&
      item.dimension.trim() &&
      typeof item.score === "number"
  );
}

function uniqueEvaluationText(values?: string[]): string[] {
  return [...new Set((values || []).map((value) => value.trim()).filter(Boolean))];
}

function hasAnswerQualityDetails(evaluation: QuestionEvaluation): boolean {
  return Boolean(
    answerQualityDimensions(evaluation).length ||
    answerQualityStrengths(evaluation).length ||
    answerQualityIssues(evaluation).length ||
    evaluation.follow_up_direction ||
    answerQualityEvidence(evaluation).length
  );
}

function canBookmarkAnswer(evaluation: QuestionEvaluation): boolean {
  return typeof evaluation.question_id === "number";
}

function isSavingAnswerBookmark(evaluation: QuestionEvaluation): boolean {
  return (
    typeof evaluation.question_id === "number" &&
    savingBookmarkQuestionId.value === evaluation.question_id
  );
}

function answerBookmarkButtonText(evaluation: QuestionEvaluation): string {
  const questionId = evaluation.question_id;
  if (typeof questionId !== "number") {
    return "无法收藏";
  }
  if (savingBookmarkQuestionId.value === questionId) {
    return "加入中";
  }
  if (savedBookmarkQuestionIds.value.has(questionId)) {
    return "已加入复盘";
  }
  return "加入复盘";
}

async function bookmarkAnswerEvaluation(evaluation: QuestionEvaluation) {
  if (!canBookmarkAnswer(evaluation) || isSavingAnswerBookmark(evaluation)) {
    return;
  }
  const questionId = evaluation.question_id as number;
  savingBookmarkQuestionId.value = questionId;
  answerBookmarkMessage.value = "";
  answerBookmarkError.value = false;
  answerBookmarkQuestionId.value = questionId;
  try {
    const issues = answerQualityIssues(evaluation);
    const primaryIssue = issues[0] || answerQualityLead(evaluation);
    const roundType =
      (evaluation.round_id ? roundTypeById(state.value, evaluation.round_id) : null) ||
      activeRound.value?.type;
    await saveReviewBookmark({
      interview_id: interviewId.value,
      round_id: evaluation.round_id,
      question_id: questionId,
      round_type: roundType,
      title: clipBookmarkText(primaryIssue, 500),
      issue: clipBookmarkText(primaryIssue, 1000),
      suggestion: clipBookmarkText(
        evaluation.follow_up_direction || issues[1] || primaryIssue,
        1000
      ),
      source_score:
        typeof evaluation.total_score === "number"
          ? normalizeBookmarkScore(evaluation.total_score)
          : undefined,
      evaluation: reviewBookmarkEvaluation(evaluation)
    });
    savedBookmarkQuestionIds.value = new Set([
      ...Array.from(savedBookmarkQuestionIds.value),
      questionId
    ]);
    answerBookmarkMessage.value = "已加入首页复盘清单";
  } catch (error) {
    answerBookmarkMessage.value =
      error instanceof ApiError ? error.message : "加入复盘失败，请稍后重试。";
    answerBookmarkError.value = true;
  } finally {
    savingBookmarkQuestionId.value = null;
  }
}

function resetAnswerBookmarkState() {
  savingBookmarkQuestionId.value = null;
  answerBookmarkMessage.value = "";
  answerBookmarkError.value = false;
  answerBookmarkQuestionId.value = null;
}

function clipBookmarkText(value: string | null | undefined, maxLength: number) {
  const normalized = value?.trim();
  return normalized ? normalized.slice(0, maxLength) : undefined;
}

function reviewBookmarkEvaluation(evaluation: QuestionEvaluation): QuestionEvaluation {
  return {
    question_id: evaluation.question_id,
    round_id: evaluation.round_id,
    round_type: evaluation.round_type,
    status: clipBookmarkText(evaluation.status, 32),
    total_score:
      typeof evaluation.total_score === "number"
        ? normalizeBookmarkScore(evaluation.total_score)
        : evaluation.total_score,
    dimension_scores: normalizeBookmarkDimensionScores(evaluation.dimension_scores),
    strengths: evaluation.strengths?.slice(0, 8).map((item) => item.slice(0, 1000)),
    issues: evaluation.issues?.slice(0, 8).map((item) => item.slice(0, 1000)),
    evidence: evaluation.evidence?.slice(0, 8).map((item) => item.slice(0, 1000)),
    should_follow_up: evaluation.should_follow_up,
    follow_up_direction: clipBookmarkText(evaluation.follow_up_direction, 1000),
    prompt_version: clipBookmarkText(evaluation.prompt_version, 128),
    model_name: clipBookmarkText(evaluation.model_name, 128)
  };
}

function normalizeBookmarkDimensionScores(value: unknown[] | undefined) {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.slice(0, 8).flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const record = item as Record<string, unknown>;
    const dimension =
      typeof record.dimension === "string" ? record.dimension.trim().slice(0, 120) : "";
    if (!dimension || typeof record.score !== "number") {
      return [];
    }
    return [
      {
        dimension,
        score: normalizeBookmarkScore(record.score),
        reason:
          typeof record.reason === "string"
            ? record.reason.trim().slice(0, 1000) || undefined
            : undefined
      }
    ];
  });
}

function normalizeBookmarkScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatDuration(totalSeconds: number) {
  const normalized = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(normalized / 60);
  const seconds = normalized % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function isStatePayload(
  payload: RoundAnswerResponse | MultiRoundState
): payload is MultiRoundState {
  return Boolean((payload as MultiRoundState).rounds && (payload as MultiRoundState).interview_id);
}

function startThinkingTimer(options?: { initialText?: string; delayedText?: string }) {
  stopThinkingTimer();
  thinkingText.value = options?.initialText || "面试官正在思考";
  thinkingTimer = window.setTimeout(() => {
    thinkingText.value = options?.delayedText || "正在整理下一问题";
  }, 8000);
}

function stopThinkingTimer() {
  if (thinkingTimer !== null) {
    window.clearTimeout(thinkingTimer);
    thinkingTimer = null;
  }
}

function draftKey(questionId: number) {
  return `multi_round_draft:${interviewId.value}:${questionId}`;
}

function clearDraft(questionId: number) {
  localStorage.removeItem(draftKey(questionId));
}

function draftContextForQuestion(
  question: MultiRoundQuestion,
  roundType: RoundType
): DraftContext | null {
  if (!Number.isFinite(interviewId.value)) {
    return null;
  }
  return {
    interviewId: interviewId.value,
    roundId: question.round_id,
    questionId: question.id,
    roundType
  };
}

function currentDraftContext(type: RoundType): DraftContext | null {
  const question = currentQuestion.value;
  if (!question || roundTypeById(state.value, question.round_id) !== type) {
    return null;
  }
  return draftContextForQuestion(question, type);
}

function isCurrentDraftContext(context: DraftContext) {
  const question = currentQuestion.value;
  return (
    question?.id === context.questionId &&
    question.round_id === context.roundId &&
    interviewId.value === context.interviewId &&
    roundTypeById(state.value, question.round_id) === context.roundType
  );
}

function setDraftStatus(status: DraftSaveStatus, questionId: number) {
  draftSaveStatus.value = status;
  draftStatusQuestionId.value = questionId;
}

function resetDraftStatus() {
  draftSaveStatus.value = "idle";
  draftStatusQuestionId.value = null;
}

function clearPendingDraftSave() {
  if (draftSaveTimer !== null) {
    window.clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
  }
  draftSaveToken += 1;
}

function onDraftInput(type: RoundType) {
  resizeTextarea(type);
  const context = currentDraftContext(type);
  if (!context) {
    return;
  }

  const value = draftTexts.value[type];
  const key = draftKey(context.questionId);
  if (value.trim()) {
    localStorage.setItem(key, value);
    setDraftStatus("saving", context.questionId);
  } else {
    localStorage.removeItem(key);
    resetDraftStatus();
  }
  scheduleRemoteDraftSave(context);
}

async function loadRemoteDraft(question: MultiRoundQuestion, type: RoundType, localDraft: string) {
  const context = draftContextForQuestion(question, type);
  if (!context) {
    return;
  }
  const token = ++draftLoadToken;
  try {
    const draft = await getRoundAnswerDraft(
      context.interviewId,
      context.roundId,
      context.questionId
    );
    if (token !== draftLoadToken || !isCurrentDraftContext(context)) {
      return;
    }
    const remoteDraft = draft.answer || "";
    const currentText = draftTexts.value[type];
    if (remoteDraft.trim() && !localDraft.trim() && !currentText.trim()) {
      draftTexts.value[type] = remoteDraft;
      localStorage.setItem(draftKey(context.questionId), remoteDraft);
      setDraftStatus("restored", context.questionId);
      resizeTextareaAfterRender(type);
      return;
    }
    if (localDraft.trim()) {
      setDraftStatus("restored", context.questionId);
      scheduleRemoteDraftSave(context);
      return;
    }
    if (!remoteDraft.trim()) {
      resetDraftStatus();
    }
  } catch {
    if (isCurrentDraftContext(context) && !localDraft.trim()) {
      resetDraftStatus();
    }
  }
}

function scheduleRemoteDraftSave(context: DraftContext) {
  clearPendingDraftSave();
  const answer = draftTexts.value[context.roundType];
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = null;
    void persistRemoteDraft(context, answer);
  }, DRAFT_SAVE_DELAY_MS);
}

async function persistRemoteDraft(context: DraftContext, answer: string) {
  if (!isCurrentDraftContext(context)) {
    return;
  }
  const token = ++draftSaveToken;
  const hasContent = Boolean(answer.trim());
  if (hasContent) {
    setDraftStatus("saving", context.questionId);
  }
  try {
    if (hasContent) {
      await saveRoundAnswerDraft(context.interviewId, context.roundId, context.questionId, answer);
    } else {
      await deleteRoundAnswerDraft(context.interviewId, context.roundId, context.questionId);
    }
    if (token !== draftSaveToken || !isCurrentDraftContext(context)) {
      return;
    }
    if (hasContent) {
      setDraftStatus("saved", context.questionId);
    } else {
      resetDraftStatus();
    }
  } catch {
    if (isCurrentDraftContext(context)) {
      setDraftStatus("error", context.questionId);
    }
  }
}

async function scrollMessagesToEnd(type: RoundType) {
  await nextTick();
  const el = messageEls.value[type];
  if (el) {
    el.scrollTop = el.scrollHeight;
  }
}

function scrollAllMessagesToEnd() {
  orderedRoundTypes.forEach((type) => {
    scrollMessagesToEnd(type);
  });
}

async function resizeTextareaAfterRender(type: RoundType) {
  await nextTick();
  resizeTextarea(type);
}

function resizeTextarea(type: RoundType) {
  const textarea = textareaEls.value[type];
  if (!textarea) {
    return;
  }

  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

async function focusRoundInput(type: RoundType) {
  await nextTick();
  textareaEls.value[type]?.focus();
}

type TemplateRefElement = Element | ComponentPublicInstance | null;

function setActiveMessagesEl(el: TemplateRefElement) {
  if (!activeRound.value) {
    return;
  }
  setMessagesEl(activeRound.value.type, el);
}

function setActiveTextareaEl(el: TemplateRefElement) {
  if (!activeRound.value) {
    return;
  }
  setTextareaEl(activeRound.value.type, el);
}

function setMessagesEl(type: RoundType, el: TemplateRefElement) {
  const element = el instanceof Element ? el : null;
  messageEls.value[type] = element as HTMLElement | null;
}

function setTextareaEl(type: RoundType, el: TemplateRefElement) {
  const element = el instanceof Element ? el : null;
  textareaEls.value[type] = element as HTMLTextAreaElement | null;
}

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function emptyMessagesByRound(): Record<RoundType, ChatMessage[]> {
  return {
    resume: [],
    technical: [],
    manager: [],
    hr: []
  };
}

function emptyDrafts(): Record<RoundType, string> {
  return {
    resume: "",
    technical: "",
    manager: "",
    hr: ""
  };
}

function showError(text: string) {
  message.value = text;
  hasError.value = true;
}

function clearMessage() {
  message.value = "";
  hasError.value = false;
}
</script>

<style scoped>
.multi-stage {
  --brand-500: #3b9cff;
  --violet-500: #7c6cff;
  --agent-resume: #3b9cff;
  --agent-tech: #7567f8;
  --agent-manager: #f59b45;
  --agent-hr: #f06f9b;
  --line: #dfe5ec;
  --ink: #172033;
  --muted: #758195;
  --soft: #f7f9fc;
  --panel: #ffffff;
  --panel-strong: #ffffff;
  --bubble-agent: #f1edff;
  --bubble-user: #e8f4ff;
  --accent: var(--violet-500);
  --shadow-md: 0 10px 30px rgba(31, 68, 120, 0.1);
  position: relative;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 12px;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  padding: 18px 20px;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 8%, rgba(59, 156, 255, 0.12), transparent 28%),
    linear-gradient(180deg, #f2f6fb 0%, #eef3f9 100%);
  color: var(--ink);
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", Inter, sans-serif;
}

.multi-stage:has(.state-strip) {
  grid-template-rows: auto auto auto minmax(0, 1fr);
}

.multi-stage.is-dark {
  --line: #2b3c55;
  --ink: #f4f7fb;
  --muted: #93a2b8;
  --soft: #101d2d;
  --panel: #15243a;
  --panel-strong: #17283f;
  --bubble-agent: #29345f;
  --bubble-user: #1e4262;
  --shadow-md: 0 18px 44px rgba(0, 0, 0, 0.24);
  background:
    radial-gradient(circle at 52% 0%, rgba(124, 108, 255, 0.16), transparent 30%),
    linear-gradient(180deg, #0f1928 0%, #111d2d 100%);
}

.multi-stage button {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  color: var(--ink);
  font: inherit;
  cursor: pointer;
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease,
    opacity 160ms ease,
    transform 160ms ease;
}

.multi-stage button:not(:disabled):hover {
  border-color: var(--brand-500);
  box-shadow: 0 8px 18px rgba(59, 156, 255, 0.12);
  transform: translateY(-1px);
}

.multi-stage button:focus-visible,
.round-card:focus-visible,
.round-composer textarea:focus {
  outline: 0;
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(59, 156, 255, 0.16);
}

.multi-stage button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.room-header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.room-title {
  min-width: 0;
}

.room-title h1 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(18px, 1.4vw, 22px);
  font-weight: 800;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.room-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

.theme-toggle,
.panel-toggle {
  min-height: 40px;
  padding: 0 14px;
  font-weight: 700;
  white-space: nowrap;
}

.theme-toggle {
  border-color: transparent;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
}

.panel-toggle {
  background: rgba(255, 255, 255, 0.72);
}

.is-dark .panel-toggle {
  background: #1c2c45;
}

.round-zone {
  min-width: 0;
  width: 100%;
}

.round-board {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  align-items: stretch;
  min-width: 0;
  width: 100%;
  max-width: none;
}

.round-card {
  --round-accent: var(--brand-500);
  position: relative;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  grid-template-rows: auto auto;
  gap: 3px 10px;
  min-width: 0;
  min-height: 60px;
  padding: 10px 12px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--panel) 92%, var(--soft));
  color: var(--ink);
  cursor: default;
  opacity: 0.76;
  text-align: left;
  transition:
    border-color 280ms ease,
    background-color 280ms ease,
    box-shadow 280ms ease,
    opacity 280ms ease;
}

.round-card[data-round="resume"] {
  --round-accent: var(--agent-resume);
}

.round-card[data-round="technical"] {
  --round-accent: var(--agent-tech);
}

.round-card[data-round="manager"] {
  --round-accent: var(--agent-manager);
}

.round-card[data-round="hr"] {
  --round-accent: var(--agent-hr);
}

.round-card.is-current,
.round-card.is-active-view {
  opacity: 1;
}

.round-card.is-current {
  border-color: var(--round-accent);
  background: var(--panel-strong);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--round-accent) 14%, transparent);
}

.is-dark .round-card {
  background: #17263c;
}

.is-dark .round-card.is-current {
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--round-accent) 45%, transparent),
    0 16px 34px color-mix(in srgb, var(--round-accent) 18%, transparent);
}

.round-card.is-switching {
  animation: round-switch-pop 540ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.round-card[aria-disabled="true"] {
  cursor: default;
}

.round-card:not([aria-disabled="true"]) {
  cursor: pointer;
}

.round-card > img {
  grid-row: 1 / 3;
  width: 34px;
  height: 34px;
  border: 2px solid color-mix(in srgb, var(--round-accent) 76%, white);
  border-radius: 999px;
  object-fit: cover;
  background: color-mix(in srgb, var(--round-accent) 12%, white);
  filter: grayscale(0.45) saturate(0.68);
  opacity: 0.82;
  transform-origin: 50% 85%;
  animation: interviewer-idle 5.4s ease-in-out infinite;
}

.round-card.is-current > img,
.round-card.is-active-view > img {
  filter: none;
  opacity: 1;
}

.round-card[data-round="resume"] > img {
  animation-delay: 0s;
}

.round-card[data-round="technical"] > img {
  animation-delay: 0.16s;
}

.round-card[data-round="manager"] > img {
  animation-delay: 0.32s;
}

.round-card[data-round="hr"] > img {
  animation-delay: 0.48s;
}

.round-card.is-current > img {
  animation-name: interviewer-current;
}

.round-title {
  min-width: 0;
}

.round-title strong,
.round-title span,
.round-state span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.round-title strong {
  color: var(--ink);
  font-size: 13px;
  line-height: 1.35;
}

.round-title span {
  display: none;
  margin-top: 2px;
  color: var(--muted);
  font-size: 13px;
}

.round-state {
  display: inline-flex;
  grid-column: 2 / 3;
  gap: 6px;
  align-items: center;
  justify-self: start;
  min-width: 0;
  padding: 2px 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--round-accent) 11%, transparent);
  color: var(--round-accent);
  font-size: 11px;
  font-weight: 700;
}

.status-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: currentColor;
}

.round-card.is-current .status-dot {
  animation: status-pulse 2.2s ease-in-out infinite;
}

.round-time {
  display: none;
}

.room-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 292px;
  gap: 16px;
  height: 100%;
  min-height: 0;
  transition: grid-template-columns 220ms ease;
}

.multi-stage.info-collapsed .room-main {
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
}

.conversation-panel {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto auto auto;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--panel-strong);
  box-shadow: var(--shadow-md);
}

.round-messages {
  display: grid;
  align-content: start;
  gap: 20px;
  min-height: 0;
  overflow-y: auto;
  padding: 22px 24px 26px;
  scrollbar-color: color-mix(in srgb, var(--muted) 42%, transparent) transparent;
}

.conversation-messages {
  background: var(--panel-strong);
}

.message-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.message-row.user {
  display: flex;
  justify-content: flex-end;
}

.message-row img {
  width: 42px;
  height: 42px;
  border-radius: 999px;
  object-fit: cover;
  box-shadow: 0 10px 20px rgba(59, 86, 150, 0.1);
  transform-origin: 50% 85%;
  animation:
    interviewer-message-pop 420ms cubic-bezier(0.2, 0.9, 0.2, 1.15),
    interviewer-idle 5.2s ease-in-out 420ms infinite;
}

.bubble {
  width: fit-content;
  max-width: min(760px, 86%);
  padding: 16px 20px;
  border-radius: 14px;
  color: var(--ink);
  line-height: 1.75;
  box-shadow: 0 1px 0 rgba(31, 68, 120, 0.04);
}

.bubble.assistant {
  border-top-left-radius: 8px;
  background: var(--bubble-agent);
}

.bubble.user {
  border-top-right-radius: 8px;
  background: var(--bubble-user);
}

.bubble small {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}

.bubble p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.message-empty {
  display: grid;
  place-items: center;
  min-height: 27px;
  border: 1px dashed var(--line);
  border-radius: 10px;
  color: var(--muted);
  font-size: 14px;
}

.round-composer {
  position: relative;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 42px;
  gap: 10px;
  align-items: center;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-right: 0;
  border-bottom: 0;
  border-left: 0;
  border-radius: 0 0 16px 16px;
  background: color-mix(in srgb, var(--panel) 92%, transparent);
}

.round-composer textarea {
  grid-column: 2;
  grid-row: 1;
  width: 100%;
  min-height: 46px;
  max-height: 132px;
  padding: 13px 8px;
  border: 0;
  background: transparent;
  color: var(--ink);
  font: inherit;
  line-height: 1.55;
  resize: none;
  outline: none;
}

.round-composer textarea::placeholder {
  color: color-mix(in srgb, var(--muted) 82%, transparent);
}

.composer-plus,
.send-button {
  display: grid;
  place-items: center;
  width: 42px;
  min-height: 42px;
  padding: 0;
  border-radius: 12px;
  font-size: 20px;
  font-weight: 800;
  line-height: 1;
}

.composer-plus {
  grid-column: 1;
  grid-row: 1;
  background: color-mix(in srgb, var(--brand-500) 9%, var(--panel));
  color: var(--brand-500);
}

.send-button {
  grid-column: 3;
  grid-row: 1;
}

.draft-status {
  grid-column: 2;
  grid-row: 2;
  align-self: start;
  min-height: 16px;
  margin: -8px 8px 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.3;
}

.draft-status-error {
  color: var(--danger);
}

.send-button {
  border-color: transparent;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
}

.action-menu {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  z-index: 5;
  display: grid;
  gap: 4px;
  width: 176px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  box-shadow: var(--shadow-md);
}

.action-menu button {
  min-height: 36px;
  padding: 7px 10px;
  border: 0;
  background: transparent;
  text-align: left;
}

.action-menu button:not(:disabled):hover {
  background: color-mix(in srgb, var(--brand-500) 9%, transparent);
  box-shadow: none;
  transform: none;
}

.action-menu .danger-item {
  color: #df4d5f;
}

.info-panel {
  display: grid;
  align-content: start;
  gap: 14px;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--panel-strong);
  box-shadow: var(--shadow-md);
  opacity: 1;
  transition:
    opacity 180ms ease,
    transform 180ms ease;
}

.multi-stage.info-collapsed .info-panel {
  opacity: 0;
  pointer-events: none;
  transform: translateX(12px);
}

.info-head {
  display: flex;
  gap: 12px;
  align-items: start;
  justify-content: space-between;
  padding: 20px 20px 0;
}

.info-head div {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.info-head span {
  color: var(--ink);
  font-size: 16px;
  font-weight: 800;
}

.info-head strong {
  color: var(--accent);
  font-size: 16px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.info-head strong.danger,
.info-list dd.danger {
  color: var(--danger);
}

.info-head button {
  min-height: 32px;
  padding: 4px 10px;
  font-size: 12px;
  white-space: nowrap;
}

.progress-meter {
  height: 6px;
  margin: 0 20px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 16%, transparent);
}

.progress-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  transition: width 240ms ease;
}

.info-list {
  display: grid;
  gap: 0;
  margin: 0 20px 20px;
}

.info-list div {
  display: grid;
  gap: 6px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
}

.info-list dt {
  color: var(--ink);
  font-size: 13px;
  font-weight: 800;
}

.info-list dd {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.state-strip,
.failure-strip,
.current-round-bar,
.overall-bar,
.answer-quality-panel,
.summary-panel {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel);
}

.state-strip {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  color: #1f64bf;
}

.state-strip div {
  display: grid;
  gap: 2px;
}

.state-strip strong,
.state-strip span {
  overflow-wrap: anywhere;
}

.state-strip strong {
  font-size: 14px;
}

.state-strip span {
  font-size: 13px;
}

.state-strip.warning {
  border-color: color-mix(in srgb, #e6962a 42%, var(--line));
  color: #a96713;
}

.state-strip.error {
  border-color: color-mix(in srgb, #df4d5f 42%, var(--line));
  color: #c0364a;
}

.state-strip button {
  min-height: 32px;
  padding: 4px 12px;
  white-space: nowrap;
}

.failure-strip {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  margin: 0 32px 14px;
  padding: 12px 14px;
  border-color: color-mix(in srgb, #df4d5f 42%, var(--line));
  color: #c0364a;
  font-size: 13px;
}

.failure-strip button {
  min-height: 32px;
  padding: 4px 10px;
}

.answer-quality-panel {
  display: grid;
  gap: 12px;
  margin: 0 32px 14px;
  padding: 14px 16px;
  border-color: color-mix(in srgb, var(--accent) 26%, var(--line));
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 9%, transparent), transparent 58%),
    var(--panel);
}

.answer-quality-panel.answer-quality-inline {
  margin: -2px 0 2px 54px;
}

.answer-quality-panel.quality-strong {
  border-color: color-mix(in srgb, #22a06b 38%, var(--line));
}

.answer-quality-panel.quality-needs-work {
  border-color: color-mix(in srgb, #df4d5f 42%, var(--line));
}

.answer-quality-panel.quality-hint {
  border-color: color-mix(in srgb, #e6962a 38%, var(--line));
}

.answer-quality-score {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
}

.answer-quality-score span,
.answer-quality-score em {
  color: var(--muted);
  font-size: 13px;
  font-style: normal;
}

.answer-quality-score strong {
  color: var(--ink);
  font-size: 22px;
  font-variant-numeric: tabular-nums;
}

.answer-quality-panel p {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.65;
}

.answer-quality-section {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.answer-quality-section h4 {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  font-weight: 800;
}

.answer-quality-dimension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.answer-quality-dimension-grid article {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--line));
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-strong) 76%, transparent);
}

.answer-quality-dimension-grid article > div {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.answer-quality-dimension-grid strong,
.answer-quality-dimension-grid span {
  font-size: 12px;
}

.answer-quality-dimension-grid span {
  flex: 0 0 auto;
  color: var(--accent);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.answer-quality-dimension-grid article p {
  color: var(--muted);
  font-size: 12px;
  font-weight: 400;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.answer-quality-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.answer-quality-detail-grid > section {
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-strong) 68%, transparent);
}

.quality-strengths h4 {
  color: #16875a;
}

.quality-issues h4 {
  color: #c0364a;
}

.quality-strengths li::before {
  background: #22a06b;
}

.quality-issues li::before {
  background: #df4d5f;
}

.answer-quality-next-step {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 9%, var(--panel-strong));
}

.answer-quality-next-step strong,
.answer-quality-next-step span,
.answer-quality-panel summary {
  font-size: 13px;
  line-height: 1.55;
}

.answer-quality-next-step strong {
  color: var(--accent);
  white-space: nowrap;
}

.answer-quality-next-step span {
  color: var(--ink);
  overflow-wrap: anywhere;
}

.answer-quality-panel details {
  color: var(--muted);
}

.answer-quality-panel summary {
  width: fit-content;
  cursor: pointer;
  font-weight: 700;
}

.answer-quality-panel details ul {
  margin-top: 8px;
}

.answer-quality-panel .quality-empty {
  color: var(--muted);
  font-size: 13px;
  font-weight: 400;
}

.answer-quality-panel ul {
  display: grid;
  gap: 7px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.answer-quality-panel li {
  position: relative;
  padding-left: 14px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
}

.answer-quality-panel li::before {
  position: absolute;
  top: 0.72em;
  left: 0;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: var(--accent);
  content: "";
}

.answer-quality-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.answer-quality-actions span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

.answer-quality-actions span.error {
  color: #c0364a;
}

.answer-quality-actions button {
  min-height: 34px;
  padding: 6px 12px;
  border-color: color-mix(in srgb, var(--accent) 36%, var(--line));
  background: color-mix(in srgb, var(--accent) 10%, var(--panel));
  color: var(--ink);
  white-space: nowrap;
}

.answer-quality-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.68;
}

.summary-panel {
  display: grid;
  gap: 12px;
  margin: 0 32px 14px;
  padding: 16px;
}

.summary-score {
  display: flex;
  gap: 10px;
  align-items: baseline;
  flex-wrap: wrap;
}

.summary-score span,
.summary-score em {
  color: var(--muted);
  font-size: 13px;
  font-style: normal;
}

.summary-score strong {
  color: var(--ink);
  font-size: 26px;
  font-variant-numeric: tabular-nums;
}

.summary-panel p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.question-score-list {
  display: grid;
  gap: 8px;
}

.question-score-list article {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}

.question-score-list strong {
  color: var(--accent);
  font-size: 13px;
}

.question-score-list p {
  margin: 0;
}

.current-round-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin: 0 32px 14px;
  padding: 12px 14px;
  color: var(--ink);
}

.current-round-bar span {
  min-width: 0;
  color: var(--muted);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.current-round-bar div {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

.current-round-bar button {
  min-height: 34px;
  padding: 5px 12px;
  white-space: nowrap;
}

.current-round-bar .primary-action {
  border-color: transparent;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
}

.toast {
  position: fixed;
  top: 18px;
  left: 50%;
  z-index: 20;
  max-width: min(620px, calc(100% - 40px));
  margin: 0;
  padding: 10px 14px;
  border: 1px solid #b7dcc8;
  border-radius: 10px;
  background: #f0fdf4;
  color: #166534;
  transform: translateX(-50%);
}

.toast.error {
  border-color: #ffd0ca;
  background: #fff4f2;
  color: #b42318;
}

.thinking {
  animation: thinking-breathe 1.45s ease-in-out infinite;
}

.dot-trail {
  display: inline-block;
  width: 20px;
  overflow: hidden;
  vertical-align: bottom;
  animation: dot-trail 1.1s ease-in-out infinite;
}

.empty-panel {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  color: var(--ink);
  pointer-events: none;
}

.empty-panel span {
  color: var(--muted);
}

.overall-bar {
  position: fixed;
  right: 28px;
  bottom: 22px;
  z-index: 12;
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  width: min(620px, calc(100% - 56px));
  padding: 14px 16px;
  box-shadow: var(--shadow-md);
}

.overall-copy {
  display: grid;
  flex: 1 1 auto;
  gap: 8px;
  min-width: 0;
}

.overall-copy > span {
  overflow-wrap: anywhere;
}

.overall-progress {
  position: relative;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--brand-500) 18%, transparent);
}

.overall-progress span {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -36%;
  width: 36%;
  border-radius: inherit;
  background: linear-gradient(90deg, #3b9cff 0%, #7c6cff 50%, #2dd4bf 100%);
  animation: overall-progress-slide 1.2s ease-in-out infinite;
}

.overall-bar button {
  min-height: 36px;
  padding: 6px 14px;
  white-space: nowrap;
}

.overall-bar .primary {
  border-color: transparent;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
}

@keyframes overall-progress-slide {
  0% {
    transform: translateX(0);
  }

  100% {
    transform: translateX(380%);
  }
}

@keyframes status-pulse {
  0%,
  100% {
    opacity: 0.55;
    transform: scale(0.95);
  }

  50% {
    opacity: 1;
    transform: scale(1.12);
  }
}

@keyframes round-switch-pop {
  0% {
    transform: translateY(0) scale(0.995);
  }

  42% {
    transform: translateY(-3px) scale(1.006);
  }

  100% {
    transform: translateY(-1px) scale(1);
  }
}

@keyframes interviewer-idle {
  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
  }

  50% {
    transform: translateY(-3px) rotate(1deg) scale(1.025);
  }
}

@keyframes interviewer-current {
  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
    box-shadow: 0 10px 22px color-mix(in srgb, var(--accent) 18%, transparent);
  }

  50% {
    transform: translateY(-4px) rotate(-1deg) scale(1.045);
    box-shadow: 0 14px 26px color-mix(in srgb, var(--accent) 28%, transparent);
  }
}

@keyframes interviewer-message-pop {
  0% {
    opacity: 0;
    transform: translateY(8px) scale(0.86);
  }

  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes thinking-breathe {
  0%,
  100% {
    opacity: 0.52;
  }

  50% {
    opacity: 1;
  }
}

@keyframes dot-trail {
  0%,
  100% {
    opacity: 0.35;
  }

  50% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .round-board,
  .round-card,
  .round-card.is-current,
  .round-card.is-switching,
  .round-card > img,
  .message-row img,
  .info-panel,
  .status-dot,
  .thinking,
  .dot-trail {
    transition: none;
    animation: none;
  }
}

.round-config-backdrop {
  position: fixed;
  z-index: 40;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgb(15 23 42 / 58%);
  backdrop-filter: blur(4px);
}

.round-config-modal {
  width: min(680px, 100%);
  padding: 26px;
  border: 1px solid #dbe3ee;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 24px 70px rgb(15 23 42 / 24%);
}

.round-config-modal > header,
.round-config-modal > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.round-config-modal > header span {
  color: #64748b;
  font-size: 13px;
}

.round-config-modal h2 {
  margin: 4px 0 0;
}

.round-config-modal > header > button {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: #f1f5f9;
  font-size: 22px;
}

.round-config-focus,
.round-config-note {
  color: #64748b;
  line-height: 1.65;
}

.round-config-modal fieldset {
  margin: 20px 0 0;
  padding: 0;
  border: 0;
}

.round-config-modal legend {
  margin-bottom: 10px;
  font-weight: 700;
}

.round-config-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.round-config-options button {
  display: grid;
  gap: 5px;
  padding: 14px;
  border: 1px solid #dbe3ee;
  border-radius: 12px;
  background: #f8fafc;
  color: #1e293b;
  text-align: left;
}

.round-config-options button.active {
  border-color: #2563eb;
  background: #eff6ff;
  box-shadow: 0 0 0 1px #2563eb;
}

.round-config-options small {
  color: #64748b;
}

.round-config-note {
  margin: 18px 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f1f5f9;
}

.round-config-modal > footer {
  justify-content: flex-end;
}

.round-config-modal > footer button {
  min-width: 96px;
  padding: 10px 16px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
}

.round-config-modal > footer .primary {
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}

@media (max-width: 1180px) {
  .multi-stage {
    gap: 12px;
    padding: 18px;
  }

  .round-board {
    gap: 8px;
  }

  .round-card {
    grid-template-columns: 34px minmax(0, 1fr);
    min-height: 56px;
    padding: 8px;
  }

  .round-card > img {
    width: 34px;
    height: 34px;
  }

  .round-state {
    grid-column: 2 / 3;
    font-size: 11px;
  }

  .round-time {
    display: none;
  }

  .round-title strong {
    font-size: 13px;
  }

  .room-main {
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 16px;
  }

  .round-messages {
    padding-right: 24px;
    padding-left: 24px;
  }

  .round-composer,
  .summary-panel,
  .failure-strip,
  .current-round-bar {
    margin-right: 24px;
    margin-left: 24px;
  }

  .answer-quality-panel.answer-quality-inline {
    margin-right: 0;
    margin-left: 0;
  }

  .round-composer {
    margin-right: 0;
    margin-left: 0;
  }

  .info-head {
    padding-right: 22px;
    padding-left: 22px;
  }

  .progress-meter,
  .info-list {
    margin-right: 22px;
    margin-left: 22px;
  }
}

@media (max-width: 900px) {
  .answer-quality-detail-grid {
    grid-template-columns: 1fr;
  }

  .multi-stage {
    height: auto;
    max-height: none;
    min-height: 100vh;
    overflow: visible;
  }

  .room-header {
    align-items: stretch;
    flex-direction: column;
  }

  .room-title {
    flex-basis: auto;
    max-width: none;
  }

  .room-actions {
    justify-content: space-between;
  }

  .theme-toggle,
  .panel-toggle {
    flex: 1 1 0;
  }

  .round-board {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
    max-width: none;
  }

  .room-main,
  .multi-stage.info-collapsed .room-main {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .conversation-panel {
    min-height: 620px;
  }
}

@media (max-width: 640px) {
  .multi-stage {
    padding: 12px;
  }

  .round-config-modal {
    padding: 20px;
  }

  .round-config-options {
    grid-template-columns: 1fr;
  }

  .room-title h1 {
    font-size: 20px;
  }

  .round-board {
    gap: 8px;
  }

  .round-card {
    grid-template-columns: 34px minmax(0, 1fr);
    min-height: 56px;
    padding: 8px;
    border-radius: 12px;
  }

  .round-card > img {
    width: 34px;
    height: 34px;
    border-width: 2px;
  }

  .round-title strong {
    font-size: 13px;
  }

  .round-title span,
  .round-state {
    font-size: 11px;
  }

  .round-state {
    padding: 2px 8px;
  }

  .round-messages {
    gap: 18px;
    padding: 16px;
  }

  .message-row {
    grid-template-columns: 38px minmax(0, 1fr);
    gap: 10px;
  }

  .message-row img {
    width: 38px;
    height: 38px;
  }

  .bubble {
    max-width: 100%;
    padding: 14px 16px;
  }

  .round-composer {
    grid-template-columns: 42px minmax(0, 1fr) 42px;
    gap: 8px;
    margin: 0;
    padding: 8px;
  }

  .composer-plus,
  .send-button {
    width: 42px;
    min-height: 42px;
  }

  .summary-panel,
  .answer-quality-panel,
  .failure-strip,
  .current-round-bar {
    margin-right: 12px;
    margin-left: 12px;
  }

  .current-round-bar,
  .state-strip,
  .overall-bar {
    display: grid;
    grid-template-columns: 1fr;
  }

  .current-round-bar div {
    flex-wrap: wrap;
  }

  .overall-bar {
    right: 12px;
    width: calc(100% - 24px);
  }
}
</style>
