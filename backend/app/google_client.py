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


def fetch_gmail_unread(creds: Credentials, max_results: int = 25) -> list[dict]:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=GMAIL_LIST_QUERY, maxResults=max_results, labelIds=["INBOX"])
        .execute()
    )
    messages = resp.get("messages", [])
    items = []
    for m in messages:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        internal_date_ms = int(msg.get("internalDate", "0") or "0")
        received_at = (
            datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc).isoformat()
            if internal_date_ms
            else None
        )
        items.append(
            {
                "id": m["id"],
                "from": headers.get("From", "(unknown sender)"),
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": msg.get("snippet", ""),
                "received_at": received_at,
                "link": f"https://mail.google.com/mail/u/0/#inbox/{m['id']}",
            }
        )
    items.sort(key=lambda x: x["received_at"] or "", reverse=True)
    return items


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
