import { createRouter, createWebHistory } from "vue-router";

import { isLoggedIn } from "../auth";
import { ensureAuthenticated } from "../session";
import AuthView from "../views/AuthView.vue";
import HarnessStatusView from "../views/HarnessStatusView.vue";
import HelpCenterView from "../views/HelpCenterView.vue";
import HistoryDetailView from "../views/HistoryDetailView.vue";
import HistoryView from "../views/HistoryView.vue";
import HomeView from "../views/HomeView.vue";
import InterviewEntryView from "../views/InterviewEntryView.vue";
import MemoriesView from "../views/MemoriesView.vue";
import MultiRoundInterviewView from "../views/MultiRoundInterviewView.vue";
import ReviewBookmarksView from "../views/ReviewBookmarksView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: { name: "login" }
    },
    {
      path: "/login",
      name: "login",
      component: AuthView
    },
    {
      path: "/dashboard",
      name: "dashboard",
      component: HomeView,
      meta: { requiresAuth: true }
    },
    {
      path: "/interviews/new",
      name: "interview-entry",
      component: InterviewEntryView,
      meta: { requiresAuth: true }
    },
    {
      path: "/interviews/multi/:id",
      name: "multi-round-interview",
      component: MultiRoundInterviewView,
      meta: { requiresAuth: true }
    },
    {
      path: "/reports",
      name: "reports",
      component: HistoryView,
      props: { mode: "reports" },
      meta: { requiresAuth: true }
    },
    {
      path: "/reports/:id",
      name: "feedback-report",
      redirect: (to) => ({ name: "history-detail", params: { id: to.params.id } }),
      meta: { requiresAuth: true }
    },
    {
      path: "/harness",
      name: "harness-status",
      component: HarnessStatusView,
      meta: { requiresAuth: true }
    },
    {
      path: "/memories",
      name: "memories",
      component: MemoriesView,
      meta: { requiresAuth: true }
    },
    {
      path: "/help",
      name: "help-center",
      component: HelpCenterView,
      meta: { requiresAuth: true }
    },
    {
      path: "/history",
      name: "history",
      component: HistoryView,
      meta: { requiresAuth: true }
    },
    {
      path: "/review-bookmarks",
      name: "review-bookmarks",
      component: ReviewBookmarksView,
      meta: { requiresAuth: true }
    },
    {
      path: "/history/:id",
      name: "history-detail",
      component: HistoryDetailView,
      meta: { requiresAuth: true }
    },
    {
      path: "/user",
      redirect: "/dashboard",
      meta: { requiresAuth: true }
    }
  ]
});

router.beforeEach(async (to) => {
  if (to.path === "/login") {
    if (!isLoggedIn()) {
      return true;
    }
    return (await ensureAuthenticated()) ? "/dashboard" : true;
  }

  if (to.meta.requiresAuth) {
    const currentUser = await ensureAuthenticated();
    if (!currentUser) {
      return {
        path: "/login",
        query: { redirect: to.fullPath }
      };
    }
  }

  return true;
});

export default router;
