<template>
  <RouterView v-if="!showWorkspaceShell" />

  <div
    v-else
    class="app-shell"
    :class="{ 'nav-collapsed': navCollapsed, 'mobile-nav-open': mobileNavOpen }"
  >
    <header class="mobile-nav-bar">
      <RouterLink
        class="brand mobile-brand"
        to="/dashboard"
        aria-label="InterviewArena 工作台"
        @click="closeMobileNav()"
      >
        <span class="brand-mark">IA</span>
        <span class="brand-copy">
          <strong>InterviewArena</strong>
          <small>Campus AI Interview Lab</small>
        </span>
      </RouterLink>
      <button
        ref="mobileMenuButton"
        class="nav-collapse-button mobile-menu-button"
        type="button"
        aria-label="打开主导航"
        aria-controls="mobile-primary-navigation"
        :aria-expanded="mobileNavOpen"
        @click="openMobileNav"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 6h16" />
          <path d="M4 12h16" />
          <path d="M4 18h16" />
        </svg>
      </button>
    </header>

    <button
      v-if="mobileNavOpen"
      class="mobile-nav-backdrop"
      type="button"
      aria-label="关闭主导航"
      @click="closeMobileNav(true)"
    ></button>

    <aside
      id="mobile-primary-navigation"
      class="side-nav"
      :class="{ 'mobile-open': mobileNavOpen }"
      aria-label="主导航"
    >
      <div class="side-nav-head">
        <RouterLink
          class="brand"
          to="/dashboard"
          aria-label="InterviewArena 工作台"
          @click="closeMobileNav()"
        >
          <span class="brand-mark">IA</span>
          <span class="brand-copy">
            <strong>InterviewArena</strong>
            <small>Campus AI Interview Lab</small>
          </span>
        </RouterLink>
        <button
          class="nav-collapse-button desktop-collapse-button"
          type="button"
          :aria-label="navCollapsed ? '展开导航' : '折叠导航'"
          :aria-pressed="navCollapsed"
          @click="toggleNavCollapsed"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 6h16" />
            <path d="M4 12h10" />
            <path d="M4 18h16" />
          </svg>
        </button>
        <button
          ref="mobileCloseButton"
          class="nav-collapse-button mobile-close-button"
          type="button"
          aria-label="关闭主导航"
          @click="closeMobileNav(true)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="m6 6 12 12" />
            <path d="m18 6-12 12" />
          </svg>
        </button>
      </div>

      <nav class="nav-list" @click="closeMobileNav()">
        <section class="nav-section" aria-label="面试">
          <p class="nav-section-label">面试</p>
          <RouterLink :class="{ active: route.name === 'dashboard' }" to="/dashboard">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M4 13.5V19a1 1 0 0 0 1 1h5.5" />
                <path d="M20 10.5V5a1 1 0 0 0-1-1h-5.5" />
                <path d="m14 4 6 6" />
                <path d="m10 20-6-6" />
                <path d="M14 14h6v6h-6z" />
                <path d="M4 4h6v6H4z" />
              </svg>
            </span>
            <span class="nav-text">工作台</span>
          </RouterLink>
          <RouterLink :class="{ active: isInterviewRoute }" to="/interviews/new">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
              </svg>
            </span>
            <span class="nav-text">新建面试</span>
          </RouterLink>
          <RouterLink :class="{ active: isHistoryRoute }" to="/history">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M12 8v5l3 2" />
                <path d="M21 12a9 9 0 1 1-2.64-6.36" />
              </svg>
            </span>
            <span class="nav-text">历史记录</span>
          </RouterLink>
        </section>

        <section class="nav-section" aria-label="成长">
          <p class="nav-section-label">成长</p>
          <RouterLink :class="{ active: isReviewBookmarkRoute }" to="/review-bookmarks">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M6 4h12v16l-6-3-6 3z" />
                <path d="M9 9h6" />
                <path d="M9 13h4" />
              </svg>
            </span>
            <span class="nav-text">复盘收藏</span>
          </RouterLink>
          <RouterLink :class="{ active: isMemoryRoute }" to="/memories">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M12 4v16" />
                <path d="M8 7a4 4 0 0 1 4-3 4 4 0 0 1 4 3" />
                <path d="M8 17a4 4 0 0 0 4 3 4 4 0 0 0 4-3" />
                <path d="M5 10h14" />
                <path d="M5 14h14" />
              </svg>
            </span>
            <span class="nav-text">我的记忆</span>
          </RouterLink>
        </section>

        <section class="nav-section" aria-label="支持">
          <p class="nav-section-label">支持</p>
          <RouterLink :class="{ active: isHelpRoute }" to="/help">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="9" />
                <path d="M9.5 9a2.7 2.7 0 0 1 5.2 1c0 2-2.7 2.2-2.7 4" />
                <path d="M12 17h.01" />
              </svg>
            </span>
            <span class="nav-text">帮助中心</span>
          </RouterLink>
        </section>
      </nav>

      <div class="side-nav-footer">
        <div class="account-area" @click.stop>
          <button
            class="account-card"
            type="button"
            :aria-expanded="showAccountMenu"
            @click="toggleAccountMenu"
          >
            <span class="avatar">
              <img v-if="accountAvatarUrl" :src="accountAvatarUrl" alt="" aria-hidden="true" />
              <template v-else>{{ userInitial }}</template>
            </span>
            <strong>{{ displayName }}</strong>
            <span class="chevron" aria-hidden="true"></span>
          </button>

          <div v-if="showAccountMenu" class="account-menu" role="menu" @click="closeMobileNav()">
            <button type="button" role="menuitem" @click="openProfileDialog">个人资料</button>
            <button type="button" role="menuitem" @click="openSettingsDialog">设置</button>
            <button type="button" role="menuitem" @click="openAdvancedDiagnostics">高级诊断</button>
            <button type="button" role="menuitem" @click="openLogoutDialog">退出登录</button>
          </div>
        </div>
      </div>
    </aside>

    <div class="app-main-area">
      <header
        v-if="showTopToolbar"
        class="top-toolbar"
        :class="{ 'history-detail-toolbar': route.name === 'history-detail' }"
      >
        <div class="toolbar-title">
          <p>{{ pageKicker }}</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="toolbar-actions" aria-label="页面操作">
          <button
            class="toolbar-icon notification-trigger"
            type="button"
            aria-label="消息中心"
            :aria-describedby="unreadNotificationCount > 0 ? 'notification-badge-label' : undefined"
            @click="openNotificationDialog"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
              <path d="M10 21h4" />
            </svg>
            <span
              v-if="unreadNotificationCount > 0"
              id="notification-badge-label"
              class="notification-badge"
            >
              {{ unreadNotificationBadge }}
            </span>
          </button>
        </div>
      </header>

      <main class="workspace-shell" :class="workspaceClass">
        <RouterView />
      </main>
    </div>

    <div v-if="activeDialog" class="modal-backdrop" @click.self="closeDialog">
      <section
        class="account-dialog"
        :class="{
          compact: activeDialog === 'logout',
          settings: activeDialog === 'settings',
          notifications: activeDialog === 'notifications'
        }"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="`${activeDialog}-dialog-title`"
      >
        <template v-if="activeDialog === 'settings'">
          <aside class="settings-sidebar">
            <button
              class="icon-button close-in-sidebar"
              type="button"
              aria-label="关闭"
              @click="closeDialog"
            >
              ×
            </button>
            <button
              class="settings-nav-item"
              :class="{ active: activeSettingsPanel === 'personalization' }"
              type="button"
              @click="selectSettingsPanel('personalization')"
            >
              <span class="settings-nav-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 2" />
                </svg>
              </span>
              个性化
            </button>
          </aside>

          <div v-if="activeSettingsPanel === 'personalization'" class="settings-content">
            <p v-if="settingsMessage" class="dialog-message" :class="{ error: settingsHasError }">
              {{ settingsMessage }}
            </p>

            <section class="settings-section">
              <div class="section-title-row">
                <h2 :id="`${activeDialog}-dialog-title`">记忆</h2>
                <span class="help-dot" title="控制是否使用历史面试表现进行个性化">?</span>
              </div>

              <div class="settings-row">
                <div>
                  <strong>启用记忆</strong>
                  <p>允许系统依据历史面试表现，为你定制更贴近个人情况的提问和反馈。</p>
                </div>
                <button
                  class="memory-toggle-button"
                  :class="{ active: memoryEnabled }"
                  type="button"
                  :aria-pressed="memoryEnabled"
                  :disabled="settingsLoading || savingPreference"
                  @click="toggleMemory"
                >
                  {{ memoryEnabled ? "已开启" : "已关闭" }}
                </button>
              </div>

              <div class="settings-row">
                <div>
                  <strong>清除记忆</strong>
                  <p>删除系统已保存的个人长期记忆，不会删除历史面试记录。</p>
                </div>
                <button
                  class="pill-button clear-memory-button"
                  type="button"
                  :disabled="settingsLoading || clearingMemories || isClearing"
                  @click="confirmClearMemories"
                >
                  {{ clearMemoryButtonLabel }}
                </button>
              </div>

              <div
                v-if="clearStatus"
                class="clear-status"
                :class="{ error: clearStatus.status === 'failed' }"
              >
                <strong>{{ clearStatusText }}</strong>
                <span v-if="clearStatus.task_id">任务编号：#{{ clearStatus.task_id }}</span>
                <span v-if="shouldShowDeletedCount">
                  已清除记忆：{{ clearStatus.deleted_count }}
                </span>
                <span v-if="clearStatus.error_message">{{ clearStatus.error_message }}</span>
              </div>

              <p class="muted-note">
                记忆用于生成个性化面试体验。关闭后，系统不会使用历史表现进行个性化。
              </p>
            </section>
          </div>

          <div v-else :id="`${activeDialog}-dialog-title`" class="settings-empty">设置暂无内容</div>
        </template>

        <header v-else class="dialog-header">
          <h2 :id="`${activeDialog}-dialog-title`">{{ dialogTitle }}</h2>
          <button class="icon-button" type="button" aria-label="关闭" @click="closeDialog">
            ×
          </button>
        </header>

        <div v-if="activeDialog === 'profile'" class="dialog-body">
          <div class="profile-summary">
            <span class="profile-avatar">
              <img v-if="profileAvatarUrl" :src="profileAvatarUrl" alt="" aria-hidden="true" />
              <template v-else>{{ profileInitial }}</template>
            </span>
            <div class="profile-summary-copy">
              <strong>{{ profileForm.displayName || displayName }}</strong>
              <span>@{{ profileForm.username || currentUser?.username }}</span>
              <button
                class="profile-avatar-button"
                type="button"
                :disabled="avatarUploading || profileLoading"
                @click="openAvatarPicker"
              >
                {{ avatarUploading ? "上传中..." : profileAvatarUrl ? "更换头像" : "上传头像" }}
              </button>
              <input
                ref="profileAvatarInput"
                class="visually-hidden"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                @change="uploadProfileAvatar"
              />
            </div>
          </div>

          <p v-if="profileMessage" class="dialog-message" :class="{ error: profileHasError }">
            {{ profileMessage }}
          </p>

          <form class="dialog-form" @submit.prevent="saveProfile">
            <label>
              显示名称
              <input
                v-model.trim="profileForm.displayName"
                type="text"
                maxlength="64"
                :disabled="profileSaving"
                @input="profileDirty = true"
              />
            </label>
            <label>
              用户名
              <input :value="profileForm.username" type="text" disabled />
            </label>

            <div class="dialog-actions">
              <button class="primary-action" type="submit" :disabled="profileSaving">
                {{ profileSaving ? "保存中..." : "保存" }}
              </button>
              <button type="button" @click="closeDialog">取消</button>
            </div>
          </form>
        </div>

        <div v-else-if="activeDialog === 'logout'" class="dialog-body logout-confirm">
          <p>你确定要退出登录吗？</p>
          <div class="dialog-actions">
            <button class="black-danger" type="button" @click="logout">退出登录</button>
            <button type="button" @click="closeDialog">取消</button>
          </div>
        </div>

        <div
          v-else-if="activeDialog === 'notifications'"
          class="dialog-body notification-dialog-body"
        >
          <template v-if="notificationDetail">
            <button class="text-button back-button" type="button" @click="backToNotificationList">
              返回列表
            </button>
            <p
              v-if="notificationMessage"
              class="dialog-message"
              :class="{ error: notificationHasError }"
            >
              {{ notificationMessage }}
            </p>
            <article class="notification-detail">
              <span class="notification-type">{{
                notificationTypeLabel(notificationDetail.notification_type)
              }}</span>
              <h3>{{ notificationDetail.title }}</h3>
              <p>{{ notificationDetail.content }}</p>
              <time :datetime="notificationDetail.created_at">
                {{ formatNotificationTime(notificationDetail.created_at) }}
              </time>
            </article>
          </template>

          <template v-else>
            <div class="notification-toolbar">
              <div class="segmented-control" aria-label="通知筛选">
                <button
                  type="button"
                  :class="{ active: notificationFilter === 'all' }"
                  @click="changeNotificationFilter('all')"
                >
                  全部
                </button>
                <button
                  type="button"
                  :class="{ active: notificationFilter === 'unread' }"
                  @click="changeNotificationFilter('unread')"
                >
                  未读
                </button>
              </div>
              <button
                class="pill-button"
                type="button"
                :disabled="markingAllNotificationsRead || unreadNotificationCount === 0"
                @click="markAllNotificationsAsRead"
              >
                {{ markingAllNotificationsRead ? "处理中..." : "全部标为已读" }}
              </button>
            </div>

            <p
              v-if="notificationMessage"
              class="dialog-message"
              :class="{ error: notificationHasError }"
            >
              {{ notificationMessage }}
            </p>

            <div v-if="notificationsLoading" class="notification-empty">正在加载通知...</div>
            <div v-else-if="notificationItems.length === 0" class="notification-empty">
              暂无通知
            </div>
            <ul v-else class="notification-list">
              <li v-for="item in notificationItems" :key="item.id">
                <button
                  class="notification-item"
                  :class="{ unread: !item.is_read }"
                  type="button"
                  :disabled="notificationDetailLoading"
                  @click="openNotificationItem(item)"
                >
                  <span class="notification-unread-dot" aria-hidden="true"></span>
                  <span class="notification-item-main">
                    <span class="notification-title-row">
                      <strong>{{ item.title }}</strong>
                      <span class="notification-type">
                        {{ notificationTypeLabel(item.notification_type) }}
                      </span>
                    </span>
                    <span class="notification-summary">{{ item.summary }}</span>
                    <time :datetime="item.created_at">
                      {{ formatNotificationTime(item.created_at) }}
                    </time>
                  </span>
                  <span class="notification-status">{{ item.is_read ? "已读" : "未读" }}</span>
                </button>
              </li>
            </ul>

            <button
              v-if="notificationNextCursor"
              class="load-more-button"
              type="button"
              :disabled="notificationsLoadingMore"
              @click="loadMoreNotifications"
            >
              {{ notificationsLoadingMore ? "加载中..." : "加载更多" }}
            </button>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  AUTH_EXPIRED_EVENT,
  ApiError,
  clearMemories,
  getNotificationDetail,
  getCurrentUser,
  getMemoryClearStatus,
  getUnreadNotificationCount,
  getUserPreferences,
  listNotifications,
  logoutCurrentUser,
  markAllNotificationsRead,
  markNotificationRead,
  uploadCurrentUserAvatar,
  updateCurrentUser,
  updateUserPreferences,
  type MemoryClearStatus,
  type NotificationDetail,
  type NotificationFilter,
  type NotificationItem,
  type UserPreferences
} from "./api";
import { getUser, isLoggedIn, saveAuth } from "./auth";
import { markSessionUnverified } from "./session";

