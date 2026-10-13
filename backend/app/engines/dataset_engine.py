"""
Dataset-based engine (default, no API key, no local LLM).

This is deliberately NOT a machine-learning model. It's a small, transparent
rule engine: keyword + regex intent detection, resolved against the actual
values present in the dataset (application names, severities, etc.), and
answered with pandas filtering. It exists so the product works out of the
box, is fully explainable, and never depends on a third-party API.

The only "soft matching" used is difflib.get_close_matches from the Python
standard library, to tolerate typos in application names - not a trained
model.
"""
import difflib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from ..roles import Role
from .. import nlp, warehouse

_DF: Optional[pd.DataFrame] = None


def load_data() -> pd.DataFrame:
    global _DF
    if _DF is None:
        # DuckDB bootstraps and persists demo data automatically when needed.
        # Application code reads only the canonical semantic_incidents view.
        df = warehouse.incidents_dataframe().copy()
        df["reported_at_dt"] = pd.to_datetime(df["reported_at_ts"])
        df["resolved_at_dt"] = pd.to_datetime(df["resolved_at_ts"], errors="coerce")
        df["resolution_hours_f"] = pd.to_numeric(df["resolution_hours"], errors="coerce")
        _DF = df
    return _DF


def reload_data() -> pd.DataFrame:
    global _DF
    warehouse.ensure_warehouse(force=True)
    _DF = None
    return load_data()


def _known_values(df: pd.DataFrame, column: str):
    return sorted(df[column].dropna().unique().tolist())


def _fuzzy_find(term: str, options: list, cutoff: float = 0.6):
    term_l = term.lower()
    lower_map = {o.lower(): o for o in options}
    if term_l in lower_map:
        return lower_map[term_l]
    # substring match first
    for o in options:
        if term_l in o.lower():
            return o
    matches = difflib.get_close_matches(term_l, list(lower_map.keys()), n=1, cutoff=cutoff)
    return lower_map[matches[0]] if matches else None


def _anchor_now(df: pd.DataFrame) -> datetime:
    # "now" for relative-time questions = the most recent reported_at in the
    # dataset, so the demo data always answers "yesterday" / "this week" etc.
    return df["reported_at_dt"].max().to_pydatetime()


TIME_PATTERNS = [
    (re.compile(r"\btoday\b"), lambda now: (now.replace(hour=0, minute=0, second=0), now)),
    (re.compile(r"\byesterday\b"), lambda now: (
        (now - timedelta(days=1)).replace(hour=0, minute=0, second=0),
        now.replace(hour=0, minute=0, second=0),
    )),
    (re.compile(r"\blast\s+week\b"), lambda now: (now - timedelta(days=7), now)),
    (re.compile(r"\bthis\s+week\b"), lambda now: (now - timedelta(days=now.weekday()), now)),
    (re.compile(r"\blast\s+month\b"), lambda now: (now - timedelta(days=30), now - timedelta(days=1))),
    (re.compile(r"\bthis\s+month\b"), lambda now: (now.replace(day=1), now)),
    (re.compile(r"\blast\s+30\s+days\b"), lambda now: (now - timedelta(days=30), now)),
    (re.compile(r"\bthis\s+quarter\b"), lambda now: (now - timedelta(days=90), now)),
    (re.compile(r"\blast\s+90\s+days\b"), lambda now: (now - timedelta(days=90), now)),
    (re.compile(r"\blast\s+24\s+hours?\b"), lambda now: (now - timedelta(hours=24), now)),
]


def _extract_time_range(question: str, now: datetime):
    q = question.lower()
    for pattern, fn in TIME_PATTERNS:
        if pattern.search(q):
            return fn(now)
    # Accept arbitrary operational windows such as "last 200 days" or
    # "past 45 days", not only the fixed dashboard-friendly shortcuts above.
    days_match = re.search(r"\b(?:last|past|previous)\s+(\d{1,4})\s+days?\b", q)
    if days_match:
        return now - timedelta(days=int(days_match.group(1))), now
    return None


def _comparison_window_days(question: str) -> Optional[int]:
    """Return a comparison window when the question asks for a prior period.

    A bare "previous period" is interpreted as two adjacent 90-day windows,
    which matches the operational dashboard's standard trend view.
    """
    q = question.lower()
    if not re.search(r"\b(?:previous|prior|preceding)\s+(?:period|window|\d{1,4}\s+days?)\b", q):
        return None
    days_match = re.search(r"\b(?:last|past|latest|previous|prior|preceding)\s+(\d{1,4})\s+days?\b", q)
    return int(days_match.group(1)) if days_match else 90


def _extract_severity(question: str, df: pd.DataFrame):
    priority_map = {"p1": "Critical", "p2": "High", "p3": "Medium", "p4": "Low"}
    priority = re.search(r"\bp\s*([1-4])\b", question.lower())
    if priority:
        return priority_map[f"p{priority.group(1)}"]
    for sev in _known_values(df, "severity"):
        if re.search(rf"\b{re.escape(sev.lower())}\b", question.lower()):
            return sev
    return None


