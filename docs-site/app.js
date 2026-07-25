const body = document.body;
const navToggle = document.querySelector(".nav-toggle");
const navBackdrop = document.querySelector(".nav-backdrop");
const navLinks = [...document.querySelectorAll(".doc-nav a")];
const sections = navLinks
  .map((link) => document.querySelector(link.getAttribute("href")))
  .filter(Boolean);

function setNavigationOpen(open) {
  body.classList.toggle("nav-open", open);
  navToggle?.setAttribute("aria-expanded", String(open));
  navToggle?.setAttribute("aria-label", open ? "关闭文档导航" : "打开文档导航");
}

navToggle?.addEventListener("click", () => {
  setNavigationOpen(!body.classList.contains("nav-open"));
});

navBackdrop?.addEventListener("click", () => setNavigationOpen(false));
navLinks.forEach((link) => {
  link.addEventListener("click", () => setNavigationOpen(false));
});

const sectionObserver = new IntersectionObserver(
  (entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort(
        (left, right) => right.intersectionRatio - left.intersectionRatio,
      )[0];
    if (!visible) return;

    navLinks.forEach((link) => {
      link.classList.toggle(
        "is-active",
        link.getAttribute("href") === `#${visible.target.id}`,
      );
    });
  },
  { rootMargin: "-20% 0px -65% 0px", threshold: [0, 0.2, 0.6] },
);

sections.forEach((section) => sectionObserver.observe(section));

function updateScrollProgress() {
  const scrollable = document.documentElement.scrollHeight - window.innerHeight;
  const progress =
    scrollable > 0 ? Math.min(window.scrollY / scrollable, 1) : 0;
  const indicator = document.querySelector(".scroll-progress span");
  if (indicator) indicator.style.width = `${progress * 100}%`;
}

window.addEventListener("scroll", updateScrollProgress, { passive: true });
updateScrollProgress();

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  }
}

document
  .querySelectorAll(".code-card button, .inline-command button")
  .forEach((button) => {
    button.addEventListener("click", async () => {
      const container = button.closest(".code-card, .inline-command");
      const command = container?.querySelector("code")?.textContent ?? "";
      const copied = await copyText(command);
      const original = button.textContent;
      button.textContent = copied ? "已复制" : "复制失败";
      window.setTimeout(() => {
        button.textContent = original;
      }, 1400);
    });
  });

const checklist = document.querySelector("[data-checklist]");
const checklistItems = checklist
  ? [...checklist.querySelectorAll('input[type="checkbox"]')]
  : [];
const meterFill = document.querySelector(".release-meter > div span");
const meterCount = document.querySelector(".release-meter p strong");
const checklistStorageKey = "interview-arena-release-checklist";

function updateChecklist() {
  const checked = checklistItems.filter((item) => item.checked).length;
  const total = checklistItems.length;
  if (meterFill)
    meterFill.style.width = `${total ? (checked / total) * 100 : 0}%`;
  if (meterCount) meterCount.textContent = String(checked);
  localStorage.setItem(
    checklistStorageKey,
    JSON.stringify(checklistItems.map((item) => item.checked)),
  );
}

try {
  const saved = JSON.parse(localStorage.getItem(checklistStorageKey) ?? "[]");
  checklistItems.forEach((item, index) => {
    item.checked = Boolean(saved[index]);
  });
} catch {
  localStorage.removeItem(checklistStorageKey);
}

checklistItems.forEach((item) =>
  item.addEventListener("change", updateChecklist),
);
updateChecklist();
