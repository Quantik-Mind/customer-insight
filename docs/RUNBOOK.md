# Operator runbook: independent A and B, no Quantik Mind UI

This is the current CLI b3 contract. Earlier UI-operated OFF/ON procedures are
superseded. You personally trigger/present the demo. A never starts, schedules or
dispatches B. All UI actions below are **GitHub** actions. Quantik Mind links are
optional authenticated presentation drill-down; no browser session/JWT is needed.

Publication/rename/deployment/access changes and live executions remain separate
operator actions. Do not execute these commands before their prerequisites pass.
Follow [PUBLICATION.md](PUBLICATION.md) first. Review PR/check links and the
publication manifest in the Platform handoff; preserve the original modified
Banking checkout. Do not use it for builds or the presenter commit.

## Required state

- Existing project `90e48503-115d-4b34-be95-9f2f1b62767d`, Continuous Resiliance;
  existing synthetic library/history, exact inventory/provider and GCP simulator.
- Accepted Platform backend with controls, saved context/changes and async fixes.
- Accepted CLI 0.1.0b3 wheel, immutable source commit, numeric release-asset URL,
  verified SHA-256 and matching hash-locked requirements.
- Same existing Customer Insight repository renamed to quantikmind-pipeline-demo;
  accepted central workflow/script SHA, generated pinned Banking caller merged
  into main, and the approved `demo/pipeline` branch containing that workflow.
- GitHub Actions access plus Banking `qm-demo-off`/`qm-demo-on` environments and
  approved operator reviewers/ref policy. Named environments alone are not a
  protection. Banking's protection API currently reports a plan-upgrade requirement;
  an owner must resolve plan support before claiming those protections exist.
- Separate project keys in Banking GitHub secrets: `QMIND_API_KEY` with
  `selection:run` and `results:read`; `QMIND_INFLUENCE_API_KEY` with ONLY
  `near_miss:influence`. A credential owner provisions that explicit opt-in scope
  through the existing authorized service-account API; never give the pipeline
  an admin key or personal JWT. No Quantik Mind UI is required by the runtime.
- `DEMO_READ_TOKEN`: narrowly scoped private Platform release-asset/central source
  read. No GitHub write/dispatch/cloud/registry privilege in the runtime.
- Variables `QMIND_API_URL` (API origin, no `/api/v1` suffix), optional
  `QMIND_FRONTEND_URL` (verified HTTPS origin, may be blank),
  `QMIND_CLI_WHEEL_URL` and `QMIND_CLI_SHA256`.

In GitHub: Banking → Settings → Secrets and variables → Actions, enter approved
values without circulating them. Settings → Environments supplies the two named
operator gates. Do not change provider credentials, detection, cadence, rules,
budgets, data, scheduler or simulator for the presentation.

## Windows CMD tooling and read-only checks

Use Git, Python 3.11, and GitHub CLI (`gh`). If necessary, an operator can install
GitHub CLI with `winget install --id GitHub.cli --exact`, open a new CMD and run
`gh auth login --hostname github.com --git-protocol https --web` (GitHub login).
Use the released wheel and lock, not a floating Git branch. For local inspection:

```cmd
set "QUANTIKMIND_TELEMETRY_DISABLED=1"
py -3.11 -m venv C:\QMindDemo\venv
call C:\QMindDemo\venv\Scripts\activate.bat
certutil -hashfile C:\QMindDemo\quantikmind_cli-0.1.0b3-py3-none-any.whl SHA256
python -m pip install --require-hashes -r C:\QMindDemo\requirements-ci.lock
python -m pip install --no-deps C:\QMindDemo\quantikmind_cli-0.1.0b3-py3-none-any.whl
qmind --version
qmind near-miss influence --help
```

Compare the printed hash with the approved release manifest; printing it alone
does not verify integrity. A credential owner supplies the project selection key
and influence key through environment variables, without committing/uploading them:

```cmd
set "QMIND_API_URL=VERIFIED_API_ORIGIN"
set "QMIND_API_KEY=APPROVED_PROJECT_SELECTION_KEY"
set "QMIND_INFLUENCE_API_KEY=APPROVED_PROJECT_INFLUENCE_ONLY_KEY"
cd /d C:\QMindDemo
qmind init --project-id 90e48503-115d-4b34-be95-9f2f1b62767d --framework pytest --non-interactive
qmind near-miss controls
qmind near-miss status
```

Uppercase values above are explicit operator substitutions. These reads verify
project/auth/current controls and stored observation history. No evaluate/select
command is part of this setup. Do not enable detection or manufacture evidence.
The hosted pipeline captures/restores influence itself; no manual OFF/ON setting
edit is required. Reserve a presentation window and avoid other settings editors
or manual selections; workflow concurrency is not a global application lease.

## Execution A: one real Banking commit

Use a clean presenter worktree created from accepted Banking main, not the original
modified Banking worktree. The following is a later operator preparation example;
stop if paths/branch already exist and inspect them rather than overwrite/reset:

```cmd
git -C C:\Users\massi\QCE\banking-app fetch origin
git -C C:\Users\massi\QCE\banking-app worktree add -b demo/pipeline C:\QMindDemo\banking-presenter origin/main
git -C C:\QMindDemo\banking-presenter status --short
```

