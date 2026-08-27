"""Gmail / Calendar access using Simon's already-authorized OAuth token.

Loads the existing token file (which carries a refresh_token) and lets
google-auth refresh it in place as needed. Never runs an interactive OAuth
flow here.
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger("pa.google")

TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "/secrets/google_token.json")

# Scopes required for this dashboard's read-only usage.
GMAIL_LIST_QUERY = "is:unread newer_than:3d -category:promotions -category:social"


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


def fetch_gmail_unread_count(creds: Credentials) -> int:
    """Cheap unread count for the same query the old full-list panel used —
    a single list call capped to 1 result, reading resultSizeEstimate rather
    than paging through and fetching every message's metadata.
    """
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    resp = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=GMAIL_LIST_QUERY,
            maxResults=1,
            labelIds=["INBOX"],
            fields="resultSizeEstimate",
        )
        .execute()
    )
    return int(resp.get("resultSizeEstimate", 0) or 0)


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
                "all_day": all_day,
                "location": e.get("location"),
                "meet_link": meet_link,
                "html_link": e.get("htmlLink"),
            }
        )
    return items
