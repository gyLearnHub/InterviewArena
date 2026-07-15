import { expect, test } from "@playwright/test";

test("root route renders login instead of a white screen when the backend is unavailable", async ({
  page
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/api/auth/me", async (route) => {
    await route.abort("connectionrefused");
  });

  await page.goto("/");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "登录继续你的面试训练" })).toBeVisible();
  await expect(page.locator("#app")).not.toBeEmpty();
  expect(pageErrors).toEqual([]);
});

test("root route renders login when browser storage is blocked", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.addInitScript(() => {
    const blocked = () => {
      throw new DOMException("Storage access is blocked", "SecurityError");
    };
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: blocked
    });
  });
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
  });

  await page.goto("/");

  expect(pageErrors).toEqual([]);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "登录继续你的面试训练" })).toBeVisible();
  await expect(page.locator("#app")).not.toBeEmpty();
});

test("login page keeps the product presentation credible and unscaled", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 720 });
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "登录继续你的面试训练" })).toBeVisible();
  await expect(page.getByText("4.8/5.0")).toHaveCount(0);
  await expect(page.locator(".floating-card")).toHaveCount(0);

  const authCard = page.locator(".auth-card");
  await expect(authCard).toHaveCSS("transform", "none");

  const cardBox = await authCard.boundingBox();
  expect(cardBox).not.toBeNull();
  expect(cardBox!.y).toBeGreaterThanOrEqual(0);
  expect(cardBox!.y + cardBox!.height).toBeLessThanOrEqual(720);
});

test("login form stays usable without horizontal overflow on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");

  await expect(page.getByRole("main", { name: "账号表单" })).toBeVisible();
  await expect(page.locator(".auth-brand")).toBeHidden();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
  expect(hasHorizontalOverflow).toBe(false);
});
