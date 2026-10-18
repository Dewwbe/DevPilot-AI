# Phase 2: VM deployment, webhook and release flow

Target: one Ubuntu 22.04/24.04 VM (about 2 vCPU / 4 GB), with a DNS name, running the stack behind
Caddy (automatic HTTPS). Images are built by GitHub Actions and pulled from ECR.

```
git push tag v0.2.0 ──► Actions: build api/web/runner ──► ECR (tags: v0.2.0 and <sha>)
                                  └─► SSH to VM ──► scripts/deploy.sh v0.2.0 ──► smoke test /readyz
GitHub workflow_run failure ──► https://<domain>/api/webhooks/github ──► worker diagnoses ──► dashboard
```

## 1. AWS side (once)
In `infra/terraform`, apply the full config (adds the `devpilot-runner` ECR repo and the GitHub OIDC
publish role), then set the GitHub variables:
```powershell
terraform apply
terraform output github_publish_role_arn      # -> repo variable AWS_ROLE_ARN
```
GitHub repo > Settings > Secrets and variables > Actions > **Variables**: `AWS_ROLE_ARN`,
`AWS_REGION` (if not us-east-1), `DEVPILOT_URL` (`https://<your domain>`).
Merging to `main` now publishes images tagged with the commit SHA.

## 2. Create the VM
Any Ubuntu VM works (EC2 t3.medium, Azure B2s, ...). Open inbound 22, 80 and 443 in the cloud
firewall. Create a DNS A record `devpilot.example.com` pointing at the VM.

ECR pulls from the VM need credentials with ECR read access. On EC2, attach an instance role with
`AmazonEC2ContainerRegistryReadOnly`. Elsewhere, run `aws configure` as the `deploy` user with a
read-only IAM user.

## 3. Bootstrap the VM
Generate a deploy key on your laptop (`ssh-keygen -t ed25519 -f devpilot_deploy`), then on the VM:
```bash
git clone https://github.com/<you>/DevPilot-AI.git && cd DevPilot-AI   # or scp the repo
sudo DEPLOY_PUBKEY="$(cat devpilot_deploy.pub)" REPO_URL=https://github.com/<you>/DevPilot-AI.git \
  ./scripts/vm-bootstrap.sh
```
This creates the `deploy` user (key-only SSH, no root login), ufw (22/80/443), Docker with log
rotation, `/opt/devpilot`, the systemd unit, logrotate and a nightly database backup.
**Before closing your current session, confirm `ssh -i devpilot_deploy deploy@<vm>` works.**

## 4. Configure
On the VM, as `deploy`:
```bash
cd /opt/devpilot && ./scripts/make-basic-auth.sh      # prints DEVPILOT_BASIC_HASH
nano .env                                             # fill in from deploy/vm/env.prod.example
```
Set `REGISTRY`, `DEVPILOT_DOMAIN`, the basic-auth user/hash, `POSTGRES_PASSWORD`, your Anthropic and
GitHub tokens, and `DEVPILOT_GITHUB_WEBHOOK_SECRET` (`openssl rand -hex 32`).

The dashboard and API sit behind HTTP basic auth. Only `/api/webhooks/github`, `/healthz` and
`/readyz` are public, and the webhook is authenticated by its HMAC signature.

## 5. First deploy
Use any tag you have pushed (a SHA from main works):
```bash
./scripts/deploy.sh <image-tag>
sudo systemctl start devpilot          # keeps the stack up across reboots
curl -fsS https://<domain>/readyz
```

## 6. Wire the CD job (task 2.9)
GitHub repo > Settings > Secrets > Actions: `VM_HOST`, `VM_USER` (`deploy`), `VM_SSH_KEY` (private
key contents) and `VM_KNOWN_HOSTS` (output of `ssh-keyscan -H <vm>`; pinning avoids
trust-on-first-use). Optionally add required reviewers to the `production` environment for a manual
approval gate. Then release:
```bash
git tag v0.2.0 && git push origin v0.2.0
```
The deploy backs up the database, pulls images, restarts, smoke-tests `/readyz` and **rolls back to
the previous tag automatically if the smoke test fails**.

## 7. GitHub webhook (task 2.5)
In the **demo target repo** (not this one): Settings > Webhooks > Add webhook.
- Payload URL: `https://<domain>/api/webhooks/github`
- Content type: `application/json`
- Secret: the value of `DEVPILOT_GITHUB_WEBHOOK_SECRET`
- Events: **Workflow runs** only

Connect the repo in DevPilot (dashboard > Repositories, or `./scripts/seed-demo.sh`), make sure
`DEVPILOT_GITHUB_TOKEN` can read that repo's Actions logs, then push a commit that breaks CI. When
the workflow run fails, a diagnosis appears under **Diagnoses** within a minute or so. GitHub's
webhook page shows each delivery and its response (`202 queued`, or `ignored` with a reason).

## Optional: sandboxed check runner (task 2.4)
`POST /api/repositories/{id}/checks` clones the repo and runs ruff, pytest, pip-audit and eslint in
throwaway containers; results are at `GET /api/repositories/{id}/checks`. It needs the Docker
socket, so it is opt-in and runs in a separate worker:
- Local: `docker compose --profile checks up -d --build` (set `DOCKER_GID` on Linux).
- VM: add `COMPOSE_PROFILES=checks` and `DOCKER_GID` to `.env`, then redeploy.
- Not available on ECS Fargate (no Docker socket).

Read the sandbox notes in [SAFETY.md](SAFETY.md) before enabling it on a public host.

## Cost note
A t3.medium is roughly $30/month, plus ECR storage. Stop or terminate the VM when not demoing.
