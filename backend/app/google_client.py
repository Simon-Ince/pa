"""Gmail / Calendar access using Simon's already-authorized OAuth token.

Loads the existing token file (which carries a refresh_token) and lets
google-auth refresh it in place as needed. Never runs an interactive OAuth
flow here.
"""
import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger("pa.google")

TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "/secrets/google_token.json")

# Scopes required for this dashboard's read-only usage.
GMAIL_CATEGORY_EXCLUSIONS = "-category:promotions -category:social"
GMAIL_FALLBACK_QUERY = (
    f"in:inbox is:unread newer_than:3d {GMAIL_CATEGORY_EXCLUSIONS}"
)
# Don't page forever if a fallback window is huge.
GMAIL_COUNT_CAP = 2000


class GoogleAuthError(Exception):
    pass


# Google's Calendar API tags the auto-generated all-day Home/Office markers
# from the "Working Locations" feature with eventType: "workingLocation"
# (confirmed against Simon's real calendar 2026-08-27 — two "Home" all-day
# entries both carried this field). Prefer that check; fall back to a
# summary denylist in case older/edge-case entries lack the field.
WORKING_LOCATION_EVENT_TYPE = "workingLocation"
WORKING_LOCATION_SUMMARY_DENYLIST = {"home", "office", "working from home", "wfh"}


def _is_working_location(event: dict) -> bool:
    if event.get("eventType") == WORKING_LOCATION_EVENT_TYPE:
        return True
    summary = (event.get("summary") or "").strip().lower()
    return summary in WORKING_LOCATION_SUMMARY_DENYLIST


class CredentialsHolder:
    """Holds a single refreshable Credentials object, shared across polling loops."""

    def __init__(self, token_file: str = TOKEN_FILE):
        self._token_file = token_file
        self._creds: Credentials | None = None
        self._lock = threading.Lock()

    def get(self) -> Credentials:
        with self._lock:
            if self._creds is None:
                self._creds = self._load()
            elif self._creds.expired and self._creds.refresh_token:
                logger.info("refreshing expired Google credentials")
                self._creds.refresh(Request())
            return self._creds

    def _load(self) -> Credentials:
        if not os.path.exists(self._token_file):
            raise GoogleAuthError(f"token file not found at {self._token_file}")
        with open(self._token_file, encoding="utf-8") as f:
            info = json.load(f)
        creds = Credentials.from_authorized_user_info(info)
        if not creds.valid:
            if creds.refresh_token:
                logger.info("loaded credentials are stale, refreshing via refresh_token")
                creds.refresh(Request())
            else:
                raise GoogleAuthError("token file has no usable refresh_token")
        return creds


def build_gmail_unread_query(since_epoch: int | None) -> tuple[str, str]:
    """Builds the unread-count query and reports which window it covers.

    Gmail's `after:{unix_epoch}` operator returns 0 when combined with
    `-category:` filters (confirmed against Simon's inbox 2026-08-28).
    Use `newer_than:{N}h` / `{N}d` instead, rounded up from generated_at
    with a one-hour buffer because Gmail only has hour granularity.
    """
    excl = GMAIL_CATEGORY_EXCLUSIONS
    if since_epoch is None:
        return GMAIL_FALLBACK_QUERY, "fallback_3d"
    age = time.time() - since_epoch
    if age < 0:
        return GMAIL_FALLBACK_QUERY, "fallback_3d"
    hours = max(1, math.ceil(age / 3600) + 1)
    if hours >= 48:
        days = min(14, max(2, math.ceil(hours / 24)))
        return f"in:inbox is:unread newer_than:{days}d {excl}", "since_last_triage"
    return f"in:inbox is:unread newer_than:{hours}h {excl}", "since_last_triage"


def fetch_gmail_unread_count(
    creds: Credentials, since_epoch: int | None = None
) -> tuple[int, str, str]:
    """Unread count for the SIGNAL panel.

    Pages message IDs only (no metadata). `resultSizeEstimate` is not used —
    with a search query it is often 0 or 1 even when mail exists.

    Returns (count, query, count_window) so the caller/frontend can display
    and link to the exact query used. Count is capped at GMAIL_COUNT_CAP.
    """
    query, count_window = build_gmail_unread_query(since_epoch)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    count = 0
    page_token = None
    while True:
        req = {
            "userId": "me",
            "q": query,
            "maxResults": 500,
            "fields": "messages/id,nextPageToken",
        }
        if page_token:
            req["pageToken"] = page_token
        resp = service.users().messages().list(**req).execute()
        count += len(resp.get("messages") or [])
        page_token = resp.get("nextPageToken")
        if not page_token or count >= GMAIL_COUNT_CAP:
            break
    return count, query, count_window


