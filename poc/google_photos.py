"""Authenticate with Google Photos API and fetch library metadata."""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    import requests as http_requests
except ImportError:
    print("Error: Google auth libraries not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
]

TOKEN_FILE = Path(__file__).parent / ".google_token.json"
CREDENTIALS_FILE = Path(__file__).parent / "google_credentials.json"
API_BASE = "https://photoslibrary.googleapis.com/v1"


@dataclass
class GooglePhoto:
    id: str
    filename: str
    creation_time: Optional[datetime]
    camera_make: Optional[str]
    camera_model: Optional[str]
    is_archived: bool


def _build_credentials_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }


def authenticate() -> Credentials:
    """Run OAuth2 flow and return credentials, caching token for reuse."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_id = os.getenv("GOOGLE_CLIENT_ID")
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

            if not client_id or not client_secret:
                # Fall back to credentials file if env vars not set
                if not CREDENTIALS_FILE.exists():
                    print(
                        "Error: Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env, "
                        "or place google_credentials.json in the poc/ directory."
                    )
                    sys.exit(1)
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
            else:
                config = _build_credentials_config(client_id, client_secret)
                flow = InstalledAppFlow.from_client_config(config, SCOPES)

            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    return creds


def _get_headers(creds: Credentials) -> dict:
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def fetch_all_photos(creds: Credentials, progress_callback=None) -> list[GooglePhoto]:
    """Paginate through entire Google Photos library and return metadata."""
    photos = []
    page_token = None
    page_num = 0

    while True:
        params = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token

        response = http_requests.get(
            f"{API_BASE}/mediaItems",
            headers=_get_headers(creds),
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("mediaItems", [])
        for item in items:
            metadata = item.get("mediaMetadata", {})
            photo_meta = metadata.get("photo", {})

            creation_time = None
            raw_time = metadata.get("creationTime")
            if raw_time:
                creation_time = datetime.fromisoformat(
                    raw_time.replace("Z", "+00:00")
                ).astimezone(tz=None).replace(tzinfo=None)

            photos.append(GooglePhoto(
                id=item["id"],
                filename=item.get("filename", ""),
                creation_time=creation_time,
                camera_make=photo_meta.get("cameraMake"),
                camera_model=photo_meta.get("cameraModel"),
                is_archived=False,  # API doesn't expose archive status in list
            ))

        page_token = data.get("nextPageToken")
        page_num += 1

        if progress_callback:
            progress_callback(len(photos))

        if not page_token:
            break

    return photos


def archive_photos(creds: Credentials, media_item_ids: list[str]) -> dict:
    """Archive a batch of Google Photos items (max 50 per request)."""
    results = {"success": [], "failed": []}

    for i in range(0, len(media_item_ids), 50):
        batch = media_item_ids[i:i + 50]
        response = http_requests.post(
            f"{API_BASE}/mediaItems:batchEdit",
            headers=_get_headers(creds),
            json={
                "mediaItemIds": batch,
                "archiveMediaItemPayload": {},
            },
        )

        if response.status_code == 200:
            results["success"].extend(batch)
        else:
            results["failed"].extend(batch)

    return results


def build_lookup_key(filename: str, date: Optional[datetime]) -> str:
    """Build a match key from filename + date truncated to the minute."""
    import os
    base = os.path.splitext(filename.lower())[0]
    if date:
        return f"{base}_{date.strftime('%Y%m%d_%H%M')}"
    return base
