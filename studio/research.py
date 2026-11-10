"""Collect a bounded YouTube candidate sample through the public Data API."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def youtube(endpoint, key, **params):
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urlencode({**params, 'key': key})}"
    try:
        with urlopen(url, timeout=25) as response:
            return json.load(response).get("items", [])
    except HTTPError as error:
        raise ValueError(f"YouTube Data API returned HTTP {error.code}. Check key, API enablement, and quota.") from None
    except (URLError, TimeoutError):
        raise ValueError("Could not reach YouTube Data API. Use browser research instead.") from None


def date_string(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def discover(queries, region, language, limit, request=youtube, now=None):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise ValueError("Set YOUTUBE_API_KEY for API discovery or use browser research")
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    locale = {"regionCode": region}
    if language:
        locale["relevanceLanguage"] = language
    ids = set()
    for query in queries:
        results = request("search", key, part="snippet", type="video", q=query, order="viewCount", maxResults=50,
                          publishedAfter=date_string(start), publishedBefore=date_string(now), **locale)
        ids.update(item["id"]["videoId"] for item in results if "videoId" in item["id"])
    grouped = defaultdict(list)
    ids = sorted(ids)
    categories = {}
    if ids:
        categories = {item["id"]: item["snippet"]["title"]
                      for item in request("videoCategories", key, part="snippet", regionCode=region)}
    for start_index in range(0, len(ids), 50):
        batch = request("videos", key, part="snippet,contentDetails,statistics",
                        id=",".join(ids[start_index:start_index + 50]))
        for video in batch:
            info = video["snippet"]
            count = video.get("statistics", {}).get("viewCount")
            published = datetime.fromisoformat(info["publishedAt"].replace("Z", "+00:00"))
            if count is None or not start <= published <= now or info.get("liveBroadcastContent") != "none":
                continue
            duration = video["contentDetails"]["duration"]
            time = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
            if not time:
                continue
            hours, minutes, seconds = (int(value or 0) for value in time.groups())
            length = hours * 3600 + minutes * 60 + seconds
            if length == 0:
                continue
            video_id, channel_id = video["id"], info["channelId"]
            grouped[channel_id].append({
                "title": info["title"], "channel": info["channelTitle"], "published": info["publishedAt"],
                "views_at_observation": int(count), "duration_seconds": length,
                "category": categories.get(info.get("categoryId")), "url": f"https://www.youtube.com/watch?v={video_id}",
            })
    channels = []
    for channel_id, videos in grouped.items():
        videos.sort(key=lambda video: (-video["views_at_observation"], video["url"]))
        channels.append({"channel": videos[0]["channel"], "channel_url": f"https://www.youtube.com/channel/{channel_id}",
                         "eligible_sample_size": len(videos), "videos": videos[:3]})
    channels.sort(key=lambda entry: (-entry["videos"][0]["views_at_observation"], entry["channel_url"]))
    return {
        "platform": "YouTube", "region": region, "language_hint": language,
        "window_start_utc": date_string(start), "observed_at_utc": date_string(now), "queries": queries,
        "candidates_sampled": len(ids), "eligible_channels": len(channels),
        "metric": "Public cumulative view count at observation, ranked by strongest sampled video per channel.",
        "coverage": "Search sample. Verify channel genre, video format, and performance hypotheses from the original pages.",
        "channels": channels[:limit],
    }
