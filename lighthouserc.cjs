module.exports = {
  ci: {
    collect: {
      staticDistDir: "./out/a11y",
      url: ["http://localhost/trace.html"],
      numberOfRuns: 1,
      // Chrome's Linux sandbox cannot initialize inside GitHub's isolated runner.
      // The audit opens only this job's generated static artifact.
      settings: { chromeFlags: "--no-sandbox" },
    },
    // One Lighthouse config for the repository, asserting the accessibility
    // score and the performance budgets from the same run. The portfolio
    // Performance standard requires exactly one, so the accessibility gate and
    // the performance gate can never drift to different numbers or a different
    // page. The regression half of the rule (no metric more than 10% worse than
    // perf/baseline.json) is scripts/check_perf_baseline.py, which reads this
    // run's own report; see perf/README.md.
    assert: {
      assertions: {
        "categories:accessibility": ["error", { minScore: 0.9 }],
        // The standard's value.
        "categories:performance": ["error", { minScore: 0.9 }],
        // This repository's value, and tighter than the standard's 204800-byte
        // critical-path budget on purpose. The trace is a static document a
        // funder opens from a file or an email attachment; the project ships no
        // web application and no network ingress, so the honest budget for
        // script bytes in a published artifact is none at all. At 204800 the
        // assertion could not fail before someone shipped 200 KB of JavaScript
        // into a funder's browser.
        "resource-summary:script:size": ["error", { maxNumericValue: 0 }],
      },
    },
    upload: {
      target: "filesystem",
      outputDir: "./.lighthouseci",
    },
  },
};
