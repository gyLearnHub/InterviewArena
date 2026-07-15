<template>
  <section class="workspace interview-entry">
    <header class="page-header">
      <div>
        <p class="entry-lead">系统会实时生成本次面试预览。</p>
      </div>
      <RouterLink class="ghost-button" to="/history">历史记录</RouterLink>
    </header>

    <nav class="stepper" aria-label="新建面试步骤">
      <button
        v-for="step in steps"
        :key="step.id"
        type="button"
        :class="{ active: currentStep === step.id, done: currentStep > step.id }"
        :disabled="step.id > currentStep"
        :aria-current="currentStep === step.id ? 'step' : undefined"
        @click="currentStep = step.id"
      >
        <span>{{ currentStep > step.id ? "✓" : step.id }}</span>
        {{ step.label }}
      </button>
    </nav>

    <div class="entry-layout">
      <div class="entry-panel">
        <section
          v-show="currentStep === 1"
          class="role-section position-section"
          aria-labelledby="position-title"
        >
          <div class="section-heading">
            <p class="eyebrow">基础信息</p>
            <h2 id="position-title">选择面试方向</h2>
          </div>

          <div class="position-select">
            <button
              v-if="!isCustomInputMode"
              class="position-trigger"
              :class="{ open: isPositionMenuOpen, placeholder: !targetPosition }"
              type="button"
              aria-haspopup="listbox"
              :aria-expanded="isPositionMenuOpen"
              @click="togglePositionMenu"
              @keydown.escape="closePositionMenu"
            >
              <span class="position-field-icon" aria-hidden="true">
                <img :src="currentPositionIcon" alt="" />
              </span>
              <span class="position-trigger-label">{{ targetPosition || "请选择面试方向" }}</span>
              <span class="menu-caret" :class="{ open: isPositionMenuOpen }" aria-hidden="true"
                >⌄</span
              >
            </button>

            <div v-else class="position-input-shell" :class="{ open: isPositionMenuOpen }">
              <span class="position-field-icon" aria-hidden="true">
                <img :src="customInputIcon" alt="" />
              </span>
              <input
                id="target-position"
                ref="customPositionInput"
                v-model="customPosition"
                placeholder="请输入自定义岗位名称"
                @input="message = ''"
                @keydown.down.prevent="openPositionMenu"
                @keydown.escape="closePositionMenu"
              />
              <button
                class="position-input-toggle"
                type="button"
                aria-label="展开面试方向"
                aria-haspopup="listbox"
                :aria-expanded="isPositionMenuOpen"
                @click="togglePositionMenu"
              >
                <span class="menu-caret" :class="{ open: isPositionMenuOpen }" aria-hidden="true"
                  >⌄</span
                >
              </button>
            </div>

            <div
              v-if="isPositionMenuOpen"
              class="position-menu"
              role="listbox"
              aria-label="面试方向"
            >
              <button
                v-for="position in presetPositions"
                :key="position.name"
                class="position-option"
                :class="{ selected: isPresetSelected(position.name) }"
                type="button"
                role="option"
                :aria-selected="isPresetSelected(position.name)"
                @click="selectPreset(position.name)"
              >
                <span class="position-option-icon" aria-hidden="true">
                  <img :src="position.icon" alt="" />
                </span>
                <span>
                  <strong>{{ position.name }}</strong>
                  <small>{{ position.note }}</small>
                </span>
              </button>
              <button
                class="position-option custom-option"
                :class="{ selected: isCustomInputMode }"
                type="button"
                role="option"
                :aria-selected="isCustomInputMode"
                @click="activateCustomInput"
              >
                <span class="position-option-icon" aria-hidden="true">
                  <img :src="customInputIcon" alt="" />
                </span>
                <span>
                  <strong>自定义输入</strong>
                  <small>输入自定义岗位名称</small>
                </span>
              </button>
            </div>
          </div>
        </section>

        <section
          v-show="currentStep === 2 || currentStep === 3 || currentStep === 4"
          class="role-section multi-settings"
          aria-labelledby="multi-title"
        >
          <div class="section-heading compact">
            <p class="eyebrow">
              {{ currentStep === 2 ? "简历与岗位" : currentStep === 3 ? "面试轮次" : "面试偏好" }}
            </p>
            <h2 id="multi-title">
              {{
                currentStep === 2
                  ? "上传或复用简历"
                  : currentStep === 3
                    ? "选择轮次"
                    : "设置面试策略"
              }}
            </h2>
          </div>

          <div v-show="currentStep === 3" class="round-grid" aria-label="面试轮次">
            <label v-for="round in roundOptions" :key="round.value" class="round-option">
              <input v-model="selectedRounds" :value="round.value" type="checkbox" />
              <span>
                <strong>{{ round.label }}</strong>
                <small>{{ round.note }}</small>
              </span>
            </label>
          </div>

          <div v-show="currentStep === 4" class="strategy-panel" aria-label="面试策略">
            <div class="strategy-group">
              <span>面试目标</span>
              <div class="strategy-options">
                <button
                  v-for="option in interviewGoalOptions"
                  :key="option.value"
                  type="button"
                  class="strategy-option"
                  :class="{ active: interviewGoal === option.value }"
                  :aria-pressed="interviewGoal === option.value"
                  @click="interviewGoal = option.value"
                >
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.note }}</small>
                </button>
              </div>
            </div>
          </div>

          <label v-show="currentStep === 4" for="job-description">岗位 JD</label>
          <textarea
            v-show="currentStep === 4"
            id="job-description"
            v-model.trim="jobDescription"
            placeholder="可选：粘贴岗位 JD，系统会保存为本次面试快照。"
            rows="4"
          />

          <div v-show="currentStep === 2" class="resume-upload-row">
            <div class="resume-picker">
              <button
                class="upload-card resume-menu-trigger"
                :class="{ disabled: isResumeBusy }"
                type="button"
                :aria-expanded="isResumeMenuOpen"
                aria-haspopup="menu"
                @click="toggleResumeMenu"
              >
                <span class="upload-icon file-icon" aria-hidden="true"></span>
                <span>
                  <strong>{{ resumeName || "选择简历" }}</strong>
                  <small>{{ resumeStatusHint }}</small>
                </span>
                <span class="menu-caret" :class="{ open: isResumeMenuOpen }" aria-hidden="true"
                  >⌄</span
                >
              </button>
              <input
                ref="resumeInput"
                class="resume-file-input"
                accept=".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                :disabled="isResumeBusy"
                type="file"
                @change="handleResumeUpload"
              />
              <div v-if="isResumeMenuOpen" class="resume-menu" role="menu">
                <button type="button" role="menuitem" @click="chooseNewResume">
                  <span class="resume-option-icon upload-option-icon" aria-hidden="true"></span>
                  <span>
                    <strong>上传新简历</strong>
                    <small>从本地选择 DOC / DOCX 文件</small>
                  </span>
                </button>
                <button type="button" role="menuitem" @click="openResumeHistory">
                  <span class="resume-option-icon history-option-icon" aria-hidden="true"></span>
                  <span>
                    <strong>复用已有简历</strong>
                    <small>直接选择已上传的简历</small>
                  </span>
                </button>
              </div>
            </div>

            <div v-if="resumeId" class="resume-actions">
              <button type="button" :disabled="isResumeBusy" @click="toggleResumeMenu">
                重新选择
              </button>
              <button class="danger" type="button" :disabled="isResumeBusy" @click="removeResume">
                移除简历
              </button>
            </div>
          </div>
        </section>

        <section v-show="currentStep === 5" class="confirm-panel">
          <p class="eyebrow">确认并开始</p>
          <h2>{{ selectedPosition || "未选择岗位" }}</h2>
          <p>{{ selectionHint }}</p>
          <div class="confirm-strategy">
            <span>{{ interviewGoalLabel }}</span>
          </div>
          <div class="confirm-rounds">
            <span v-for="label in selectedRoundLabels" :key="label">{{ label }}</span>
          </div>
        </section>

        <div class="selection-bar">
          <button
            class="ghost-button"
            type="button"
            :disabled="currentStep === 1 || isResumeBusy"
            @click="previousStep"
          >
            上一步
          </button>
          <div class="selection-actions">
            <button
              class="ghost-button"
              type="button"
              :disabled="isResumeBusy"
              @click="saveDraft(true)"
            >
              保存草稿
            </button>
            <button
              class="primary"
              type="button"
              :disabled="isResumeBusy"
              @click="handlePrimaryAction"
            >
              {{ currentStep === 5 ? submitLabel : "下一步" }}
            </button>
          </div>
        </div>

        <p v-if="message" class="message error">{{ message }}</p>
      </div>

      <aside v-if="currentStep < 5" class="summary-card" aria-label="配置摘要">
        <header class="summary-heading">
          <h2>配置摘要</h2>
          <span>步骤 {{ currentStep }}/5</span>
        </header>
        <div class="summary-target">
          <span>目标岗位</span>
          <strong>{{ selectedPosition || "待选择" }}</strong>
        </div>
        <div class="summary-strategy">
          <span>{{ interviewGoalLabel }}</span>
        </div>
        <div class="summary-flow">
          <div
            v-for="round in roundOptions"
            :key="round.value"
            :class="{ muted: !selectedRounds.includes(round.value) }"
          >
            <span>{{ round.label }}</span>
            <small>{{
              selectedRounds.includes(round.value) ? "Agent 自适应追问" : "未启用"
            }}</small>
          </div>
        </div>
        <p>{{ resumeName || "还没有选择简历" }}</p>
      </aside>
    </div>

    <div v-if="isResumeHistoryOpen" class="resume-modal-backdrop" @click.self="closeResumeHistory">
      <section
        class="resume-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="resume-history-title"
      >
        <header class="resume-modal-header">
          <h3 id="resume-history-title">历史简历</h3>
          <button type="button" aria-label="关闭" @click="closeResumeHistory">×</button>
        </header>

        <p v-if="resumeHistoryMessage" class="message error">{{ resumeHistoryMessage }}</p>
        <p v-if="isLoadingResumes" class="resume-state">加载中...</p>
        <p v-else-if="resumeOptions.length === 0" class="resume-state">暂无历史简历。</p>
        <div v-else class="resume-history-list">
          <article
            v-for="resume in resumeOptions"
            :key="resume.id"
            class="resume-history-row"
            :class="{ selected: resume.id === resumeId }"
          >
            <span class="resume-history-main">
              <span class="resume-title-line">
                <strong>{{ resume.name }}</strong>
                <small v-if="resume.is_default" class="default-badge">默认</small>
              </span>
              <small>{{ formatParseStatus(resume.parse_status) }}</small>
            </span>
            <span>
              <small>上传时间</small>
              {{ formatDateTime(resume.uploaded_at) }}
            </span>
            <span>
              <small>最近使用</small>
              {{ formatDateTime(resume.last_used_at) }}
            </span>
            <div v-if="editingResumeId === resume.id" class="resume-rename-row">
              <input
                v-model.trim="editingResumeName"
                type="text"
                maxlength="128"
                @keydown.enter.prevent="saveResumeRename(resume)"
                @keydown.escape.prevent="cancelResumeRename"
              />
              <button
                type="button"
                :disabled="savingRenameId === resume.id"
                @click="saveResumeRename(resume)"
              >
                保存
              </button>
              <button
                type="button"
                :disabled="savingRenameId === resume.id"
                @click="cancelResumeRename"
              >
                取消
              </button>
            </div>
            <div v-else class="resume-row-actions">
              <button type="button" @click="selectExistingResume(resume)">
                {{ resume.id === resumeId ? "已选择" : "选择" }}
              </button>
              <button type="button" @click="openResumeDetail(resume)">查看</button>
              <button type="button" @click="startResumeRename(resume)">重命名</button>
              <button
                type="button"
                :disabled="resume.is_default || settingDefaultResumeId === resume.id"
                @click="makeResumeDefault(resume)"
              >
                设默认
              </button>
              <button
                class="danger"
                type="button"
                :disabled="deletingResumeId === resume.id"
                @click="deleteResumeOption(resume)"
              >
                删除
              </button>
            </div>
          </article>
        </div>
      </section>
    </div>

    <div v-if="isResumeDetailOpen" class="resume-modal-backdrop" @click.self="closeResumeDetail">
      <section
        class="resume-modal resume-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="resume-detail-title"
      >
        <header class="resume-modal-header">
          <div>
            <h3 id="resume-detail-title">{{ resumeDetail?.name || "简历解析结果" }}</h3>
            <p v-if="resumeDetail" class="resume-detail-meta">
              {{ formatParseStatus(resumeDetail.parse_status) }} · 上传于
              {{ formatDateTime(resumeDetail.uploaded_at) }}
            </p>
          </div>
          <button type="button" aria-label="关闭" @click="closeResumeDetail">×</button>
        </header>
        <p v-if="resumeDetailMessage" class="message error">{{ resumeDetailMessage }}</p>
        <p v-if="isLoadingResumeDetail" class="resume-state">加载中...</p>
        <div v-else-if="resumeDetail" class="resume-detail-content">
          <section
            v-for="section in resumeDetailSections"
            :key="section.title"
            class="resume-detail-section"
          >
            <h4>{{ section.title }}</h4>
            <p v-if="!section.items.length" class="resume-empty-text">暂无内容</p>
            <ul v-else>
              <li v-for="item in section.items" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import agentIcon from "../assets/position-icons/agent.png";
