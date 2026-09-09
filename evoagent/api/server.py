"""HTTP 服务启动入口：装配 Settings/ReviewService 并启动 ThreadingHTTPServer。"""
from http.server import ThreadingHTTPServer

from ..config import Settings
from ..service import ReviewService
from .handler import ApiHandler


def run() -> None:
    """从环境变量装配服务并阻塞式启动 HTTP 服务器。"""
    settings = Settings.from_env()
    service = ReviewService(settings)
    handler = type("ConfiguredApiHandler", (ApiHandler,), {"service": service, "settings": settings})
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    print("EvoAgent dashboard: http://%s:%d" % (settings.host, settings.port))
    print("Persistence: %s | Queue: %s | Orchestrator: %s" % (
        "postgresql" if settings.database_url else "sqlite", service.queue.backend, service.reviewer.name
    ))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.queue.close()
        server.server_close()