const router = useRouter();
const route = useRoute();
const NAV_COLLAPSED_STORAGE_KEY = "interviewarena.navCollapsed";
const NOTIFICATION_PAGE_SIZE = 10;
const NOTIFICATION_POLL_INTERVAL_MS = 60000;
const authVersion = ref(0);
const navCollapsed = ref(readNavCollapsedPreference());
const mobileNavOpen = ref(false);
const mobileMenuButton = ref<HTMLButtonElement | null>(null);
const mobileCloseButton = ref<HTMLButtonElement | null>(null);
const showAccountMenu = ref(false);
const activeDialog = ref<"profile" | "settings" | "logout" | "notifications" | "">("");
const profileLoading = ref(false);
const profileSaving = ref(false);
const avatarUploading = ref(false);
const profileAvatarInput = ref<HTMLInputElement | null>(null);
const profileMessage = ref("");
const profileHasError = ref(false);
const profileDirty = ref(false);
const profileForm = reactive({
  displayName: "",
  username: "",
  avatarUrl: ""
});
const preferences = ref<UserPreferences | null>(null);
const memoryEnabled = ref(true);
const activeSettingsPanel = ref<"personalization" | "">("");
const settingsLoading = ref(false);
const savingPreference = ref(false);
const clearingMemories = ref(false);
const clearStatus = ref<MemoryClearStatus | null>(null);
const settingsMessage = ref("");
const settingsHasError = ref(false);
const unreadNotificationCount = ref(0);
const notificationFilter = ref<NotificationFilter>("all");
const notificationItems = ref<NotificationItem[]>([]);
const notificationNextCursor = ref<string | null>(null);
const notificationsLoading = ref(false);
const notificationsLoadingMore = ref(false);
const notificationDetailLoading = ref(false);
const notificationDetail = ref<NotificationDetail | null>(null);
const markingAllNotificationsRead = ref(false);
const notificationMessage = ref("");
const notificationHasError = ref(false);
let settingsMessageTimer: number | null = null;
let clearMemoryPollTimer: ReturnType<typeof window.setInterval> | null = null;
let notificationPollTimer: ReturnType<typeof window.setInterval> | null = null;