Coordinate the branch's first publication before the presentation. A baseline-only
new branch resolves an empty diff and skips selection. A real reviewed change in
an existing mapped, allowlisted service supplies the presentation commit. Inspect
and stage that exact file only, commit and push `demo/pipeline`. This is the live
demo trigger; implementation preparation does not create/push that application
change. A handles multi-commit ranges, renames and deletions and skips empty diffs.

In GitHub Banking → Actions → **Quantik Mind independent pipeline executions**,
open the push run. Approve the `qm-demo-off` GitHub gate after verifying source
and real build. The pipeline captures current controls, conditionally sets OFF,
selects once through the CLI, waits, verifies saved OFF mode, exports completely,
restores the original influence and publishes **qmind-execution-A**. It then ends.

Download that artifact and open `report/report.html` locally. Read Actions summary,
`report/report.md`, JSON/integrity manifest and complete CSV/JSON in
`execution/bundle`. Confirm original influence restoration says `restored`, saved
mode is OFF, and export is complete. A remains complete/useful if B is never run.
Record the **Actions run ID**, separate from the Quantik Mind selection UUID and
artifact session UUID. Do not use GitHub's Re-run jobs for selections.

A controlled manual A alternative is available on the same branch:

```cmd
gh workflow run quantikmind-pipeline-demo.yml --repo Quantik-Mind/banking-app --ref demo/pipeline -f execution=A -f base_sha=EXACT_ANCESTOR_SHA -f head_sha=EXACT_DEMO_BRANCH_HEAD_SHA
```

## Execution B: a new explicit trigger, no application code change

Only after reviewing successful/restored A, record its Actions ID:

```cmd
set "A_ACTIONS_RUN_ID=ACTUAL_SUCCESSFUL_A_ACTIONS_ID"
gh workflow run quantikmind-pipeline-demo.yml --repo Quantik-Mind/banking-app --ref demo/pipeline -f execution=B -f a_run_id=%A_ACTIONS_RUN_ID%
```

Equivalent GitHub UI: Actions → workflow → Run workflow → choose `demo/pipeline`,
execution **B**, A run ID; leave base/head empty. Do not make another application
change. B validates A's repository/workflow/branch/event/attempt/success, immutable
artifact digest, session seal, source/base/files/services, CLI/tooling pins,
complete OFF export and restoration. It rebuilds A's exact source and service set.
No script from A's artifact is executed. An expired/mismatched/partial A is rejected.

Approve the `qm-demo-on` GitHub gate. B uses the narrow CLI control, reads existing
evidence, selects once, verifies saved ON, exports and restores. Download
**qmind-execution-B** for the independent B report and **qmind-paired-report** for
A/B. Between-run counts are descriptive; only B's backend frozen comparison
supports attribution. Zero additions is valid. Missing evidence stays unavailable.

Both executions require real affected-service image assembly. Images are not
started, pushed or deployed; selected Banking tests are not executed. A build does
not establish application startup/functional correctness. Library/workload data
are synthetic; pipeline/CLI/backend/provider calls are real. Count reduction is
not measured time/cost savings or incident prevention. Do not loop for a favorable
outcome or alter project/simulator settings to produce one.

## Failure, cancellation and restoration recovery

Inspect/download sanitized receipts, `execution/influence-state.json`,
`execution/restoration.json` and the failure report. A pending or uncertain
submission holds restoration to avoid changing influence before worker execution.
With a known selection UUID, use only saved reads:

```cmd
qmind runs wait SAVED_SELECTION_UUID --timeout-seconds 600 --json
qmind runs export SAVED_SELECTION_UUID --output-dir C:\QMindDemo\recovered-export
qmind near-miss controls
qmind near-miss influence restore --state-file C:\QMindDemo\influence-state.json --run-id SAVED_SELECTION_UUID
```

If the response/run ID was lost, reconcile `qmind runs list --json` and the run
timestamps before another request. Never blindly repeat `subset` or rerun a
workflow. Concurrent edits cause restoration refusal; preserve evidence and
coordinate with that editor. Do not fetch a fresh revision to overwrite them.

Runner cancellation may prevent `finally`/artifact upload. The backend retains an
intact temporary operation's original influence for CLI-only recovery. After
reconciling a terminal run:

```cmd
qmind near-miss controls
qmind near-miss influence recover --state-file C:\QMindDemo\recovered-influence.json --run-id TERMINAL_SELECTION_UUID
```

Only if reconciliation confirms **no selection was submitted**, substitute
`--confirmed-no-submission` for `--run-id`. This is not appropriate for unknown
outcomes. If the operation lineage is no longer intact, recovery refuses and
requires explicit editor reconciliation, not an unconditional settings write.

Offline regeneration never selects/evaluates:

```cmd
python -m demo.report --execution A --a C:\QMindDemo\A\execution\bundle --changes C:\QMindDemo\A\source-build\changes.json --build C:\QMindDemo\A\source-build\build.json --output C:\QMindDemo\A-regenerated
```

The local disposable integrated reproduction is described in LOCAL-INTEGRATION.md.
Opening a report requires no API connection. Do not upload credential/config
directories or distribute the broad working directory; use the packaged artifacts.
