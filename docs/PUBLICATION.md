# Coordinated publication and rename — independent CLI-controlled A/B

This is a prepared operator sequence, not authorization to merge, rename, release,
deploy or configure GitHub. Implementation PRs target each repository's main on
the requested isolated branches. Logical review groups/commits preserve backend,
CLI, Banking build/caller and central reporting boundaries. Demo triggers remain
inert until a later generated-caller PR is reviewed and accepted.

## Verified identities and remaining setup gates

Authenticated GitHub inspection confirms the existing repository IDs:

| Repository today | Stable ID | Visibility / default |
|---|---|---|
| Quantik-Mind/quantikmind-platform | 1111326907 | private / main |
| Quantik-Mind/banking-app | 1242804493 | private / main |
| Quantik-Mind/customer-insight | 1147764462 | public / main |

The authenticated account has repository administration/push access. Actions are
enabled, with allowed_actions=all in inspected repositories. Customer Insight's
private-reuse policy endpoint returns 422 because it is public; private reuse
configuration is not currently applicable. If visibility changes, explicitly allow
Banking and verify least-privilege private script access.

Banking currently has **zero environments**. Its branch-protection endpoint returns
403: plan upgrade is required. Required reviewer/ref protections must be established
by an owner under a supported plan before claiming they exist. No settings, secrets,
environments, access policies or repository identity have been changed here.

Organization repository enumeration succeeded. Organization code search for the
old name returned `incomplete_results=true`; this is not a complete consumer
inventory. Before rename, an owner must reconcile all current action/workflow
consumers, links/docs, webhooks/apps, packages and external integrations. Current
metadata reports no Pages site for Customer Insight. Preserve legacy examples and
never dispatch its direct-API workflow during publication.

## Exact order and acceptance gates

1. Review all main-targeting implementation PRs and their CI. Accept Platform
   lifecycle, saved evidence, narrow controls and CLI changes together before
   runtime use. Resolve conflicts normally; preserve unrelated work. Do not merge
   via this preparation task. Record the accepted **full Platform main SHA**.
2. Under separate release authorization, run the existing **Build Quantik Mind CLI
   Packages** workflow at that accepted Platform ref (not a floating feature head).
   It builds CLI **0.1.0b3**. Inspect clean install/tests and the source/asset integrity
   manifest. Publishing a release/asset is a separate operator action; the build
   workflow's artifacts alone are not a numeric release-asset URL. Record the real
   wheel asset ID, SHA-256, lock hash and source SHA. Never publish a local
   uncommitted wheel as if its base commit contained these changes.

   Exact Windows CMD example after approval (substitute the accepted SHA and the
   successful packaging Actions run ID; stop if the destination/tag already exists):

   ```cmd
   set "PLATFORM_SHA=ACTUAL_ACCEPTED_PLATFORM_SHA"
   set "PACKAGE_RUN_ID=SUCCESSFUL_PACKAGING_ACTIONS_RUN_ID"
   gh run download %PACKAGE_RUN_ID% --repo Quantik-Mind/quantikmind-platform --name quantikmind-cli-python-package --dir C:\QMindDemo\release-b3
   type C:\QMindDemo\release-b3\release-manifest.json
   certutil -hashfile C:\QMindDemo\release-b3\quantikmind_cli-0.1.0b3-py3-none-any.whl SHA256
   ```

   Compare source SHA, wheel hash and lock hash with the approved build; perform
   the clean installation checks in RUNBOOK.md. In GitHub Platform → Releases,
   check that `cli-0.1.0b3` is unused, then draft a prerelease using a new tag
   **cli-0.1.0b3** targeting the exact accepted Platform commit. Attach the verified
   wheel, `release-manifest.json` and `requirements-ci.lock`, record the source SHA
   in release notes, review and publish only under release authorization. This
   explicit `cli-` tag avoids the separate `v*` automatic packaging/release trigger.
   Do not replace assets after recording their integrity pins. Obtain real asset
   IDs and immutable API URLs with:

   ```cmd
   gh api repos/Quantik-Mind/quantikmind-platform/releases/tags/cli-0.1.0b3 --jq ".assets[] | {name: .name, id: .id, url: .url}"
   ```

   Record the wheel's numeric API URL and verified SHA in the later Banking
   variables; the CLI source pin remains the full accepted Platform commit.
3. Release required Platform backend changes through the existing normal backend
   deployment process, separately authorized. GitHub → Platform Actions →
   **Deploy Production Release**, choose the accepted main ref; set
   `deploy_backend=true`, `run_migrations=false` (no new schema migration),
   `deploy_frontend=false`, `run_backend_smoke_tests=false`,
   `run_frontend_smoke_tests=false`. Review normal release approvals/image tag.
   The default deployment health check remains active. Avoid authenticated smoke
   suites that might perform additional application writes. This task does not
   dispatch/deploy. Record previous and resulting image/revision/traffic. Verify
   every actual API/worker service running this code; if workers are separate,
   their release topology must be identified rather than assumed identical.
   Preserve runtime mode, provider connections, observer/scheduler configuration,
   database data and simulator. No frontend release is required by this demo.
4. After consumer inventory and explicit approval, rename the **same** repository:
   GitHub Customer Insight → Settings → General → Repository name →
   `quantikmind-pipeline-demo` → Rename. Confirm stable ID **1147764462**, history,
   branches, issues, PRs and workflows remain. Do not create a replacement.