import backendIcon from "../assets/position-icons/backend.png";
import customInputIcon from "../assets/position-icons/custom-input.png";
import dataAnalysisIcon from "../assets/position-icons/data-analysis.png";
import selectDirectionIcon from "../assets/position-icons/select-direction.png";
import {
  ApiError,
  createInterview,
  deleteResume,
  getResumeDetail,
  listResumes,
  renameResume,
  setDefaultResume,
  uploadResume,
  type InterviewGoal,
  type ResumeDetail,
  type ResumeListItem,
  type RoundType
} from "../api";

const router = useRouter();
const DRAFT_KEY = "interview_arena_create_draft";
const currentStep = ref(1);
const steps = [
  { id: 1, label: "基础信息" },
  { id: 2, label: "简历与岗位" },
  { id: 3, label: "面试轮次" },
  { id: 4, label: "面试偏好" },
  { id: 5, label: "确认并开始" }
];
const presetPositions = [
  { name: "后端开发", note: "接口、数据库、系统设计", icon: backendIcon },
  { name: "Agent 应用开发", note: "工具调用、RAG、工程落地", icon: agentIcon },
  { name: "数据分析", note: "指标、SQL、业务判断", icon: dataAnalysisIcon }
];
const roundOptions: { value: RoundType; label: string; note: string }[] = [
  { value: "resume", label: "简历面", note: "经历真实性、项目理解" },
  { value: "technical", label: "技术面", note: "基础、原理、工程实践" },
  { value: "manager", label: "主管面", note: "业务理解、协作推动" },
  { value: "hr", label: "HR 面", note: "动机、稳定性、规划" }
];
const interviewGoalOptions: { value: InterviewGoal; label: string; note: string }[] = [
  { value: "internship", label: "实习", note: "基础和成长潜力" },
  { value: "campus", label: "校招", note: "能力覆盖与项目深度" },
  { value: "big_tech", label: "冲刺大厂", note: "深度追问和抗压表达" }
];
const targetPosition = ref("");
const customPosition = ref("");
const isCustomInputMode = ref(false);
const isPositionMenuOpen = ref(false);
const selectedRounds = ref<RoundType[]>(roundOptions.map((round) => round.value));
const interviewGoal = ref<InterviewGoal>("campus");
const jobDescription = ref("");
const resumeId = ref<number | null>(null);
const resumeName = ref("");
const message = ref("");
const customPositionInput = ref<HTMLInputElement | null>(null);
const resumeInput = ref<HTMLInputElement | null>(null);
const resumeOptions = ref<ResumeListItem[]>([]);
const resumeDetail = ref<ResumeDetail | null>(null);
const resumeHistoryMessage = ref("");
const resumeDetailMessage = ref("");
const isUploadingResume = ref(false);
const isResumeMenuOpen = ref(false);
const isResumeHistoryOpen = ref(false);
const isResumeDetailOpen = ref(false);
const isLoadingResumes = ref(false);
const isLoadingResumeDetail = ref(false);
const isCreating = ref(false);
const editingResumeId = ref<number | null>(null);
const editingResumeName = ref("");
const savingRenameId = ref<number | null>(null);
const settingDefaultResumeId = ref<number | null>(null);
const deletingResumeId = ref<number | null>(null);

