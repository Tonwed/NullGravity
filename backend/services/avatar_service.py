"""Avatar caching service.

Downloads user avatars from Google and caches them locally
so the frontend doesn't need to fetch from Google every time.
"""

import logging
from pathlib import Path

from database.connection import DATA_DIR

logger = logging.getLogger("avatar_service")

# Avatar cache directory
AVATAR_DIR = DATA_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)


def get_avatar_path(account_id: str) -> Path:
    """Get the local file path for a cached avatar."""
    return AVATAR_DIR / f"{account_id}.jpg"


def has_cached_avatar(account_id: str) -> bool:
    """Check if an avatar is cached locally."""
    path = get_avatar_path(account_id)
    return path.exists() and path.stat().st_size > 0


async def download_and_cache_avatar(account_id: str, avatar_url: str) -> bool:
    """Download avatar from URL and cache it locally.
    
    Returns True if successful, False otherwise.
    """
    if not avatar_url:
        return False

    try:
        from utils.proxy import get_http_client

        # Request a reasonably sized avatar (96px is good for UI)
        # Google avatar URLs support =sN suffix for size
        url = avatar_url
        if "googleusercontent.com" in url:
            # Strip existing size params and request 96px
            if "=s" in url:
                url = url.rsplit("=s", 1)[0]
            url = f"{url}=s96-c"

        async with get_http_client(timeout=15.0) as client:
            response = await client.get(url)

        if response.status_code != 200:
            logger.warning(
                f"Failed to download avatar for {account_id}: HTTP {response.status_code}"
            )
            return False

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.warning(
                f"Unexpected content type for avatar: {content_type}"
            )
            return False

        avatar_path = get_avatar_path(account_id)
        avatar_path.write_bytes(response.content)
        logger.info(
            f"Cached avatar for {account_id} ({len(response.content)} bytes)"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to cache avatar for {account_id}: {e}")
        return False


def delete_cached_avatar(account_id: str) -> None:
    """Delete a cached avatar file."""
    path = get_avatar_path(account_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete cached avatar: {e}")
