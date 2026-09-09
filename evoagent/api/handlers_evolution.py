"""进化、评测与发布 handler：提示词进化、Skill 进化与评测样本管理。"""
from .routes import ROLLBACK, SKILL_ARTIFACT_ACTIVATE, SKILL_ARTIFACT_VERSIONS


class EvolutionHandlers:
    """承载 /v1/evolution*、/v1/skill-evolution*、/v1/evaluation/cases 的处理逻辑。"""

    def _handle_evolution_get(self, path: str, query: dict, principal) -> bool:
        if path == "/v1/evaluation/cases":
            split = query.get("split", ["validation"])[0]
            if split == "holdout":
                self._send_json(403, {"error": "holdout cases are not exposed through the API"})
                return True
            self._send_json(200, {
                "cases": self.service.store.list_evaluation_cases(split, True, 100)
            })
            return True
        if path == "/v1/evolution/runs":
            self._send_json(200, {
                "runs": self.service.store.list_evolution_runs(int(query.get("limit", [50])[0]))
            })
            return True
        if path == "/v1/evolution/status":
            status = self.service.evolution.status()
            status["provider"] = self.service.llm_config.get("provider", "local")
            status["model"] = self.service.llm_config.get("model", "")
            self._send_json(200, status)
            return True
        if path == "/v1/skill-evolution/status":
            if not principal.can("manage"):
                self._send_json(403, {"error": "permission denied"})
                return True
            skill_name = query.get("skill_name", ["evolved-review"])[0]
            self._send_json(200, self.service.skill_evolution.status(
                skill_name, principal.tenant_id
            ))
            return True
        if path == "/v1/skill-evolution/runs":
            if not principal.can("manage"):
                self._send_json(403, {"error": "permission denied"})
                return True
            self._send_json(200, {"runs": self.service.store.list_skill_evolution_runs(
                int(query.get("limit", [50])[0]), principal.tenant_id
            )})
            return True
        match = SKILL_ARTIFACT_VERSIONS.match(path)
        if match:
            if not principal.can("manage"):
                self._send_json(403, {"error": "permission denied"})
                return True
            self._send_json(200, {"versions": self.service.store.list_skill_artifact_versions(
                match.group(1), principal.tenant_id
            )})
            return True
        return False

    def _handle_evolution_post(self, path: str, body: bytes) -> bool:
        if path == "/v1/evaluation/cases":
            self._principal("manage")
            payload = self._read_json(body)
            result = self.service.evolution.add_evaluation_case(
                str(payload.get("name", "")),
                str(payload.get("diff", "")),
                payload.get("expected_findings", []),
                str(payload.get("split", "validation")),
                "api",
            )
            self._send_json(201, result)
            return True
        if path == "/v1/evolution/auto":
            principal = self._principal("manage")
            payload = self._read_json(body)
            result = self.service.evolution.auto_propose(
                str(payload.get("skill_name", "llm-review")), principal.tenant_id
            )
            if result["decision"] == "activated":
                self.service.reload_skills()
            self._send_json(201, result)
            return True
        if path == "/v1/evolution/propose":
            self._principal("manage")
            payload = self._read_json(body)
            result = self.service.evolution.propose(
                str(payload.get("skill_name", "")), str(payload.get("prompt", "")),
                float(payload["regression_score"]) if "regression_score" in payload else None,
            )
            if result["decision"] == "activated":
                self.service.reload_skills()
            self._send_json(201, result)
            return True
        if path == "/v1/skill-evolution/auto":
            principal = self._principal("manage")
            payload = self._read_json(body)
            result = self.service.skill_evolution.auto_propose(
                str(payload.get("skill_name", "evolved-review")), principal.tenant_id
            )
            if result["decision"] == "activated":
                self.service.reload_skills()
            self.service.store.audit(
                principal.tenant_id, principal.username, "skill.evolution.auto",
                str(payload.get("skill_name", "evolved-review")),
                {"decision": result["decision"], "run_id": result.get("run_id")},
            )
            self._send_json(201, result)
            return True
        if path == "/v1/skill-evolution/propose":
            principal = self._principal("manage")
            payload = self._read_json(body)
            artifact = payload.get("artifact")
            if artifact is None and "skill_md" in payload:
                artifact = {
                    "name": str(payload.get("skill_name", "")),
                    "skill_md": payload.get("skill_md"),
                    "supporting_files": payload.get("supporting_files") or {},
                }
            result = self.service.skill_evolution.propose(
                str(payload.get("skill_name", "")), artifact,
                principal.tenant_id,
            )
            if result["decision"] == "activated":
                self.service.reload_skills()
            self.service.store.audit(
                principal.tenant_id, principal.username, "skill.evolution.propose",
                str(payload.get("skill_name", "")),
                {"decision": result["decision"], "run_id": result.get("run_id")},
            )
            self._send_json(201, result)
            return True
        match = SKILL_ARTIFACT_ACTIVATE.match(path)
        if match:
            principal = self._principal("manage")
            ok = self.service.skill_evolution.rollback(
                match.group(1), int(match.group(2)), principal.tenant_id
            )
            if ok:
                self.service.reload_skills()
            self.service.store.audit(
                principal.tenant_id, principal.username, "skill.evolution.activate",
                match.group(1), {"version": int(match.group(2)), "activated": ok},
            )
            self._send_json(200 if ok else 404, {"activated": ok})
            return True
        match = ROLLBACK.match(path)
        if match:
            self._principal("manage")
            ok = self.service.evolution.rollback(match.group(1), int(match.group(2)))
            if ok:
                self.service.reload_skills()
            self._send_json(200 if ok else 404, {"activated": ok})
            return True
        return False
