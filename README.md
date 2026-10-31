# quantikmind-pipeline-demo

General-purpose Quantik Mind pipeline demonstration tooling: controlled Banking
commit → affected-service image build → existing CLI → real saved selection →
friendly, auditable report. This is the EXISTING Customer Insight repository,
prepared for its approved future rename; history is preserved. Rename and live
rehearsal remain separately authorized; publication PRs do not enable the caller.

- [Windows CMD setup and operator runbook](docs/RUNBOOK.md)
- [Rename, publication, access and rollback](docs/PUBLICATION.md)
- [Synthetic offline HTML sample](samples/synthetic/report.html)
- [Synthetic Markdown sample](samples/synthetic/report.md)
- [Original README preserved byte-for-byte](legacy/CUSTOMER_INSIGHT.md)

The new reusable workflow is `.github/workflows/selection-demo.yml`. The Banking
caller remains a `.yml.in` publication template until actual immutable published
pins exist. The template generator rejects unresolved substitutions. No
placeholder caller is enabled. `demo/` contains safe diff/build tooling,
CLI-only orchestration, offline reporting and integrity-checked installation.
Opening or regenerating a report makes no API calls.

A trusted Banking push starts only execution A. A sets influence OFF through the
conditional CLI operation, selects once, restores the original state and publishes
its complete report. A new explicit manual trigger starts B, referencing A's
successful Actions run; B verifies/reuses A's exact source/inputs, builds again,
sets influence ON, selects once, restores and publishes its own and paired reports.
There is no automatic OFF→ON chain. Quantik Mind UI use is optional drill-down.

Controls require a separate project-scoped `near_miss:influence` key; no personal
JWT or broad settings administrator is used. Conditional revisions and operation
lineage protect restoration; uncertain/pending runs hold restoration for explicit
CLI recovery. Attribution comes from B's backend-validated frozen comparison.
Missing evidence remains unavailable; zero direct additions is valid. Hosted
acceptance always requires real builds, without starting/deploying services or
executing selected tests. Count reduction is not time/cost savings or incident
prevention. Samples are synthetic fixtures, not live provider acceptance.

Offline development uses Python 3.11: `python -m pytest tests -q` and
`python -m demo.sample --output samples/synthetic`. See the runbook for setup.

## Legacy Customer Insight example

The legacy `.github/workflows/customer-insight.yml` is now manual-only; its
selection logic/project/credentials remain independent. Its original definition
is preserved in `legacy/customer-insight.yml`, outside the enabled workflow
directory. `ci-examples` remain legacy templates. This prevents publishing the
new tooling from automatically submitting a legacy selection. The
new workflow does not repoint or refresh them. The following original material
describes that legacy example only; it does not define the new CLI workflow.

**Quantik Mind – Customer Insight (Example Pipeline)**

This repository contains an example CI/CD pipeline demonstrating how Quantik Mind can be used to apply Decision Intelligence to software testing.

---

⚠️**Important**⚠️

_This pipeline is not intended for production execution.
It is a fully working demo designed to show how Quantik Mind selects the right tests, how results are returned, and how they can be integrated into an existing pipeline._

---

🔧**What This Pipeline Does**🔧

The pipeline simulates a real customer scenario using:

- An example project: Customer Insight

- An example test library containing 2,175 functional test cases

- A real call to the Quantik Mind API

_The pipeline_:

- Calls Quantik Mind to select the most relevant tests

- Prints the decision results directly in the CI logs

- Saves the list of selected tests to a file:
selected_tests.txt

- Fetches detailed Decision Insight and KPIs

- Uploads all decision artifacts for later inspection

No tests are executed.
The goal is decision transparency, not execution.

---

💡**Why This Pipeline Exist**💡

This example is meant to answer one question:

“What would Quantik Mind decide, right now, for my system?”

It shows:

- How many tests exist

- How many tests are actually selected

- How much test reduction is achieved

- How risk coverage is maximized

- Which quantum principles contributed to the decision

Think of it as a decision preview, not a test runner.

---
       
📬**Questions, Issues, or Feedback**📬

This repository is provided as an example integration to showcase how Quantik Mind decision intelligence works in a CI/CD context.

If you have:

- Questions about the pipeline logic

- Issues running the example workflow

- Feedback or ideas for deeper integrations

- Interest in using Quantik Mind in a real environment

📧 Contact us at: info@quantikmind.com 

We’re happy to discuss:

- Real-world pipeline integrations

- Custom test libraries

- Pilot projects and enterprise setups