const selectedPosition = computed(() => {
  return isCustomInputMode.value ? customPosition.value.trim() : targetPosition.value;
});
const currentPositionIcon = computed(() => {
  if (isCustomInputMode.value) {
    return customInputIcon;
  }
  return (
    presetPositions.find((position) => position.name === targetPosition.value)?.icon ||
    selectDirectionIcon
  );
});
const selectionHint = computed(() => {
  return `${selectedRounds.value.length} 个轮次，${interviewGoalLabel.value}${
    resumeId.value ? "，简历已就绪" : "，待上传简历"
  }`;
});
const interviewGoalLabel = computed(
  () => interviewGoalOptions.find((option) => option.value === interviewGoal.value)?.label || "校招"
);
const selectedRoundLabels = computed(() =>
  roundOptions
    .filter((round) => selectedRounds.value.includes(round.value))
    .map((round) => round.label)
);
const submitLabel = computed(() => {
  if (isUploadingResume.value) {
    return "简历解析中";
  }
  if (isCreating.value) {
    return "创建中";
  }
  return "开始面试";
});
const isResumeBusy = computed(
  () => isUploadingResume.value || isCreating.value || isLoadingResumes.value
);
const resumeDetailSections = computed(() =>
  buildResumeDetailSections(resumeDetail.value?.structured_data)
);
const resumeStatusHint = computed(() => {
  if (isUploadingResume.value) {
    return "正在上传并解析";
  }
  if (resumeId.value) {
    return "已选择，可重新上传或复用其他简历";
  }
  return "上传新简历或复用已有简历";
});

