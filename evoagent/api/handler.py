"""组合各域 handler mixin 的 ApiHandler，以及 do_GET/do_POST 路由分发骨架。"""
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Any

from ..foundation.metrics import metrics
from .base import BaseHandlerMixin
from .handlers_admin import AdminHandlers
from .handlers_evolution import EvolutionHandlers
from .handlers_review import ReviewHandlers


class ApiHandler(BaseHTTPRequestHandler, BaseHandlerMixin, AdminHandlers,
                 EvolutionHandlers, ReviewHandlers):
    """组合 HTTP 基础设施与各域处理逻辑，保留手写路由骨架。"""

    server_version = "EvoAgent/0.3"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)
        if self._handle_static(path):
            return
        if self._handle_health(path):
            return
        principal = self._authenticate_or_send("read")
        if principal is None:
            return
        if self._handle_metrics(path):
            return
        if self._handle_admin_get(path, query, principal):
            return
        if self._handle_evolution_get(path, query, principal):
            return
        if self._handle_github_get(path, query):
            return
        if self._handle_task_get(path, principal):
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)
        try:
            body = self._read_body()
            if self._handle_login_post(path, body):
                return
            if self._handle_review_post(path, query, body):
                return
            if self._handle_webhook_post(path, body):
                return
            if self._handle_task_post(path, body):
                return
            if self._handle_admin_post(path, body):
                return
            if self._handle_evolution_post(path, body):
                return
            self._send_json(404, {"error": "not found"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except PermissionError as exc:
            self._send_json(403, {"error": str(exc)})
        except Exception as exc:
            metrics.inc("http_errors_total")
            self._send_json(500, {"error": "operation failed", "detail": str(exc)})
