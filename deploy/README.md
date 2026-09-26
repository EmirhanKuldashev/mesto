# Production: mesto.sbs

The Ubuntu host runs Nginx and Certbot. Nginx terminates TLS and proxies `/api/` and `/health` to the backend on `127.0.0.1:8000`; all other paths go to the frontend on `127.0.0.1:3000`. PostgreSQL has no published port in `docker-compose.prod.yml`.

The certificate for `mesto.sbs` is issued by Let's Encrypt with `certbot --nginx`. The `certbot.timer` systemd unit renews it. Check with `certbot renew --dry-run` and `certbot certificates`. Ports 80 and 443 must remain reachable so HTTP validation and HTTPS work.

The deployment checkout is `/opt/mesto`, owned by `mesto-deploy`. Its `.env` contains the database password and is never committed. Use:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

`.github/workflows/ci.yml` runs backend tests, frontend lint/build, and production Compose validation for each push to `main`. `mesto-deploy.timer` checks `origin/main` every five minutes. `deploy/mesto-deploy.sh` asks the public GitHub Actions API for a successful **push** CI run on the exact commit before building and starting containers. A failed or pending CI run never deploys. The host pulls the public repository; no SSH private key or GitHub token is stored in Actions or on the server.

Service logs: `journalctl -u mesto-deploy.service -n 100 --no-pager`. To trigger a check immediately: `systemctl start mesto-deploy.service`. The script records a healthy deployed commit in `/opt/mesto/.deployed-sha`.