function selectPreset(position: string) {
  targetPosition.value = position;
  customPosition.value = "";
  isCustomInputMode.value = false;
  isPositionMenuOpen.value = false;
  message.value = "";
}

function isPresetSelected(position: string) {
  return !isCustomInputMode.value && targetPosition.value === position;
}

function togglePositionMenu() {
  isPositionMenuOpen.value = !isPositionMenuOpen.value;
}

function openPositionMenu() {
  isPositionMenuOpen.value = true;
}

function closePositionMenu() {
  isPositionMenuOpen.value = false;
}

async function activateCustomInput() {
  targetPosition.value = "";
  isCustomInputMode.value = true;
  isPositionMenuOpen.value = false;
  message.value = "";
  await nextTick();
  customPositionInput.value?.focus();
}

function toggleResumeMenu() {
  if (isResumeBusy.value) {
    return;
  }
  isResumeMenuOpen.value = !isResumeMenuOpen.value;
}

function chooseNewResume() {
  if (isResumeBusy.value) {
    return;
  }
  isResumeMenuOpen.value = false;
  resumeInput.value?.click();
}

async function openResumeHistory() {
  if (isResumeBusy.value) {
    return;
  }
  isResumeMenuOpen.value = false;
  isResumeHistoryOpen.value = true;
  await loadResumeOptions();
}

function closeResumeHistory() {
  if (isLoadingResumes.value) {
    return;
  }
  isResumeHistoryOpen.value = false;
}

async function loadResumeOptions() {
  isLoadingResumes.value = true;
  resumeHistoryMessage.value = "";
  try {
    resumeOptions.value = await listResumes();
  } catch (error) {
    resumeHistoryMessage.value =
      error instanceof ApiError ? error.message : "历史简历加载失败，请稍后重试。";
  } finally {
    isLoadingResumes.value = false;
  }
}

function selectExistingResume(resume: ResumeListItem) {
  resumeId.value = resume.id;
  resumeName.value = resume.name;
  message.value = "";
  resumeHistoryMessage.value = "";
  isResumeHistoryOpen.value = false;
}

async function openResumeDetail(resume: ResumeListItem) {
  resumeDetail.value = null;
  resumeDetailMessage.value = "";
  isResumeDetailOpen.value = true;
  isLoadingResumeDetail.value = true;
  try {
    resumeDetail.value = await getResumeDetail(resume.id);
  } catch (error) {
    resumeDetailMessage.value =
      error instanceof ApiError ? error.message : "简历解析结果加载失败，请稍后重试。";
  } finally {
    isLoadingResumeDetail.value = false;
  }
}

function closeResumeDetail() {
  if (isLoadingResumeDetail.value) {
    return;
  }
  isResumeDetailOpen.value = false;
  resumeDetail.value = null;
  resumeDetailMessage.value = "";
}

function startResumeRename(resume: ResumeListItem) {
  editingResumeId.value = resume.id;
  editingResumeName.value = resume.name;
  resumeHistoryMessage.value = "";
}

function cancelResumeRename() {
  editingResumeId.value = null;
  editingResumeName.value = "";
}

async function saveResumeRename(resume: ResumeListItem) {
  const nextName = editingResumeName.value.trim();
  if (!nextName) {
    resumeHistoryMessage.value = "简历名称不能为空。";
    return;
  }
  savingRenameId.value = resume.id;
  resumeHistoryMessage.value = "";
  try {
    const updated = await renameResume(resume.id, nextName);
    updateResumeOption(updated);
    if (resumeId.value === updated.id) {
      resumeName.value = updated.name;
    }
    cancelResumeRename();
  } catch (error) {
    resumeHistoryMessage.value =
      error instanceof ApiError ? error.message : "简历重命名失败，请稍后重试。";
  } finally {
    savingRenameId.value = null;
  }
}

async function makeResumeDefault(resume: ResumeListItem) {
  settingDefaultResumeId.value = resume.id;
  resumeHistoryMessage.value = "";
  try {
    const updated = await setDefaultResume(resume.id);
    resumeOptions.value = resumeOptions.value.map((item) => ({
      ...item,
      is_default: item.id === updated.id
    }));
  } catch (error) {
    resumeHistoryMessage.value =
      error instanceof ApiError ? error.message : "默认简历设置失败，请稍后重试。";
  } finally {
    settingDefaultResumeId.value = null;
  }
}

