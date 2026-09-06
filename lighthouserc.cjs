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
        // Rule-based and deterministic: the same markup scores the same
        // everywhere, so this one is a real gate on a real property.
        "categories:accessibility": ["error", { minScore: 0.9 }],

        // `categories:performance` is deliberately NOT asserted here.
        //
        // It is a simulated-throttling timing score of whatever machine ran
        // Lighthouse. On byte-identical input this trace scored 1.00 on a local
        // macOS checkout, 0.99 on one GitHub-hosted runner, and 0.87 on
        // another -- 0.87 in the `verify` job of run 33591194873 while the
        // `accessibility` job of that same run, on that same commit, passed the
        // identical command; a re-run of the same commit four days later passed
        // both. A 0.90 floor sits inside that spread, so it was failing on
        // runner contention rather than on anything a diff had done or could
        // undo, and lowering the floor would only reschedule the same failure.
        //
        // What replaces it is the set of budgets below, which are byte counts
        // rather than timings and measured identically on every run on every
        // machine tried. For a static document with no scripts, no stylesheets
        // and no third-party requests, its transferred weight is what "is this
        // fast for a funder" actually reduces to. The score is still measured,
        // still recorded in perf/baseline.json, and still printed by `make
        // perf`; it is just not something the build fails on.

        // This repository's value, and tighter than the standard's 204800-byte
        // critical-path budget on purpose. The trace is a static document a
        // funder opens from a file or an email attachment; the project ships no
        // web application and no network ingress, so the honest budget for
        // script bytes in a published artifact is none at all. At 204800 the
        // assertion could not fail before someone shipped 200 KB of JavaScript
        // into a funder's browser.
        "resource-summary:script:size": ["error", { maxNumericValue: 0 }],
        // The same argument for the other two kinds of subresource the trace
        // claims not to have. Zero is assertable here precisely because the
        // document is self-contained; a stylesheet or a third-party request
        // appearing at all is the regression, not its size.
        "resource-summary:stylesheet:size": ["error", { maxNumericValue: 0 }],
        "resource-summary:third-party:size": ["error", { maxNumericValue: 0 }],
        // The absolute ceiling on the whole artifact, standing where the 0.90
        // performance floor used to. 2469 bytes measured; 51200 is the ceiling
        // an emailable document should never approach, so this fails on a page
        // that has genuinely become heavy while leaving normal edits to the
        // report template alone. The tight half of the rule is the 10% band
        // around `total_kb_gzip` in perf/baseline.json.
        "resource-summary:total:size": ["error", { maxNumericValue: 51200 }],
      },
    },
    upload: {
      target: "filesystem",
      outputDir: "./.lighthouseci",
    },
  },
};
