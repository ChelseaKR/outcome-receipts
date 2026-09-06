# v0.2.0 compatibility baseline

- Tag: `v0.2.0`
- Commit: `b8f5a27e48283e6b97add1841d1f8a110f760265`
- Release date: 2026-08-16
- Frozen paths:
  - `examples/housing-demo/report.toml`
  - `examples/housing-demo/services.csv`
  - `examples/housing-demo/receipts.json`

These files are byte-for-byte copies from the signed tag.

What the second release changed, and what it did not, matters more here than the
files themselves. `services.csv` and `receipts.json` are **byte-identical** to
the `v0.1.0` baseline in the sibling directory: the second tagged release
produced exactly the artifact the first one did. The only difference between the
two frozen specs is that this one declares its contract version explicitly —

```toml
schema_version = "1.0"
```

— where `v0.1.0`'s spec carried no `schema_version` key at all and was
interpreted as `1.0` by default.

So this directory is evidence for one specific claim, and not for others. It
shows that a spec which names its version and a spec which omits it are read the
same way by the current loader, and that the manifest a released implementation
wrote is still re-derivable field-for-field. It does **not** show that a changed
contract survives a release boundary, because no contract changed across this
boundary. Issue 65's remaining criteria need a release that actually moves one.

Do not regenerate this directory from `main`.
