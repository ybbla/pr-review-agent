"""审查主流程 handler：创建审查、GitHub webhook 与任务操作。"""
import hashlib
from datetime import datetime, timezone

from ..integration.github import verify_signature
from ..report import to_markdown
from .routes import CANCEL, FEEDBACK, FIX, REPORT, RESUME, TASK


class ReviewHandlers:
    """承载 /v1/reviews、/webhooks/github 与 /v1/tasks/* 的处理逻辑。"""

    def _handle_review_post(self, path: str, query: dict, body: bytes) -> bool:
        if path != "/v1/reviews":
            return False
        principal = self._principal("review")
        payload = self._read_json(body)
        pr = payload.get("pull_request")
        if pr is not None and not isinstance(pr, int):
            raise ValueError("pull_request must be an integer")
        args = (str(payload.get("repository", "")), str(payload.get("diff", "")), pr)
        enabled_agents = payload.get("enabled_agents")
        if enabled_agents is not None and (
            not isinstance(enabled_agents, list)
            or not all(isinstance(item, str) for item in enabled_agents)
        ):
            raise ValueError("enabled_agents must be an array of role names")
        enabled_skills = payload.get("enabled_skills")
        if enabled_skills is not None and (
            not isinstance(enabled_skills, list)
            or not all(isinstance(item, str) for item in enabled_skills)
        ):
            raise ValueError("enabled_skills must be an array of Agent Skill names")
        options = {
            "tenant_id": principal.tenant_id,
            "mode": str(payload.get("mode", "")),
            "repository_root": str(payload.get("repository_root", "")),
            "enabled_agents": enabled_agents,
            "enabled_skills": enabled_skills,
        }
        if query.get("async", ["false"])[0].lower() == "true":
            result = self.service.enqueue_review(*args, **options)
            self._send_json(202, result)
        else:
            self._send_json(201, self.service.create_review(*args, **options))
        self.service.store.audit(
            principal.tenant_id, principal.username, "review.create",
            str(payload.get("repository", "")), {
                "async": query.get("async", ["false"])[0],
                "mode": str(payload.get("mode", "")),
            },
        )
        return True

    def _handle_webhook_post(self, path: str, body: bytes) -> bool:
        if path != "/webhooks/github":
            return False
        if self.headers.get("X-GitHub-Event", "") != "pull_request":
            self._send_json(202, {"ignored": True, "reason": "unsupported GitHub event"})
            return True
        if not self.settings.github_webhook_secret:
            self._send_json(503, {"error": "GitHub webhook secret is not configured"})
            return True
        if not verify_signature(self.settings.github_webhook_secret, body,
                                self.headers.get("X-Hub-Signature-256", "")):
            self._send_json(401, {"error": "invalid webhook signature"})
            return True
        payload = self._read_json(body)
        updated_at = (payload.get("pull_request") or {}).get("updated_at")
        if updated_at:
            try:
                event_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("invalid pull_request.updated_at")
            age = abs((datetime.now(timezone.utc) - event_time).total_seconds())
            if age > self.settings.webhook_max_age_seconds:
                self._send_json(409, {"error": "webhook is outside the replay window"})
                return True
        delivery_id = self.headers.get("X-GitHub-Delivery", "")
        digest = hashlib.sha256(body).hexdigest()
        self._send_json(202, self.service.handle_github_pull_request(
            payload, delivery_id, digest
        ))
        return True

    def _handle_task_post(self, path: str, body: bytes) -> bool:
        match = FIX.match(path)
        if match:
            principal = self._principal("fix")
            payload = self._read_json(body)
            installation_id = payload.get("installation_id")
            if installation_id is not None and not isinstance(installation_id, int):
                raise ValueError("installation_id must be an integer")
            result = self.service.create_fix(
                match.group(1), installation_id, principal.tenant_id
            )
            self.service.store.audit(
                principal.tenant_id, principal.username, "repair.create",
                match.group(1), {"branch": result.get("branch")},
            )
            self._send_json(201, result)
            return True
        match = FEEDBACK.match(path)
        if match:
            principal = self._principal("review")
            payload = self._read_json(body)
            result = self.service.record_feedback(
                match.group(1), str(payload.get("category", "")), payload.get("finding"),
                str(payload.get("note", "")), principal.tenant_id,
            )
            self.service.store.audit(
                principal.tenant_id, principal.username, "feedback.record", match.group(1),
                {"category": result["category"]},
            )
            self._send_json(201, result)
            return True
        match = CANCEL.match(path)
        if match:
            principal = self._principal("review")
            ok = self.service.cancel_task(match.group(1), principal.tenant_id)
            self.service.store.audit(
                principal.tenant_id, principal.username, "task.cancel", match.group(1)
            )
            self._send_json(202 if ok else 404, {"cancel_requested": ok})
            return True
        match = RESUME.match(path)
        if match:
            principal = self._principal("review")
            result = self.service.resume_task(match.group(1), principal.tenant_id)
            self.service.store.audit(
                principal.tenant_id, principal.username, "task.resume", match.group(1)
            )
            self._send_json(202, result)
            return True
        return False

    def _handle_task_get(self, path: str, principal) -> bool:
        report_match = REPORT.match(path)
        task_match = TASK.match(path)
        feedback_match = FEEDBACK.match(path)
        if feedback_match:
            if not principal.can("review"):
                self._send_json(403, {"error": "permission denied"})
                return True
            task = self.service.store.get(feedback_match.group(1), principal.tenant_id)
            if not task:
                self._send_json(404, {"error": "task not found"})
                return True
            self._send_json(200, {"cases": self.service.store.list_task_failure_cases(
                feedback_match.group(1), principal.tenant_id
            )})
            return True
        if report_match:
            task = self.service.store.get(report_match.group(1), principal.tenant_id)
            if not task or not task.get("report"):
                self._send_json(404, {"error": "task or report not found"})
                return True
            self._send_text(200, to_markdown(task["report"]), "text/markdown; charset=utf-8")
            return True
        if task_match:
            task = self.service.store.get(task_match.group(1), principal.tenant_id)
            if not task:
                self._send_json(404, {"error": "task not found"})
                return True
            self._send_json(200, task)
            return True
        return False