def _extract_status(question: str, df: pd.DataFrame):
    # Use the final status reference. Follow-up questions are represented as
    # prior scope plus "Follow-up: ...", so a later "resolved" intentionally
    # replaces an earlier "unresolved" filter.
    q = question.lower()
    matches = []
    for match in re.finditer(r"\b(not\s+resolved|unresolved|still\s+open|active|pending|incomplete)\b", q):
        matches.append((match.start(), "Not Resolved"))
    for st in _known_values(df, "status"):
        for match in re.finditer(rf"\b{re.escape(st.lower())}\b", q):
            # Do not treat the word "resolved" inside "not resolved" as a
            # separate completed-status request.
            if st.lower() == "resolved" and re.search(r"not\s+$", q[:match.start()]):
                continue
            matches.append((match.start(), st))
    for match in re.finditer(r"\bopen\b", q):
        matches.append((match.start(), "Open"))
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def _extract_resolution_hours_limit(question: str) -> Optional[float]:
    """Return an upper resolution-duration bound expressed in hours.

    Accepts operations phrases such as "4 hours or less", "under 4 hours",
    and "within 4h".
    """
    q = question.lower()
    patterns = (
        r"\b(?:resolution(?:\s+time|\s+hours?)?\s*)?(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\s*(?:or\s+less|or\s+under|or\s+below|or\s+fewer)\b",
        r"\b(?:resolution(?:\s+time|\s+hours?)?\s*)?(?:under|below|less\s+than|within|at\s+most|no\s+more\s+than)\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b",
        r"\b(?:resolution(?:\s+time|\s+hours?)?\s*)?(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\s*or\s+less\b",
    )
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return float(match.group(1))
    return None


def _extract_resolution_hours_breach(question: str) -> Optional[float]:
    """Return the SLA threshold when the question asks for breaches."""
    q = question.lower()
    breach_requested = re.search(r"\b(?:breach(?:ed|es)?|beyond|over|exceed(?:ed|s)?|outside)\b", q)
    if not breach_requested or not re.search(r"\b(?:sla|resolution|resolved|resolution time)\b", q):
        return None
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b", q)
    return float(match.group(1)) if match else 24.0


def _extract_application(question: str, df: pd.DataFrame):
    apps = _known_values(df, "application")
    # look for any app name token (case-insensitive, allow partials)
    for app in apps:
        if app.lower() in question.lower():
            return app
    # try fuzzy match against individual capitalized-looking tokens
    # Only use fuzzy matching for plausible application terms. Short/common
    # grammar tokens (for example "not") can otherwise resemble an app name.
    ignored = {"not", "are", "the", "and", "for", "with", "from", "which", "what", "show", "open", "closed", "resolved", "unresolved", "incident", "incidents"}
    tokens = [token for token in re.findall(r"[A-Za-z]{3,}", question) if token.lower() not in ignored]
    for tok in tokens:
        match = _fuzzy_find(tok, apps, cutoff=0.72)
        if match:
            return match
    return None


def _extract_category(question: str, df: pd.DataFrame):
    for cat in _known_values(df, "category"):
        if cat.lower() in question.lower():
            return cat
    return None


def _extract_team(question: str, df: pd.DataFrame):
    for team in _known_values(df, "assigned_team"):
        if team.lower() in question.lower():
            return team
    return None


def _extract_root_cause(question: str, df: pd.DataFrame):
    """Return an exact recorded root-cause phrase mentioned in a question."""
    q = question.lower()
    matches = [cause for cause in _known_values(df, "root_cause") if cause and cause.lower() in q]
    return max(matches, key=len) if matches else None


def _extract_incident_id(question: str) -> Optional[str]:
    """Recognize explicit incident references such as INC-14372, case-insensitively."""
    match = re.search(r"\binc\s*-\s*(\d+)\b", question, flags=re.IGNORECASE)
    return f"INC-{match.group(1)}" if match else None


def _wants_root_cause(question: str) -> bool:
    return bool(re.search(r"r+o+t\s*cause|why did|explain(?:\s+the)?\s+(?:cause|reason)|recurring|repeated", question.lower()))


def _wants_count(question: str) -> bool:
    return bool(re.search(r"\bhow many\b|\bcount\b|\bnumber of\b", question.lower()))


def _wants_most(question: str) -> bool:
    return bool(re.search(r"most incidents|top\b|highest|largest|which (application(s)?|team|category|severity) (generated|has|had)", question.lower()))


def _aggregation_column(question: str) -> tuple[str, str]:
    """Choose the dimension requested by a ranking question."""
    q = question.lower()
    if re.search(r"\b(team|teams|owner|owners)\b", q):
        return "assigned_team", "Teams"
    if re.search(r"\b(category|categories|type|types)\b", q):
        return "category", "Categories"
    if re.search(r"\b(severity|severities)\b", q):
        return "severity", "Severities"
    return "application", "Applications"


def _wants_recurring(question: str) -> bool:
    return bool(re.search(r"recurring|repeated", question.lower()))


def _wants_trend(question: str) -> bool:
    return bool(re.search(r"\btrend(?:ing)?\b|over\s+(?:the\s+)?(?:last|past|previous)\s+\d+\s+days?", question.lower()))


def wants_report(question: str) -> bool:
    return bool(re.search(r"\breport\b", question.lower()))


STOPWORDS = {
    "what", "which", "wht", "how", "are", "show", "provide", "details", "incidents", "incident",
    "reported", "were", "was", "last", "this", "week", "month", "quarter",
    "year", "today", "yesterday", "give", "list", "with", "from", "that",
    "have", "there", "their", "identify", "recurring", "root", "causes",
    "cause", "applications", "application", "most", "generated", "critical",
    "days", "hours", "about", "over", "many", "count", "number", "some",
    "recent", "please", "tell", "find", "results", "issue", "issues", "follow", "up",
    "explain", "explanation", "reason", "reasons", "why", "root", "rrot",
    "one", "ones", "these", "those", "them", "same", "previous", "above", "related",
    "linked", "link", "team", "teams", "impact", "impacts",
    "affect", "affects", "affected", "who", "owns", "owner", "owners", "owning",
    "the", "and", "for", "all", "details", "generate", "report",
    # Analysis language describes how to present the answer, not evidence
    # which every individual incident must literally contain.  Treating these
    # as title/description filters caused valid broad questions to return 0.
    "trend", "blast", "radius", "recurrence", "recurring", "scope", "filter", "total",
    "caused", "causing", "prevent", "prevention", "avoid", "mitigate", "mitigation", "were",
    "breach", "breached", "breaches", "sla", "resolution", "resolve", "resolved",
    "hour", "hours", "identify", "owners", "pending", "incomplete",
}

