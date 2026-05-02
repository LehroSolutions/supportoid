"""
API security layer with OWASP-oriented guardrails for SupportOID.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger("supportoid.security")

THREAT_ORDER = ["none", "low", "medium", "high", "critical"]


def _max_threat(current: str, candidate: str) -> str:
    return max(current, candidate, key=lambda item: THREAT_ORDER.index(item))


@dataclass
class SecurityCheck:
    passed: bool
    checks_passed: int
    checks_failed: int
    flags: List[str]
    sanitized_input: str
    threat_level: str = "none"
    details: str = ""


class SecurityLayer:
    """OWASP-aligned security guardrails for agentic support."""

    MAX_AUDIT_ENTRIES = 1000

    INJECTION_PATTERNS = [
        r"(?i)(?:ignore\s+all\s+previous\s*(?:instructions|rules|constraints|prompt[s]?))",
        r"(?i)(?:from\s+now\s+on\s+you\s+are)",
        r"(?i)(?:ignore\s+safety\s*(?:rules|guidelines|filters|policies))",
        r"(?i)(?:bypass\s+(?:all\s+)?filter[s]?)",
        r"(?i)(?:act\s+as\s+system)",
        r"(?i)(?:system\s*(?::\s*)?override)",
        r"(?i)(?:developer\s*:\s*)",
        r"(?i)(?:<\s*user\s*>)",
        r"(?i)(?:new\s+instructions[\s:]*)",
        r"(?i)(?:you\s+are\s+now\s+dan)",
        r"(?i)(?:do\s+anything\s+now)",
        r"(?i)(?:do\s+not\s+follow\s+(?:the\s+)?rules)",
        r"(?i)(?:pretend\s+to\s+be\s+(?:admin|root|system))",
        r"(?i)(?:mode\s*:\s*developer)",
        r"(?i)(?:disregard\s+your\s+(?:previous|initial|original)\s+instructions)",
        r"(?i)(?:you\s+are\s+(?:an\s+)?uncensored\s+(?:ai|model))",
        r"(?i)(?:without\s+(?:any\s+)?restrictions)",
        r"(?i)(?:free\s+of\s+(?:content\s+)?policies)",
        r"(?:```[\s\S]*?ignore.*?previous)",
        r"(?:\[\[.*?system.*?\]\])",
        r"(?i)(?:context\s*:\s*previous)",
        r"(?i)(?:user\s+message\s*:\s*)",
    ]

    SQL_INJECTION = [
        r"(?i)(?:['\"]?\s*(?:OR|AND)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+)",
        r"(?i)(?:UNION\s+(?:ALL\s+)?SELECT)",
        r"(?i)(?:SELECT\s+.*\s+FROM\s+)",
        r"(?i)(?:INSERT\s+INTO\s+)",
        r"(?i)(?:UPDATE\s+\w+\s+SET\s+)",
        r"(?i)(?:DROP\s+(?:TABLE|DATABASE|INDEX))",
        r"(?i)(?:DELETE\s+FROM\s+)",
        r"(?i)(?:;?\s*--\s*$)",
        r"(\s*;\s*(?:DROP|ALTER|CREATE|DELETE|UPDATE|INSERT|SELECT)\s)",
        r"(?i)(?:WAITFOR\s+DELAY)",
        r"(?i)(?:BENCHMARK\s*\()",
        r"(?i)(?:LOAD_FILE\s*\()",
    ]

    NOSQL_INJECTION = [
        r"(?:\[\s*\$[\w]+\s*])",
        r'(?i)(?:"\$\w+"\s*:\s*)',
        r"(?i)(?:\$\w+\s*:)",
        r"(?:\{.*?\$where.*?\})",
        r"(?i)(?:\$where\s*:)",
    ]

    COMMAND_INJECTION = [
        r"(?i)(?:;\s*(?:rm|cat|wget|curl|nc|bash|sh|python|perl|ruby)\b)",
        r"(?i)(?:&&\s*(?:rm|cat|wget|curl|nc|bash|sh))",
        r"(?i)(?:\|\s*(?:cat|less|more|head|tail))",
        r"(?i)(?:`[^`]*(?:cat|passwd|shadow|id|whoami|ls)[^`]*`)",
        r"\$\([^)]*(?:cat|passwd|id|whoami|ls|pwd)",
        r"(?i)(?:rm\s+-r[fF]?\s+\/)|(?:rm\s+-r[fF]?\s+\*)",
    ]

    XSS_PATTERNS = [
        r"(?i)(?:<\s*script[^>]*>)",
        r"(?i)(?:javascript\s*:)",
        r"(?i)(?:on\w+\s*=\s*(?:['\"]|{))",
        r"(?i)(?:<\s*img\s+[^>]*on\w+)",
        r"(?i)(?:<\s*iframe)",
        r"(?i)(?:<\s*svg[^>]*on\w+)",
        r"(?i)(?:<\s*body[^>]*on\w+)",
        r"(?i)(?:expression\s*\()",
        r"(?i)(?:eval\s*\([^)]*\))",
        r"(?i)(?:document\s*\.\s*(?:cookie|write|location|domain))",
        r"(?i)(?:window\s*\.\s*(?:location|open))",
    ]

    SSRF_PATTERNS = [
        r"(?i)(?:(?:https?|ftp|file|gopher|dict)://(?:127\.0\.0\.1|localhost|0\.0\.0\.0|169\.254\.169\.254|metadata\.google))",
        r"(?i)(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3})",
        r"(?i)(?:172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})",
        r"(?i)(?:192\.168\.\d{1,3}\.\d{1,3})",
        r"(?i)(?:file:///etc/)",
    ]

    PATH_TRAVERSAL = [
        r"(?:\.\./|\.\.\\)",
        r"(?i)(?:%2e%2e(?:/|\\|%2f|%5c))",
        r"(?:/etc/(?:passwd|shadow|hosts))",
        r"(?:/proc/(?:self|1)/)",
        r"(?:\.\.[\\/]){2,}",
    ]

    SECRET_PATTERNS = [
        (r"(?:sk-|pk-|rk-|sk_|pk_|rk_)[a-zA-Z0-9_-]{20,}", "[REDACTED_KEY]"),
        (
            r"(?i)(?:api[_-]?key|api[_-]?secret|token)[\s:=]*[\"']?([a-zA-Z0-9]{16,})[\"']?",
            "[REDACTED_SECRET]",
        ),
        (
            r"(?i)(?:password|passwd|pwd)[\s:=]*[\"']?[^\s\"']{4,}[\"']?",
            "[REDACTED_PASSWORD]",
        ),
        (
            r"(?i)(?:aws_access_key|aws_secret)[\s:=]*[\"']?[a-zA-Z0-9/+=]{16,}[\"']?",
            "[REDACTED_AWS_KEY]",
        ),
        (r"\b(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}\b", "[REDACTED_GITHUB_TOKEN]"),
        (r"\b(?:xoxb|xoxp|xoxe)-[a-zA-Z0-9-]{10,}\b", "[REDACTED_SLACK_TOKEN]"),
    ]

    DANGEROUS_OPERATIONS = [
        r"(?i)(?:drop\s+table)",
        r"(?i)(?:delete\s+from)",
        r"(?i)(?:rm\s+-rf)",
        r"(?i)(?:exec\s*\()",
        r"(?i)(?:eval\s*\()",
        r"(?i)(?:__import__)",
        r"(?i)(?:execfile\s*\()",
        r"(?i)(?:subprocess\.\w+\()",
        r'(?i)(?:os\.\w+\(\s*["\x27])',
    ]

    def __init__(self):
        self.rate_limits: Dict[str, List[float]] = {}
        self.audit_log: List[Dict[str, object]] = []
        self.compiled_injections = [re.compile(p) for p in self.INJECTION_PATTERNS]
        self.compiled_operations = [re.compile(p) for p in self.DANGEROUS_OPERATIONS]
        self.compiled_sqli = [re.compile(p) for p in self.SQL_INJECTION]
        self.compiled_nosqli = [re.compile(p) for p in self.NOSQL_INJECTION]
        self.compiled_cmdi = [re.compile(p) for p in self.COMMAND_INJECTION]
        self.compiled_xss = [re.compile(p) for p in self.XSS_PATTERNS]
        self.compiled_ssrf = [re.compile(p) for p in self.SSRF_PATTERNS]
        self.compiled_traversal = [re.compile(p) for p in self.PATH_TRAVERSAL]

    def _check_patterns(
        self, text: str, patterns: List[re.Pattern[str]], flag_name: str
    ) -> tuple[bool, list[str]]:
        flags: list[str] = []
        for pattern in patterns:
            if pattern.search(text):
                flags.append(flag_name)
                break
        return (True, flags) if not flags else (False, flags)

    def _append_audit_event(self, event: Dict[str, object]) -> None:
        self.audit_log.append(event)
        if len(self.audit_log) > self.MAX_AUDIT_ENTRIES:
            self.audit_log = self.audit_log[-self.MAX_AUDIT_ENTRIES :]

    def check_input(
        self, text: str, user_id: str = "anonymous", max_rpm: int = 60
    ) -> SecurityCheck:
        passed = 0
        failed = 0
        flags: list[str] = []
        threat_level = "none"

        now = time.monotonic()
        recent = [t for t in self.rate_limits.get(user_id, []) if now - t < 60]
        self.rate_limits[user_id] = recent
        if len(recent) >= max_rpm:
            failed += 1
            flags.append("rate_limit_exceeded")
            threat_level = _max_threat(threat_level, "medium")
        else:
            self.rate_limits[user_id].append(now)
            passed += 1

        if len(text) > 50_000:
            failed += 1
            flags.append("excessive_length")
            threat_level = _max_threat(threat_level, "medium")
        else:
            passed += 1

        injection_found = any(pattern.search(text) for pattern in self.compiled_injections)
        if injection_found:
            failed += 1
            flags.append("injection_detected")
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        if any(pattern.search(text) for pattern in self.compiled_operations):
            failed += 1
            flags.append("dangerous_operation")
            threat_level = _max_threat(threat_level, "critical")
        else:
            passed += 1

        _, sqli_flags = self._check_patterns(text, self.compiled_sqli, "sql_injection_detected")
        if sqli_flags:
            failed += 1
            flags.extend(sqli_flags)
            threat_level = _max_threat(threat_level, "critical")
        else:
            passed += 1

        _, nosqli_flags = self._check_patterns(text, self.compiled_nosqli, "nosql_injection_detected")
        if nosqli_flags:
            failed += 1
            flags.extend(nosqli_flags)
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        _, cmdi_flags = self._check_patterns(text, self.compiled_cmdi, "command_injection_detected")
        if cmdi_flags:
            failed += 1
            flags.extend(cmdi_flags)
            threat_level = _max_threat(threat_level, "critical")
        else:
            passed += 1

        _, xss_flags = self._check_patterns(text, self.compiled_xss, "xss_detected")
        if xss_flags:
            failed += 1
            flags.extend(xss_flags)
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        _, ssrf_flags = self._check_patterns(text, self.compiled_ssrf, "ssrf_detected")
        if ssrf_flags:
            failed += 1
            flags.extend(ssrf_flags)
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        _, traversal_flags = self._check_patterns(text, self.compiled_traversal, "path_traversal_detected")
        if traversal_flags:
            failed += 1
            flags.extend(traversal_flags)
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        sanitized = text
        for pattern, replacement in self.SECRET_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        if sanitized != text:
            flags.append("secrets_detected_and_masked")
        passed += 1

        threat_fingerprint = hashlib.sha256(
            (sanitized[:200] + user_id + str(len(sanitized))).encode("utf-8")
        ).hexdigest()[:16]

        self._append_audit_event(
            {
                "timestamp": time.time(),
                "user_id": user_id,
                "passed": passed,
                "failed": failed,
                "flags": flags,
                "threat_level": threat_level,
                "input_hash": hashlib.sha256(sanitized.encode("utf-8")).hexdigest()[:16],
                "threat_fingerprint": threat_fingerprint,
                "input_length": len(sanitized),
            }
        )

        return SecurityCheck(
            passed=failed == 0,
            checks_passed=passed,
            checks_failed=failed,
            flags=flags,
            sanitized_input=sanitized,
            threat_level=threat_level,
            details=f"{len(flags)} flags detected" if flags else "All checks passed",
        )

    def check_output(self, text: str, classification: Dict | None = None) -> SecurityCheck:
        passed = 0
        failed = 0
        flags: list[str] = []
        threat_level = "none"

        sanitized = text
        for pattern, replacement in self.SECRET_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        if sanitized != text:
            failed += 1
            flags.append("output_contains_secrets")
            threat_level = _max_threat(threat_level, "critical")
        else:
            passed += 1

        if any(word in text.lower() for word in ["guaranteed", "100%", "will definitely"]):
            failed += 1
            flags.append("unsafe_promise")
            threat_level = _max_threat(threat_level, "medium")
        else:
            passed += 1

        if any(word in text.lower() for word in ["your fault", "you should have", "you broke it"]):
            failed += 1
            flags.append("user_blame")
            threat_level = _max_threat(threat_level, "medium")
        else:
            passed += 1

        if len(text) > 10_000:
            failed += 1
            flags.append("excessive_output")
            threat_level = _max_threat(threat_level, "medium")
        else:
            passed += 1

        if not text or not text.strip():
            failed += 1
            flags.append("empty_response")
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        if any(pattern.search(text) for pattern in self.compiled_xss):
            failed += 1
            flags.append("output_xss_content")
            threat_level = _max_threat(threat_level, "high")
        else:
            passed += 1

        return SecurityCheck(
            passed=failed == 0,
            checks_passed=passed,
            checks_failed=failed,
            flags=flags,
            sanitized_input=sanitized,
            threat_level=threat_level,
            details=f"{len(flags)} flags detected" if flags else "Output clean",
        )

    def get_audit_report(self, last_n: int = 100) -> Dict:
        recent = self.audit_log[-last_n:]
        total = len(recent)
        passed = sum(1 for row in recent if row["failed"] == 0)
        flagged = [flag for row in recent for flag in row["flags"]]
        flag_counts: dict[str, int] = {}
        for flag in flagged:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

        threat_dist: dict[str, int] = {}
        for row in recent:
            level = str(row.get("threat_level", "none"))
            threat_dist[level] = threat_dist.get(level, 0) + 1

        unique_fingerprints = len(
            {
                row.get("threat_fingerprint", "")
                for row in recent
                if row["failed"] > 0
            }
        )

        return {
            "total_checks": total,
            "passed": passed,
            "failed_rate": round((total - passed) / max(total, 1) * 100, 1),
            "flag_counts": flag_counts,
            "total_flags": len(flagged),
            "threat_distribution": threat_dist,
            "unique_attack_fingerprints": unique_fingerprints,
            "audit_window": f"Last {last_n} checks",
        }

    def get_threat_summary(self, last_n: int = 50) -> Dict:
        recent = self.audit_log[-last_n:]
        blocked = [row for row in recent if row["failed"] > 0]

        top_flagged_users: dict[str, int] = {}
        top_threat_types: dict[str, int] = {}
        for row in blocked:
            user = str(row.get("user_id", "anonymous"))
            top_flagged_users[user] = top_flagged_users.get(user, 0) + 1
            for flag in row.get("flags", []):
                top_threat_types[str(flag)] = top_threat_types.get(str(flag), 0) + 1

        return {
            "total_blocked": len(blocked),
            "block_rate": round(len(blocked) / max(len(recent), 1) * 100, 1),
            "top_threat_types": dict(
                sorted(top_threat_types.items(), key=lambda item: item[1], reverse=True)[:10]
            ),
            "top_flagged_users": dict(
                sorted(top_flagged_users.items(), key=lambda item: item[1], reverse=True)[:5]
            ),
        }
