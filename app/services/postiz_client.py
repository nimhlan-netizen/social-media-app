import logging
from pathlib import Path
from datetime import datetime, timezone

import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class PostizClient:
    def __init__(self):
        self.base_url = settings.postiz_api_url.rstrip("/")
        self.headers = {
            "Authorization": settings.postiz_api_key,
            "Accept": "application/json",
        }

    def _get_integration_ids(self) -> list[str]:
        """Return configured platform integration IDs."""
        ids = []
        for id_ in [
            settings.postiz_instagram_integration_id,
            settings.postiz_facebook_integration_id,
            settings.postiz_youtube_integration_id,
        ]:
            if id_ and id_.strip():
                ids.append(id_.strip())
        return ids

    def upload_media(self, file_path: str) -> dict:
        """Upload a video file to Postiz. Returns dict with id and path."""
        path = Path(file_path)
        url = f"{self.base_url}/api/public/v1/upload"

        logger.info(f"Uploading {path.name} to Postiz at {url}...")
        with httpx.Client(timeout=300) as client:
            with open(file_path, "rb") as f:
                response = client.post(
                    url,
                    headers=self.headers,
                    files={"file": (path.name, f, "video/mp4")},
                )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Postiz media upload failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        logger.info(f"Postiz upload response: {data}")

        media_id = data.get("id") or data.get("mediaId") or data.get("data", {}).get("id")
        media_path = data.get("path") or data.get("url") or data.get("data", {}).get("path", "")
        if not media_id:
            raise RuntimeError(f"Postiz upload response missing media ID: {data}")

        logger.info(f"Media uploaded to Postiz: id={media_id}")
        return {"id": str(media_id), "path": str(media_path)}

    def find_next_slot(self, integration_id: str) -> str:
        """Find the next available posting time slot for an integration. Returns ISO datetime string."""
        url = f"{self.base_url}/api/public/v1/find-slot/"
        params = {"integrationId": integration_id}

        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=self.headers, params=params)

        if response.status_code not in (200, 201):
            logger.warning(
                f"find-slot call failed ({response.status_code}): {response.text}. "
                f"Falling back to posting now."
            )
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        data = response.json()
        logger.info(f"find-slot response: {data}")

        slot = (
            data.get("date")
            or data.get("slot")
            or data.get("nextSlot")
            or data.get("data", {}).get("date")
        )
        if not slot:
            logger.warning(f"find-slot response has no date, posting now: {data}")
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        return slot

    def create_post(
        self,
        media: dict,
        caption: str,
        hashtags: list[str],
    ) -> str:
        """Create a scheduled post in Postiz for all configured platforms. Returns post ID."""
        integration_ids = self._get_integration_ids()
        if not integration_ids:
            raise RuntimeError(
                "No Postiz integration IDs configured. "
                "Set POSTIZ_INSTAGRAM_INTEGRATION_ID, POSTIZ_FACEBOOK_INTEGRATION_ID, "
                "and/or POSTIZ_YOUTUBE_INTEGRATION_ID in your .env"
            )

        hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
        full_caption = f"{caption}\n\n{hashtag_str}".strip()

        # Find the next slot using the first integration ID
        schedule_date = self.find_next_slot(integration_ids[0])
        logger.info(f"Scheduling post for: {schedule_date}")

        url = f"{self.base_url}/api/public/v1/posts"
        payload = {
            "type": "schedule",
            "date": schedule_date,
            "shortLink": False,
            "tags": [],
            "posts": [
                {
                    "integration": {"id": integration_id},
                    "value": [
                        {
                            "content": full_caption,
                            "image": [media],
                        }
                    ],
                }
                for integration_id in integration_ids
            ],
        }

        with httpx.Client(timeout=60) as client:
            response = client.post(
                url,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
            )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Postiz post creation failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        logger.info(f"Postiz post response: {data}")

        post_id = (
            data.get("id")
            or data.get("postId")
            or str(data.get("data", {}).get("id", "unknown"))
        )
        logger.info(f"Post created in Postiz: {post_id} → {len(integration_ids)} platforms")
        return str(post_id)

    def post_video(
        self,
        file_path: str,
        caption: str,
        hashtags: list[str],
    ) -> str:
        """Full flow: upload media + find slot + create scheduled post. Returns post ID."""
        media = self.upload_media(file_path)
        return self.create_post(media, caption, hashtags)