# Governed operational playbooks make free-tier root-cause answers useful and
# auditable. They are not inferred from the count; each maps a known cause to
# an explanation, diagnostic evidence and a preventative control.
ROOT_CAUSE_PLAYBOOKS = {
    "Misconfigured auto-scaling policy": ("Capacity did not increase or decrease at the correct threshold.", "Compare demand, desired/actual replica counts, scaling events, and throttling around the incident.", "Set load-tested thresholds, minimum capacity, cooldowns, and an alert when desired capacity cannot be met."),
    "Third-party API rate limiting": ("An upstream provider rejected calls after a quota or burst threshold was exceeded.", "Review 429 responses, provider quota dashboards, request rate, and retry volume.", "Apply exponential backoff with jitter, request throttling, caching, quota monitoring, and a provider fallback where possible."),
    "Unhandled null reference in edge case": ("An application code path used an absent value without validating it.", "Inspect stack traces, the input payload, and the release that introduced the failing path.", "Add input validation, null-safe handling, regression tests for the edge case, and error-rate alerts."),
    "Network partition between availability zones": ("Components in separate availability zones temporarily could not communicate reliably.", "Check packet loss, connection resets, routing changes, and cloud-network health for the affected zones.", "Use multi-AZ retry/circuit-breaker patterns, quorum-safe design, and alerts for cross-zone connectivity loss."),
    "Disk space exhaustion on host": ("A host or volume exhausted available storage, preventing normal writes or service operation.", "Check disk utilization trends, largest directories, log growth, and failed write events.", "Set capacity thresholds, log rotation, retention policies, and automated expansion or cleanup."),
    "Memory leak in service under sustained load": ("The service retained memory over time until pressure degraded or stopped it.", "Review heap growth, garbage-collection pauses, pod restarts, and load correlation.", "Profile allocations, fix retained references, set resource limits, and alert on sustained memory growth."),
    "Expired TLS certificate": ("A certificate passed its validity date, causing secure connections to fail.", "Check certificate expiry, TLS handshake errors, and deployment/renewal logs.", "Automate renewal, monitor expiry at 30/14/7 days, and test certificate rollout."),
    "Upstream AWS service degradation": ("A dependent AWS service degraded and affected the application path.", "Correlate AWS Health events, dependency error rates, and regional latency.", "Design graceful degradation, multi-region/fallback paths, dependency timeouts, and customer-impact runbooks."),
    "Database connection pool exhaustion": ("All available database connections were occupied or leaked.", "Check active connections, pool wait time, slow queries, and connection lifetime metrics.", "Right-size pools, close leaked connections, tune slow queries, and alert on saturation."),
    "Faulty deployment / bad configuration push": ("A release or configuration change introduced the incident.", "Compare deployment timeline, configuration diffs, error rates, and rollback events.", "Use staged rollout, automated validation, feature flags, change approval, and rapid rollback."),
    "Unoptimized query causing table locks": ("A database query held locks or consumed resources long enough to block other work.", "Inspect query plans, lock waits, execution duration, and concurrent transactions.", "Add indexes, reduce transaction scope, set query timeouts, and test production-like query plans."),
    "DNS resolution failure": ("The service could not resolve a required hostname consistently.", "Review resolver errors, DNS latency, record changes, and network path to resolvers.", "Use redundant resolvers, appropriate caching, DNS health checks, and controlled record changes."),
    "Cache invalidation storm": ("A large cache invalidation caused a sudden surge of backend requests.", "Check cache hit rate, invalidation volume, backend load, and release events.", "Use staggered invalidation, request coalescing, TTL jitter, and cache-warming controls."),
    "Credential / secret rotation failure": ("A rotated credential was not propagated or accepted consistently by dependent services.", "Compare rotation time, authentication failures, secret versions, and rollout status.", "Use overlapping validity windows, automated propagation checks, canary validation, and rotation runbooks."),
}


def _root_cause_explanations(causes: list[str]) -> str:
    lines = []
    for cause in causes:
        playbook = ROOT_CAUSE_PLAYBOOKS.get(cause)
        if not playbook:
            continue
        meaning, signals, prevention = playbook
        lines.append(f"{cause}\n  What it means: {meaning}\n  Validate: {signals}\n  Prevent: {prevention}")
    return "\n\n".join(lines)


def _root_cause_notes(causes: list[str]) -> list[dict[str, str]]:
    """Structured operational notes for report cards and Word export."""
    notes = []
    for cause in causes:
        playbook = ROOT_CAUSE_PLAYBOOKS.get(cause)
        if not playbook:
            continue
        meaning, signals, prevention = playbook
        notes.append({"cause": cause, "meaning": meaning, "validate": signals, "prevention": prevention})
    return notes


def _extract_keywords(question: str, exclude: set) -> list:
    tokens = re.findall(r"[A-Za-z]{3,}", question)
    keywords = []
    for tok in tokens:
        low = tok.lower()
        if low in STOPWORDS or low in exclude:
            continue
        keywords.append(low)
    return keywords


