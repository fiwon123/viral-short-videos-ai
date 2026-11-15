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


RANKS = ("views", "velocity", "outlier")
SHORT_MAX_SECONDS = 180  # YouTube Shorts can run up to three minutes; length alone never proves a Short.


def _snapshot_views(folder):
    """Latest earlier observation per video URL from saved snapshots: {url: (observed_at, views)}."""
    seen = {}
    if not folder or not os.path.isdir(folder):
        return seen
    for name in sorted(os.listdir(folder)):
        if not (name.startswith("discover-") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        observed = data.get("observed_at_utc")
        for channel in data.get("channels", []):
            for video in channel.get("videos", []):
                if observed and (video["url"] not in seen or seen[video["url"]][0] < observed):
                    seen[video["url"]] = (observed, video["views_at_observation"])
    return seen


def discover(queries, region, language, limit, request=youtube, now=None, *, days=7, shorts=False,
             rank="views", snapshots=None):
    """Sample recent videos and rank channels by their strongest video.

    ``rank``: ``views`` (cumulative), ``velocity`` (views per hour since publish) or ``outlier``
    (views divided by the channel's subscribers, the "small channel, huge video" signal).
    ``snapshots``: a folder of earlier ``discover-*.json`` results; videos seen before get
    ``views_gained`` and ``views_per_hour_since_last``, and this result is saved there too.
    """
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise ValueError("Set YOUTUBE_API_KEY for API discovery or use browser research")
    if rank not in RANKS:
        raise ValueError(f"rank must be one of {', '.join(RANKS)}")
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    locale = {"regionCode": region}
    if language:
        locale["relevanceLanguage"] = language
    ids = set()
    for query in queries:
        extra = {"videoDuration": "short"} if shorts else {}
        results = request("search", key, part="snippet", type="video", q=query, order="viewCount", maxResults=50,
                          publishedAfter=date_string(start), publishedBefore=date_string(now), **locale, **extra)
        ids.update(item["id"]["videoId"] for item in results if "videoId" in item["id"])
    grouped = defaultdict(list)
    ids = sorted(ids)
    categories = {}
    if ids:
        categories = {item["id"]: item["snippet"]["title"]
                      for item in request("videoCategories", key, part="snippet", regionCode=region)}
    earlier = _snapshot_views(snapshots)
    for start_index in range(0, len(ids), 50):
        batch = request("videos", key, part="snippet,contentDetails,statistics",
                        id=",".join(ids[start_index:start_index + 50]))
        for video in batch:
            info = video["snippet"]
            stats = video.get("statistics", {})
            count = stats.get("viewCount")
            published = datetime.fromisoformat(info["publishedAt"].replace("Z", "+00:00"))
            if count is None or not start <= published <= now or info.get("liveBroadcastContent") != "none":
                continue
            duration = video["contentDetails"]["duration"]
            time = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
            if not time:
                continue
            hours, minutes, seconds = (int(value or 0) for value in time.groups())
            length = hours * 3600 + minutes * 60 + seconds
            if length == 0 or (shorts and length > SHORT_MAX_SECONDS):
                continue
            video_id, channel_id = video["id"], info["channelId"]
            age_hours = max(1.0, (now - published).total_seconds() / 3600)
            url = f"https://www.youtube.com/watch?v={video_id}"
            entry = {
                "title": info["title"], "channel": info["channelTitle"], "published": info["publishedAt"],
                "views_at_observation": int(count), "duration_seconds": length,
                "likely_short": length <= SHORT_MAX_SECONDS,
                "age_hours": round(age_hours, 1), "views_per_hour": round(int(count) / age_hours, 1),
                "views_per_day": round(int(count) / age_hours * 24),
                "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
                "comments": int(stats["commentCount"]) if "commentCount" in stats else None,
                "category": categories.get(info.get("categoryId")), "url": url,
            }
            if url in earlier:
                observed, views = earlier[url]
                hours_between = max(0.01, (now - datetime.fromisoformat(observed.replace("Z", "+00:00")))
                                    .total_seconds() / 3600)
                entry["views_gained"] = int(count) - int(views)
                entry["views_per_hour_since_last"] = round((int(count) - int(views)) / hours_between, 1)
                entry["previous_observation_utc"] = observed
            grouped[channel_id].append(entry)
    subscribers = {}
    channel_ids = sorted(grouped)
    for start_index in range(0, len(channel_ids), 50):
        for item in request("channels", key, part="statistics", id=",".join(channel_ids[start_index:start_index + 50])):
            stats = item.get("statistics", {})
            if not stats.get("hiddenSubscriberCount") and "subscriberCount" in stats:
                subscribers[item["id"]] = int(stats["subscriberCount"])
    score = {"views": lambda video: video["views_at_observation"],
             "velocity": lambda video: video["views_per_hour"],
             "outlier": lambda video: video.get("views_per_subscriber") or 0}[rank]
    channels = []
    for channel_id, videos in grouped.items():
        subs = subscribers.get(channel_id)
        for video in videos:
            video["views_per_subscriber"] = round(video["views_at_observation"] / subs, 2) if subs else None
        videos.sort(key=lambda video: (-score(video), video["url"]))
        channels.append({"channel": videos[0]["channel"], "channel_url": f"https://www.youtube.com/channel/{channel_id}",
                         "subscribers": subs, "eligible_sample_size": len(videos), "videos": videos[:3]})
    channels.sort(key=lambda entry: (-score(entry["videos"][0]), entry["channel_url"]))
    result = {
        "platform": "YouTube", "region": region, "language_hint": language, "days": days, "shorts_only": shorts,
        "window_start_utc": date_string(start), "observed_at_utc": date_string(now), "queries": queries,
        "candidates_sampled": len(ids), "eligible_channels": len(channels), "rank": rank,
        "metric": {"views": "Public cumulative views at observation.",
                   "velocity": "Views per hour since publish (cumulative views / age).",
                   "outlier": "Views divided by channel subscribers; high values mean the video broke out of "
                              "its audience."}[rank] + " Ranked by each channel's strongest sampled video.",
        "coverage": "Search sample, not a census. Verify genre, format and Shorts status on the original pages. "
                    "Re-run with the same --snapshots folder to measure real growth between observations.",
        "channels": channels[:limit],
    }
    if snapshots:
        os.makedirs(snapshots, exist_ok=True)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        with open(os.path.join(snapshots, f"discover-{stamp}.json"), "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        result["snapshot"] = os.path.join(snapshots, f"discover-{stamp}.json")
    return result
