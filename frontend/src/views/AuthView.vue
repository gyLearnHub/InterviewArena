<template>
  <section class="auth-page">
    <div class="auth-glow auth-glow-left" aria-hidden="true"></div>
    <div class="auth-glow auth-glow-right" aria-hidden="true"></div>

    <div class="auth-brand">
      <RouterLink class="brand-pill" to="/login" aria-label="InterviewArena 登录页">
        <span class="brand-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M6.8 15.4 4 18V7.8C4 5.7 5.7 4 7.8 4h8.4C18.3 4 20 5.7 20 7.8v4.4c0 2.1-1.7 3.8-3.8 3.8H9.4l-2.6 2.4v-3z" />
            <circle cx="9" cy="10" r="1" />
            <circle cx="12" cy="10" r="1" />
            <circle cx="15" cy="10" r="1" />
          </svg>
        </span>
        <span>InterviewArena</span>
      </RouterLink>
      <div class="brand-copy">
        <h1>每一次练习，<br />都让理想 <em>offer</em> 更近一步</h1>
        <p>AI 模拟面试 · 智能评分 · 成长分析</p>
      </div>

      <div class="agent-row" aria-label="四轮面试官">
        <div
          v-for="agent in agents"
          :key="agent.name"
          class="agent-chip"
          :style="{ '--agent': agent.color, '--delay': agent.delay }"
        >
          <span class="agent-face" aria-hidden="true">
            <img :src="agent.avatar" :alt="`${agent.name}面试官头像`" />
          </span>
          <strong>{{ agent.name }}</strong>
        </div>
      </div>

      <div class="feature-grid" aria-label="核心能力">
        <article v-for="feature in features" :key="feature.title" class="feature-card">
          <div class="feature-top">
            <span>{{ feature.index }}</span>
            <i :class="feature.icon" aria-hidden="true"></i>
          </div>
          <div>
            <strong>{{ feature.title }}</strong>
            <p>{{ feature.text }}</p>
          </div>
        </article>
      </div>

      <div class="hero-figure" aria-hidden="true">
        <div class="floating-card rating-card">
          <strong>4.8/5.0</strong>
          <span>★★★★★</span>
        </div>
        <div class="floating-card chat-card">
          <span></span>
          <span></span>
        </div>
        <img class="hero-girl" :src="heroGirl" alt="" />
      </div>
    </div>

    <main class="auth-card" aria-label="账号表单">
      <form class="auth-form" novalidate @submit.prevent="submit">
        <div class="form-heading">
          <p>{{ mode === "login" ? "欢迎回来 👋" : "开始训练" }}</p>
          <h2>{{ mode === "login" ? "登录继续你的面试训练" : "创建你的训练账号" }}</h2>
          <span>{{ mode === "login" ? "在 InterviewArena，成就更好的自己" : "注册后即可进入面试工作台" }}</span>
        </div>

        <label class="field-group" for="username">
          <span>账号</span>
          <div class="field-shell">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20 21a8 8 0 0 0-16 0" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            <input
              id="username"
              v-model.trim="username"
              autocomplete="username"
              name="username"
              placeholder="请输入账号"
              :aria-invalid="Boolean(fieldErrors.username)"
              @input="clearFieldError('username')"
            />
          </div>
          <small v-if="fieldErrors.username">{{ fieldErrors.username }}</small>
        </label>

        <label class="field-group" for="password">
          <span>密码</span>
          <div class="field-shell password-input">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="5" y="11" width="14" height="10" rx="2" />
              <path d="M8 11V8a4 4 0 0 1 8 0v3" />
            </svg>
            <input
              id="password"
              v-model="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              name="password"
              placeholder="请输入密码"
              :type="showPassword ? 'text' : 'password'"
              :aria-invalid="Boolean(fieldErrors.password)"
              @input="clearFieldError('password')"
              @keyup="detectCapsLock"
            />
            <button
              class="password-toggle"
              type="button"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <svg v-if="showPassword" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 3l18 18" />
                <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                <path d="M9.9 4.2A10.5 10.5 0 0 1 12 4c5 0 8.5 4.4 10 8a15.7 15.7 0 0 1-3.1 4.7" />
                <path d="M6.6 6.6A15.8 15.8 0 0 0 2 12c1.5 3.6 5 8 10 8 1.4 0 2.7-.3 3.9-.9" />
              </svg>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>
          <small v-if="fieldErrors.password">{{ fieldErrors.password }}</small>
          <small v-else-if="capsLockOn" class="warning">Caps Lock 已开启</small>
        </label>

        <div class="form-options">
          <label class="remember-option">
            <input v-model="rememberMe" type="checkbox" />
            <span>记住登录状态</span>
          </label>
          <button class="link-button" type="button">忘记密码？</button>
        </div>

        <p v-if="message" class="message" :class="{ error: hasError }">{{ message }}</p>

        <button class="submit-button" type="submit" :disabled="loading">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          {{ submitLabel }}
        </button>

        <p class="mode-switch">
          {{ mode === "login" ? "还没有账号？" : "已有账号？" }}
          <button type="button" @click="switchMode">
            {{ mode === "login" ? "立即注册" : "立即登录" }}
          </button>
        </p>
      </form>
    </main>

    <Transition name="welcome">
      <div v-if="showWelcome" class="welcome-pop" role="status" aria-live="polite">
        <span class="welcome-agent" aria-hidden="true">
          <img :src="technicalAvatar" alt="" />
        </span>
        <strong>{{ welcomeAgent }} 已就位</strong>
        <p>欢迎回来，训练继续。</p>
      </div>
    </Transition>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { ApiError, login, register } from "../api";