def _keyword_score(row, keywords: list) -> int:
    if not keywords:
        return 0
    # A phrase appearing in the incident title is the strongest signal for a
    # detail request. Root-cause matches are supporting evidence only: without
    # this weighting, any newer incident sharing an AWS root cause could beat
    # the actual incident titled "AWS outage".
    title = str(row.get("title", "")).lower()
    description = str(row.get("description", "")).lower()
    root_cause = str(row.get("root_cause", "")).lower()
    return sum(
        3 if kw in title else 2 if kw in description else 1 if kw in root_cause else 0
        for kw in keywords
    )


def _filter_by_keywords(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """Keep rows where every requested free-text term appears in incident evidence.

    Entity filters (application, severity, status, and so on) are applied
    separately. This covers operational terms such as ``AWS`` that may occur
    in a title, description (when available), or root cause without being an
    application name.
    """
    if not keywords or df.empty:
        return df
    evidence_columns = [column for column in ("title", "description", "root_cause") if column in df.columns]
    evidence = (
        df[evidence_columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
    )
    mask = pd.Series(True, index=df.index)
    for keyword in keywords:
        mask &= evidence.str.contains(re.escape(keyword), regex=True)
    return df[mask]


def _wants_details(question: str) -> bool:
    return bool(re.search(r"\b(detail|details|describe|information about)\b", question.lower()))


def _operational_summary(df: pd.DataFrame) -> str:
    """Explain the severity and operating state of a matched incident set."""
    if df.empty:
        return ""

    severity_order = ["Critical", "High", "Medium", "Low"]
    severity_counts = df.groupby("severity").size().reindex(severity_order, fill_value=0)
    severity_text = "; ".join(f"{level}: {int(count)}" for level, count in severity_counts.items())
    status_counts = df.groupby("status").size().sort_values(ascending=False)
    status_text = "; ".join(f"{status}: {int(count)}" for status, count in status_counts.items())
    top_apps = df.groupby("application").size().sort_values(ascending=False)
    top_app = f"{top_apps.index[0]} ({int(top_apps.iloc[0])})" if len(top_apps) else "not available"

    return (
        "\n\nQuick operational breakdown:\n"
        f"- Severity: {severity_text}\n"
        f"- Current status: {status_text}\n"
        f"- Most affected application: {top_app}\n"
        "- Severity guide: Critical = major business/service impact; High = significant impact; "
        "Medium = contained impact; Low = minor impact."
    )


def _shape_for_role(answer: str, sample_df: pd.DataFrame, role: Role, total_matches: int) -> str:
    """Put the same governed result into an audience-appropriate narrative."""
    if sample_df.empty or role.id == "engineer":
        return answer

    # Lists and aggregation queries deliberately return only a small table
    # sample. ``sample_df`` is the full filtered scope here, so summaries
    # remain accurate even when the table is limited.
    if total_matches > len(sample_df):
        # This branch is retained for callers that pass only a sample.
        return f"{role.label} view: the headline result covers {total_matches} matched incidents; the table is a limited sample.\n\n{answer}"

    open_count = int((sample_df["status"].str.lower() == "open").sum())
    critical_count = int((sample_df["severity"].str.lower() == "critical").sum())
    resolved = sample_df[sample_df["status"].str.lower().isin(["resolved", "closed"])]
    average_resolution = float(resolved["resolution_hours_f"].mean()) if len(resolved) else 0.0

    if role.id == "manager":
        workloads = sample_df.groupby("assigned_team").size().sort_values(ascending=False)
        busiest = f"{workloads.index[0]} ({int(workloads.iloc[0])})" if len(workloads) else "not available"
        in_progress = int((sample_df["status"].str.lower() == "in progress").sum())
        return (
            f"Manager operational summary: {total_matches} incident(s) match the requested scope. "
            f"{critical_count} are critical; {open_count} are open and {in_progress} are in progress. "
            f"The highest team workload is {busiest}.\n\n{answer}"
        )

    if role.id == "executive":
        in_progress = int((sample_df["status"].str.lower() == "in progress").sum())
        top_apps = sample_df.groupby("application").size().sort_values(ascending=False)
        top_app = f"{top_apps.index[0]} ({int(top_apps.iloc[0])})" if len(top_apps) else "not available"
        return (
            f"Executive risk summary: {total_matches} incident(s) match the requested scope; "
            f"{critical_count} are critical, with {open_count} open and {in_progress} in progress. "
            f"The most affected application is {top_app}.\n\n{answer}"
        )
    return answer


def answer_question(question: str, role: Role) -> dict:
    """Returns dict: {answer, matched_count, data(list of dict), intent}"""
    nlp_result = nlp.analyse(question)
    df = load_data()
    now = _anchor_now(df)
    working = df.copy()
    intent = {"nlp_intent": nlp_result.intent}

    # An incident ID is an exact primary-key lookup, not a fuzzy keyword query.
    incident_id = _extract_incident_id(question)
    if incident_id:
        working = working[working["incident_id"].str.upper() == incident_id]
        intent["incident_id"] = incident_id
        if working.empty:
            return _package(
                f"Incident {incident_id} was not found in the dataset.", working, role, intent, total_matches=0
            )
        record = working.iloc[0]
        resolution = (
            f"It was resolved in {record['resolution_hours']} hours."
            if record.get("resolution_hours", "") else "It is not yet resolved."
        )
        answer = (
            f"{record['incident_id']} — {record['title']}\n\n"
            f"This is a {record['severity']} {record['category']} incident affecting "
            f"{record['application']} in {record['environment']} ({record['region']}). "
            f"Status: {record['status']}. Reported: {record['reported_at']}. {resolution} "
            f"Root cause: {record.get('root_cause') or 'not recorded'}."
        )
        if _wants_root_cause(question):
            explanation = _root_cause_explanations([str(record.get("root_cause") or "")])
            answer += (
                f"\n\nWhy it happened:\n{explanation}"
                if explanation else "\n\nA root-cause explanation is unavailable because none was recorded for this incident."
            )
        return _package(answer, working, role, intent, total_matches=1)

    comparison_days = _comparison_window_days(question)
    # Do not pre-filter comparison requests: both the current and preceding
    # windows must be available below.
    time_range = None if comparison_days else _extract_time_range(question, now)
    if time_range:
        start, end = time_range
        working = working[(working["reported_at_dt"] >= start) & (working["reported_at_dt"] <= end)]
        intent["time_range"] = f"{start.date()} to {end.date()}"

    severity = _extract_severity(question, df)
    combined_trend = _wants_trend(question) and bool(
        re.search(r"\bcritical\b.*\btotal\b|\btotal\b.*\bcritical\b", question.lower())
    )
    if combined_trend:
        severity = None
    if severity:
        working = working[working["severity"] == severity]
        intent["severity"] = severity

    status = _extract_status(question, df)
    if status:
        if status == "Not Resolved":
            working = working[working["status"].str.lower().isin(["open", "in progress"])]
        else:
            working = working[working["status"] == status]
        intent["status"] = status

    application = _extract_application(question, df)
    if application:
        working = working[working["application"] == application]
        intent["application"] = application

    category = _extract_category(question, df)
    if category:
        working = working[working["category"] == category]
        intent["category"] = category

    team = _extract_team(question, df)
    if team:
        working = working[working["assigned_team"] == team]
        intent["assigned_team"] = team

    root_cause = _extract_root_cause(question, df)
    if root_cause:
        working = working[working["root_cause"] == root_cause]
        intent["root_cause"] = root_cause

    has_recorded_root_cause = "has recorded root cause" in question.lower()
    if has_recorded_root_cause:
        working = working[working["root_cause"].fillna("") != ""]
        intent["root_cause_recorded"] = True

    resolution_breach = _extract_resolution_hours_breach(question)
    resolution_limit = _extract_resolution_hours_limit(question) if resolution_breach is None else None
    if resolution_breach is not None:
        working = working[working["resolution_hours_f"].notna() & (working["resolution_hours_f"] > resolution_breach)]
        intent["resolution_hours"] = f"> {resolution_breach:g} hours (SLA breach)"
    elif resolution_limit is not None:
        # Blank duration means an incident is not resolved and therefore
        # cannot satisfy a completed-resolution SLA duration.
        working = working[working["resolution_hours_f"].notna() & (working["resolution_hours_f"] <= resolution_limit)]
        intent["resolution_hours"] = f"<= {resolution_limit:g} hours"

    # A named root cause is an exact evidence filter. Return its incident
    # population and governed prevention playbook directly rather than
    # treating helper wording such as "caused by" as a title keyword.
    if root_cause:
        explanation = _root_cause_explanations([root_cause])
        answer = f"{len(working)} incident(s) were recorded with the root cause: {root_cause}."
        if explanation:
            answer += "\n\nRoot-cause interpretation and preventive actions:\n\n" + explanation
        sample = working.sort_values("reported_at_dt", ascending=False).head(25)
        return _package(answer, sample, role, intent, total_matches=len(working), scope_df=working)

    if comparison_days:
        current_start = now - timedelta(days=comparison_days)
        previous_start = current_start - timedelta(days=comparison_days)
        current = working[(working["reported_at_dt"] > current_start) & (working["reported_at_dt"] <= now)]
        previous = working[(working["reported_at_dt"] > previous_start) & (working["reported_at_dt"] <= current_start)]
        current_count, previous_count = len(current), len(previous)
        difference = current_count - previous_count
        if previous_count:
            change = f"{abs(difference) / previous_count * 100:.1f}% " + ("increase" if difference >= 0 else "decrease")
        elif current_count:
            change = "increase from zero"
        else:
            change = "no incidents in either period"
        answer = (
            f"Incident volume in the latest {comparison_days} days was {current_count}, compared with "
            f"{previous_count} in the preceding {comparison_days} days: {change}."
        )
        sample = current.sort_values("reported_at_dt", ascending=False).head(15)
        intent["comparison_window"] = f"{comparison_days} days"
        return _package(answer, sample, role, intent, total_matches=current_count, scope_df=current)

    # A question such as "give me all AWS unresolved" must retrieve only
    # AWS-related unresolved incidents. Previously AWS was used merely to rank
    # the 790 unresolved rows, which made the reported match count incorrect.
    entity_values = {str(value).lower() for key, value in intent.items() if key != "nlp_intent"}
    # Intent values can be phrases (for example "Not Resolved"). Exclude the
    # individual terms as well, otherwise a status word is accidentally
    # required in title/root-cause text after its status filter already ran.
    entity_words = set().union(*(set(re.findall(r"[a-z]{3,}", value)) for value in entity_values)) if entity_values else set()
    if status:
        entity_words.update({"unresolved", "active", "still", "open", "progress"})
    if severity:
        entity_words.update({"severity", "priority", "p1", "p2", "p3", "p4"})
    if has_recorded_root_cause:
        entity_words.update({"has", "recorded", "root", "cause"})
    # Ranking language describes an aggregation, not literal incident text.
    # "Teams with the highest unresolved workload" must group all unresolved
    # records by team instead of searching each record for "highest".
    free_text_keywords = [] if _wants_most(question) else _extract_keywords(question, entity_values | entity_words)
    if free_text_keywords:
        working = _filter_by_keywords(working, free_text_keywords)
        intent["text_terms"] = ", ".join(free_text_keywords)

    # ---- Aggregation-style questions ----
    if _wants_most(question):
        aggregate_column, aggregate_label = _aggregation_column(question)
        counts = working.groupby(aggregate_column).size().sort_values(ascending=False)
        top = counts.head(5)
        lines = [f"{value}: {cnt} incident(s)" for value, cnt in top.items()]
        answer = (
            f"{aggregate_label} with the most incidents in the selected period:\n- "
            + "\n- ".join(lines)
            if lines else "No incidents matched that time period."
        )
        sample = working.sort_values("reported_at_dt", ascending=False).head(15)
        return _package(answer, sample, role, intent, total_matches=len(working), scope_df=working)

    if _wants_trend(question):
        if working.empty:
            answer = "No incidents matched the selected time period, so there is no trend to display."
        else:
            timeline = working.groupby(working["reported_at_dt"].dt.to_period("M")).size()
            labels = [f"{period.strftime('%b %Y')}: {int(count)}" for period, count in timeline.items()]
            answer = f"{len(working)} incident(s) match the selected trend scope. Monthly volume: {', '.join(labels)}."
            if combined_trend:
                critical_timeline = working[working["severity"] == "Critical"].groupby(working["reported_at_dt"].dt.to_period("M")).size()
                critical_labels = [f"{period.strftime('%b %Y')}: {int(critical_timeline.get(period, 0))}" for period in timeline.index]
                answer += f" Critical incidents by month: {', '.join(critical_labels)}."
        sample = working.sort_values("reported_at_dt", ascending=False).head(15)
        return _package(answer, sample, role, intent, total_matches=len(working), scope_df=working)

    if _wants_recurring(question) or _wants_root_cause(question):
        rc = working[working["root_cause"] != ""]
        counts = rc.groupby("root_cause").size().sort_values(ascending=False)
        top = counts.head(5)
        if len(top) == 0:
            answer = (
                "No incidents with a recorded root cause matched this scope. "
                "Root causes are recorded after resolution, so an unresolved-only scope has no root-cause evidence to explain."
                if status == "Not Resolved" else "No incidents with a recorded root cause matched this scope."
            )
        else:
            lines = [f"{cause} — {cnt} occurrence(s)" for cause, cnt in top.items()]
            answer = "Most frequent root causes:\n- " + "\n- ".join(lines)
            explanations = _root_cause_explanations([str(cause) for cause in top.index])
            if explanations:
                answer += "\n\nRoot-cause interpretation and preventive actions:\n\n" + explanations
        sample = rc.sort_values("reported_at_dt", ascending=False).head(15)
        result = _package(answer, sample, role, intent, total_matches=len(working), scope_df=working)
        # Keep the complete matched scope internal to the LangGraph workflow;
        # only its compact topology is returned to the browser.
        result["_graph_incident_ids"] = rc["incident_id"].astype(str).tolist()
        return result

    if _wants_count(question):
        n = len(working)
        answer = f"{n} incident(s) match your query"
        if intent:
            answer += " (" + ", ".join(f"{k}: {v}" for k, v in intent.items()) + ")"
        answer += "." + _operational_summary(working)
        sample = working.sort_values("reported_at_dt", ascending=False).head(15)
        return _package(answer, sample, role, intent, total_matches=n, scope_df=working)

    # Service ownership questions should answer the ownership part in prose,
    # not merely leave the user to infer it from a large incident table.
    if application and re.search(r"\b(?:who\s+owns|owner|owners|owning|responsible\s+team)\b", question.lower()):
        owners = working.groupby("assigned_team").size().sort_values(ascending=False)
        owner_lines = [f"{team} ({count})" for team, count in owners.items()]
        answer = (
            f"{application} has {len(working)} matching incident(s). "
            f"The teams recorded against those incidents are: {', '.join(owner_lines)}."
            if len(working) else f"No incidents were found for {application}."
        )
        sample = working.sort_values("reported_at_dt", ascending=False).head(25)
        return _package(answer, sample, role, intent, total_matches=len(working), scope_df=working)

    # ---- Default: list matching incidents, boosting free-text keyword matches ----
    exclude = {str(v).lower() for v in intent.values()}
    keywords = _extract_keywords(question, exclude)
    n = len(working)

    if keywords and n > 0:
        working = working.copy()
        working["_kw_score"] = working.apply(lambda r: _keyword_score(r, keywords), axis=1)
        top_score = working["_kw_score"].max()
        if top_score > 0:
            # Detail requests are expected to return the named incident, not
            # every record in the period that happens to share one word or a
            # root-cause tag. Require all meaningful query terms in the title
            # (e.g. AWS + outage) whenever such a precise match exists.
            title_matches = working[working["title"].str.lower().apply(lambda title: all(kw in title for kw in keywords))]
            if _wants_details(question) and not title_matches.empty:
                exact = title_matches.sort_values("reported_at_dt", ascending=False)
                record = exact.iloc[0]
                recovery = (
                    f"It was {record['status'].lower()} after {record['resolution_hours']} hours."
                    if record.get("resolution_hours", "") else f"It is currently {record['status'].lower()}."
                )
                answer = (
                    f"{record['incident_id']} was a {record['severity'].lower()} incident affecting "
                    f"{record['application']} in {record['environment']} ({record['region']}). "
                    f"The incident is {record['status'].lower()} and was reported on {record['reported_at']}.\n\n"
                    f"The recorded cause was {record.get('root_cause') or 'not recorded'}. {recovery}"
                )
                return _package(answer, exact.head(10), role, intent, total_matches=len(exact), scope_df=exact)
            # a specific free-text match exists (e.g. "AWS outage") - surface it first
            sample = working.sort_values(["_kw_score", "reported_at_dt"], ascending=[False, False]).head(25)
            best = sample.iloc[0]
            answer = (
                f"Best match: {best['incident_id']} — \"{best['title']}\". "
                f"{best.get('description', '')} "
                f"(status: {best['status']}, severity: {best['severity']}, reported: {best['reported_at']}). "
                f"{n} incident(s) matched overall in that period."
            )
            return _package(answer, sample, role, intent, total_matches=n, scope_df=working)

    sample = working.sort_values("reported_at_dt", ascending=False).head(25)
    if n == 0:
        answer = "No incidents matched your query. Try a different time range, application, or severity."
    else:
        parts = []
        if intent.get("application"):
            parts.append(f"application '{intent['application']}'")
        if intent.get("severity"):
            parts.append(f"severity '{intent['severity']}'")
        if intent.get("status"):
            parts.append(f"status '{intent['status']}'")
        if intent.get("category"):
            parts.append(f"category '{intent['category']}'")
        if intent.get("time_range"):
            parts.append(f"reported between {intent['time_range']}")
        filter_desc = f" for {', '.join(parts)}" if parts else ""
        shown = min(n, 25)
        answer = (
            f"Found {n} incident(s){filter_desc}. Showing {shown} most recent."
            + _operational_summary(working)
        )
    return _package(answer, sample, role, intent, total_matches=n, scope_df=working)


def generate_report(question: str, role: Role) -> dict:
    """Create a reproducible report from the incident data selected by the question."""
    base = answer_question(question, role)
    df = load_data()
    now = _anchor_now(df)
    working = df.copy()
    time_range = _extract_time_range(question, now)
    if time_range:
        start, end = time_range
        working = working[(working["reported_at_dt"] >= start) & (working["reported_at_dt"] <= end)]
    for column, value in (("severity", _extract_severity(question, df)), ("status", _extract_status(question, df)),
                          ("application", _extract_application(question, df)), ("category", _extract_category(question, df)),
                          ("assigned_team", _extract_team(question, df))):
        if value:
            working = working[working[column] == value]
    severity = working.groupby("severity").size().sort_values(ascending=False)
    apps = working.groupby("application").size().sort_values(ascending=False).head(5)
    monthly = working.assign(month=working["reported_at_dt"].dt.strftime("%Y-%m")).groupby("month").size().sort_index()
    causes = working[working["root_cause"] != ""].groupby("root_cause").size().sort_values(ascending=False).head(5)
    scope = base["intent"].get("time_range", "all available historical data")
    total = len(working)
    open_count = int((working["status"] == "Open").sum())
    critical_count = int((working["severity"] == "Critical").sum())
    resolved = working[working["status"].isin(["Resolved", "Closed"])]
    avg_resolution = round(float(resolved["resolution_hours_f"].mean() or 0), 2) if len(resolved) else 0
    top_app = apps.index[0] if len(apps) else "No application"
    top_app_count = int(apps.iloc[0]) if len(apps) else 0
    top_cause = causes.index[0] if len(causes) else "No recorded root cause"
    top_cause_count = int(causes.iloc[0]) if len(causes) else 0
    cause_notes = _root_cause_notes([str(cause) for cause in causes.index])
    resolution_note = (
        "The data records the final incident status and time to restore; it does not include a separate remediation-action field."
    )
    sections = [
        ("Executive summary", [f"{total} incidents matched the requested scope ({scope}).", f"Open incidents: {open_count}; critical incidents: {critical_count}; average resolution: {avg_resolution} hours." ]),
        ("Severity distribution", [f"{name}: {count}" for name, count in severity.items()]),
        ("Most affected applications", [f"{name}: {count}" for name, count in apps.items()]),
        ("Recurring root causes", [f"{name}: {count}" for name, count in causes.items()] or ["No resolved root causes in this scope."]),
        ("Root-cause notes", [
            f"{note['cause']}: {note['meaning']} Validate by: {note['validate']} Prevent recurrence by: {note['prevention']}"
            for note in cause_notes
        ] or ["No governed root-cause notes are available for this scope."]),
        ("Resolution evidence", [f"Resolved or closed: {len(resolved)}; average time to restore: {avg_resolution} hours.", resolution_note]),
    ]
    markdown = "# Incident analysis report\n\n" + "\n\n".join("## " + heading + "\n" + "\n".join(f"- {line}" for line in lines) for heading, lines in sections)
    trend_sentence = "Incident volume is distributed across the selected period."
    if len(monthly) >= 2:
        first, last = int(monthly.iloc[0]), int(monthly.iloc[-1])
        direction = "increased" if last > first else "decreased" if last < first else "remained stable"
        trend_sentence = f"Monthly volume {direction} from {first} incidents in {monthly.index[0]} to {last} in {monthly.index[-1]}."
    root_cause_sentence = (
        f"The main recurring cause was {top_cause}, appearing in {top_cause_count} incidents. "
        f"{cause_notes[0]['meaning']}"
        if cause_notes else "There were no recorded root causes in this scope."
    )
    base["answer"] = (
        f"I reviewed {total} incidents reported between {scope}. The overall position is manageable but needs attention: "
        f"{critical_count} incidents were critical and {open_count} are still open. Resolved or closed incidents took "
        f"an average of {avg_resolution} hours to restore.\n\n"
        f"{top_app} was the most affected application, with {top_app_count} incidents. {root_cause_sentence} "
        f"{trend_sentence} The report cards below include the severity split, a small incident evidence sample, and "
        "root-cause notes with recommended validation and prevention actions."
    )
    base["report"] = {
        "title": "Incident analysis report", "markdown": markdown, "matched_count": total,
        "stats": [{"label": "Matched incidents", "value": total}, {"label": "Critical", "value": critical_count}, {"label": "Open", "value": open_count}, {"label": "Avg resolution", "value": f"{avg_resolution}h"}],
        "severity": [{"label": str(name), "count": int(count)} for name, count in severity.items()],
        "applications": [{"label": str(name), "count": int(count)} for name, count in apps.items()],
        "root_causes": [{"label": str(name), "count": int(count)} for name, count in causes.items()],
        "root_cause_notes": cause_notes,
        "monthly": [{"label": str(name), "count": int(count)} for name, count in monthly.items()],
        # Keep a concise, role-governed evidence table in the downloadable
        # report. The complete matching set remains available through the API.
        "sample_incidents": working.sort_values("reported_at_dt", ascending=False)
        .head(8)[[column for column in role.visible_columns if column in working.columns]]
        .to_dict(orient="records"),
    }
    # The graph workflow consumes this internally and removes it before the
    # response is returned to the browser.
    base["_graph_incident_ids"] = working["incident_id"].astype(str).tolist()
    return base


def _package(answer: str, sample_df: pd.DataFrame, role: Role, intent: dict, total_matches: Optional[int] = None,
             scope_df: Optional[pd.DataFrame] = None) -> dict:
    cols = [c for c in role.visible_columns if c in sample_df.columns]
    records = sample_df[cols].to_dict(orient="records") if len(sample_df) else []
    matched_count = int(len(sample_df) if total_matches is None else total_matches)
    return {
        "answer": _shape_for_role(answer, scope_df if scope_df is not None else sample_df, role, matched_count),
        "matched_count": matched_count,
        "data": records,
        "intent": intent,
    }


def analytics_summary() -> dict:
    """Return deterministic dashboard metrics from the incident CSV."""
    df = load_data()
    resolved = df[df["status"].str.lower().isin(["resolved", "closed"])]
    by_month = (
        df.assign(month=df["reported_at_dt"].dt.strftime("%Y-%m"))
        .groupby("month").size().sort_index().tail(12)
    )
    by_week = (
        df.assign(week=df["reported_at_dt"].dt.strftime("%Y-W%U"))
        .groupby("week").size().sort_index().tail(12)
    )
    by_day = (
        df.assign(day=df["reported_at_dt"].dt.strftime("%Y-%m-%d"))
        .groupby("day").size().sort_index().tail(30)
    )
    recent_days = sorted(df["reported_at_dt"].dt.strftime("%Y-%m-%d").unique())[-30:]
    daily_frame = df.assign(day=df["reported_at_dt"].dt.strftime("%Y-%m-%d"))
    daily_total = daily_frame.groupby("day").size()
    daily_critical = daily_frame[daily_frame["severity"].str.lower() == "critical"].groupby("day").size()
    # The warehouse does not carry per-service SLA contracts. A 24-hour
    # resolution threshold is the standard operational breach indicator.
    daily_breaches = daily_frame[daily_frame["resolution_hours_f"] > 24].groupby("day").size()
    by_app = df.groupby("application").size().sort_values(ascending=False).head(8)
    by_severity = df.groupby("severity").size().reindex(["Critical", "High", "Medium", "Low"], fill_value=0)
    root_causes = (
        resolved[resolved["root_cause"] != ""]
        .groupby("root_cause").size().sort_values(ascending=False).head(6)
    )
    by_status = df.groupby("status").size().sort_values(ascending=False)
    by_team = df.groupby("assigned_team").size().sort_values(ascending=False).head(8)
    return {
        "total_incidents": int(len(df)),
        "open_incidents": int((df["status"].str.lower() == "open").sum()),
        "critical_incidents": int((df["severity"].str.lower() == "critical").sum()),
        "resolved_incidents": int(len(resolved)),
        "average_resolution_hours": round(float(resolved["resolution_hours_f"].mean() or 0), 2),
        "incidents_by_month": [{"label": label, "count": int(count)} for label, count in by_month.items()],
        "incidents_by_week": [{"label": label, "count": int(count)} for label, count in by_week.items()],
        "incidents_by_day": [{"label": label, "count": int(count)} for label, count in by_day.items()],
        "volume_vs_critical_by_day": [{"label": label, "total": int(daily_total.get(label, 0)), "critical": int(daily_critical.get(label, 0))} for label in recent_days],
        "sla_breaches_by_day": [{"label": label, "count": int(daily_breaches.get(label, 0))} for label in recent_days],
        "incidents_by_application": [{"label": label, "count": int(count)} for label, count in by_app.items()],
        "incidents_by_severity": [{"label": label, "count": int(count)} for label, count in by_severity.items()],
        "recurring_root_causes": [{"label": label, "count": int(count)} for label, count in root_causes.items()],
        "incidents_by_status": [{"label": label, "count": int(count)} for label, count in by_status.items()],
        "incidents_by_team": [{"label": label, "count": int(count)} for label, count in by_team.items()],
    }