async function deleteResumeOption(resume: ResumeListItem) {
  const confirmed = window.confirm(`确认删除简历“${resume.name}”吗？历史面试记录不会被删除。`);
  if (!confirmed) {
    return;
  }
  deletingResumeId.value = resume.id;
  resumeHistoryMessage.value = "";
  try {
    await deleteResume(resume.id);
    resumeOptions.value = resumeOptions.value.filter((item) => item.id !== resume.id);
    if (resumeId.value === resume.id) {
      removeResume();
    }
  } catch (error) {
    resumeHistoryMessage.value =
      error instanceof ApiError ? error.message : "简历删除失败，请稍后重试。";
  } finally {
    deletingResumeId.value = null;
  }
}

function updateResumeOption(updated: ResumeDetail) {
  resumeOptions.value = resumeOptions.value.map((item) =>
    item.id === updated.id
      ? {
          ...item,
          name: updated.name,
          is_default: updated.is_default,
          parse_status: updated.parse_status,
          uploaded_at: updated.uploaded_at,
          last_used_at: updated.last_used_at
        }
      : item
  );
}

function removeResume() {
  resumeId.value = null;
  resumeName.value = "";
  message.value = "";
}

async function submitEntry() {
  if (!selectedPosition.value) {
    message.value = "请选择或输入目标岗位。";
    currentStep.value = 1;
    return;
  }

  await createMultiRoundInterview();
}

function handlePrimaryAction() {
  if (currentStep.value < 5) {
    nextStep();
    return;
  }
  void submitEntry();
}

function nextStep() {
  if (currentStep.value === 1 && !selectedPosition.value) {
    message.value = "请选择或输入目标岗位。";
    return;
  }
  if (currentStep.value === 2 && !resumeId.value) {
    message.value = "需要先上传或复用简历。";
    return;
  }
  if (currentStep.value === 3 && selectedRounds.value.length === 0) {
    message.value = "请至少选择一个面试轮次。";
    return;
  }
  message.value = "";
  currentStep.value = Math.min(5, currentStep.value + 1);
}

function previousStep() {
  message.value = "";
  currentStep.value = Math.max(1, currentStep.value - 1);
}

async function handleResumeUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }

  if (!isWordFile(file)) {
    message.value = "上传格式不支持，请上传 DOC 或 DOCX。";
    input.value = "";
    return;
  }

  isUploadingResume.value = true;
  isResumeMenuOpen.value = false;
  message.value = "";
  resumeName.value = file.name;
  try {
    const result = await uploadResume(file);
    resumeId.value = result.id;
  } catch (error) {
    resumeName.value = "";
    resumeId.value = null;
    message.value = error instanceof ApiError ? error.message : "简历解析失败，请重新上传。";
  } finally {
    isUploadingResume.value = false;
    input.value = "";
  }
}

async function createMultiRoundInterview() {
  if (!resumeId.value) {
    message.value = "需要先上传简历。";
    return;
  }

  if (selectedRounds.value.length === 0) {
    message.value = "请至少选择一个面试轮次。";
    return;
  }

  isCreating.value = true;
  message.value = "";
  try {
    const interview = await createInterview(resumeId.value, selectedPosition.value, {
      jobDescription: jobDescription.value,
      selectedRounds: selectedRounds.value,
      interviewGoal: interviewGoal.value
    });
    localStorage.removeItem(DRAFT_KEY);
    router.push({ name: "multi-round-interview", params: { id: interview.id } });
  } catch (error) {
    message.value = error instanceof ApiError ? error.message : "面试创建失败，请稍后重试。";
  } finally {
    isCreating.value = false;
  }
}

function isWordFile(file: File) {
  return /\.(doc|docx)$/i.test(file.name);
}

function formatParseStatus(status: string) {
  if (status === "parsed") {
    return "已解析";
  }
  if (status === "failed") {
    return "解析失败";
  }
  return "解析中";
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function buildResumeDetailSections(data: Record<string, unknown> | undefined) {
  if (!data) {
    return [];
  }
  return [
    { title: "基本信息", items: objectEntries(data.basic_info) },
    { title: "教育经历", items: listEntries(data.education) },
    { title: "工作经历", items: listEntries(data.work_experience) },
    { title: "项目经历", items: listEntries(data.project_experience) },
    { title: "技能", items: listEntries(data.skills) },
    { title: "证书与奖项", items: listEntries(data.certificates_awards) }
  ];
}

function objectEntries(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => item !== null && item !== undefined && String(item).trim() !== "")
    .map(([key, item]) => `${key}：${formatResumeValue(item)}`);
}

function listEntries(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(formatResumeValue).filter(Boolean);
}

function formatResumeValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(formatResumeValue).filter(Boolean).join("、");
  }
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== null && item !== undefined && String(item).trim() !== "")
      .map(([key, item]) => `${key}：${formatResumeValue(item)}`)
      .join("；");
  }
  return String(value ?? "").trim();
}

function saveDraft(showMessage = false) {
  localStorage.setItem(
    DRAFT_KEY,
    JSON.stringify({
      targetPosition: targetPosition.value,
      customPosition: customPosition.value,
      isCustomInputMode: isCustomInputMode.value,
      selectedRounds: selectedRounds.value,
      interviewGoal: interviewGoal.value,
      jobDescription: jobDescription.value,
      resumeId: resumeId.value,
      resumeName: resumeName.value
    })
  );
  if (showMessage) {
    message.value = "草稿已保存。";
  }
}