import heroGirl from "../assets/auth-hero-girl.png";
import hrAvatar from "../assets/interviewers/hr-interviewer.png";
import managerAvatar from "../assets/interviewers/manager-interviewer.png";
import resumeAvatar from "../assets/interviewers/resume-interviewer.png";
import technicalAvatar from "../assets/interviewers/technical-interviewer.png";

const router = useRouter();
const route = useRoute();
const mode = ref<"login" | "register">("login");
const username = ref("");
const password = ref("");
const rememberMe = ref(false);
const showPassword = ref(false);
const loading = ref(false);
const message = ref("");
const hasError = ref(false);
const capsLockOn = ref(false);
const showWelcome = ref(false);
const welcomeAgent = ref("技术面试官");
const fieldErrors = ref({
  username: "",
  password: ""
});

const agents = [
  { name: "简历面", color: "#3b9cff", avatar: resumeAvatar, delay: "0s" },
  { name: "技术面", color: "#7567f8", avatar: technicalAvatar, delay: "0.16s" },
  { name: "主管面", color: "#f59b45", avatar: managerAvatar, delay: "0.32s" },
  { name: "HR 面", color: "#f06f9b", avatar: hrAvatar, delay: "0.48s" }
];
const features = [
  { index: "1", title: "四轮完整面试", text: "从简历到 HR 的完整流程", icon: "feature-doc" },
  { index: "2", title: "可信评分反馈", text: "单题、轮次、最终三级评估", icon: "feature-chart" },
  { index: "3", title: "持续成长记忆", text: "记录每一次训练的进步", icon: "feature-rise" }
];

const submitLabel = computed(() => {
  if (loading.value) {
    return mode.value === "login" ? "登录中..." : "注册中...";
  }

  return mode.value === "login" ? "登录" : "注册并进入";
});

async function submit() {
  message.value = "";
  hasError.value = false;
  fieldErrors.value = { username: "", password: "" };

  if (!validateForm()) {
    return;
  }

  loading.value = true;
  try {
    if (mode.value === "register") {
      await register(username.value, password.value);
    }

    await login(username.value, password.value);
    await playWelcomeOnce();
    router.push(getRedirectTarget());
  } catch (error) {
    hasError.value = true;
    message.value = error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
    password.value = "";
  } finally {
    loading.value = false;
  }
}

function validateForm(): boolean {
  const nextErrors = {
    username: "",
    password: ""
  };
  if (!username.value) {
    nextErrors.username = "请输入账号。";
  }
  if (!password.value) {
    nextErrors.password = "请输入密码。";
  } else if (mode.value === "register" && password.value.length < 6) {
    nextErrors.password = "密码至少需要 6 位。";
  }
  fieldErrors.value = nextErrors;
  hasError.value = Boolean(nextErrors.username || nextErrors.password);
  message.value = hasError.value ? "请先修正表单中的问题。" : "";
  return !hasError.value;
}

