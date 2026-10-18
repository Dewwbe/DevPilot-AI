# How AI tools were used to build this project

This project is itself about responsible use of AI, so this page records how Claude Code was used
to build it, what was verified, and where humans stayed in control. Edit the "My notes" sections
with your own experience; they should reflect what you actually did.

## What Claude Code did here
- Wrote and edited code, Terraform, Helm templates, CI workflows and docs from the roadmap tasks.
- Ran the project's own tooling to check its work: `pytest`, `ruff`, `tsc`/`vite build`,
  `docker compose`, `terraform validate`, `helm lint`, `kubeconform`, `hadolint`, `promtool`, and
  real end-to-end runs (a sandboxed check against a throwaway container, a signed webhook against
  the running stack, an Alembic migration against an existing Postgres).
- Found and fixed problems by running things, for example: cleanup of read-only git files that
  silently failed on Windows (a failing test) and a silent failure path in the webhook-triggered
  diagnosis task (a live webhook test against the running stack).

## Where a human stayed in control
- **Pushing and merging were done by the repository owner.** The tool made local commits only on
  feature branches when asked, and left the latest phase uncommitted for review at the owner's
  request.
- **Secrets are kept out of git:** API keys live only in `.env`, `terraform.tfvars` and Secrets
  Manager (ignored or external). A local commit that accidentally included `terraform.tfvars` and
  Terraform state was never pushed (GitHub rejected it over file size); those paths are
  gitignored and must never be committed.
- **Cloud actions needed the owner's credentials and approval:** nothing was applied to AWS by the
  tool. Infrastructure code was validated, not deployed, until the owner runs it.
- **Design decisions were explicit:** ECS first for cost, then EKS (ADR-002, ADR-003); a GitHub
  App with minimal permissions (ADR-006).

## Limits of AI-generated work in this repo
- Generated code and infrastructure were validated by tools and tests, not proven in production.
  Unrun paths (first `terraform apply`, the CD workflow on a real VM, the PR flow against real
  GitHub) are called out in the docs and should be treated as untested until you run them.
- Test coverage reflects what was built; the eval set has only three seed cases, so accuracy
  numbers say little until roadmap 1.14 adds real failures.
- AI output was treated as a proposal: review diffs, read the Terraform plan, and run the checks
  yourself before trusting any of it.

## My notes (fill in)
- Prompts and workflow I used (for example plan-first, small tasks, review each diff):
- Things Claude Code got wrong that I caught:
- Things I verified by hand:
- What I would not delegate to an AI tool:
