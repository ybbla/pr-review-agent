"""控制台与运维 handler：静态资源、健康检查、指标、管理端点与登录。"""
from ..foundation.metrics import metrics
from ..foundation.modes import public_taxonomy, resolve_mode


class AdminHandlers:
    """承载 /assets/*、/health、/metrics、/api/*、/github/* 与登录的处理逻辑。"""

    def _handle_static(self, path: str) -> bool:
        if path == "/":
            self._serve_file("index.html")
            return True
        if path == "/assets/app.css":
            self._serve_file("app.css")
            return True
        if path == "/assets/login.css":
            self._serve_file("login.css")
            return True
        if path == "/assets/app.js":
            self._serve_file("app.js")
            return True
        return False

    def _handle_health(self, path: str) -> bool:
        if path != "/health":
            return False
        mode = resolve_mode(None, bool(self.service.llm_config))
        self._send_json(200, {"status": "ok", "reviewer": self.service.reviewer.name,
                              "runtime": self.service.harness.name,
                              "queue": self.service.queue.backend,
                              "llm_provider": self.service.llm_config.get("provider", "local"),
                              "llm_model": self.service.llm_config.get("model", ""),
                              "run_mode": mode.to_dict(),
                              "taxonomy": public_taxonomy()})
        return True

    def _handle_metrics(self, path: str) -> bool:
        if path != "/metrics":
            return False
        self._send_text(200, metrics.prometheus(), "text/plain; version=0.0.4; charset=utf-8")
        return True

    def _handle_admin_get(self, path: str, query: dict, principal) -> bool:
        if path == "/api/dashboard":
            mode = resolve_mode(None, bool(self.service.llm_config))
            self._send_json(200, {"stats": self.service.store.dashboard_stats(principal.tenant_id),
                                  "tasks": self.service.store.list_tasks(10, principal.tenant_id),
                                  "queue": self.service.queue.backend,
                                  "orchestrator": self.service.reviewer.name,
                                  "llm": {
                                      "enabled": bool(self.service.llm_config),
                                      "provider": self.service.llm_config.get("provider", "local"),
                                      "model": self.service.llm_config.get("model", ""),
                                  },
                                  "run_mode": mode.to_dict(),
                                  "taxonomy": public_taxonomy()})
            return True
        if path == "/api/tasks":
            self._send_json(200, {"tasks": self.service.store.list_tasks(
                int(query.get("limit", [50])[0]), principal.tenant_id)})
            return True
        if path == "/api/skills":
            self._send_json(200, {
                "skills": self.service.list_skills(principal.tenant_id),
                "llm": {
                    "enabled": bool(self.service.llm_config),
                    "provider": self.service.llm_config.get("provider", "local"),
                    "model": self.service.llm_config.get("model", ""),
                },
            })
            return True
        if path == "/api/failures":
            if not principal.can("audit"):
                self._send_json(403, {"error": "permission denied"})
                return True
            self._send_json(200, {"cases": self.service.store.list_failure_cases(
                False, 100, principal.tenant_id
            )})
            return True
        if path == "/api/audit":
            if not principal.can("audit"):
                self._send_json(403, {"error": "permission denied"})
                return True
            self._send_json(200, {"events": self.service.store.list_audit(
                principal.tenant_id, int(query.get("limit", [100])[0])
            )})
            return True
        if path == "/api/alerts":
            self._send_json(200, {"alerts": self.service.store.list_alerts(principal.tenant_id)})
            return True
        if path == "/api/deployments/llm-review":
            self._send_json(200, {"deployment": self.service.store.get_deployment(
                principal.tenant_id, "llm-review"
            )})
            return True
        if path == "/api/queue/dead-letters":
            if not principal.can("manage"):
                self._send_json(403, {"error": "permission denied"})
                return True
            self._send_json(200, {"messages": self.service.queue.dead_letters(
                int(query.get("limit", [100])[0])
            )})
            return True
        return False

    def _handle_github_get(self, path: str, query: dict) -> bool:
        if path == "/github/install":
            if not self.settings.github_app_slug:
                self._send_json(503, {"error": "EVOAGENT_GITHUB_APP_SLUG is not configured"})
                return True
            self.send_response(302)
            self.send_header("Location", "https://github.com/apps/%s/installations/new" % self.settings.github_app_slug)
            self.end_headers()
            return True
        if path == "/github/setup":
            try:
                installation_id = int(query.get("installation_id", [""])[0])
            except ValueError:
                self._send_json(400, {"error": "missing installation_id"})
                return True
            self.service.store.save_installation(installation_id, query.get("account", ["github-app"])[0])
            self.send_response(302)
            self.send_header("Location", "/#github")
            self.end_headers()
            return True
        return False

    def _handle_login_post(self, path: str, body: bytes) -> bool:
        if path != "/v1/auth/login":
            return False
        if not self.settings.auth_required:
            self._send_json(409, {"error": "authentication is disabled"})
            return True
        payload = self._read_json(body)
        try:
            result = self.service.auth.login(
                str(payload.get("username", "")), str(payload.get("password", "")),
                str(payload.get("tenant_id", "")),
            )
        except PermissionError as exc:
            self._send_json(401, {"error": str(exc)})
            return True
        self._send_json(200, result)
        return True

    def _handle_admin_post(self, path: str, body: bytes) -> bool:
        if path == "/v1/skills/reload":
            self._principal("manage")
            self._send_json(200, {"skills": self.service.reload_skills(),
                                  "note": "New tasks now use the reloaded skill set."})
            return True
        if path == "/v1/deployments/llm-review":
            principal = self._principal("manage")
            payload = self._read_json(body)
            result = self.service.releases.configure(
                principal.tenant_id, "llm-review", payload
            )
            self.service.store.audit(
                principal.tenant_id, principal.username, "deployment.configure",
                "llm-review", payload,
            )
            self._send_json(201, result)
            return True
        if path == "/v1/queue/dead-letters/replay":
            self._principal("manage")
            payload = self._read_json(body)
            ok = self.service.queue.replay_dead_letter(
                str(payload.get("message_id", ""))
            )
            self._send_json(202 if ok else 404, {"replayed": ok})
            return True
        return False