const activeClearStatuses = new Set(["pending", "processing", "retry_wait"]);

const loggedIn = ref(isLoggedIn());
const currentUser = ref(getUser());

function refreshAuthState(): void {
  loggedIn.value = isLoggedIn();
  currentUser.value = getUser();
}

watch(() => [route.fullPath, authVersion.value], refreshAuthState, { flush: "sync" });
watch(
  () => route.fullPath,
  () => closeMobileNav()
);
const showWorkspaceShell = computed(() => loggedIn.value && route.name !== "login");
const isDashboardShell = computed(() => route.name === "dashboard");
const isInterviewRoute = computed(() =>
  ["interview-entry", "multi-round-interview"].includes(String(route.name))
);
const isHistoryRoute = computed(() => ["history", "history-detail"].includes(String(route.name)));
const isReviewBookmarkRoute = computed(() => route.name === "review-bookmarks");
const isMemoryRoute = computed(() => route.name === "memories");
const isHelpRoute = computed(() => route.name === "help-center");
const showTopToolbar = computed(
  () =>
    !["multi-round-interview", "harness-status"].includes(String(route.name)) &&
    !isDashboardShell.value
);
const workspaceClass = computed(() => ({
  "interview-workspace": route.name === "multi-round-interview",
  "history-detail-workspace": route.name === "history-detail"
}));
const pageMeta = computed(() => {
  const meta: Record<string, { title: string; kicker: string }> = {
    dashboard: { title: "工作台", kicker: "面试训练总览" },
    "interview-entry": { title: "新建面试", kicker: "配置多轮模拟面试" },
    history: { title: "历史记录", kicker: "复盘与继续训练" },
    "history-detail": { title: "面试详情", kicker: "单场面试复盘" },
    "review-bookmarks": { title: "复盘收藏", kicker: "错题与专项训练" },
    memories: { title: "我的记忆", kicker: "个性化记忆管理" },
    "harness-status": { title: "高级诊断", kicker: "面试运行与恢复信息" },
    "help-center": { title: "帮助中心", kicker: "使用说明与常见问题" }
  };
  return meta[String(route.name)] || { title: "InterviewArena", kicker: "AI Interview Lab" };
});
const pageTitle = computed(() => pageMeta.value.title);
const pageKicker = computed(() => pageMeta.value.kicker);
const displayName = computed(() => {
  const user = currentUser.value;
  return user?.display_name || user?.username || "已登录用户";
});
const userInitial = computed(() => displayName.value.slice(0, 1).toUpperCase());
const profileInitial = computed(() =>
  (profileForm.displayName || displayName.value).slice(0, 1).toUpperCase()
);
const accountAvatarUrl = computed(() => currentUser.value?.avatar_url || "");
const profileAvatarUrl = computed(
  () => profileForm.avatarUrl || currentUser.value?.avatar_url || ""
);
const unreadNotificationBadge = computed(() =>
  unreadNotificationCount.value > 99 ? "99+" : String(unreadNotificationCount.value)
);
const dialogTitle = computed(() => {
  const titles = {
    profile: "个人资料",
    settings: "设置",
    notifications: "通知中心",
    logout: "退出登录",
    "": ""
  };
  return titles[activeDialog.value];
});

const isClearing = computed(() => {
  if (!clearStatus.value) {
    return false;
  }
  return activeClearStatuses.has(clearStatus.value.status);
});

const clearStatusText = computed(() => {
  const status = clearStatus.value?.status;
  const map: Record<string, string> = {
    idle: "暂无清除任务",
    pending: "清除任务等待中",
    processing: "正在清除个人长期记忆",
    retry_wait: "清除任务等待重试",
    completed: "个人长期记忆已清除",
    failed: "清除失败"
  };
  return status ? map[status] || status : "";
});

const clearMemoryButtonLabel = computed(() => {
  if (clearingMemories.value) {
    return "提交中...";
  }
  if (isClearing.value) {
    return "清除中...";
  }
  return "清除";
});

const shouldShowDeletedCount = computed(() => {
  if (!clearStatus.value || clearStatus.value.deleted_count === undefined) {
    return false;
  }
  return clearStatus.value.status === "completed" || clearStatus.value.deleted_count > 0;
});

onMounted(() => {
  document.addEventListener("click", closeAccountMenu);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  window.addEventListener("focus", handleWindowFocus);
  window.addEventListener("keydown", handleMobileNavKeydown);
  window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
});

onUnmounted(() => {
  document.removeEventListener("click", closeAccountMenu);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  window.removeEventListener("focus", handleWindowFocus);
  window.removeEventListener("keydown", handleMobileNavKeydown);
  window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  clearSettingsMessageTimer();
  stopClearMemoryPolling();
  stopNotificationPolling();
});

watch(
  showWorkspaceShell,
  (visible) => {
    if (visible) {
      void refreshUnreadNotificationCount();
      startNotificationPolling();
    } else {
      unreadNotificationCount.value = 0;
      stopNotificationPolling();
    }
  },
  { immediate: true }
);

