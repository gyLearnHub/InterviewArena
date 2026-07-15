import { expect, test } from "@playwright/test";

test("restores an authenticated cookie session without a local user cache", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.removeItem("interview_arena_user");
  });

  let sessionChecks = 0;
  await page.route("**/api/auth/me", async (route) => {
    sessionChecks += 1;
    await route.fulfill({
      json: { id: 1, username: "alice", display_name: "Alice", avatar_url: null }
    });
  });
  await page.route("**/api/notifications/unread-count", async (route) => {
    await route.fulfill({ json: { count: 0 } });
  });
  await page.route("**/api/review-bookmarks**", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 0,
        report_count: 0,
        personalized_feedback_used: false,
        latest_interview: null,
        latest_report: null,
        score_trend: [],
        score_delta: null,
        abilities: [],
        weak_points: []
      }
    });
  });

  await page.goto("/dashboard");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: /Alice/ })).toBeVisible();
  await expect(page.locator(".dashboard-header")).toHaveCount(0);
  expect(
    await page
      .locator(".hero-grid")
      .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)
  ).toBe(2);
  expect(
    await page
      .locator(".dashboard-grid")
      .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)
  ).toBe(2);
  expect(sessionChecks).toBe(1);
});

test("uses an off-canvas navigation drawer on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      json: { id: 1, username: "alice", display_name: "Alice", avatar_url: null }
    });
  });
  await page.route("**/api/notifications/unread-count", async (route) => {
    await route.fulfill({ json: { count: 0 } });
  });
  await page.route("**/api/review-bookmarks**", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 0,
        report_count: 0,
        personalized_feedback_used: false,
        latest_interview: null,
        latest_report: null,
        score_trend: [],
        score_delta: null,
        abilities: [],
        weak_points: []
      }
    });
  });

  await page.goto("/dashboard");

  const menuButton = page.getByRole("button", { name: "打开主导航" });
  const navigation = page.locator("aside.side-nav");
  await expect(menuButton).toBeVisible();
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");

  await menuButton.click();

  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  await expect(navigation).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
  await expect(page.locator(".mobile-nav-backdrop")).toBeVisible();
  await expect(navigation.getByRole("button", { name: "关闭主导航" })).toBeFocused();
  await expect(navigation.getByText("Harness 状态", { exact: true })).toHaveCount(0);

  await page.keyboard.press("Escape");

  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".mobile-nav-backdrop")).toHaveCount(0);
  await expect(menuButton).toBeFocused();

  await menuButton.click();
  await navigation.locator(".account-card").click();
  await expect(navigation.getByRole("menuitem", { name: "高级诊断" })).toBeVisible();
});
