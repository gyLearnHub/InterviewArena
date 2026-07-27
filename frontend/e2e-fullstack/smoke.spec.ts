import { expect, test } from "@playwright/test";

test("real backend supports readiness, authentication, and dashboard loading", async ({ page }) => {
  const browserErrors: string[] = [];
  const serverErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500) {
      serverErrors.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });

  const ready = await page.request.get("/api/health/ready");
  expect(ready.status()).toBe(200);
  await expect(ready.json()).resolves.toMatchObject({ status: "ready" });

  const username = `smoke${Date.now()}`;
  const password = "Smoke-test-password-2026";
  const registration = await page.request.post("/api/auth/register", {
    data: {
      username,
      password,
      external_model_consent: false
    }
  });
  expect(registration.status()).toBe(200);

  const login = await page.request.post("/api/auth/login", {
    data: { username, password }
  });
  expect(login.status()).toBe(200);

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: new RegExp(username) })).toBeVisible();
  await expect(page.getByRole("link", { name: "开始新面试" })).toBeVisible();

  expect(browserErrors).toEqual([]);
  expect(serverErrors).toEqual([]);
});
