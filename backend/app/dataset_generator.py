"""
Generates synthetic but realistic Incident Management demo data.

The application uses this generator to bootstrap DuckDB automatically. Run
the API's `POST /api/dataset/reload` endpoint to regenerate local demo data.

No external dependencies (uses only the standard library) so the dataset
can be regenerated anywhere the backend runs.
"""
import csv
import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # deterministic dataset across runs

APPLICATIONS = [
    "PaymentGateway", "OrderService", "InventoryAPI", "CustomerPortal",
    "AuthService", "NotificationEngine", "ReportingHub", "MobileBFF",
    "SearchIndexer", "BillingEngine", "DataPipeline", "CDNEdge",
]

ENVIRONMENTS = ["Production", "Staging", "Development"]
ENV_WEIGHTS = [0.7, 0.2, 0.1]

REGIONS = ["US-East", "US-West", "EU-Central", "AP-South"]

SEVERITIES = ["Critical", "High", "Medium", "Low"]
SEVERITY_WEIGHTS = [0.08, 0.22, 0.40, 0.30]

STATUSES = ["Open", "In Progress", "Resolved", "Closed"]

TEAMS = [
    "Platform Engineering", "SRE", "Database Team", "Network Ops",
    "Application Support", "Security Team", "Cloud Infra",
]

CATEGORIES = [
    "Infrastructure", "Application Error", "Network", "Database",
    "Third-Party Dependency", "Deployment", "Security", "Performance",
]

ROOT_CAUSES = [
    "Memory leak in service under sustained load",
    "Misconfigured auto-scaling policy",
    "Expired TLS certificate",
    "Upstream AWS service degradation",
    "Database connection pool exhaustion",
    "Faulty deployment / bad configuration push",
    "Network partition between availability zones",
    "Third-party API rate limiting",
    "Unoptimized query causing table locks",
    "DNS resolution failure",
    "Disk space exhaustion on host",
    "Cache invalidation storm",
    "Unhandled null reference in edge case",
    "Credential / secret rotation failure",
]

REPORTERS = [
    "priya.sharma", "arjun.mehta", "kevin.oconnor", "li.wei",
    "fatima.khan", "james.carter", "ananya.rao", "daniel.kim",
    "sara.gomez", "vikram.singh",
]

TITLE_TEMPLATES = [
    "{app} experiencing elevated error rates",
    "{app} outage in {env}",
    "Latency spike on {app}",
    "{app} unavailable for {region} users",
    "Failed health checks on {app}",
    "{app} throwing 5xx errors intermittently",
    "Data sync failure in {app}",
    "{app} login/auth failures",
    "{app} degraded performance during peak hours",
    "{app} connection timeouts to downstream service",
]


def _weighted_choice(options, weights):
    return random.choices(options, weights=weights, k=1)[0]


def _random_date_within(days_back: int, anchor: datetime) -> datetime:
    delta_minutes = random.randint(0, days_back * 24 * 60)
    return anchor - timedelta(minutes=delta_minutes)


def generate_incidents(n: int = 5000, anchor: datetime = None):
    if anchor is None:
        # Keep relative-time demo queries aligned with the day the warehouse
        # is regenerated instead of letting the synthetic data age out.
        anchor = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)

    rows = []
    for i in range(1, n + 1):
        app = random.choice(APPLICATIONS)
        env = _weighted_choice(ENVIRONMENTS, ENV_WEIGHTS)
        region = random.choice(REGIONS)
        severity = _weighted_choice(SEVERITIES, SEVERITY_WEIGHTS)
        category = random.choice(CATEGORIES)
        root_cause = random.choice(ROOT_CAUSES)
        team = random.choice(TEAMS)
        reporter = random.choice(REPORTERS)

        reported_dt = _random_date_within(365, anchor)  # a full year of historical analysis
        status = _weighted_choice(
            STATUSES, [0.05, 0.10, 0.25, 0.60]
        )

        if status in ("Resolved", "Closed"):
            resolution_hours = round(random.expovariate(1 / 6) + 0.25, 2)
            resolution_hours = min(resolution_hours, 96)
            resolved_dt = reported_dt + timedelta(hours=resolution_hours)
        else:
            resolution_hours = None
            resolved_dt = None

        title = random.choice(TITLE_TEMPLATES).format(
            app=app, env=env, region=region
        )
        description = (
            f"{app} in {env} ({region}) reported a {severity.lower()} "
            f"severity {category.lower()} incident. Symptom: {title.lower()}. "
            f"Assigned to {team}."
        )

        rows.append({
            "incident_id": f"INC-{10000 + i}",
            "title": title,
            "description": description,
            "application": app,
            "environment": env,
            "region": region,
            "severity": severity,
            "status": status,
            "category": category,
            "assigned_team": team,
            "reporter": reporter,
            "root_cause": root_cause if status in ("Resolved", "Closed") else "",
            "reported_at": reported_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "resolved_at": resolved_dt.strftime("%Y-%m-%d %H:%M:%S") if resolved_dt else "",
            "resolution_hours": resolution_hours if resolution_hours else "",
        })

    # Seed a few well-known, "findable" incidents so sample questions from the
    # use-case doc (e.g. "the AWS outage reported last month") always resolve.
    landmark_dt = anchor - timedelta(days=27)
    rows.append({
        "incident_id": "INC-19001",
        "title": "AWS us-east-1 outage impacting PaymentGateway",
        "description": (
            "Upstream AWS service degradation in us-east-1 caused "
            "PaymentGateway to fail processing transactions for ~2 hours."
        ),
        "application": "PaymentGateway",
        "environment": "Production",
        "region": "US-East",
        "severity": "Critical",
        "status": "Closed",
        "category": "Third-Party Dependency",
        "assigned_team": "Cloud Infra",
        "reporter": "priya.sharma",
        "root_cause": "Upstream AWS service degradation",
        "reported_at": landmark_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "resolved_at": (landmark_dt + timedelta(hours=2, minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "resolution_hours": 2.17,
    })

    rows.sort(key=lambda r: r["reported_at"], reverse=True)
    return rows


FIELDNAMES = [
    "incident_id", "title", "description", "application", "environment",
    "region", "severity", "status", "category", "assigned_team", "reporter",
    "root_cause", "reported_at", "resolved_at", "resolution_hours",
]


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    from .warehouse import ensure_warehouse

    ensure_warehouse(force=True)
    print("Regenerated DuckDB incident warehouse.")
