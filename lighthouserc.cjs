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
    assert: {
      assertions: {
        "categories:accessibility": ["error", { minScore: 0.9 }],
      },
    },
    upload: {
      target: "filesystem",
      outputDir: "./.lighthouseci",
    },
  },
};