5. Update clone remotes and consumers explicitly; do not rely on workflow/action
   redirects. Remote config is shared across worktrees:

   ```cmd
   git -C C:\Users\massi\QCE\customer-insight remote set-url origin https://github.com/Quantik-Mind/quantikmind-pipeline-demo.git
   git -C C:\Users\massi\QCE\customer-insight remote -v
   git -C C:\Users\massi\QCE\customer-insight worktree list
   ```

   Update explicit `uses`, checkout repository fields, badges/docs/webhooks and
   external consumers. Review every actual consumer; public Git redirects are not
   an action/workflow reference migration. Any validation archive reference by
   stable numeric repository ID remains bound to the same repository/history.
6. Accept the central implementation PR at the renamed repository and record its
   actual **full accepted central SHA**, containing the reusable workflow, scripts
   and CLI lock. Verify every external action pin and the accepted CLI source/
   wheel/lock relationship. The legacy workflow remains manual-only and independent.
7. Accept Banking build prerequisites from its implementation PR. The caller is
   intentionally still `demo/pipeline-caller.yml.in`, with no active placeholder
   YAML. After the real accepted central/CLI pins exist, generate the active caller
   in a **new reviewed Banking publication PR**:

   ```cmd
   python -m demo.publication --template C:\BANKING\demo\pipeline-caller.yml.in --demo-sha ACTUAL_ACCEPTED_CENTRAL_SHA --cli-source-sha ACTUAL_ACCEPTED_PLATFORM_SHA --published-commits-verified --output C:\BANKING\.github\workflows\quantikmind-pipeline-demo.yml
   ```

   `ACTUAL_ACCEPTED_*` are explicit publication-time substitutions, not usable pins.
   The generator refuses invalid pins, unresolved tokens and overwrites. Verify
   that the remote commits really contain the accepted code; a well-formed SHA
   alone proves nothing. Run actionlint plus caller/callee contract checks, review
   the generated literal `uses`/tooling/CLI pins and merge only under authorization.
   Do not create the application presentation commit or dispatch a demo here.
8. Configure Banking runtime secrets/variables and OFF/ON GitHub gates through its
   owner under separate approval. Confirm approved branch, required reviewers,
   available plan features and any bypass policy. Exact names are below. The
   default branch must contain the manual workflow. Prepare the approved
   `demo/pipeline` branch without manufacturing an application change.
9. Read-only readiness: verify deployed contracts, project key scopes, existing
   project/library/ownership/inventory/provider, history entitlement and current
   controls through the CLI. No Quantik Mind UI, personal JWT or general settings
   administrator is required by the demo. Do not import/seed/evaluate/change rules.
   An unavailable qualifying episode is a disclosed outcome, not a reason to loop.
10. Only the operator triggers A with a real reviewed Banking commit, reviews its
    complete report/restoration, then separately triggers B by A Actions run ID.
    [RUNBOOK.md](RUNBOOK.md) contains exact Windows CMD/GitHub UI actions and
    recovery. This preparation does not perform these live executions.

## Required credentials and variables

| Name | Kind / exact purpose |
|---|---|
| QMIND_API_KEY | Project key: `selection:run`, `results:read`; no history/library/settings writes |
| QMIND_INFLUENCE_API_KEY | Separate exact-project key: ONLY `near_miss:influence`, explicit opt-in; influence-only conditional edit/recovery |
| DEMO_READ_TOKEN | Narrow central source/private Platform release-asset read; no dispatch/write/admin/cloud permissions |
| QMIND_API_URL | Verified backend origin without duplicate `/api/v1` |
| QMIND_FRONTEND_URL | Optional verified HTTPS origin; can remain blank |
| QMIND_CLI_WHEEL_URL | Real numeric release asset URL `https://api.github.com/repos/Quantik-Mind/quantikmind-platform/releases/assets/ID` |
| QMIND_CLI_SHA256 | Reviewed released wheel SHA-256 |

No actual secret values are read/configured by this preparation. A credential
owner provisions the influence-only project key via existing authorized API key
management, not by granting the runtime general settings administration. Its
scope is absent from default and full-workflow scope presets.

Called jobs cannot elevate the caller token. `contents:read` plus `actions:read`
supports source and authenticated cross-run artifact retrieval. Build jobs receive
no Quantik Mind keys. Selection jobs use explicit named secrets, no inheritance,
and persist no checkout credentials. No GCP/provider/registry/OIDC privilege is
needed. New live workflow/action/script references are immutable; intended target
name is quantikmind-pipeline-demo. Optional simulated local builds do not satisfy
hosted acceptance. Artifact audience/14-day retention requires owner approval.

## Rollback

GitHub documents the [rename behavior and action-reference limitation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)
and [concurrency queue semantics](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
`queue:max` permits up to 100 pending executions; further arrivals can be rejected.
Actionlint 1.7.12 predates this property. Our validator checks its exact value and
false cancellation, suppressing only that unknown-key diagnostic; all other
diagnostics are fatal. This is distinct from GitHub's actual workflow validation.

Disable/revert only the new Banking caller or restore last accepted immutable
pins; preserve reports, saved runs and legacy example. Use reviewed revert PRs,
never resets/cleaning. Before stopping a run, account for temporary influence:
conditional CLI restore/recover must confirm terminal/reconciled submission and
intact operation lineage; do not overwrite an intervening editor. A killed runner
cannot guarantee automatic cleanup; backend original-state recovery is documented.

If separately authorized to reverse the rename, rename the same ID back and
update every explicit consumer/ref/remote again. Do not recreate the old repository
name. If a Platform release must roll back, use its normal approved previous-image
revision procedure; no data/schema rollback is introduced by this feature. There
is no Banking deployed-image rollback, because demo images are never pushed or
deployed. Do not alter cloud, simulator or scheduler as a demo rollback shortcut.
