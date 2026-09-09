"""HTTP 路由正则常量集中定义，供 handler 骨架与各域 mixin 复用。"""
import re


TASK = re.compile(r"^/v1/tasks/([0-9a-f-]+)$")
REPORT = re.compile(r"^/v1/tasks/([0-9a-f-]+)/report$")
FIX = re.compile(r"^/v1/tasks/([0-9a-f-]+)/fix$")
FEEDBACK = re.compile(r"^/v1/tasks/([0-9a-f-]+)/feedback$")
CANCEL = re.compile(r"^/v1/tasks/([0-9a-f-]+)/cancel$")
RESUME = re.compile(r"^/v1/tasks/([0-9a-f-]+)/resume$")
ROLLBACK = re.compile(r"^/v1/skills/([A-Za-z0-9_-]+)/versions/(\d+)/activate$")
SKILL_ARTIFACT_VERSIONS = re.compile(r"^/v1/skill-evolution/([a-z0-9_-]+)/versions$")
SKILL_ARTIFACT_ACTIVATE = re.compile(
    r"^/v1/skill-evolution/([a-z0-9_-]+)/versions/(\d+)/activate$"
)
