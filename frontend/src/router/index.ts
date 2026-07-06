import { createRouter, createWebHistory } from "vue-router";

import { isLoggedIn } from "../auth";
import { ensureAuthenticated, hydrateCurrentSession } from "../session";
import AuthView from "../views/AuthView.vue";
import HarnessStatusView from "../views/HarnessStatusView.vue";
import HelpCenterView from "../views/HelpCenterView.vue";
import HistoryDetailView from "../views/HistoryDetailView.vue";
import HistoryView from "../views/HistoryView.vue";
import HomeView from "../views/HomeView.vue";
import InterviewEntryView from "../views/InterviewEntryView.vue";
import MultiRoundInterviewView from "../views/MultiRoundInterviewView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: () => (isLoggedIn() ? { name: "dashboard" } : { name: "login" })
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
      redirect: { name: "history" },
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
  const currentUser = to.meta.requiresAuth || to.path === "/login"
    ? await ensureAuthenticated()
    : isLoggedIn()
      ? await hydrateCurrentSession()
      : null;

  if (to.meta.requiresAuth && !currentUser) {
    return {
      path: "/login",
      query: { redirect: to.fullPath }
    };
  }

  if (to.path === "/login" && currentUser) {
    return "/dashboard";
  }

  return true;
});

export default router;