function loadDraft() {
  const raw = localStorage.getItem(DRAFT_KEY);
  if (!raw) {
    return;
  }
  try {
    const draft = JSON.parse(raw) as {
      targetPosition?: string;
      customPosition?: string;
      isCustomInputMode?: boolean;
      selectedRounds?: RoundType[];
      interviewGoal?: InterviewGoal;
      jobDescription?: string;
      resumeId?: number | null;
      resumeName?: string;
    };
    targetPosition.value = draft.targetPosition || "";
    customPosition.value = draft.customPosition || "";
    isCustomInputMode.value = Boolean(draft.isCustomInputMode);
    selectedRounds.value =
      Array.isArray(draft.selectedRounds) && draft.selectedRounds.length
        ? draft.selectedRounds
        : selectedRounds.value;
    if (isInterviewGoal(draft.interviewGoal)) {
      interviewGoal.value = draft.interviewGoal;
    }
    jobDescription.value = draft.jobDescription || "";
    resumeId.value = typeof draft.resumeId === "number" ? draft.resumeId : null;
    resumeName.value = draft.resumeName || "";
  } catch {
    localStorage.removeItem(DRAFT_KEY);
  }
}

function isInterviewGoal(value: unknown): value is InterviewGoal {
  return interviewGoalOptions.some((option) => option.value === value);
}

onMounted(loadDraft);

watch(
  [
    targetPosition,
    customPosition,
    isCustomInputMode,
    selectedRounds,
    interviewGoal,
    jobDescription,
    resumeId,
    resumeName
  ],
  () => saveDraft(false),
  { deep: true }
);
</script>

<style scoped>
.interview-entry {
  width: 100%;
  max-width: none;
}

.entry-lead {
  margin: 0;
  color: #5d6673;
}

.stepper {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  align-items: center;
  margin-bottom: 18px;
}

.stepper button {
  position: relative;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  min-height: 36px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #758195;
  font-size: 14px;
  font-weight: 800;
  text-align: left;
}

.stepper button + button::before {
  position: absolute;
  right: calc(100% + 10px);
  width: min(62px, 5vw);
  height: 2px;
  background: #dfe5ec;
  content: "";
}

.stepper span {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: #d0d8e2;
  color: #fff;
}

.stepper .active,
.stepper .done {
  color: #172033;
}

.stepper .active span {
  background: #3b9cff;
  box-shadow: 0 6px 16px rgba(59, 156, 255, 0.2);
}

.stepper .done span {
  background: #e8f7f1;
  color: #16805f;
}

.stepper button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.entry-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 0.42fr);
  gap: 20px;
  align-items: start;
}

.entry-panel {
  display: grid;
  gap: 18px;
  min-height: 520px;
  padding: 28px 30px;
  border: 1px solid #e4edf7;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 14px 36px rgba(31, 68, 120, 0.07);
}

.round-option small,
.upload-card small {
  color: #5d6673;
  font-size: 14px;
  line-height: 1.45;
}

.role-section {
  display: grid;
  gap: 14px;
}

.section-heading h2 {
  margin: 2px 0 0;
  font-size: 20px;
  line-height: 1.3;
}

.section-heading.compact h2 {
  font-size: 17px;
  font-weight: 650;
}

.position-section {
  position: relative;
  z-index: 5;
}

.position-select {
  position: relative;
  width: 100%;
}

.position-trigger,
.position-input-shell {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 34px;
  gap: 12px;
  align-items: center;
  width: 100%;
  min-height: 58px;
  padding: 8px 12px;
  border: 1px solid #cfd8df;
  border-radius: 10px;
  background: #fff;
  color: #17212f;
  box-shadow: 0 8px 20px rgba(23, 33, 47, 0.06);
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease;
}

.position-trigger {
  text-align: left;
}

.position-trigger.placeholder {
  color: #7d8793;
}

.position-trigger:hover,
.position-trigger:focus-visible,
.position-trigger.open,
.position-input-shell:focus-within,
.position-input-shell.open {
  border-color: #8b99a8;
  outline: none;
  box-shadow: 0 10px 24px rgba(23, 33, 47, 0.1);
}

.position-field-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid #d9e0e4;
  border-radius: 8px;
  background: #f8fafc;
  color: #4f5966;
  font-size: 15px;
  font-weight: 700;
}

.position-field-icon img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.position-trigger-label {
  overflow: hidden;
  font-size: 16px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.position-input-shell #target-position {
  width: 100%;
  min-height: 40px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #17212f;
  font: inherit;
  font-size: 16px;
  outline: none;
}

.position-input-shell #target-position::placeholder {
  color: #8a94a1;
}

.position-input-toggle {
  display: grid;
  place-items: center;
  width: 34px;
  min-height: 34px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
}

.position-input-toggle:hover,
.position-input-toggle:focus-visible {
  background: #f2f4f7;
  outline: none;
}

.position-menu {
  position: absolute;
  z-index: 20;
  top: calc(100% + 8px);
  left: 0;
  display: grid;
  width: 100%;
  overflow: hidden;
  border: 1px solid #d9e0e4;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 16px 34px rgba(23, 33, 47, 0.14);
}

.position-option {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  min-height: 76px;
  padding: 12px 14px;
  border: 0;
  border-radius: 0;
  background: #fff;
  text-align: left;
}

.position-option + .position-option {
  border-top: 1px solid #edf0f2;
}

.position-option:hover,
.position-option:focus-visible,
.position-option.selected {
  background: #f7f8fa;
  outline: none;
}