# Gmail's hash router blanks the page if the #search/ fragment is
# percent-encoded (`:` → `%3A`) or is a long paraphrased sentence.
# Distinctive tokens only — a full paraphrase ANDed together rarely matches.
_GMAIL_SEARCH_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "for", "on", "in", "with",
        "need", "needs", "needed", "review", "before", "after", "from", "this",
        "that", "into", "your", "you", "simon", "asked", "asking", "please",
        "due", "goes", "go", "live", "app", "help", "center", "changes",
    }
)
_GMAIL_THREAD_URL_CACHE: dict[str, str] = {}
_GMAIL_EMAIL_CACHE: str | None = None


def gmail_account_email(creds: Credentials) -> str | None:
    global _GMAIL_EMAIL_CACHE
    if _GMAIL_EMAIL_CACHE:
        return _GMAIL_EMAIL_CACHE
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me", fields="emailAddress").execute()
        _GMAIL_EMAIL_CACHE = profile.get("emailAddress") or None
    except Exception:
        logger.exception("gmail getProfile failed")
    return _GMAIL_EMAIL_CACHE


def gmail_ui_search_url(query: str, email: str | None = None) -> str:
    """Search URL with a query-string prefix so Gmail's SPA actually boots."""
    cleaned = re.sub(r"[#%&]", " ", query or "")
    cleaned = re.sub(r"\s+", "+", cleaned.strip())
    auth = f"authuser={email}&" if email else ""
    return f"https://mail.google.com/mail/u/0/?{auth}fs=1#search/{cleaned}"


def gmail_thread_open_url(thread_id: str, email: str | None = None) -> str:
    auth = f"authuser={email}&" if email else ""
    return f"https://mail.google.com/mail/u/0/?{auth}fs=1#all/{thread_id}"


def gmail_keyword_query(summary: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'.-]*", summary or "")
    proper = [
        t
        for t in tokens
        if t.lower() not in _GMAIL_SEARCH_STOPWORDS
        and len(t) > 1
        and (t[0].isupper() or any(c.isdigit() for c in t))
    ]
    if len(proper) >= 2:
        return " ".join(proper[:4])
    words = [t for t in tokens if t.lower() not in _GMAIL_SEARCH_STOPWORDS and len(t) > 2]
    return " ".join(words[:4])


def cached_gmail_thread_url(summary: str) -> str | None:
    return _GMAIL_THREAD_URL_CACHE.get((summary or "").strip().lower())


def resolve_gmail_thread_url(creds: Credentials, summary: str) -> str | None:
    """Find a real Gmail thread for a triage paraphrase, or None."""
    key = (summary or "").strip().lower()
    if not key:
        return None
    cached = _GMAIL_THREAD_URL_CACHE.get(key)
    if cached:
        return cached
    keywords = gmail_keyword_query(summary)
    if not keywords:
        return None
    email = gmail_account_email(creds)
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        queries = [keywords, f"newer_than:21d {keywords}"]
        for q in queries:
            resp = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=q,
                    maxResults=1,
                    fields="messages/id,messages/threadId",
                )
                .execute()
            )
            messages = resp.get("messages") or []
            if not messages:
                continue
            thread_id = messages[0].get("threadId")
            if not thread_id:
                continue
            url = gmail_thread_open_url(thread_id, email)
            _GMAIL_THREAD_URL_CACHE[key] = url
            logger.info("gmail thread matched %r via %r", summary[:60], q)
            return url
        logger.warning("gmail thread not found for %r (q=%r)", summary[:60], keywords)
    except Exception:
        logger.exception("gmail thread lookup failed for %r", summary[:80])
    return None


def resolve_triage_gmail_links(creds: Credentials, items: list) -> list:
    """Fill gmail item links with thread URLs where the API can find them."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        source = (row.get("source") or "").strip().lower()
        if source == "gmail":
            url = resolve_gmail_thread_url(creds, row.get("summary") or "")
            if url:
                row["link"] = url
        out.append(row)
    return out


def fetch_calendar_events(creds: Credentials, tz_name: str = "Europe/London") -> list[dict]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    now_local = datetime.now(tz)
    end_of_tomorrow = (now_local + timedelta(days=1)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    resp = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now_local.astimezone(timezone.utc).isoformat(),
            timeMax=end_of_tomorrow.astimezone(timezone.utc).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        .execute()
    )
    items = []
    for e in resp.get("items", []):
        if e.get("status") == "cancelled":
            continue
        # Filter out all-day working-location markers (Home/Office/etc) —
        # they're not real meetings, just location noise. See
        # _is_working_location() above for the detection logic/comment.
        if _is_working_location(e):
            continue
        start = e.get("start", {})
        start_str = start.get("dateTime") or start.get("date")
        all_day = "date" in start and "dateTime" not in start
        end = e.get("end", {})
        end_str = end.get("dateTime") or end.get("date")

        meet_link = e.get("hangoutLink")
        if not meet_link:
            for ep in e.get("conferenceData", {}).get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri")
                    break

        items.append(
            {
                "id": e.get("id"),
                "title": e.get("summary", "(no title)"),
                "start": start_str,
                "end": end_str,
                "all_day": all_day,
                "location": e.get("location"),
                "meet_link": meet_link,
                "html_link": e.get("htmlLink"),
            }
        )
    return items
