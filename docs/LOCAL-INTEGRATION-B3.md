# Actual local b3 integration: independent executions and CLI controls

31 October 2026. This extends the preserved earlier baseline. No CLI/backend
response or provider adapter was mocked in the integrated rehearsal. Actual CLI
0.1.0b3, ASGI loopback HTTP, fully migrated disposable PostgreSQL and real local
Prometheus were used. Measurement history/exporter and the 1,200 test definitions/
historical outcomes are explicitly synthetic. No existing development/production
database, project, cloud simulator, scheduler, connection or data was touched.

Four cases completed: sync A/OFF, sync B/ON, async A/OFF, async B/ON. Each had its
own real auth/transaction image build, separate actual CLI invocation, complete
independent HTML/Markdown/JSON and selected CSV/JSON export, verified saved mode,
full context/changes and verified original-state restoration. A's report and safe
session artifact were generated before B started. B validated that actual sealed
A source/input/export artifact and reused the same source/base/files/services.
The local GitHub run envelope was an explicitly synthetic metadata fixture;
authenticated hosted artifact retrieval/approvals remain for operator acceptance.
No script from recovered data was executed.

Both execution modes selected 103/1,200 for OFF and 107/1,200 for ON. ON's actual
backend-validated frozen comparison reported baseline 103, four direct additions,
zero indirect additions/removals. These are fixture observations, not a live result
promise. Complete exports used two selected pages, twelve explanation pages and
nineteen mapping pages, with identities reconciled against persisted rows. Each
run had one validated context anchor and fourteen mapping gaps, including skipped
test matches. API comparisons/classifications were used unchanged.

Separate machine keys exercised real authorization: selection/results key writes
were denied; a narrow `near_miss:influence` key could edit only the exact project;
cross-project reads failed. Two concurrent same-revision writes produced exactly
one success and one 409 conflict in each execution mode. Detection, observation,
cadence, rules, inventory/provider and unrelated settings were preserved. Initial
fixture influence differed between the sync/async pairs so both restoration
directions were exercised. No owner edit occurred inside an A/B case.

Async used real queued receipts and CLI polling, then actual authenticated worker
HTTP delivery driven locally because in_memory has no dispatcher. Wrong-org worker
delivery was denied. The actual CLI refused restoration while each async run was
queued (exit 7), then restored only after terminal completion. Known-run recovery
and full async B re-export did not submit a selection. Exactly four selection HTTP
requests occurred in the completed rehearsal. Cloud Tasks transport is not validated.

Affected validation also passed 264 CLI checks, 247 focused backend checks and 35
offline demo/provenance/report checks. Counts overlap historical runs; do not add
them. Existing Click/Starlette deprecation warnings remain. Workflow caller/callee
contracts and actionlint passed with the narrowly documented queue-key exception.
Banking functional tests were not selected/executed; implementation unit tests and
image syntax compilation are separate checks.

Local actual artifacts are under
`implementation/_tools/integrated-rehearsal/independent-b3-final` (with the final
defensive-state-parser build repeated under `publication-b3-final`):
`sync/off/report`, `sync/on/report`, corresponding async directories, each case's
`publication/session.json`, complete `bundle`, restoration and CAS/pending receipts,
and paired reports under each mode's `report`. They remain local review artifacts;
the Platform verification record contains their integrity/provenance summary.
Portable illustrative [A](../samples/synthetic/execution-a-report/report.html),
[B](../samples/synthetic/execution-b-report/report.html) and
[paired](../samples/synthetic/report.html) samples are clearly labelled simulated
synthetic fixtures and are not substituted for the actual rehearsal.

Windows CMD reproduction (three sibling implementation worktrees and the isolated
validated Python 3.11/backend environment plus clean b3 wheel install are required):

```cmd
cd /d C:\Users\massi\QCE\quantikmind-platform\implementation
_tools\validation\Scripts\python.exe demo\tools\local_integration.py --output _tools\integrated-rehearsal\new-b3-rehearsal
```

The output directory must be new. This explicitly authorized fixture command
creates/migrates new labelled tmpfs services and runs four local cases/builds,
not hosted demo workflows. Cleanup stops only its own services and removes
synthetic credentials. A startup failure requires inspecting the output's own
container identity/label before removing that specific container.

Offline inspection/regeneration performs no service/API/submission operation:

```cmd
_tools\validation\Scripts\python.exe demo\tools\local_integration.py --verify-existing --output _tools\integrated-rehearsal\independent-b3-final
```

Hosted CI validates implementation with fixtures; it is not hosted live-provider
acceptance. The operator alone will run the published Banking demo. See RUNBOOK.md
for the complete UI-optional runtime and cancellation/concurrent-edit recovery.

The final `publication-safe-cas-final` rehearsal also exercised actual CLI
restoration before a prepared control request had arrived. A conditional no-op
cancellation barrier advanced the revision; the deliberately delayed original
request was rejected with 409. This adds no selection submission and prevents a
late control write from landing after successful cleanup.
