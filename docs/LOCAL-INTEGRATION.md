# Disposable integrated rehearsal — 31 October 2026

Historical baseline: this record describes the first b2 rehearsal. The current b3
independently triggered, CLI-controlled/restored flow is documented in
[LOCAL-INTEGRATION-B3.md](LOCAL-INTEGRATION-B3.md). The reproduction script now
exercises that current contract; it does not recreate b2 byte-for-byte.

The earlier 259 CLI, 213 focused backend and 29 offline demo checks were component
validation. They did **not** establish integrated end-to-end acceptance.

The subsequent rehearsal used the actual installed CLI wheel, the real ASGI
application over loopback HTTP, fully migrated PostgreSQL 16 with a non-superuser
runtime role without BYPASSRLS, and real Prometheus 3.5. Synthetic OpenMetrics
history and a small continuously scraped synthetic exporter supplied measurements;
no provider adapter, CLI response, backend response or selector was mocked.

Only newly created, labelled, loopback-bound disposable containers with tmpfs data
were used. The project UUID was reproduced inside that empty isolated database;
it is not a readback of the existing project. Fixtures contain 1,200 test metadata
definitions and synthetic historical outcomes, not executed Banking tests.
Detection stayed enabled, automatic observation stayed disabled, and the local
fixture's influence flag alone changed after each preceding run completed.
No existing database, GCP simulator, scheduler, provider connection or cloud data
was accessed or altered.

| Actual fixture execution | Selected / library | Saved influence | Frozen comparison |
|---|---|---|---|
| Synchronous A | 103 / 1,200 | OFF | Unavailable, as expected when disabled |
| Synchronous B | 107 / 1,200 | ON | Complete |
| Asynchronous A | 103 / 1,200 | OFF | Unavailable, as expected when disabled |
| Asynchronous B | 107 / 1,200 | ON | Complete |

Both ON runs' backend classifications report baseline 103, actual 107, 1,200
eligible tests, four applied/retained promotions, four direct additions, zero
indirect additions and zero removals. Those are this controlled fixture's
observations, not a promised live result. The report takes these fields from
backend validation; A/B subtraction supplies no attribution.

Each selected export spans two pages, explanations span twelve, and mapping
details span nineteen. All selected JSON/CSV identities reconcile with persisted
selected rows. Each run has exactly one validated selection-context anchor,
whole-library mapping evidence including skipped tests, fourteen unmatched paths,
captured controls/fingerprints and evaluation provenance. The existing backend
matcher normalizes paths; the original changed-file artifact remains separate.

Async requests returned durable queued receipts and were polled by the real CLI.
Because the existing in-memory queue has no dispatcher loop, the harness explicitly
delivered those jobs to the actual authenticated internal worker HTTP endpoint.
Two wrong-organization deliveries returned 404; both legitimate deliveries
completed. This validates queue receipt, pending polling, tenant scope, canonical
worker execution and persistence. It does **not** validate Cloud Tasks transport.

`runs wait` recovered all four known runs. Async B was fully re-exported and
matched its original summary and selected identities. Persisted run counts stayed
unchanged during recovery; HTTP access logs contain exactly four selection requests
in the completed rehearsal, two per execution mode. Artifact verification and
report regeneration subsequently ran offline without submissions or evaluations.

The real Banking build script built the two affected allowlisted images, auth
and transaction, from sanitized current local implementation contexts. Source
provenance explicitly records the uncommitted overlay on base `9d70b81...`.
Actual Git range planning used a historical ancestor through that base; no test
commit was created and no hosted push/checkpoint was simulated as acceptance.
Images were not started or pushed. No selected functional tests or deployment ran.

## Defects found and corrected

Real PostgreSQL exposed loss of transaction-local tenant scope after async enqueue
commits, worker lifecycle commits and rollback. Existing scope restoration is now
used before subsequent reads/writes. The token-authenticated internal worker also
binds the supplied organization before its first RLS read. No scoring, detection,
schedule, budget or causal classification changed. Six targeted regression cases
plus affected existing lifecycle/worker checks passed: **62 tests** in total.

Visual inspection caught the formatter's hardcoded GCP telemetry description.
Reports now display saved source/dataset provenance, with an explicit synthetic
fixture qualification for sample mode. **30** offline demo/report tests passed.

Early harness attempts also exposed Windows OpenMetrics line endings, PostgreSQL
startup timing, UTF-8 BOM CSV decoding and backend log encoding differences.
These were harness corrections. The final log-decoding check was completed from
saved artifacts after the four executions; it did not cause a resubmission.

## Review evidence

- [Machine verification record](../../platform/docs/pipeline-demo-integrated-validation-20261031.json).
- [Sync offline HTML](../../_tools/integrated-rehearsal/attempt-8/sync/report/report.html),
  [Markdown](../../_tools/integrated-rehearsal/attempt-8/sync/report/report.md),
  [JSON](../../_tools/integrated-rehearsal/attempt-8/sync/report/report.json).
- [Async offline HTML](../../_tools/integrated-rehearsal/attempt-8/async/report/report.html),
  [Markdown](../../_tools/integrated-rehearsal/attempt-8/async/report/report.md),
  [JSON](../../_tools/integrated-rehearsal/attempt-8/async/report/report.json).
- [Complete async ON CSV](../../_tools/integrated-rehearsal/attempt-8/async/on/bundle/selected-tests.csv)
  and [JSON](../../_tools/integrated-rehearsal/attempt-8/async/on/bundle/selected-tests.json).

Each report directory has an integrity manifest. Each A/B bundle contains a
separate file-hash manifest, complete exports and focused sanitized evidence.
These generated local outputs are outside source worktrees. Do not distribute
the broad harness working directory; allowlist report/bundle files. Example.invalid
saved-result links intentionally do not point to a deployed UI. Screenshots were
rendered offline with an isolated headless browser profile.

## Windows CMD reproduction

Use the three sibling implementation worktrees and the validated Python 3.11
environment with backend dependencies, plus the separate clean CLI wheel install
at `_tools\clean-cli`. Docker Desktop's Linux engine must be available. The harness
does not read repository environment files: it explicitly runs in staging with
synthetic local configuration. It creates a fresh database by default, applies
all migrations and refuses to seed a nonempty supplied disposable database.

```cmd
cd /d C:\Users\massi\QCE\quantikmind-platform\implementation
_tools\validation\Scripts\python.exe demo\tools\local_integration.py --output _tools\integrated-rehearsal\fresh-local-run
```

The output directory must not exist. This command makes exactly four local fixture
submissions and performs image builds; it is not an offline report-only command.
Successful/finally cleanup stops the task-created backend, exporter and containers.
Synthetic CLI credentials are excluded from artifacts and removed afterward.
On an initialization failure, inspect the new output's container ID/label before
removing that specific disposable container. Never clean other databases/containers.

The following command starts no services and never submits selection/evaluation:

```cmd
_tools\validation\Scripts\python.exe demo\tools\local_integration.py --verify-existing --output _tools\integrated-rehearsal\attempt-8
start "" _tools\integrated-rehearsal\attempt-8\async\report\report.html
```

All fixture services from this rehearsal were stopped/removed. Hosted GitHub
permissions, environments/checkpoints, immutable publication pins, deployed backend
revision, real provider reliability and actual project readback remain separate
publication/live acceptance gates. Nothing was staged, committed, pushed or opened
as a PR, and no repository rename occurred.
