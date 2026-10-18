# Runbook (VM deployment)

Run commands as `deploy` on the VM in `/opt/devpilot`. `docker compose` already targets the
production file through `COMPOSE_FILE` in `.env`.

Quick triage: `docker compose ps`, then `docker compose logs --tail=100 <service>`.
Service names: `caddy`, `web`, `api`, `worker`, `postgres`, `redis` (and `check-worker`).

---

## 1. "The VM is down" (site unreachable)

| Check | Command | If it fails |
|---|---|---|
| VM reachable? | `ssh deploy@<vm>` | Start/reboot it in the cloud console; check the instance status and security group allow 22/80/443 |
| DNS correct? | `nslookup <domain>` | Fix the A record (an elastic IP avoids IP changes after a stop/start) |
| Stack up? | `docker compose ps` | `sudo systemctl start devpilot`, or `docker compose up -d` |
| TLS issue? | `docker compose logs caddy --tail=50` | Certificate errors usually mean DNS not pointing here or port 80 blocked |
| Disk full? | `df -h /` and `docker system df` | `docker image prune -af`, clear old backups in `/var/backups/devpilot` |
| Out of memory? | `free -h`, `dmesg \| grep -i oom` | Resize the VM; check the worker's memory limit |

After a VM reboot the `devpilot` systemd unit restarts the stack. Verify with
`systemctl status devpilot` and `curl -fsS https://<domain>/readyz`.

If the data is damaged, restore the latest backup:
```bash
ls -lt /var/backups/devpilot | head
gunzip -c /var/backups/devpilot/devpilot-<stamp>.sql.gz | docker compose exec -T postgres psql -U devpilot devpilot
```

## 2. "Worker is stuck" (diagnoses never appear)

1. Is it alive? `docker compose ps worker`, `docker compose logs --tail=100 worker`.
2. Queue depth: `docker compose exec redis redis-cli llen celery` (and `llen checks`). A growing
   number with no consumption means the worker is down or wedged.
3. What is it doing? `docker compose exec worker celery -A app.workers.celery_app inspect active`.
4. Restart: `docker compose restart worker`. Tasks use `acks_late`, so an interrupted task is
   redelivered. Tasks are hard-killed after 10 minutes.
5. Webhook not triggering anything? GitHub > repo > Settings > Webhooks > Recent Deliveries.
   - `401` signature mismatch: secret in GitHub differs from `DEVPILOT_GITHUB_WEBHOOK_SECRET`.
   - `503` the secret is not set in `.env` (restart `api` after fixing).
   - `202 ignored`: repository is not connected in DevPilot, the run succeeded, or it was already
     processed (the reason is in the response body).
   - Timeouts: Caddy/DNS/firewall problem, see section 1.
6. Queued but no diagnosis: the worker fetches logs with `DEVPILOT_GITHUB_TOKEN`; a 403/404 in the
   worker log means the token lacks Actions read access to that repo.

## 3. "Claude API errors"

Symptoms: diagnoses show `model: heuristic` with warnings, or worker logs show anthropic errors.

| Log / warning | Cause | Fix |
|---|---|---|
| `DEVPILOT_ANTHROPIC_API_KEY is not set` | Missing key | Add it to `.env`, then `docker compose up -d --force-recreate api worker` |
| 401 / authentication_error | Wrong or revoked key | Create a new key in the Anthropic console, update `.env`, recreate |
| 400 credit balance too low | No billing credit | Add credit in the console |
| 429 / overloaded | Rate limit or load | The client retries (3 times). Wait, or lower the load. Heuristic fallback keeps diagnoses flowing |
| Timeouts | Slow responses or network | Check outbound connectivity: `docker compose exec api curl -sS https://api.anthropic.com -o /dev/null -w '%{http_code}'` |
| 404 model not found | Bad `DEVPILOT_CLAUDE_MODEL` | Set a valid model id, recreate |

The app degrades to the offline heuristic classifier, so a Claude outage does not take the
service down; it only lowers diagnosis quality (confidence is capped at 0.3).

## 4. A deploy failed

`scripts/deploy.sh` rolls back automatically when `/readyz` does not become healthy. Check
`/var/log/devpilot/` and `docker compose logs api`. To roll back by hand:
```bash
./scripts/deploy.sh <previous-tag>
```
If images cannot be pulled from ECR: the VM's AWS credentials or instance role may have expired.
Run `aws sts get-caller-identity` as `deploy`.

## 5. Useful commands

```bash
docker compose ps                         # state of every service
docker compose logs -f api                # follow logs
./scripts/db-backup.sh                    # manual backup now
sudo systemctl status devpilot            # boot-time unit
sudo ufw status                           # firewall
```