function clearFieldError(field: "username" | "password") {
  fieldErrors.value[field] = "";
  if (!fieldErrors.value.username && !fieldErrors.value.password && hasError.value) {
    message.value = "";
    hasError.value = false;
  }
}

function detectCapsLock(event: KeyboardEvent) {
  capsLockOn.value = event.getModifierState?.("CapsLock") ?? false;
}

function switchMode() {
  mode.value = mode.value === "login" ? "register" : "login";
  message.value = "";
  hasError.value = false;
  fieldErrors.value = { username: "", password: "" };
  password.value = "";
}

async function playWelcomeOnce() {
  if (sessionStorage.getItem("interview_arena_welcome_seen")) {
    return;
  }
  sessionStorage.setItem("interview_arena_welcome_seen", "1");
  welcomeAgent.value = ["简历面试官", "技术面试官", "主管面试官", "HR 面试官"][
    Math.floor(Math.random() * 4)
  ];
  showWelcome.value = true;
  await new Promise((resolve) => window.setTimeout(resolve, 1800));
  showWelcome.value = false;
  await new Promise((resolve) => window.setTimeout(resolve, 260));
}

function getRedirectTarget(): string {
  const redirect = route.query.redirect;
  if (typeof redirect === "string" && redirect.startsWith("/") && !redirect.startsWith("//")) {
    return redirect;
  }

  return "/dashboard";
}
</script>

<style scoped>
.auth-page {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(380px, 508px);
  gap: clamp(36px, 7vw, 92px);
  align-items: center;
  width: 100%;
  min-width: 320px;
  min-height: 100vh;
  padding: 48px clamp(24px, 5vw, 72px);
  overflow: auto;
  background:
    radial-gradient(circle at 20% 88%, rgba(124, 108, 255, 0.12), transparent 28%),
    linear-gradient(100deg, #edf7ff 0%, #f7f5ff 58%, #eaf6ff 100%);
  color: #172033;
}

.auth-brand {
  display: grid;
  gap: 44px;
  min-width: 0;
}

.brand-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 56px;
  padding: 0 28px;
  border-radius: 14px;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
  font-size: 27px;
  font-weight: 900;
  box-shadow: 0 18px 36px rgba(59, 156, 255, 0.2);
}

.brand-copy h1 {
  max-width: 780px;
  margin: 0;
  color: #172033;
  font-size: clamp(44px, 5vw, 64px);
  line-height: 1.32;
  letter-spacing: 0;
}

.brand-copy p {
  margin: 20px 0 0;
  color: #758195;
  font-size: 22px;
  font-weight: 700;
}

.agent-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(88px, 1fr));
  gap: 22px;
  max-width: 700px;
}

.agent-chip {
  display: grid;
  justify-items: center;
  gap: 10px;
  color: #25324a;
  font-weight: 900;
}

