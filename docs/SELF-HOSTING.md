# Container self-hosting

The container packages the same offline CLI as the Python installation. It is
not a web service and opens no listening port. Source CSVs and outputs stay in a
directory the operator bind-mounts into `/workspace`.

## One-command demo

With Docker running from the repository root:

```sh
make container-demo
```

The target builds the digest-pinned image, disables network access, drops Linux
capabilities, uses a read-only root filesystem, runs as the host user, and writes
the synthetic demo to `out/container/`.

To build and smoke-test without running a report:

```sh
make container-smoke
```

For an organization-owned spec and CSV stored under the current directory:

```sh
mkdir -p out/production
docker run --rm --read-only --network none --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" \
  outcome-receipts:local run \
  --config path/to/report.toml \
  --out out/production \
  --ledger out/production/export-ledger.jsonl \
  --approved-by "Reviewer name"
```

The mount should contain only the input and destination needed for that run.
Do not mount credential directories, unrelated client files, or a broad home
directory. Keep the network disabled for the deterministic path.

## Image and update policy

The Dockerfile pins the official Python and uv image indexes by SHA-256 digest.
CI builds the image, starts the CLI under the locked-down runtime options, and
fails on HIGH or CRITICAL operating-system or library findings reported by
the digest-pinned Trivy scanner. `make verify` and CI both invoke the same
`container-verify` target. A dependency update changes the human-readable tag
and digest together. The scan reads an ephemeral image archive; the scanner does
not receive the Docker control socket.

The default image contains no Bedrock optional dependency. Cloud drafting
therefore remains fused off in the self-host path. An organization that creates
a cloud-enabled derivative owns the provider authorization, retention review,
image scan, and explicit CLI opt-in described in
[`drafting.md`](drafting.md).

Outputs are ordinary files. Backup and recovery follow
[`OPERATIONS.md`](OPERATIONS.md): keep the spec, source export, report bundle,
ledger, and optional signing key together, then run the verification commands
after recovery.
