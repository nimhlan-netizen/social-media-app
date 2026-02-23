import logging
from pathlib import Path
from typing import Optional

import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class PostizClient:
    def __init__(self):
        self.base_url = settings.postiz_api_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.postiz_api_key}",
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

    def upload_media(self, file_path: str) -> str:
        """Upload a video file to Postiz media library. Returns media ID."""
        path = Path(file_path)
        url = f"{self.base_url}/api/media"

        with httpx.Client(headers=self.headers, timeout=120) as client:
            with open(file_path, "rb") as f:
                response = client.post(
                    url,
                    files={"file": (path.name, f, "video/mp4")},
                )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Postiz media upload failed ({response.status_code}): {response.text}"
            )

        data = response.json()
        media_id = data.get("id") or data.get("mediaId") or data.get("data", {}).get("id")
        if not media_id:
            raise RuntimeError(f"Postiz upload response missing media ID: {data}")

        logger.info(f"Media uploaded to Postiz: {media_id}")
        return str(media_id)

    def create_post(
        self,
        media_id: str,
        caption: str,
        hashtags: list[str],
    ) -> str:
        """Create a post in Postiz for all configured platforms. Returns post ID."""
        integration_ids = self._get_integration_ids()
        if not integration_ids:
            raise RuntimeError(
                "No Postiz integration IDs configured. "
                "Set POSTIZ_INSTAGRAM_INTEGRATION_ID, POSTIZ_FACEBOOK_INTEGRATION_ID, "
                "and/or POSTIZ_YOUTUBE_INTEGRATION_ID in your .env"
            )

        hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
        full_caption = f"{caption}\n\n{hashtag_str}".strip()

        url = f"{self.base_url}/api/posts"
        payload = {
            "type": "now",
            "posts": [
                {
                    "integrationId": integration_id,
                    "value": [
                        {
                            "content": full_caption,
                            "media": [{"id": media_id}],
                        }
                    ],
                    "settings": {
                        "comments": False,
                    },
                }
                for integration_id in integration_ids
            ],
        }

        with httpx.Client(headers=self.headers, timeout=60) as client:
            response = client.post(url, json=payload)

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Postiz post creation failed ({response.status_code}): {response.text}"
            )

        data = response.json()
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
        """Full flow: upload media + create post. Returns post ID."""
        media_id = self.upload_media(file_path)
        return self.create_post(media_id, caption, hashtags)
