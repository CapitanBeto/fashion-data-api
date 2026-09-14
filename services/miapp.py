import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN")
PROFILES_DATASET_ID = os.getenv("BRIGHTDATA_PROFILES_DATASET_ID", "gd_l1vikfch901nx3by4")
POSTS_DATASET_ID = os.getenv("BRIGHTDATA_POSTS_DATASET_ID", "gd_lk5ns7kz21pck8jpis")

BASE_URL = "https://api.brightdata.com/datasets/v3"
SCRAPE_URL = f"{BASE_URL}/scrape"
PROGRESS_URL = f"{BASE_URL}/progress"
SNAPSHOT_URL = f"{BASE_URL}/snapshot"

MAX_POLL_ATTEMPTS = 60
POLL_INTERVAL_SECONDS = 5
DONE_STATUS = "ready"
FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}


def _headers() -> dict:
    if not API_TOKEN:
        raise RuntimeError("BRIGHTDATA_API_TOKEN no está configurado")
    return {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}


async def _wait_for_snapshot(client: httpx.AsyncClient, snapshot_id: str) -> None:
    for _ in range(MAX_POLL_ATTEMPTS):
        response = await client.get(f"{PROGRESS_URL}/{snapshot_id}", headers=_headers())
        response.raise_for_status()

        status = response.json().get("status", "").lower()
        if status == DONE_STATUS:
            return
        if status in FAILED_STATUSES:
            raise RuntimeError(f"Bright Data falló procesando el snapshot {snapshot_id}: {status}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Bright Data no terminó el snapshot {snapshot_id} "
        f"después de {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS} segundos"
    )


async def scrape(dataset_id: str, payload, *, scrape_type: str | None = None, discover_by: str | None = None):
    """Trigger a Bright Data scrape and return the result, polling until ready if needed."""
    params = {"dataset_id": dataset_id, "notify": "false", "include_errors": "true"}
    if scrape_type:
        params["type"] = scrape_type
    if discover_by:
        params["discover_by"] = discover_by

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(SCRAPE_URL, headers=_headers(), params=params, json=payload)
        response.raise_for_status()
        result = response.json()

        snapshot_id = result.get("snapshot_id")
        if not snapshot_id:
            return result

        await _wait_for_snapshot(client, snapshot_id)

        snapshot_response = await client.get(
            f"{SNAPSHOT_URL}/{snapshot_id}", params={"format": "json"}, headers=_headers()
        )
        snapshot_response.raise_for_status()
        return snapshot_response.json()


def _clean_usernames(usernames: list[str]) -> list[str]:
    return [u.strip().lstrip("@") for u in usernames if u and u.strip().lstrip("@")]


async def get_profile(username: str):
    """Devuelve el perfil normalizado (o None), reutilizando get_profiles."""
    profiles = await get_profiles([username])
    return profiles[0] if profiles else None


async def get_profiles(usernames: list[str]):
    clean = _clean_usernames(usernames)
    if not clean:
        return []

    payload = {"input": [{"user_name": u} for u in clean], "limit_per_input": None}
    result = await scrape(PROFILES_DATASET_ID, payload, scrape_type="discover_new", discover_by="user_name")

    profiles = _extract_list(result, context="respuesta de Bright Data")
    normalized = [normalize_profile(p) for p in profiles if isinstance(p, dict)]

    await add_missing_post_metrics(normalized)
    return normalized


async def get_post(url: str):
    return await scrape(POSTS_DATASET_ID, [{"url": url}])


def _extract_list(result, *, context: str) -> list:
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        return result["data"]
    raise RuntimeError(f"Formato inesperado en {context}: {result}")


async def get_posts_metrics(urls: list[str]) -> dict:
    clean_urls = list(dict.fromkeys(str(u).strip() for u in urls if u))
    if not clean_urls:
        return {}

    result = await scrape(POSTS_DATASET_ID, [{"url": u} for u in clean_urls])
    posts = _extract_list(result, context="respuesta del dataset de posts")

    metrics = {}
    for post in posts:
        if not isinstance(post, dict) or not post.get("url"):
            continue
        metrics[post["url"]] = {
            "likes": post.get("likes") if post.get("likes") is not None else post.get("num_likes"),
            "comments": post.get("num_comments") if post.get("num_comments") is not None else post.get("comments"),
        }
    return metrics


async def add_missing_post_metrics(profiles: list[dict]) -> None:
    """Fill in likes/comments for any post missing them, via a single batched lookup."""
    urls_to_lookup = list(dict.fromkeys(
        post["url"]
        for profile in profiles
        for post in profile.get("posts", [])
        if post.get("url") and (post.get("likes") is None or post.get("comments") is None)
    ))

    if not urls_to_lookup:
        return

    metrics = await get_posts_metrics(urls_to_lookup)

    for profile in profiles:
        for post in profile.get("posts", []):
            post_metrics = metrics.get(post.get("url"))
            if not post_metrics:
                continue
            if post.get("likes") is None:
                post["likes"] = post_metrics.get("likes")
            if post.get("comments") is None:
                post["comments"] = post_metrics.get("comments")


def _clean_text(text) -> str | None:
    if not isinstance(text, str):
        return text
    return " ".join(text.split())


def normalize_profile(profile: dict) -> dict:
    posts = []
    for post in profile.get("posts", []):
        if not isinstance(post, dict):
            continue
        published = post.get("datetime")
        posts.append({
            "caption": _clean_text(post.get("caption")),
            "hashtags": post.get("post_hashtags") or [],
            "likes": post.get("likes"),
            "comments": post.get("comments"),
            "date_posted": published[:10] if published else None,
            "url": post.get("url"),
        })

    return {
        "account": profile.get("account") or profile.get("user_name") or profile.get("username") or "",
        "followers": profile.get("followers"),
        "following": profile.get("following"),
        "is_verified": profile.get("is_verified"),
        "posts": posts,
    }