function readNavCollapsedPreference() {
  try {
    return window.localStorage.getItem(NAV_COLLAPSED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function toggleNavCollapsed() {
  navCollapsed.value = !navCollapsed.value;
  try {
    window.localStorage.setItem(NAV_COLLAPSED_STORAGE_KEY, String(navCollapsed.value));
  } catch {
    // Ignore storage failures so the navigation remains usable in private modes.
  }
}

async function openMobileNav() {
  mobileNavOpen.value = true;
  await nextTick();
  mobileCloseButton.value?.focus();
}

function closeMobileNav(restoreFocus = false) {
  if (!mobileNavOpen.value) {
    return;
  }
  mobileNavOpen.value = false;
  closeAccountMenu();
  if (restoreFocus) {
    void nextTick(() => mobileMenuButton.value?.focus());
  }
}

function handleMobileNavKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && mobileNavOpen.value) {
    closeMobileNav(true);
  }
}

function toggleAccountMenu() {
  showAccountMenu.value = !showAccountMenu.value;
}

function closeAccountMenu() {
  showAccountMenu.value = false;
}

function openProfileDialog() {
  closeAccountMenu();
  hydrateProfileForm(currentUser.value);
  activeDialog.value = "profile";
  profileMessage.value = "";
  profileHasError.value = false;
  profileDirty.value = false;
  void loadProfile();
}

function openSettingsDialog() {
  closeAccountMenu();
  activeDialog.value = "settings";
  activeSettingsPanel.value = "personalization";
  clearSettingsMessage();
  void loadSettings();
  void refreshClearStatus(false);
}

function openAdvancedDiagnostics() {
  closeAccountMenu();
  closeMobileNav();
  void router.push({ name: "harness-status" });
}

function openLogoutDialog() {
  closeAccountMenu();
  activeDialog.value = "logout";
}

function openNotificationDialog() {
  closeAccountMenu();
  activeDialog.value = "notifications";
  notificationDetail.value = null;
  clearNotificationMessage();
  void loadNotifications({ reset: true });
}

function closeDialog() {
  const closingDialog = activeDialog.value;
  activeDialog.value = "";
  activeSettingsPanel.value = "";
  clearSettingsMessage();
  clearNotificationMessage();
  notificationDetail.value = null;
  if (closingDialog === "settings") {
    stopClearMemoryPolling();
  }
  if (profileAvatarInput.value) {
    profileAvatarInput.value.value = "";
  }
}

function selectSettingsPanel(panel: "personalization") {
  if (activeSettingsPanel.value === panel) {
    return;
  }

  activeSettingsPanel.value = panel;
  clearSettingsMessage();
  if (!preferences.value) {
    void loadSettings();
  }
}

async function loadProfile() {
  profileLoading.value = true;
  try {
    const profile = await getCurrentUser();
    const hydratedProfile = normalizeProfile(profile, profileForm.displayName);
    if (!profileDirty.value) {
      hydrateProfileForm(hydratedProfile);
    } else {
      profileForm.username = hydratedProfile.username;
    }
    saveAuth(hydratedProfile);
    authVersion.value += 1;
  } catch (error) {
    showProfileError(error instanceof ApiError ? error.message : "个人资料加载失败。");
  } finally {
    profileLoading.value = false;
  }
}

async function saveProfile() {
  const displayNameToSave = profileForm.displayName.trim();
  if (!displayNameToSave) {
    showProfileError("显示名称不能为空。");
    return;
  }
  profileSaving.value = true;
  try {
    const profile = await updateCurrentUser(displayNameToSave);
    const hydratedProfile = normalizeProfile(profile, displayNameToSave);
    hydrateProfileForm(hydratedProfile);
    profileDirty.value = false;
    saveAuth(hydratedProfile);
    authVersion.value += 1;
    profileMessage.value = "个人资料已保存。";
    profileHasError.value = false;
  } catch (error) {
    showProfileError(error instanceof ApiError ? error.message : "个人资料保存失败。");
  } finally {
    profileSaving.value = false;
  }
}

function openAvatarPicker() {
  if (avatarUploading.value || profileLoading.value) {
    return;
  }
  profileAvatarInput.value?.click();
}

async function uploadProfileAvatar(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }

  avatarUploading.value = true;
  try {
    const profile = await uploadCurrentUserAvatar(file);
    const hydratedProfile = normalizeProfile(profile, profileForm.displayName);
    if (!profileDirty.value) {
      hydrateProfileForm(hydratedProfile);
    } else {
      profileForm.username = hydratedProfile.username;
      profileForm.avatarUrl = hydratedProfile.avatar_url || "";
    }
    saveAuth(hydratedProfile);
    authVersion.value += 1;
    profileMessage.value = "头像已更新。";
    profileHasError.value = false;
  } catch (error) {
    showProfileError(error instanceof ApiError ? error.message : "头像上传失败。");
  } finally {
    avatarUploading.value = false;
    input.value = "";
  }
}

function hydrateProfileForm(
  user: { username?: string; display_name?: string; avatar_url?: string | null } | null
) {
  profileForm.displayName = user?.display_name || user?.username || "";
  profileForm.username = user?.username || "";
  profileForm.avatarUrl = user?.avatar_url || "";
}

function normalizeProfile<
  T extends { username: string; display_name?: string; avatar_url?: string | null }
>(profile: T, fallbackDisplayName: string) {
  return {
    ...profile,
    display_name: profile.display_name || fallbackDisplayName || profile.username,
    avatar_url: profile.avatar_url || null
  };
}

async function loadSettings() {
  settingsLoading.value = true;
  try {
    preferences.value = await getUserPreferences();
    memoryEnabled.value = preferences.value.memory_enabled;
  } catch (error) {
    showSettingsError(error instanceof ApiError ? error.message : "设置加载失败。");
  } finally {
    settingsLoading.value = false;
  }
}

async function toggleMemory() {
  const nextValue = !memoryEnabled.value;
  savingPreference.value = true;
  try {
    preferences.value = await updateUserPreferences(nextValue);
    memoryEnabled.value = preferences.value.memory_enabled;
    showSettingsMessage(memoryEnabled.value ? "记忆系统已开启。" : "记忆系统已关闭。");
  } catch (error) {
    showSettingsError(error instanceof ApiError ? error.message : "记忆设置保存失败。");
  } finally {
    savingPreference.value = false;
  }
}

async function confirmClearMemories() {
  const confirmed = window.confirm("将永久删除个人长期记忆，但不会删除历史面试记录。确认继续吗？");
  if (!confirmed) {
    return;
  }

  clearingMemories.value = true;
  try {
    clearStatus.value = await clearMemories();
    showSettingsMessage("已提交清除记忆请求。");
    if (isClearing.value) {
      startClearMemoryPolling();
    }
  } catch (error) {
    showSettingsError(error instanceof ApiError ? error.message : "清除记忆请求失败。");
  } finally {
    clearingMemories.value = false;
  }
}

async function refreshClearStatus(showFailure = true) {
  try {
    clearStatus.value = await getMemoryClearStatus();
    if (isClearing.value && activeDialog.value === "settings") {
      startClearMemoryPolling();
    } else {
      stopClearMemoryPolling();
    }
  } catch (error) {
    stopClearMemoryPolling();
    if (showFailure) {
      showSettingsError(error instanceof ApiError ? error.message : "清除状态刷新失败。");
    }
  }
}

function startClearMemoryPolling() {
  if (clearMemoryPollTimer) {
    return;
  }
  clearMemoryPollTimer = window.setInterval(() => {
    void refreshClearStatus();
  }, 3000);
}

function stopClearMemoryPolling() {
  if (!clearMemoryPollTimer) {
    return;
  }
  window.clearInterval(clearMemoryPollTimer);
  clearMemoryPollTimer = null;
}

async function refreshUnreadNotificationCount() {
  if (!showWorkspaceShell.value || document.hidden) {
    return;
  }
  try {
    const response = await getUnreadNotificationCount();
    unreadNotificationCount.value = response.count;
  } catch {
    stopNotificationPolling();
  }
}

function startNotificationPolling() {
  if (notificationPollTimer || document.hidden) {
    return;
  }
  notificationPollTimer = window.setInterval(() => {
    void pollNotifications();
  }, NOTIFICATION_POLL_INTERVAL_MS);
}

function stopNotificationPolling() {
  if (!notificationPollTimer) {
    return;
  }
  window.clearInterval(notificationPollTimer);
  notificationPollTimer = null;
}

async function pollNotifications() {
  if (!showWorkspaceShell.value || document.hidden) {
    return;
  }
  await refreshUnreadNotificationCount();
  if (
    activeDialog.value === "notifications" &&
    !notificationDetail.value &&
    !notificationsLoading.value &&
    !notificationsLoadingMore.value
  ) {
    await loadNotifications({ reset: true, silent: true });
  }
}

function handleVisibilityChange() {
  if (document.hidden) {
    stopNotificationPolling();
    return;
  }
  if (showWorkspaceShell.value) {
    void pollNotifications();
    startNotificationPolling();
  }
}

function handleWindowFocus() {
  if (!document.hidden && showWorkspaceShell.value) {
    void pollNotifications();
    startNotificationPolling();
  }
}

async function loadNotifications(options: { reset?: boolean; silent?: boolean } = {}) {
  const reset = options.reset ?? false;
  if (reset) {
    notificationNextCursor.value = null;
  }
  if (!options.silent) {
    notificationsLoading.value = reset;
  }
  try {
    const response = await listNotifications({
      filter: notificationFilter.value,
      cursor: reset ? null : notificationNextCursor.value,
      limit: NOTIFICATION_PAGE_SIZE
    });
    unreadNotificationCount.value = response.unread_count;
    notificationNextCursor.value = response.next_cursor;
    notificationItems.value = reset
      ? response.items
      : [...notificationItems.value, ...response.items];
    if (!options.silent) {
      clearNotificationMessage();
    }
  } catch {
    clearNotificationMessage();
  } finally {
    notificationsLoading.value = false;
  }
}

async function loadMoreNotifications() {
  if (!notificationNextCursor.value || notificationsLoadingMore.value) {
    return;
  }
  notificationsLoadingMore.value = true;
  await loadNotifications({ reset: false });
  notificationsLoadingMore.value = false;
}