.position-option > span:last-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.position-option strong {
  overflow: hidden;
  color: #17212f;
  font-size: 16px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.position-option small {
  overflow: hidden;
  color: #687384;
  font-size: 14px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.position-option-icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid #dfe5ea;
  border-radius: 9px;
  background: #f8fafc;
  color: #4f5966;
  font-size: 13px;
  font-weight: 800;
}

.position-option-icon img {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.custom-option {
  border-top-color: #d9e0e4;
}

.multi-settings {
  padding: 18px;
  border: 0;
  border-radius: 14px;
  background: #f7f9fc;
}

.round-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.round-option {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 10px;
  min-height: 86px;
  padding: 12px;
  margin: 0;
  border: 1px solid #d9e0e4;
  border-radius: 8px;
  background: #f8fafc;
  cursor: pointer;
}

.round-option input {
  width: 18px;
  min-height: 18px;
  margin-top: 2px;
}

.round-option span,
.upload-card > span:nth-of-type(2) {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.round-option strong,
.upload-card strong {
  color: #17212f;
}

.strategy-panel {
  display: grid;
  gap: 14px;
}

.strategy-group {
  display: grid;
  gap: 8px;
}

.strategy-group > span {
  color: #17212f;
  font-size: 14px;
  font-weight: 800;
}

.strategy-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.strategy-option {
  display: grid;
  gap: 4px;
  min-height: 76px;
  padding: 12px;
  border: 1px solid #d9e0e4;
  border-radius: 8px;
  background: #fff;
  color: #17212f;
  text-align: left;
}

.strategy-option:hover,
.strategy-option:focus-visible,
.strategy-option.active {
  border-color: #3b9cff;
  outline: none;
  box-shadow: 0 10px 24px rgba(59, 156, 255, 0.14);
}

.strategy-option.active {
  background: #f2f8ff;
}

.strategy-option small {
  color: #5d6673;
  line-height: 1.35;
}

#job-description {
  width: 100%;
  min-height: 112px;
}

.resume-upload-row {
  display: grid;
  gap: 10px;
}

.resume-picker {
  position: relative;
  min-width: 0;
}

.upload-card {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 28px;
  gap: 16px;
  align-items: center;
  width: 100%;
  min-height: 88px;
  padding: 16px 20px;
  margin: 0;
  border: 1px solid #d3dce4;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(20, 32, 46, 0.06);
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease,
    transform 160ms ease;
}

.upload-card:hover,
.upload-card:focus-visible {
  border-color: #aebcc8;
  outline: none;
  box-shadow: 0 12px 30px rgba(20, 32, 46, 0.1);
  transform: translateY(-1px);
}

.upload-card.disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.resume-file-input {
  display: none;
}

.resume-menu-trigger {
  text-align: left;
}

.menu-caret {
  color: #5d6673;
  font-size: 24px;
  line-height: 1;
  text-align: center;
  transition: transform 160ms ease;
}

.menu-caret.open {
  transform: rotate(180deg);
}

.resume-menu {
  position: static;
  z-index: 10;
  display: grid;
  width: 100%;
  margin-top: 10px;
  padding: 8px;
  border: 1px solid #e4ebf0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 28px rgba(23, 33, 47, 0.1);
}

.resume-menu button {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  justify-content: flex-start;
  min-height: 64px;
  padding: 10px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  text-align: left;
}

.resume-menu button + button {
  border-top: 1px solid #e5ebf0;
  border-radius: 0 0 8px 8px;
}

.resume-menu button:first-child {
  border-radius: 8px 8px 0 0;
}

.resume-menu button:hover,
.resume-menu button:focus-visible {
  background: #f6fbfb;
  outline: none;
}

.resume-menu button span:last-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.resume-menu button strong {
  color: #17212f;
  font-size: 15px;
}

.resume-menu button small {
  color: #6a7482;
  font-size: 13px;
}

.resume-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.upload-icon {
  position: relative;
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  border-radius: 14px;
  background: #eef8f7;
  color: #168982;
}

.file-icon::before {
  width: 24px;
  height: 30px;
  border: 3px solid currentColor;
  border-radius: 4px;
  content: "";
}

.file-icon::after {
  position: absolute;
  top: 21px;
  left: 24px;
  width: 13px;
  height: 3px;
  background: currentColor;
  box-shadow: 0 8px 0 currentColor;
  content: "";
}

.resume-option-icon {
  position: relative;
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: #eef8f7;
  color: #168982;
}

.resume-option-icon::before,
.resume-option-icon::after {
  transform: scale(0.76);
}

.upload-option-icon::before {
  width: 28px;
  height: 18px;
  border: 3px solid currentColor;
  border-top: 0;
  border-radius: 0 0 12px 12px;
  content: "";
}

.upload-option-icon::after {
  position: absolute;
  width: 15px;
  height: 15px;
  border-top: 3px solid currentColor;
  border-left: 3px solid currentColor;
  content: "";
  transform: translateY(-6px) scale(0.76) rotate(45deg);
}

.history-option-icon {
  background: #eef6ff;
  color: #2682d9;
}

.history-option-icon::before {
  width: 24px;
  height: 30px;
  border: 3px solid currentColor;
  border-radius: 4px;
  content: "";
}

.history-option-icon::after {
  position: absolute;
  right: 7px;
  bottom: 6px;
  width: 16px;
  height: 16px;
  border: 3px solid currentColor;
  border-radius: 50%;
  background: #eef6ff;
  content: "";
  transform: scale(0.76);
}

.selection-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border: 1px solid #e4edf7;
  border-radius: 12px;
  background: #f8fafc;
}

.selection-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-left: auto;
}

