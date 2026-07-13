import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import path from "node:path";

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.goto(pathToFileURL(path.resolve("out/a11y/trace.html")).href);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const blocking = result.violations.filter((violation) =>
    ["critical", "serious", "moderate"].includes(violation.impact ?? ""),
  );
  if (blocking.length) {
    throw new Error(`axe violations:\n${JSON.stringify(blocking, null, 2)}`);
  }

  await page.setViewportSize({ width: 320, height: 256 });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  if (overflow) {
    throw new Error("trace view overflows horizontally at 320 CSS pixels");
  }

  await page.emulateMedia({ reducedMotion: "reduce" });
  const moving = await page.locator("*").evaluateAll((nodes) =>
    nodes.some((node) => {
      const style = getComputedStyle(node);
      return style.animationDuration !== "0s" || style.transitionDuration !== "0s";
    }),
  );
  if (moving) {
    throw new Error("trace view retains animation or transition under reduced motion");
  }
  console.log("axe WCAG 2.2 AA, 320px reflow, and reduced-motion checks: pass");
} finally {
  await browser.close();
}
