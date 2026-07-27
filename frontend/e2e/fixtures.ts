import { expect, test as base, type ConsoleMessage, type Page } from "@playwright/test";

type BrowserViolation = {
  kind: "console" | "pageerror" | "unhandled-api";
  message: string;
};

function attachBrowserErrorGuards(page: Page, violations: BrowserViolation[]): void {
  page.on("console", (message: ConsoleMessage) => {
    const browserResourceFailure =
      message.type() === "error" &&
      message.text().startsWith("Failed to load resource: the server responded with a status of");
    if (message.type() === "error" && !browserResourceFailure) {
      violations.push({ kind: "console", message: message.text() });
    }
  });
  page.on("pageerror", (error: Error) => {
    violations.push({ kind: "pageerror", message: error.message });
  });
}

export const test = base.extend({
  page: async ({ page }, use) => {
    const violations: BrowserViolation[] = [];
    attachBrowserErrorGuards(page, violations);
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      violations.push({
        kind: "unhandled-api",
        message: `${request.method()} ${new URL(request.url()).pathname}`
      });
      await route.fulfill({
        status: 599,
        contentType: "application/json",
        body: JSON.stringify({
          code: "UNHANDLED_E2E_API",
          message: "E2E test did not register an API mock."
        })
      });
    });

    await use(page);

    if (violations.length > 0) {
      throw new Error(
        `Strict E2E guard found browser violations:\n${violations
          .map((item) => `- [${item.kind}] ${item.message}`)
          .join("\n")}`
      );
    }
  }
});

export { expect };