.confirm-panel {
  display: grid;
  gap: 14px;
  min-height: 240px;
  padding: 24px;
  border: 1px solid #c8e3ff;
  border-radius: 16px;
  background: linear-gradient(135deg, #f2f8ff 0%, #f7f5ff 100%);
}

.confirm-panel h2 {
  margin: 0;
  color: #172033;
  font-size: 28px;
}

.confirm-panel p {
  margin: 0;
  color: #758195;
}

.confirm-rounds {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.confirm-strategy,
.summary-strategy {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.confirm-strategy span,
.summary-strategy span {
  padding: 7px 10px;
  border: 1px solid #dbe7f3;
  border-radius: 8px;
  background: #fff;
  color: #247de8;
  font-size: 13px;
  font-weight: 800;
}

.confirm-rounds span {
  padding: 8px 12px;
  border-radius: 999px;
  background: #fff;
  color: #247de8;
  font-weight: 800;
}

.summary-card {
  position: sticky;
  top: 24px;
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid #e4edf7;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 14px 36px rgba(31, 68, 120, 0.07);
}

.summary-heading {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.summary-card h2 {
  margin: 0;
  color: #172033;
  font-size: 21px;
}

.summary-heading > span {
  padding: 5px 9px;
  border-radius: 999px;
  background: #eef4fb;
  color: #5d6673;
  font-size: 12px;
  font-weight: 800;
}

.summary-target {
  display: grid;
  gap: 6px;
  padding: 16px;
  border-radius: 12px;
  background: #f2f8ff;
}

.summary-target span,
.summary-card p,
.summary-flow small {
  color: #758195;
}

.summary-target strong {
  color: #172033;
  font-size: 17px;
}

.summary-strategy span {
  background: #f8fafc;
}

.summary-flow {
  display: grid;
  gap: 14px;
}

.summary-flow div {
  position: relative;
  display: grid;
  gap: 4px;
  padding-left: 42px;
}

.summary-flow div::before {
  position: absolute;
  left: 4px;
  top: 2px;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #3b9cff;
  color: #fff;
  font-weight: 900;
  content: "";
}

.summary-flow div:nth-child(2)::before {
  background: #7567f8;
}

.summary-flow div:nth-child(3)::before {
  background: #f59b45;
}

.summary-flow div:nth-child(4)::before {
  background: #f06f9b;
}

.summary-flow .muted {
  opacity: 0.45;
}

.summary-card > p {
  margin: 0;
}

.resume-modal-backdrop {
  position: fixed;
  z-index: 40;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(23, 33, 47, 0.34);
}

.resume-modal {
  display: grid;
  gap: 12px;
  width: min(820px, 100%);
  max-height: min(680px, calc(100vh - 40px));
  padding: 18px;
  overflow: auto;
  border: 1px solid #d9e0e4;
  border-radius: 8px;
  background: #fffefb;
  box-shadow: 0 22px 46px rgba(23, 33, 47, 0.2);
}

.resume-modal-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.resume-modal-header h3 {
  margin: 0;
  font-size: 18px;
}

.resume-modal-header button {
  width: 40px;
  padding: 0;
}

.resume-state {
  margin: 0;
  color: #5d6673;
}

.resume-history-list {
  display: grid;
  gap: 10px;
}

.resume-history-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(140px, 0.55fr) minmax(140px, 0.55fr);
  gap: 12px;
  align-items: center;
  min-height: 72px;
  padding: 12px;
  border: 1px solid #d9e0e4;
  border-radius: 10px;
  background: #fff;
  text-align: left;
}

.resume-history-row.selected {
  border-color: #3b9cff;
  background: #f2f8ff;
}

.resume-history-row:hover {
  border-color: #2f6f73;
  outline: none;
}

.resume-history-row span,
.resume-history-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.resume-history-row strong {
  overflow: hidden;
  color: #17212f;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-history-row small {
  color: #5d6673;
  font-size: 13px;
}

.resume-title-line,
.resume-row-actions,
.resume-rename-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.default-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: #e8f7f1;
  color: #16805f !important;
  font-size: 12px !important;
  font-weight: 900;
}

.resume-row-actions {
  grid-column: 1 / -1;
}

.resume-row-actions button,
.resume-rename-row button {
  min-height: 34px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 13px;
}

.resume-rename-row {
  grid-column: 1 / -1;
}

.resume-rename-row input {
  flex: 1 1 240px;
  width: auto;
  min-height: 38px;
}

.resume-detail-modal {
  width: min(920px, 100%);
}

.resume-detail-meta {
  margin: 4px 0 0;
  color: #758195;
  font-size: 13px;
}

.resume-detail-content {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.resume-detail-section {
  min-width: 0;
  padding: 14px;
  border: 1px solid #e4ebf0;
  border-radius: 10px;
  background: #f8fafc;
}

.resume-detail-section h4 {
  margin: 0 0 8px;
  color: #17212f;
}

.resume-detail-section ul {
  display: grid;
  gap: 6px;
  padding-left: 18px;
  margin: 0;
}

.resume-detail-section li,
.resume-empty-text {
  color: #3b4658;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.resume-empty-text {
  margin: 0;
}

@media (max-width: 760px) {
  .entry-layout {
    grid-template-columns: 1fr;
  }

  .stepper {
    grid-template-columns: repeat(5, minmax(118px, 1fr));
    overflow-x: auto;
    padding-bottom: 6px;
  }

  .stepper button + button::before {
    display: none;
  }

  .round-grid {
    grid-template-columns: 1fr;
  }

  .strategy-options {
    grid-template-columns: 1fr;
  }

  .resume-history-row {
    grid-template-columns: 1fr;
  }

  .resume-detail-content {
    grid-template-columns: 1fr;
  }

  .selection-bar {
    display: grid;
    grid-template-columns: 1fr;
  }

  .selection-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
    margin-left: 0;
  }

  .selection-actions button {
    width: 100%;
  }

  .entry-panel {
    padding: 22px 18px;
  }

  .summary-card {
    position: static;
  }
}
</style>