function changeNotificationFilter(filter: NotificationFilter) {
  if (notificationFilter.value === filter) {
    return;
  }
  notificationFilter.value = filter;
  notificationDetail.value = null;
  void loadNotifications({ reset: true });
}

async function openNotificationItem(item: NotificationItem) {
  const wasRead = item.is_read;
  applyNotificationReadState(item.id, true);
  notificationDetailLoading.value = true;
  clearNotificationMessage();
  try {
    await markNotificationRead(item.id);
    const detail = await getNotificationDetail(item.id);
    if (detail.target.exists === false) {
      notificationDetail.value = detail;
      showNotificationMessage(detail.target.message || "关联内容不存在或已被删除。", true);
      return;
    }
    if (detail.target.path) {
      closeDialog();
      await router.push(detail.target.path);
      return;
    }
    notificationDetail.value = detail;
  } catch (error) {
    applyNotificationReadState(item.id, wasRead);
    showNotificationMessage(
      notificationErrorMessage(error, "通知处理失败。", "关联内容不存在或已被删除。"),
      true
    );
  } finally {
    notificationDetailLoading.value = false;
  }
}

async function markAllNotificationsAsRead() {
  if (unreadNotificationCount.value === 0 || markingAllNotificationsRead.value) {
    return;
  }
  const previousCount = unreadNotificationCount.value;
  const previousItems = notificationItems.value.map((item) => ({ ...item }));
  markingAllNotificationsRead.value = true;
  notificationItems.value = notificationItems.value.map((item) => ({ ...item, is_read: true }));
  unreadNotificationCount.value = 0;
  clearNotificationMessage();
  try {
    await markAllNotificationsRead();
    if (notificationFilter.value === "unread") {
      notificationItems.value = [];
      notificationNextCursor.value = null;
    }
  } catch (error) {
    unreadNotificationCount.value = previousCount;
    notificationItems.value = previousItems;
    showNotificationMessage(notificationErrorMessage(error, "全部已读失败。"), true);
  } finally {
    markingAllNotificationsRead.value = false;
  }
}

function applyNotificationReadState(notificationId: number, isRead: boolean) {
  const target = notificationItems.value.find((item) => item.id === notificationId);
  if (!target || target.is_read === isRead) {
    return;
  }
  target.is_read = isRead;
  unreadNotificationCount.value = Math.max(0, unreadNotificationCount.value + (isRead ? -1 : 1));
}

function backToNotificationList() {
  notificationDetail.value = null;
  clearNotificationMessage();
}

function notificationTypeLabel(type: string) {
  const map: Record<string, string> = {
    interview_flow: "面试流程",
    interview: "面试流程",
    score_report: "评分报告",
    scoring_report: "评分报告",
    report: "评分报告",
    memory_system: "记忆系统",
    memory: "记忆系统",
    harness_exception: "面试运行异常",
    harness_error: "面试运行异常",
    harness: "面试运行异常",
    system: "系统通知",
    system_notice: "系统通知"
  };
  return map[type] || type;
}

function formatNotificationTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function showNotificationMessage(text: string, hasError = false) {
  notificationMessage.value = text;
  notificationHasError.value = hasError;
}

function clearNotificationMessage() {
  notificationMessage.value = "";
  notificationHasError.value = false;
}

function notificationErrorMessage(error: unknown, fallback: string, notFoundFallback = fallback) {
  if (!(error instanceof ApiError)) {
    return fallback;
  }
  if (error.status === 404 || error.message.trim().toLowerCase() === "not found") {
    return notFoundFallback;
  }
  return error.message || fallback;
}

function showProfileError(text: string) {
  profileMessage.value = text;
  profileHasError.value = true;
}

function showSettingsError(text: string) {
  showSettingsMessage(text, true);
}

function showSettingsMessage(text: string, hasError = false) {
  clearSettingsMessageTimer();
  settingsMessage.value = text;
  settingsHasError.value = hasError;
  settingsMessageTimer = window.setTimeout(() => {
    clearSettingsMessage();
  }, 3000);
}

function clearSettingsMessage() {
  clearSettingsMessageTimer();
  settingsMessage.value = "";
  settingsHasError.value = false;
}

function clearSettingsMessageTimer() {
  if (settingsMessageTimer !== null) {
    window.clearTimeout(settingsMessageTimer);
    settingsMessageTimer = null;
  }
}

function handleAuthExpired() {
  markSessionUnverified();
  authVersion.value += 1;
  closeDialog();
  closeAccountMenu();
  if (route.name !== "login") {
    router.push({ path: "/login", query: { redirect: route.fullPath } });
  }
}

async function logout() {
  await logoutCurrentUser();
  markSessionUnverified();
  authVersion.value += 1;
  closeDialog();
  router.push("/login");
}
</script>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  width: 100%;
  height: 100vh;
  min-height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: #f8fafc;
}

.side-nav {
  position: sticky;
  top: 0;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 22px;
  height: 100vh;
  padding: 22px 16px 0;
  border-right: 1px solid #e1e5ea;
  background: #fbfcfe;
}

.brand {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 46px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid #dde3ea;
  border-radius: 8px;
  background: #fff;
  color: #101418;
  font-size: 14px;
  font-weight: 700;
}

.brand strong {
  display: block;
  overflow: hidden;
  color: #111418;
  font-size: 18px;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-list {
  display: grid;
  align-content: start;
  gap: 10px;
  margin-top: 12px;
}

.nav-list a {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  min-height: 54px;
  padding: 0 14px;
  border-radius: 8px;
  color: #313941;
  font-size: 17px;
  font-weight: 500;
}

.nav-list a:hover,
.nav-list a.active,
.nav-list a.router-link-active {
  background: #f0f2f4;
  color: #0d1117;
  font-weight: 700;
}

.nav-icon {
  display: grid;
  place-items: center;
  color: #6b7280;
}

.nav-list a.active .nav-icon,
.nav-list a.router-link-active .nav-icon {
  color: #0d1117;
}

.nav-icon svg {
  width: 21px;
  height: 21px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.account-area {
  position: relative;
  align-self: end;
}

.account-card {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) 24px;
  gap: 10px;
  align-items: center;
  width: 100%;
  min-width: 0;
  min-height: 62px;
  padding: 11px 12px;
  border: 1px solid #e1e5ea;
  border-radius: 8px 8px 0 0;
  background: #fff;
  text-align: left;
}

.account-card:hover,
.account-card[aria-expanded="true"] {
  background: #f6f7f9;
}

.account-card strong {
  display: block;
  overflow: hidden;
  color: #111418;
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: #f2f3f5;
  color: #111418;
  font-weight: 700;
}

.chevron {
  position: relative;
  display: grid;
  place-items: center;
  justify-self: end;
  width: 24px;
  height: 24px;
  color: #4b5563;
}

.chevron::before {
  width: 8px;
  height: 8px;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  content: "";
  transform: translateY(-2px) rotate(45deg);
}

.account-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 6px;
  border: 1px solid #dce2ea;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 18px 40px rgb(15 23 42 / 12%);
  z-index: 20;
}

.account-menu button {
  display: block;
  width: 100%;
  min-height: 40px;
  padding: 8px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  text-align: left;
}

.account-menu button:hover {
  background: #f3f4f6;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(15 23 42 / 38%);
  z-index: 50;
}

.account-dialog {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: min(520px, 100%);
  max-height: min(600px, calc(100vh - 48px));
  border: 1px solid #dbe1e8;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 24px 80px rgb(15 23 42 / 22%);
  overflow: hidden;
}

.account-dialog.settings {
  grid-template-columns: 230px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  width: min(960px, calc(100vw - 32px));
  height: min(620px, calc(100vh - 32px));
  max-height: calc(100vh - 32px);
}

.account-dialog.compact {
  max-height: min(280px, calc(100vh - 48px));
}

.dialog-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid #edf0f3;
}

.dialog-header h2 {
  margin: 0;
  color: #111827;
  font-size: 20px;
}

.icon-button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  min-height: 34px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #4b5563;
  font-size: 24px;
  line-height: 1;
}

.icon-button:hover {
  background: #f3f4f6;
}

.settings-sidebar {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  align-content: start;
  gap: 24px;
  min-width: 0;
  padding: 18px 10px;
  border-right: 1px solid #eceff3;
  background: #fff;
}

.close-in-sidebar {
  justify-self: start;
  margin-left: 2px;
}

