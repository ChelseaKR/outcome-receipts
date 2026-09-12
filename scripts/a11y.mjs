import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import path from "node:path";

// Every HTML surface this project publishes, checked with the same four gates.
// The list is here rather than inside the loop because a page that is rendered
// but not listed is a page with no accessibility verdict at all, and an absent
// verdict reads exactly like a passing one in CI.
const PAGES = [
  { label: "trace view", file: "out/a11y/trace.html" },
  { label: "portfolio index", file: "out/a11y-portfolio/index.html" },
];

async function check(page, { label, file }) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(pathToFileURL(path.resolve(file)).href);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const blocking = result.violations.filter((violation) =>
    ["critical", "serious", "moderate"].includes(violation.impact ?? ""),
  );
  if (blocking.length) {
    throw new Error(`${label}: axe violations:\n${JSON.stringify(blocking, null, 2)}`);
  }

  await page.setViewportSize({ width: 320, height: 256 });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  if (overflow) {
    throw new Error(`${label} overflows horizontally at 320 CSS pixels`);
  }

  await page.emulateMedia({ reducedMotion: "reduce" });
  const moving = await page.locator("*").evaluateAll((nodes) =>
    nodes.some((node) => {
      const style = getComputedStyle(node);
      return style.animationDuration !== "0s" || style.transitionDuration !== "0s";
    }),
  );
  if (moving) {
    throw new Error(`${label} retains animation or transition under reduced motion`);
  }
  // The zero-JavaScript budget, checked on the markup rather than on the wire.
  //
  // `resource-summary:script:size` in lighthouserc.cjs is a budget on script
  // *requests*, so it only ever sees a `src=` script. An inline `<script>` is
  // not a network request: injecting 1216 bytes of inline JavaScript into this
  // trace left that row reading 0 bytes and moved the whole document's transfer
  // size by 26 bytes after compression, so neither the Lighthouse assertion nor
  // the 10% band in perf/baseline.json could see it. The budget the README and
  // docs/ROADMAP.md publish is "the trace ships no JavaScript"; this is the
  // check that is actually true of that claim, and it is a DOM query, so it
  // costs nothing and cannot vary between machines.
  const scripts = await page.locator("script").count();
  if (scripts) {
    throw new Error(
      `${label} ships ${scripts} <script> element(s); the published budget is zero ` +
        "JavaScript, inline or external",
    );
  }
}

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  for (const target of PAGES) {
    await check(page, target);
  }
  console.log(
    `axe WCAG 2.2 AA, 320px reflow, reduced-motion, and zero-JavaScript checks: pass (${PAGES.length} page(s))`,
  );
} finally {
  await browser.close();
}
