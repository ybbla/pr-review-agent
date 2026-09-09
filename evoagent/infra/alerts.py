"""Review failure-rate alerting backed by the task store."""


class AlertManager:
    def __init__(self, store, failure_rate: float = .2, min_samples: int = 10):
        self.store = store
        self.failure_rate = failure_rate
        self.min_samples = min_samples

    def evaluate(self, tenant_id: str) -> None:
        stats = self.store.dashboard_stats(tenant_id)
        if stats["tasks_total"] >= self.min_samples:
            rate = stats["tasks_failed"] / stats["tasks_total"]
            if rate > self.failure_rate:
                self.store.create_alert(
                    tenant_id, "review-failure-rate", "critical",
                    "Review failure rate %.1f%% exceeds the %.1f%% threshold."
                    % (rate * 100, self.failure_rate * 100),
                )