.settings-nav-item {
  align-self: start;
  justify-self: start;
  display: grid;
  grid-template-columns: 24px auto;
  gap: 10px;
  align-items: center;
  width: fit-content;
  min-height: 48px;
  padding: 0 14px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #111827;
  text-align: left;
  font-size: 17px;
}

.settings-nav-item.active {
  background: #f0f0f0;
}

.settings-nav-icon {
  display: grid;
  place-items: center;
  color: #111827;
}

.settings-nav-icon svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.settings-content {
  min-width: 0;
  padding: 24px;
  overflow: auto;
}

.settings-empty {
  display: grid;
  place-items: center;
  min-width: 0;
  padding: 24px;
  color: #6b7280;
  font-size: 17px;
}

.settings-content h2 {
  margin: 0 0 14px;
  color: #111827;
  font-size: 22px;
  line-height: 1.3;
}

.settings-section {
  display: grid;
  gap: 0;
}

.section-title-row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding-bottom: 26px;
}

.section-title-row h2 {
  margin: 0;
  color: #020617;
  font-size: 24px;
  line-height: 1.2;
}

.help-dot {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid #9ca3af;
  border-radius: 999px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}

.settings-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 22px;
  align-items: center;
  min-height: 96px;
  padding: 18px 0;
  border-top: 1px solid #edf0f3;
}

.settings-row strong {
  display: block;
  margin-bottom: 6px;
  color: #111827;
  font-size: 19px;
  font-weight: 500;
}

.settings-row p,
.muted-note {
  margin: 0;
  color: #6b7280;
  font-size: 16px;
  line-height: 1.45;
}

.muted-note {
  padding: 26px 0;
  border-top: 1px solid #edf0f3;
}

.pill-button {
  min-width: 80px;
  min-height: 44px;
  padding: 0 18px;
  border-color: #d5d9df;
  border-radius: 999px;
  background: #fff;
  color: #111827;
}

.clear-memory-button {
  border-color: #b42318;
  color: #b42318;
  font-weight: 600;
}

.clear-memory-button:hover:not(:disabled) {
  background: #fff4f2;
}

.clear-memory-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.memory-toggle-button {
  min-width: 88px;
  min-height: 44px;
  padding: 0 18px;
  border: 1px solid #d5d9df;
  border-radius: 999px;
  background: #fff;
  color: #111827;
  font-size: 16px;
  font-weight: 600;
}

.memory-toggle-button.active {
  border-color: #111827;
  background: #111827;
  color: #fff;
}

.memory-toggle-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.dialog-body {
  display: grid;
  gap: 16px;
  align-content: start;
  padding: 20px;
  overflow: auto;
}

.profile-summary {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
}

.profile-summary-copy {
  display: grid;
  gap: 4px;
  justify-items: start;
}

.profile-summary strong,
.profile-summary span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-summary strong {
  color: #111827;
  font-size: 20px;
}

.profile-summary span {
  color: #6b7280;
}

.profile-avatar {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  overflow: hidden;
  border-radius: 999px;
  background: #111827;
  color: #fff;
  font-size: 22px;
  font-weight: 800;
}

