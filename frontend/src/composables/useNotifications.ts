import { computed, ref, type Ref } from "vue";

import {
  ApiError,
  getNotificationDetail,
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead as markAllNotificationsReadApi,
  markNotificationRead,
  type NotificationFilter,
  type NotificationItem
} from "../api";
import { parseApiDate } from "../formatters";

const NOTIFICATION_PAGE_SIZE = 10;
const NOTIFICATION_POLL_INTERVAL_MS = 60000;

type NotificationCenterOptions = {
  enabled: Readonly<Ref<boolean>>;
  isDialogOpen: () => boolean;
  closeDialog: () => void;
  navigate: (path: string) => Promise<unknown> | unknown;
};

export function useNotifications(options: NotificationCenterOptions) {
  const unreadNotificationCount = ref(0);
  const notificationFilter = ref<NotificationFilter>("all");
  const notificationItems = ref<NotificationItem[]>([]);
  const notificationNextCursor = ref<string | null>(null);
  const notificationsLoading = ref(false);
  const notificationsLoadingMore = ref(false);
  const notificationDetailLoading = ref(false);
  const notificationDetail = ref<Awaited<ReturnType<typeof getNotificationDetail>> | null>(null);
  const markingAllNotificationsRead = ref(false);
  const notificationMessage = ref("");
  const notificationHasError = ref(false);
  let pollTimer: ReturnType<typeof window.setInterval> | null = null;
  let requestSequence = 0;

  const unreadNotificationBadge = computed(() =>
    unreadNotificationCount.value > 99 ? "99+" : String(unreadNotificationCount.value)
  );

  async function refreshUnreadNotificationCount() {
    if (!options.enabled.value || document.hidden) {
      return;
    }
    try {
      const response = await getUnreadNotificationCount();
      unreadNotificationCount.value = response.count;
    } catch {
      // A transient polling failure must not disable future refresh attempts.
    }
  }

  function startNotificationPolling() {
    if (pollTimer || document.hidden) {
      return;
    }
    pollTimer = window.setInterval(() => {
      void pollNotifications();
    }, NOTIFICATION_POLL_INTERVAL_MS);
  }

  function stopNotificationPolling() {
    if (!pollTimer) {
      return;
    }
    window.clearInterval(pollTimer);
    pollTimer = null;
  }

  async function pollNotifications() {
    if (!options.enabled.value || document.hidden) {
      return;
    }
    await refreshUnreadNotificationCount();
    if (
      options.isDialogOpen() &&
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
    if (options.enabled.value) {
      void pollNotifications();
      startNotificationPolling();
    }
  }

  function handleWindowFocus() {
    if (!document.hidden && options.enabled.value) {
      void pollNotifications();
      startNotificationPolling();
    }
  }

  async function loadNotifications(options: { reset?: boolean; silent?: boolean } = {}) {
    const currentRequest = ++requestSequence;
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
      if (currentRequest !== requestSequence) {
        return;
      }
      unreadNotificationCount.value = response.unread_count;
      notificationNextCursor.value = response.next_cursor;
      notificationItems.value = reset
        ? response.items
        : [
            ...notificationItems.value,
            ...response.items.filter(
              (item) => !notificationItems.value.some((existing) => existing.id === item.id)
            )
          ];
      if (!options.silent) {
        clearNotificationMessage();
      }
    } catch (error) {
      if (currentRequest !== requestSequence) {
        return;
      }
      if (!options.silent) {
        showNotificationMessage(
          error instanceof ApiError ? error.message : "通知加载失败，请稍后重试。",
          true
        );
      }
    } finally {
      if (currentRequest === requestSequence) {
        notificationsLoading.value = false;
      }
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
      if (!wasRead) {
        await markNotificationRead(item.id);
      }
      const detail = await getNotificationDetail(item.id);
      if (detail.target.exists === false) {
        notificationDetail.value = detail;
        showNotificationMessage(detail.target.message || "关联内容不存在或已被删除。", true);
        return;
      }
      if (detail.target.path) {
        options.closeDialog();
        await options.navigate(detail.target.path);
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
      await markAllNotificationsReadApi();
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
    const labels: Record<string, string> = {
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
    return labels[type] || type;
  }

  function formatNotificationTime(value: string) {
    const date = parseApiDate(value);
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

  return {
    unreadNotificationCount,
    notificationFilter,
    notificationItems,
    notificationNextCursor,
    notificationsLoading,
    notificationsLoadingMore,
    notificationDetailLoading,
    notificationDetail,
    markingAllNotificationsRead,
    notificationMessage,
    notificationHasError,
    unreadNotificationBadge,
    refreshUnreadNotificationCount,
    startNotificationPolling,
    stopNotificationPolling,
    handleVisibilityChange,
    handleWindowFocus,
    loadNotifications,
    loadMoreNotifications,
    changeNotificationFilter,
    openNotificationItem,
    markAllNotificationsAsRead,
    backToNotificationList,
    notificationTypeLabel,
    formatNotificationTime,
    clearNotificationMessage
  };
}