.agent-face,
.welcome-agent {
  position: relative;
  display: block;
  width: 70px;
  height: 70px;
  border: 4px solid var(--agent, #3b9cff);
  border-radius: 999px;
  background:
    radial-gradient(circle at 38% 54%, #172033 0 2px, transparent 3px),
    radial-gradient(circle at 62% 54%, #172033 0 2px, transparent 3px),
    linear-gradient(#172033 0 34%, transparent 35%),
    #ffd6c7;
  box-shadow: inset 0 -12px 0 var(--agent, #3b9cff);
}

.agent-face::after,
.welcome-agent::after {
  position: absolute;
  right: -7px;
  bottom: 5px;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: var(--agent, #3b9cff);
  color: #fff;
  font-size: 11px;
  font-weight: 900;
  line-height: 22px;
  text-align: center;
  content: "我";
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 30px;
  max-width: 780px;
}

.feature-card {
  display: grid;
  gap: 18px;
  min-height: 178px;
  padding: 26px 24px;
  border: 1px solid rgba(200, 227, 255, 0.8);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 18px 46px rgba(31, 68, 120, 0.08);
}

.feature-card span {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: #e4f1ff;
  color: #247de8;
  font-weight: 900;
}

.feature-card strong {
  color: #172033;
  font-size: 22px;
}

.feature-card p {
  margin: 0;
  color: #758195;
  line-height: 1.6;
}

.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 508px;
  min-width: 0;
  padding: 58px 60px;
  border: 1px solid rgba(200, 227, 255, 0.88);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 30px 80px rgba(31, 68, 120, 0.14);
}

.auth-form {
  display: grid;
  gap: 22px;
}

.form-heading {
  margin-bottom: 12px;
}

.form-heading p {
  margin: 0 0 10px;
  color: #758195;
  font-size: 15px;
}

.form-heading h2 {
  margin: 0;
  color: #172033;
  font-size: 38px;
  line-height: 1.18;
}

.form-heading span {
  display: block;
  margin-top: 4px;
  color: #758195;
  font-size: 17px;
}

.field-group {
  display: grid;
  gap: 9px;
  margin: 0;
}

.field-group > span {
  color: #3b4658;
  font-size: 15px;
  font-weight: 700;
}

.field-group input {
  width: 100%;
  min-height: 54px;
  padding: 0 16px;
  border: 1px solid #c8e3ff;
  border-radius: 12px;
  outline: 0;
  background: #fbfdff;
  color: #172033;
  font: 500 15px/1.2 Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease,
    background 160ms ease;
}

.field-group input::placeholder {
  color: #9aa8ba;
}

.field-group input:focus {
  border-color: #3b9cff;
  background: #fff;
  box-shadow: 0 0 0 4px rgba(59, 156, 255, 0.12);
}

.field-group input[aria-invalid="true"] {
  border-color: #df4d5f;
}

.field-group small {
  color: #df4d5f;
  font-size: 13px;
}

.field-group small.warning {
  color: #e6962a;
}

.password-input {
  position: relative;
}

.password-input input {
  padding-right: 70px;
}

.password-toggle {
  position: absolute;
  top: 50%;
  right: 10px;
  min-height: 34px;
  padding: 0 12px;
  border: 0;
  border-radius: 9px;
  background: #e4f1ff;
  color: #247de8;
  font-size: 13px;
  font-weight: 800;
  transform: translateY(-50%);
}

.remember-option {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  color: #526174;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.remember-option input {
  width: 18px;
  height: 18px;
  margin: 0;
  accent-color: #3b9cff;
  cursor: pointer;
}

.form-options {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.link-button,
.mode-switch button {
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: #247de8;
  font-size: 14px;
  font-weight: 700;
}

.message {
  margin: 0;
  color: #22a06b;
  font-size: 13px;
}

.message.error {
  color: #df4d5f;
}

.submit-button {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 56px;
  border: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%);
  color: #fff;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 18px 34px rgba(59, 156, 255, 0.24);
}

.submit-button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 22px 38px rgba(59, 156, 255, 0.28);
}

.submit-button:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.5);
  border-top-color: #fff;
  border-radius: 999px;
  animation: spin 700ms linear infinite;
}

.mode-switch {
  margin: 0;
  color: #64748b;
  font-size: 14px;
  text-align: center;
}

.welcome-pop {
  position: fixed;
  z-index: 20;
  top: 50%;
  left: 50%;
  display: grid;
  justify-items: center;
  gap: 8px;
  width: min(280px, calc(100vw - 40px));
  padding: 24px;
  border: 1px solid #c8e3ff;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(31, 68, 120, 0.2);
  transform: translate(-50%, -50%);
}

.welcome-agent {
  --agent: #7567f8;
  animation: wave 900ms ease-in-out infinite alternate;
}

.welcome-pop strong {
  color: #172033;
  font-size: 18px;
}

.welcome-pop p {
  margin: 0;
  color: #758195;
}

.welcome-enter-active,
.welcome-leave-active {
  transition:
    opacity 260ms ease,
    transform 260ms ease;
}

.welcome-enter-from,
.welcome-leave-to {
  opacity: 0;
  transform: translate(-50%, -44%) scale(0.96);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes wave {
  to {
    transform: translateY(-5px);
  }
}

@media (max-width: 1180px) {
  .auth-page {
    grid-template-columns: 1fr;
    gap: 36px;
  }
}

@media (max-width: 760px) {
  .auth-page {
    padding: 24px 16px;
  }

  .auth-card {
    padding: 28px 20px;
  }

  .feature-grid,
  .agent-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .brand-copy h1 {
    font-size: 36px;
  }

  .feature-card {
    min-height: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner,
  .welcome-agent {
    animation: none;
  }

  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
  }
}

.auth-page {
  --auth-scale: 0.9;

  grid-template-columns: minmax(690px, 1.24fr) minmax(390px, 590px);
  gap: clamp(28px, 4.8vw, 78px);
  align-items: stretch;
  height: 100vh;
  height: 100svh;
  max-height: 100vh;
  max-height: 100svh;
  min-height: 100vh;
  min-height: 100svh;
  padding: clamp(32px, 4.2vw, 68px) clamp(32px, 4.8vw, 80px);
  overflow: hidden;
  background:
    radial-gradient(circle at 97% 6%, rgba(125, 172, 255, 0.34), transparent 26%),
    radial-gradient(circle at 34% 92%, rgba(132, 106, 255, 0.18), transparent 31%),
    linear-gradient(112deg, #f7fbff 0%, #f7f5ff 52%, #eaf3ff 100%);
  color: #06072a;
}

.auth-page::before,
.auth-page::after {
  position: absolute;
  pointer-events: none;
  content: "";
}

.auth-page::before {
  right: -8vw;
  bottom: -16vw;
  width: 70vw;
  height: 34vw;
  border-radius: 100% 0 0 0;
  background: linear-gradient(150deg, rgba(76, 135, 255, 0.22), rgba(157, 122, 255, 0.08) 50%, transparent 70%);
  transform: rotate(-7deg);
}

.auth-page::after {
  top: 12%;
  left: 28%;
  width: 10px;
  height: 10px;
  background: #ffffff;
  box-shadow:
    360px 38px 0 rgba(126, 151, 255, 0.32),
    620px 215px 0 rgba(255, 255, 255, 0.95),
    1020px -38px 0 rgba(255, 255, 255, 0.9),
    1088px -10px 0 rgba(255, 255, 255, 0.9);
  transform: rotate(45deg);
}

.auth-glow {
  position: absolute;
  pointer-events: none;
  filter: blur(10px);
}

.auth-glow-left {
  left: 0;
  bottom: 18%;
  width: 46vw;
  height: 18vw;
  background: radial-gradient(ellipse, rgba(128, 105, 255, 0.14), transparent 68%);
}

.auth-glow-right {
  right: 8%;
  top: 7%;
  width: 32vw;
  height: 18vw;
  background: radial-gradient(ellipse, rgba(69, 142, 255, 0.18), transparent 68%);
}

.auth-brand {
  position: relative;
  z-index: 1;
  align-content: start;
  gap: clamp(24px, 3.3vw, 42px);
  min-height: 0;
  height: 100%;
  padding-top: 6px;
  transform: scale(var(--auth-scale));
  transform-origin: top left;
}

.brand-pill {
  min-height: 86px;
  padding: 0 24px 0 20px;
  border: 0;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.96);
  color: #07082c;
  font-size: clamp(24px, 1.9vw, 34px);
  line-height: 1;
  box-shadow: 0 16px 36px rgba(59, 86, 150, 0.12);
  backdrop-filter: blur(18px);
}

.brand-icon {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  margin-right: 16px;
  border-radius: 14px;
  background: linear-gradient(135deg, #5b7cff 0%, #8658ff 100%);
  box-shadow: 0 10px 22px rgba(91, 124, 255, 0.28);
}

.brand-icon svg {
  width: 30px;
  height: 30px;
  fill: none;
  stroke: #fff;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2.3;
}

.brand-copy {
  position: relative;
  z-index: 2;
  width: min(720px, 64vw);
}

.brand-copy h1 {
  max-width: 760px;
  margin-top: 4px;
  color: #07082c;
  font-size: clamp(50px, 4.9vw, 76px);
  font-weight: 950;
  line-height: 1.26;
}

.brand-copy h1 em {
  color: #4e61ff;
  font-style: normal;
  text-shadow: 0 12px 26px rgba(83, 104, 255, 0.2);
}

.brand-copy p {
  margin-top: 16px;
  color: #68718f;
  font-size: clamp(19px, 1.45vw, 27px);
  font-weight: 800;
}

.agent-row {
  position: relative;
  z-index: 3;
  grid-template-columns: repeat(4, 110px);
  gap: clamp(18px, 2.1vw, 34px);
  max-width: 600px;
}

.agent-chip {
  gap: 12px;
  color: #090a2e;
  font-size: clamp(16px, 1.05vw, 20px);
  animation: agent-float 4.8s ease-in-out infinite;
  animation-delay: var(--delay, 0s);
}

.agent-face,
.welcome-agent {
  width: 92px;
  height: 92px;
  border: 4px solid color-mix(in srgb, var(--agent, #3b9cff) 64%, white);
  background: color-mix(in srgb, var(--agent, #3b9cff) 12%, white);
  box-shadow:
    0 14px 26px color-mix(in srgb, var(--agent, #3b9cff) 26%, transparent),
    inset 0 0 0 4px rgba(255, 255, 255, 0.74);
}

.agent-face::after,
.welcome-agent::after {
  display: none;
}

.agent-face img,
.welcome-agent img {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  object-fit: cover;
}

.agent-face::before {
  position: absolute;
  inset: -8px;
  z-index: -1;
  border-radius: inherit;
  background:
    radial-gradient(circle at 18% 18%, #fff 0 4px, transparent 5px),
    radial-gradient(circle at 82% 28%, color-mix(in srgb, var(--agent, #3b9cff) 70%, white) 0 3px, transparent 4px),
    conic-gradient(from 35deg, transparent, color-mix(in srgb, var(--agent, #3b9cff) 38%, white), transparent 46%);
  content: "";
  animation: orbit-spark 7s linear infinite;
}

.feature-grid {
  position: relative;
  z-index: 3;
  grid-template-columns: repeat(3, minmax(170px, 252px));
  gap: clamp(18px, 2.1vw, 32px);
  max-width: 790px;
  margin-top: 2px;
}

.feature-card {
  gap: 18px;
  min-height: 250px;
  padding: 34px 30px;
  border: 1px solid rgba(214, 224, 251, 0.82);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 24px 60px rgba(72, 95, 150, 0.12);
  backdrop-filter: blur(18px);
}

.feature-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.feature-card span {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #e8f1ff, #eeeaff);
  color: #497bff;
  font-size: 27px;
}

.feature-card i {
  position: relative;
  display: block;
  width: 52px;
  height: 52px;
  border-radius: 13px;
  background: linear-gradient(135deg, rgba(76, 124, 255, 0.14), rgba(142, 94, 255, 0.2));
}

.feature-card i::before,
.feature-card i::after {
  position: absolute;
  content: "";
}

.feature-doc::before {
  top: 13px;
  left: 16px;
  width: 20px;
  height: 4px;
  border-radius: 99px;
  background: #507cff;
  box-shadow: 0 9px 0 #7f8fff, 0 18px 0 #a6b1ff;
}

.feature-chart::before {
  left: 13px;
  bottom: 12px;
  width: 8px;
  height: 15px;
  border-radius: 3px 3px 0 0;
  background: #6aa7ff;
  box-shadow: 12px -8px 0 #7c6cff, 24px -20px 0 #9c74ff;
}

.feature-chart::after,
.feature-rise::after {
  top: 13px;
  right: 11px;
  width: 18px;
  height: 18px;
  border-top: 4px solid #9c74ff;
  border-right: 4px solid #9c74ff;
}

.feature-rise::before {
  left: 11px;
  bottom: 15px;
  width: 34px;
  height: 22px;
  border-top: 5px solid #507cff;
  border-right: 5px solid #507cff;
  transform: skewY(-24deg);
}

.feature-card strong {
  display: block;
  margin-bottom: 14px;
  color: #08092d;
  font-size: 24px;
  line-height: 1.25;
}

.feature-card p {
  color: #637092;
  font-size: 16px;
  font-weight: 600;
}

.hero-figure {
  position: absolute;
  z-index: 2;
  right: clamp(-150px, -9vw, -70px);
  bottom: clamp(-94px, -8vw, -54px);
  width: clamp(430px, 38vw, 660px);
  pointer-events: none;
}

.hero-girl {
  display: block;
  width: 100%;
  height: auto;
  -webkit-mask-image:
    linear-gradient(90deg, transparent 0%, #000 12%, #000 88%, transparent 100%),
    linear-gradient(180deg, transparent 0%, #000 7%, #000 88%, transparent 100%);
  -webkit-mask-composite: source-in;
  mask-image:
    linear-gradient(90deg, transparent 0%, #000 12%, #000 88%, transparent 100%),
    linear-gradient(180deg, transparent 0%, #000 7%, #000 88%, transparent 100%);
  mask-composite: intersect;
  filter: drop-shadow(0 26px 44px rgba(72, 76, 150, 0.18));
  animation: heroine-breathe 5.4s ease-in-out infinite;
  mix-blend-mode: multiply;
  transform-origin: 52% 78%;
}

.floating-card {
  position: absolute;
  z-index: 2;
  border: 1px solid rgba(218, 226, 252, 0.78);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: 0 16px 34px rgba(75, 91, 144, 0.12);
  backdrop-filter: blur(12px);
  animation: float-card 5s ease-in-out infinite;
}

.rating-card {
  top: 7%;
  left: -10%;
  display: grid;
  gap: 4px;
  width: 150px;
  padding: 22px 24px;
  color: #5976ff;
  font-weight: 900;
  transform: rotate(13deg);
}

.rating-card::before {
  width: 42px;
  height: 42px;
  border-radius: 999px;
  background: conic-gradient(#7d6dff 0 34%, #6eb6ff 34% 66%, #d9ddff 66% 100%);
  content: "";
}

.rating-card span {
  color: #718aff;
  font-size: 13px;
  letter-spacing: 1px;
}

.chat-card {
  top: 10%;
  right: 0;
  display: grid;
  gap: 10px;
  width: 82px;
  height: 64px;
  padding: 18px;
  border-radius: 18px 18px 18px 6px;
  background: rgba(190, 180, 255, 0.8);
  animation-delay: 0.7s;
}

.chat-card span {
  display: block;
  height: 6px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.8);
}

.auth-card {
  align-self: center;
  max-width: 590px;
  min-height: min(820px, calc(100vh - 112px));
  padding: clamp(48px, 4.8vw, 78px) clamp(42px, 4.5vw, 68px);
  border: 0;
  border-radius: 32px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 30px 88px rgba(78, 96, 151, 0.13);
  backdrop-filter: blur(20px);
  transform: scale(var(--auth-scale));
  transform-origin: top center;
}

.auth-form {
  gap: 28px;
}

.form-heading {
  margin-bottom: 10px;
}

.form-heading p {
  margin-bottom: 18px;
  color: #6f7b9d;
  font-size: 20px;
  font-weight: 800;
}

.form-heading h2 {
  color: #08092d;
  font-size: clamp(28px, 2.55vw, 40px);
  font-weight: 950;
  line-height: 1.25;
}

.form-heading span {
  margin-top: 12px;
  color: #68718f;
  font-size: 18px;
  font-weight: 600;
}

.field-group {
  gap: 12px;
}

.field-group > span {
  color: #111330;
  font-size: 16px;
  font-weight: 900;
}

.field-shell {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  min-height: 70px;
  padding: 0 20px;
  border: 1px solid #dbe3f4;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease,
    background 160ms ease;
}

.field-shell:focus-within {
  border-color: #7fa1ff;
  background: #fff;
  box-shadow: 0 0 0 4px rgba(83, 119, 255, 0.1);
}

.field-shell svg {
  width: 24px;
  height: 24px;
  fill: none;
  stroke: #8a94b4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.field-group input {
  width: 100%;
  min-height: 68px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #10122f;
  font-size: 16px;
  font-weight: 700;
  box-shadow: none;
}

.field-group input:focus,
.field-group input[aria-invalid="true"] {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}

.field-shell:has(input[aria-invalid="true"]) {
  border-color: #df4d5f;
}

.field-group input::placeholder {
  color: #a5aec7;
  font-weight: 700;
}

.password-input {
  grid-template-columns: 28px minmax(0, 1fr) 34px;
}

.password-input input {
  padding-right: 0;
}

.password-toggle {
  position: static;
  display: grid;
  place-items: center;
  width: 34px;
  min-height: 34px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #8a94b4;
  transform: none;
}

.password-toggle svg {
  width: 24px;
  height: 24px;
  stroke: currentColor;
}

.form-options {
  margin-top: -2px;
}

.remember-option {
  color: #6f7894;
  font-size: 16px;
  font-weight: 700;
}

.remember-option input {
  width: 22px;
  height: 22px;
  accent-color: #4e7cff;
}

.link-button,
.mode-switch button {
  color: #346fff;
  font-size: 16px;
  font-weight: 900;
}

.submit-button {
  min-height: 74px;
  margin-top: 4px;
  border-radius: 13px;
  background: linear-gradient(100deg, #4186ff 0%, #8950ff 100%);
  font-size: 23px;
  box-shadow: 0 20px 38px rgba(86, 102, 255, 0.25);
}

.mode-switch {
  color: #69728d;
  font-size: 16px;
  font-weight: 700;
}

.welcome-agent {
  --agent: #7567f8;
  animation: agent-float 1s ease-in-out infinite alternate;
}

@keyframes heroine-breathe {
  0%,
  100% {
    transform: translate3d(0, 0, 0) rotate(0deg) scale(1);
  }
  50% {
    transform: translate3d(0, -14px, 0) rotate(0.6deg) scale(1.012);
  }
}

@keyframes agent-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-9px);
  }
}

@keyframes orbit-spark {
  to {
    transform: rotate(360deg);
  }
}

@keyframes float-card {
  0%,
  100% {
    translate: 0 0;
  }
  50% {
    translate: 0 -12px;
  }
}

@media (max-width: 1280px) {
  .auth-page {
    grid-template-columns: minmax(540px, 1fr) minmax(360px, 500px);
    gap: clamp(22px, 3vw, 40px);
    padding: 28px 34px;
  }

  .auth-brand {
    gap: 22px;
  }

  .brand-copy {
    width: min(720px, 100%);
  }

  .brand-copy h1 {
    font-size: clamp(42px, 4.8vw, 58px);
  }

  .brand-copy p {
    font-size: clamp(18px, 2vw, 22px);
  }

  .agent-row {
    grid-template-columns: repeat(4, 88px);
    gap: 14px;
  }

  .agent-face,
  .welcome-agent {
    width: 74px;
    height: 74px;
  }

  .feature-grid {
    grid-template-columns: repeat(3, minmax(140px, 1fr));
    gap: 16px;
  }

  .feature-card {
    min-height: 188px;
    padding: 22px 18px;
  }

  .feature-card strong {
    font-size: 20px;
  }

  .hero-figure {
    right: -10%;
    width: min(500px, 39vw);
  }

  .auth-card {
    justify-self: center;
    min-height: auto;
    max-height: calc(100svh - 56px);
    width: min(590px, 100%);
    padding: 42px 42px;
  }

  .auth-form {
    gap: 20px;
  }
}

@media (max-width: 820px) {
  .auth-page {
    grid-template-columns: 1fr;
    padding: 24px 16px 32px;
  }

  .auth-brand {
    gap: 24px;
    display: none;
  }

  .brand-pill {
    min-height: 64px;
    border-radius: 16px;
    font-size: 24px;
  }

  .brand-icon {
    width: 42px;
    height: 42px;
  }

  .brand-copy h1 {
    font-size: 38px;
  }

  .agent-row {
    grid-template-columns: repeat(2, minmax(96px, 1fr));
    width: min(460px, 100%);
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }

  .feature-card {
    min-height: 0;
    padding: 24px;
  }

  .hero-figure {
    position: relative;
    right: auto;
    bottom: auto;
    justify-self: center;
    order: 4;
    width: min(420px, 94vw);
    margin-top: -16px;
  }

  .floating-card {
    display: none;
  }

  .auth-card {
    align-self: center;
    padding: 32px 22px;
    border-radius: 24px;
    transform-origin: center;
  }

  .field-shell {
    min-height: 62px;
  }

  .field-group input {
    min-height: 60px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-girl,
  .agent-chip,
  .agent-face::before,
  .floating-card,
  .welcome-agent {
    animation: none !important;
  }
}
</style>