.profile-avatar-button {
  margin-top: 6px;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.profile-avatar-button:hover:not(:disabled) {
  border-color: #9ca3af;
  background: #f9fafb;
}

.profile-avatar-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.dialog-form {
  display: grid;
  gap: 14px;
}

.dialog-form input {
  width: 100%;
  margin-top: 8px;
}

.dialog-panel {
  display: grid;
  gap: 18px;
  padding: 16px;
  border: 1px solid #e1e5ea;
  border-radius: 8px;
  background: #fff;
}

.setting-heading {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.setting-heading h3 {
  margin: 0 0 6px;
  color: #111827;
  font-size: 18px;
}

.setting-heading p {
  margin: 0;
  color: #5f6875;
  line-height: 1.6;
}

.status-pill {
  flex: 0 0 auto;
  padding: 5px 9px;
  border: 1px solid #b9dcc2;
  border-radius: 999px;
  background: #eefaf1;
  color: #166534;
  font-size: 13px;
  font-weight: 800;
}

.status-pill.muted {
  border-color: #d8dee6;
  background: #f4f6f8;
  color: #5f6875;
}

.switch-row {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  width: fit-content;
  margin: 0;
  color: #1f2328;
  cursor: pointer;
}

.switch-row input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.switch-control {
  position: relative;
  width: 48px;
  height: 28px;
  border: 1px solid #c7c0b6;
  border-radius: 999px;
  background: #e7e0d5;
  transition: background 0.16s ease;
}

.switch-control::after {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 1px 4px rgb(43 41 38 / 20%);
  content: "";
  transition: transform 0.16s ease;
}

.switch-row input:checked + .switch-control {
  border-color: #166534;
  background: #1f7a3b;
}

.switch-row input:checked + .switch-control::after {
  transform: translateX(20px);
}

.switch-row input:disabled ~ span {
  cursor: not-allowed;
  opacity: 0.6;
}

.clear-status {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid #e1e5ea;
  border-radius: 8px;
  background: #f8fafc;
}

.clear-status.error {
  border-color: #f1b5af;
  background: #fff7f6;
}

.clear-status strong {
  color: #111827;
  font-size: 15px;
}

.clear-status span {
  color: #5f6875;
  font-size: 14px;
}

.dialog-message {
  margin: 0;
  color: #166534;
}

.dialog-message.error {
  color: #b42318;
}

.dialog-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 4px;
}

.primary-action {
  border-color: #111827;
  background: #111827;
  color: #fff;
}

.black-danger {
  border-color: #111827;
  background: #111827;
  color: #fff;
}

.danger-outline {
  justify-self: start;
  border-color: #b42318;
  color: #b42318;
}

.logout-confirm p {
  margin: 0;
  color: #374151;
  line-height: 1.7;
}

.workspace-shell {
  min-width: 0;
  min-height: 100vh;
  padding: 28px;
  overflow: auto;
}

.workspace-shell.interview-workspace {
  grid-row: 1 / -1;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

@media (max-width: 760px) {
  .app-shell {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }

  .side-nav {
    position: static;
    grid-template-rows: auto auto auto;
    height: auto;
    padding: 14px;
  }

  .nav-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .nav-list a {
    justify-content: center;
    padding: 0 8px;
    text-align: center;
    font-size: 14px;
  }

  .account-area {
    align-self: auto;
  }

  .account-card {
    border-radius: 8px;
  }

  .account-menu {
    bottom: auto;
    top: calc(100% + 8px);
  }

  .workspace-shell {
    padding: 16px;
  }

  .modal-backdrop {
    padding: 12px;
  }

  .account-dialog.settings {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
    width: min(100%, 520px);
  }

  .settings-sidebar {
    grid-template-rows: auto auto;
    gap: 12px;
    border-right: 0;
    border-bottom: 1px solid #eceff3;
  }

  .settings-content {
    padding: 18px;
  }

  .settings-row {
    grid-template-columns: 1fr;
    gap: 14px;
    align-items: start;
  }
}
</style>

<style scoped>
.app-shell {
  --shell-sidebar-width: 272px;
  --shell-sidebar-collapsed-width: 82px;

  display: grid;
  grid-template-columns: var(--shell-sidebar-width) minmax(0, 1fr);
  width: 100%;
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 12%, rgb(59 156 255 / 12%), transparent 28%),
    linear-gradient(135deg, var(--brand-50, #f2f8ff) 0%, var(--gray-50, #f7f9fc) 44%, #ffffff 100%);
  color: var(--gray-900, #172033);
}

.app-shell.nav-collapsed {
  grid-template-columns: var(--shell-sidebar-collapsed-width) minmax(0, 1fr);
}

.mobile-nav-bar,
.mobile-close-button,
.mobile-nav-backdrop {
  display: none;
}

.side-nav {
  position: sticky;
  top: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 18px;
  height: 100vh;
  padding: 18px 14px;
  border-right: 1px solid rgb(199 208 220 / 72%);
  background: rgb(255 255 255 / 88%);
  box-shadow: 10px 0 34px rgb(31 68 120 / 7%);
  backdrop-filter: blur(16px);
}

.side-nav-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 38px;
  gap: 10px;
  align-items: center;
}

.brand {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-width: 0;
  min-height: 48px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 14px;
  background: var(--brand-gradient, linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%));
  box-shadow: 0 10px 24px rgb(59 156 255 / 28%);
  color: #fff;
  font-family: var(--font-mono, monospace);
  font-size: 14px;
  font-weight: 800;
}

.brand-copy {
  display: grid;
  min-width: 0;
}

.brand strong {
  overflow: hidden;
  color: var(--gray-900, #172033);
  font-family: var(--font-display, sans-serif);
  font-size: 18px;
  letter-spacing: 0;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brand small {
  overflow: hidden;
  color: var(--gray-500, #758195);
  font-size: 11px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-collapse-button,
.toolbar-icon,
.icon-button {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  min-height: 38px;
  padding: 0;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 10px;
  background: var(--gray-0, #fff);
  color: var(--gray-700, #3b4658);
  transition:
    border-color 160ms var(--ease-standard, ease),
    box-shadow 160ms var(--ease-standard, ease),
    transform 160ms var(--ease-standard, ease);
}

.nav-collapse-button:hover,
.toolbar-icon:hover:not(:disabled),
.icon-button:hover {
  border-color: var(--brand-300, #9fd0ff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
  transform: translateY(-1px);
}

.nav-collapse-button svg,
.toolbar-icon svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.nav-list {
  display: grid;
  align-content: start;
  gap: 18px;
  min-height: 0;
  margin: 0;
  overflow: auto;
}

.nav-section {
  display: grid;
  gap: 6px;
}

.nav-section-label {
  margin: 0;
  padding: 0 12px 4px;
  color: var(--gray-500, #758195);
  font-size: 12px;
  font-weight: 700;
}

.nav-list a,
.nav-action {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  width: 100%;
  min-height: 46px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--gray-700, #3b4658);
  font-size: 15px;
  font-weight: 700;
  text-align: left;
  transition:
    background 160ms var(--ease-standard, ease),
    border-color 160ms var(--ease-standard, ease),
    color 160ms var(--ease-standard, ease),
    transform 160ms var(--ease-standard, ease);
}

.nav-list a:hover,
.nav-action:hover:not(:disabled) {
  background: var(--brand-50, #f2f8ff);
  color: var(--brand-700, #1f64bf);
  transform: translateY(-1px);
}

.nav-list a.active,
.nav-list a.router-link-active,
.nav-action.active {
  border-color: rgb(59 156 255 / 22%);
  background:
    linear-gradient(135deg, rgb(59 156 255 / 14%), rgb(124 108 255 / 12%)), var(--gray-0, #fff);
  color: var(--brand-800, #214f96);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.nav-action.muted,
.nav-action:disabled {
  color: var(--gray-500, #758195);
}

.nav-icon {
  display: grid;
  place-items: center;
  color: currentColor;
}

.nav-icon svg {
  width: 21px;
  height: 21px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.side-nav-footer {
  display: grid;
  gap: 10px;
}

.account-area {
  position: relative;
  align-self: end;
}

.account-card {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 20px;
  gap: 10px;
  align-items: center;
  width: 100%;
  min-height: 56px;
  padding: 9px 10px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 14px;
  background: var(--gray-0, #fff);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
  text-align: left;
}

.account-card:hover,
.account-card[aria-expanded="true"] {
  border-color: var(--brand-300, #9fd0ff);
  background: var(--brand-50, #f2f8ff);
}

.account-card strong {
  overflow: hidden;
  color: var(--gray-900, #172033);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.avatar,
.profile-avatar {
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--brand-500, #3b9cff), var(--violet-500, #7c6cff));
  color: #fff;
  font-weight: 800;
}

.avatar img,
.profile-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar {
  width: 36px;
  height: 36px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
  padding: 0;
  margin: -1px;
}

.chevron {
  width: 20px;
  height: 20px;
}

.account-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 10px);
  display: grid;
  gap: 4px;
  width: 100%;
  min-width: 188px;
  padding: 6px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 14px;
  background: var(--gray-0, #fff);
  box-shadow: var(--shadow-lg, 0 20px 50px rgb(31 68 120 / 14%));
  z-index: 20;
}

.account-menu button {
  min-height: 38px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  text-align: left;
}

.account-menu button:hover {
  background: var(--brand-50, #f2f8ff);
  color: var(--brand-700, #1f64bf);
}

.app-main-area {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.top-toolbar {
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
  min-height: 76px;
  padding: 16px 32px 12px;
  border-bottom: 1px solid rgb(223 229 236 / 80%);
  background: rgb(247 249 252 / 78%);
  backdrop-filter: blur(14px);
}

.top-toolbar.history-detail-toolbar {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 10;
  width: auto;
  min-height: 0;
  padding: 24px 30px 0 0;
  border-bottom: 0;
  background: transparent;
  backdrop-filter: none;
}

.top-toolbar.history-detail-toolbar .toolbar-title {
  display: none;
}

.workspace-shell.history-detail-workspace {
  padding: 0;
}

.toolbar-title {
  min-width: 0;
}

.toolbar-title p {
  margin: 0 0 4px;
  color: var(--brand-700, #1f64bf);
  font-size: 12px;
  font-weight: 800;
}

.toolbar-title h1 {
  margin: 0;
  color: var(--gray-900, #172033);
  font-family: var(--font-display, sans-serif);
  font-size: 24px;
  line-height: 1.25;
}

.toolbar-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
  align-items: center;
}

.notification-trigger {
  position: relative;
  cursor: pointer;
}

.notification-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  display: grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border: 2px solid var(--gray-0, #fff);
  border-radius: 999px;
  background: var(--danger, #df4d5f);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
}

.workspace-shell {
  min-width: 0;
  min-height: 0;
  padding: 28px 32px 34px;
  overflow-x: hidden;
  overflow-y: auto;
}

.workspace-shell.interview-workspace {
  grid-row: 1 / -1;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(23 32 51 / 42%);
  backdrop-filter: blur(10px);
  z-index: 50;
}

.account-dialog {
  width: min(540px, 100%);
  max-height: min(640px, calc(100vh - 48px));
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 16px;
  background: var(--gray-0, #fff);
  box-shadow: var(--shadow-lg, 0 20px 50px rgb(31 68 120 / 14%));
}

.account-dialog.settings {
  grid-template-columns: 232px minmax(0, 1fr);
  width: min(960px, calc(100vw - 40px));
  height: min(620px, calc(100vh - 40px));
}

.account-dialog.notifications {
  width: min(680px, calc(100vw - 40px));
  max-height: min(720px, calc(100vh - 40px));
}

.dialog-header {
  padding: 18px 20px;
  border-bottom: 1px solid var(--gray-100, #eef2f7);
}

.dialog-header h2,
.settings-content h2,
.section-title-row h2 {
  color: var(--gray-900, #172033);
  font-family: var(--font-display, sans-serif);
}

.settings-sidebar {
  gap: 20px;
  padding: 18px 12px;
  border-right: 1px solid var(--gray-100, #eef2f7);
  background: linear-gradient(180deg, var(--brand-50, #f2f8ff), #fff 64%);
}

.settings-nav-item {
  min-height: 44px;
  border-radius: 12px;
  color: var(--gray-700, #3b4658);
  font-size: 15px;
  font-weight: 800;
}

.settings-nav-item.active {
  background: var(--gray-0, #fff);
  color: var(--brand-700, #1f64bf);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.settings-content {
  padding: 26px 28px;
}

.settings-row {
  min-height: 96px;
  border-top: 1px solid var(--gray-100, #eef2f7);
}

.settings-row strong {
  color: var(--gray-900, #172033);
  font-size: 17px;
  font-weight: 800;
}

.settings-row p,
.muted-note,
.clear-status span {
  color: var(--gray-500, #758195);
  line-height: 1.6;
}

.memory-toggle-button.active,
.primary-action,
.black-danger {
  border-color: transparent;
  background: var(--brand-gradient, linear-gradient(135deg, #3b9cff 0%, #7c6cff 100%));
  box-shadow: 0 10px 24px rgb(59 156 255 / 20%);
  color: #fff;
}

.clear-memory-button {
  border-color: rgb(223 77 95 / 34%);
  color: var(--danger, #df4d5f);
  font-weight: 800;
}

.clear-memory-button:hover:not(:disabled) {
  background: rgb(223 77 95 / 8%);
}

.clear-status {
  border-color: var(--brand-200, #c8e3ff);
  border-radius: 12px;
  background: var(--brand-50, #f2f8ff);
}

.clear-status.error {
  border-color: rgb(223 77 95 / 28%);
  background: rgb(223 77 95 / 7%);
}

.profile-avatar {
  width: 56px;
  height: 56px;
  font-size: 22px;
}

.dialog-message {
  color: var(--success, #22a06b);
}

.dialog-message.error {
  color: var(--danger, #df4d5f);
}

.notification-dialog-body {
  min-height: 420px;
}

.notification-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.segmented-control {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(72px, 1fr));
  padding: 4px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 12px;
  background: var(--gray-50, #f7f9fc);
}

.segmented-control button {
  min-height: 34px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--gray-600, #5f6b7a);
  font-weight: 800;
}

.segmented-control button.active {
  background: var(--gray-0, #fff);
  color: var(--brand-700, #1f64bf);
  box-shadow: var(--shadow-sm, 0 4px 12px rgb(31 68 120 / 6%));
}

.notification-empty {
  display: grid;
  place-items: center;
  min-height: 220px;
  color: var(--gray-500, #758195);
  font-weight: 700;
}

.notification-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.notification-item {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  width: 100%;
  min-height: 92px;
  padding: 14px;
  border: 1px solid var(--gray-100, #eef2f7);
  border-radius: 12px;
  background: var(--gray-0, #fff);
  text-align: left;
}

.notification-item:hover:not(:disabled) {
  border-color: var(--brand-200, #c8e3ff);
  background: var(--brand-50, #f2f8ff);
}

.notification-item:disabled {
  cursor: wait;
  opacity: 0.7;
}

.notification-unread-dot {
  width: 8px;
  height: 8px;
  margin-top: 7px;
  border-radius: 999px;
  background: transparent;
}

.notification-item.unread .notification-unread-dot {
  background: var(--danger, #df4d5f);
}

.notification-item-main {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.notification-title-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.notification-title-row strong {
  min-width: 0;
  overflow: hidden;
  color: var(--gray-900, #172033);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notification-type {
  display: inline-grid;
  place-items: center;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid var(--brand-200, #c8e3ff);
  border-radius: 999px;
  background: var(--brand-50, #f2f8ff);
  color: var(--brand-700, #1f64bf);
  font-size: 12px;
  font-weight: 800;
}

.notification-summary,
.notification-item time,
.notification-detail time,
.notification-status {
  color: var(--gray-500, #758195);
  font-size: 13px;
  line-height: 1.5;
}

.notification-summary {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.notification-status {
  min-width: 34px;
  text-align: right;
  font-weight: 800;
}

.load-more-button,
.text-button {
  min-height: 38px;
  border: 1px solid var(--gray-200, #dfe5ec);
  border-radius: 10px;
  background: var(--gray-0, #fff);
  color: var(--gray-700, #3b4658);
  font-weight: 800;
}

.load-more-button {
  justify-self: center;
  min-width: 120px;
}

.text-button {
  justify-self: start;
  padding: 0 12px;
}

.notification-detail {
  display: grid;
  gap: 14px;
  align-content: start;
}

.notification-detail h3 {
  margin: 0;
  color: var(--gray-900, #172033);
  font-size: 22px;
  line-height: 1.35;
}

.notification-detail p {
  margin: 0;
  color: var(--gray-700, #3b4658);
  line-height: 1.8;
  white-space: pre-wrap;
}

.app-shell.nav-collapsed .side-nav {
  padding-inline: 12px;
}

.app-shell.nav-collapsed .side-nav-head {
  grid-template-columns: 1fr;
}

.app-shell.nav-collapsed .brand {
  grid-template-columns: 1fr;
  justify-items: center;
}

.app-shell.nav-collapsed .brand-copy,
.app-shell.nav-collapsed .nav-section-label,
.app-shell.nav-collapsed .nav-text,
.app-shell.nav-collapsed .account-card strong,
.app-shell.nav-collapsed .chevron,
.app-shell.nav-collapsed .help-entry {
  display: none;
}

.app-shell.nav-collapsed .nav-collapse-button {
  justify-self: center;
}

.app-shell.nav-collapsed .nav-list a,
.app-shell.nav-collapsed .nav-action {
  grid-template-columns: 1fr;
  justify-items: center;
  padding: 0;
}

.app-shell.nav-collapsed .account-card {
  grid-template-columns: 1fr;
  justify-items: center;
  padding: 9px;
}

.app-shell.nav-collapsed .account-menu {
  left: calc(100% + 10px);
  right: auto;
  bottom: 0;
}

@media (prefers-reduced-motion: reduce) {
  .side-nav,
  .nav-collapse-button,
  .toolbar-icon,
  .icon-button,
  .nav-list a,
  .nav-action {
    transition: none;
  }
}

@media (max-width: 900px) {
  .app-shell,
  .app-shell.nav-collapsed {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }

  .app-shell.mobile-nav-open {
    height: 100vh;
    overflow: hidden;
  }

  .mobile-nav-bar {
    position: sticky;
    top: 0;
    z-index: 40;
    display: flex;
    gap: 16px;
    align-items: center;
    justify-content: space-between;
    min-height: 64px;
    padding: 8px 16px;
    border-bottom: 1px solid rgb(199 208 220 / 72%);
    background: rgb(255 255 255 / 92%);
    box-shadow: 0 8px 24px rgb(31 68 120 / 8%);
    backdrop-filter: blur(16px);
  }

  .mobile-brand {
    min-height: 48px;
  }

  .mobile-brand .brand-mark {
    width: 40px;
    height: 40px;
    border-radius: 12px;
  }

  .mobile-brand .brand-copy strong {
    font-size: 16px;
  }

  .mobile-menu-button,
  .mobile-close-button {
    display: grid;
    flex: 0 0 auto;
  }

  .mobile-nav-backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: block;
    width: 100%;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: rgb(23 32 51 / 38%);
    box-shadow: none;
    backdrop-filter: blur(5px);
    transform: none;
  }

  .mobile-nav-backdrop:hover,
  .mobile-nav-backdrop:focus-visible {
    border: 0;
    box-shadow: none;
    outline: 0;
    transform: none;
  }

  .side-nav {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 60;
    width: min(320px, calc(100vw - 48px));
    height: 100vh;
    height: 100dvh;
    padding: 18px 14px;
    overflow: hidden;
    box-shadow: 24px 0 60px rgb(23 32 51 / 18%);
    transform: translateX(calc(-100% - 24px));
    transition: transform 220ms var(--ease-standard, ease);
  }

  .side-nav.mobile-open {
    transform: translateX(0);
  }

  .side-nav-head {
    grid-template-columns: minmax(0, 1fr) 38px;
  }

  .desktop-collapse-button {
    display: none;
  }

  .nav-list {
    grid-template-columns: 1fr;
  }

  .app-shell.nav-collapsed .side-nav {
    padding: 18px 14px;
  }

  .app-shell.nav-collapsed .side-nav-head {
    grid-template-columns: minmax(0, 1fr) 38px;
  }

  .app-shell.nav-collapsed .brand {
    grid-template-columns: 44px minmax(0, 1fr);
    justify-items: initial;
  }

  .app-shell.nav-collapsed .brand-copy,
  .app-shell.nav-collapsed .nav-section-label,
  .app-shell.nav-collapsed .nav-text,
  .app-shell.nav-collapsed .account-card strong,
  .app-shell.nav-collapsed .chevron {
    display: initial;
  }

  .app-shell.nav-collapsed .brand-copy {
    display: grid;
  }

  .app-shell.nav-collapsed .nav-list a,
  .app-shell.nav-collapsed .nav-action {
    grid-template-columns: 24px minmax(0, 1fr);
    justify-items: initial;
    padding: 0 12px;
  }

  .app-shell.nav-collapsed .account-card {
    grid-template-columns: 38px minmax(0, 1fr) 20px;
    justify-items: initial;
    padding: 9px 10px;
  }

  .app-shell.nav-collapsed .account-menu {
    right: 0;
    bottom: calc(100% + 10px);
    left: auto;
  }

  .top-toolbar {
    padding: 16px;
  }

  .workspace-shell {
    padding: 18px 16px 24px;
  }

  .account-dialog.settings {
    grid-template-columns: 1fr;
    width: min(100%, 560px);
  }
}
</style>
