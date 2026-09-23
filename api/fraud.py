from __future__ import annotations

import re
from urllib.parse import urlparse


OFFICIAL_DOMAINS = {
    "fema.gov",
    "disasterassistance.gov",
    "va.gov",
    "virginia.gov",
    "sba.gov",
    "weather.gov",
    "usa.gov",
    "211virginia.org",
}

RED_FLAGS = (
    (re.compile(r"\b(?:gift card|bitcoin|crypto|wire transfer)\b", re.I), "Requests unusual payment"),
    (re.compile(r"\b(?:act now|final warning|immediately pay|limited time)\b", re.I), "Uses pressure or urgency"),
    (re.compile(r"\b(?:fee to apply|processing fee|guaranteed approval)\b", re.I), "Claims a fee or guaranteed approval"),
    (re.compile(r"\b(?:social security|ssn|bank password|verification code)\b", re.I), "Asks for highly sensitive information"),
)


def scan_message(text: str) -> dict:
    findings = [label for pattern, label in RED_FLAGS if pattern.search(text)]
    urls = re.findall(r"https?://[^\s]+", text)
    domains: list[dict] = []
    for url in urls:
        hostname = (urlparse(url.rstrip(".,)")).hostname or "").lower()
        official = any(hostname == domain or hostname.endswith("." + domain) for domain in OFFICIAL_DOMAINS)
        domains.append({"domain": hostname, "official_allowlist": official})
        if not official:
            findings.append(f"Link is not on the official-domain allowlist: {hostname}")
    risk = "high" if len(findings) >= 2 else "caution" if findings else "no_obvious_red_flags"
    return {
        "risk": risk,
        "findings": list(dict.fromkeys(findings)),
        "domains": domains,
        "notice": "This is a red-flag check, not proof that a message is authentic. Verify through an agency website you navigate to yourself.",
        "report": "Report disaster fraud at ReportFraud.ftc.gov or call the FEMA Disaster Fraud Hotline at 866-720-5721.",
    }

