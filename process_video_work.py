import glob
import threading
import json
import requests
import time
import yt_dlp
import tempfile
import os
import re
import traceback
from io import BytesIO
from resources.pydantic_models import Comments, Comment, User

TT_VID_SCRAPER_VERSION = "0.0.6"

work_server = os.environ.get(
    "WORK_SERVER", "https://archive-tiktok-worker.blazelight.dev"
)
concurrency = os.environ.get("CONCURRENCY", 1)

credit_user = os.environ.get("USERNAME", "anonymous")


def get_title_from_description(description):
    # Naive attempt. Replace hashtags and "stitch with"
    title = re.sub("#stitch with @\w+", "", description)
    title = re.sub("#\w+", "", title)
    title = title.strip()
    return title


def get_comments(video_id):
    headers = {
        "Accept-Encoding": "gzip, deflate, sdch",
        "Accept-Language": "en-US,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
    }

    headers["referer"] = f"https://www.tiktok.com/embed/{video_id}"

    cursor = 0

    comments = []

    r_session = requests.Session()

    while True:
        try:
            params = {
                "aweme_id": str(video_id),
                "count": "50",  # Max allowed by TT
                "cursor": str(cursor),
            }
            response = r_session.get(
                "https://www.tiktok.com/api/comment/list/",
                headers=headers,
                params=params,
                timeout=5,
            )
            data = response.json()

            comments.extend(data["comments"])

            old_cursor = cursor
            cursor = cursor + len(data["comments"])

            print(f"{video_id=}: Got {old_cursor} to {cursor} comments")

            if data["has_more"] != 1:
                break

            time.sleep(0.5)
        except:
            print(traceback.format_exc())
            return comments, cursor

    return comments, cursor


def get_users_from_comments(comments):
    users = list(set([comment["user"]["unique_id"] for comment in comments]))
    return users


def process_vid(video_id):
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)

        with yt_dlp.YoutubeDL(
            params={"outtmpl": "tiktok-%(id)s.%(ext)s", "quiet": True}
        ) as ytdl:
            try:
                info = ytdl.extract_info(f"https://www.tiktok.com/embed/{video_id}")
            except yt_dlp.utils.DownloadError:
                print(f"{video_id=}: Deleted video")
                return

        comments, comment_cursor = get_comments(video_id)
        min_comments_str = Comments.parse_obj(comments).json()
        print(f"{video_id=}: Got {len(comments)} comments")

        thumbnail_url = [
            x for x in info["thumbnails"] if x["id"] == "cover" and "jpeg" in x["url"]
        ][0]["url"]
        thumbnail = requests.get(thumbnail_url).content

        animated_thumbnail_url = [
            x for x in info["thumbnails"] if x["id"] == "dynamic_cover"
        ][0]["url"]
        animated_thumbnail = requests.get(animated_thumbnail_url).content

        # Try get captions
        captions = {}
        if info["interaction_stickers"]:
            for val in info["interaction_stickers"]:
                if "auto_video_caption_info" in val.keys():
                    url = val["auto_video_caption_info"]["auto_captions"][0]["url"][
                        "url_list"
                    ][0]
                    caption_res = requests.get(url).json()
                    captions = {
                        "track_info": json.loads(val["track_info"]),
                        **caption_res,
                    }

        # Trim the info
        del info["formats"]
        del info["thumbnails"]
        del info["requested_downloads"]
        del info["http_headers"]
        del info["webpage_url_domain"]
        del info["webpage_url_basename"]
        del info["_has_drm"]
        del info["duration_string"]
        del info["interaction_stickers"]
        if info.get("fulltitle"):
            del info["fulltitle"]
        if info.get("title"):
            del info["title"]

        info["_scraper_version"] = TT_VID_SCRAPER_VERSION
        info["_yt_dlp_commit"] = yt_dlp.version.RELEASE_GIT_HEAD

        r = requests.post(
            work_server + "/completed_work_video",
            data={
                "id": video_id,
                "info": json.dumps(info),
                "comments": min_comments_str,
                "captions": json.dumps(captions),
                "credit_user": credit_user,
                "comment_cursor": comment_cursor,
            },
            files={
                "thumbnail": BytesIO(thumbnail),
                "animated_thumbnail": BytesIO(animated_thumbnail),
                "video": open(glob.glob("*.mp4")[0], "rb"),
            },
        )

        return r


def worker():

    while True:
        try:
            # Get work
            r = requests.post(
                work_server + "/get_work",
                json={"job_type": "video", "max_items": 1},
            )
            for video_id in r.json()["video_ids"]:
                try:
                    start_time = time.time()
                    res = process_vid(video_id)
                    end_time = time.time()
                    print(
                        f"\r{video_id=}: Processed with {res=} in {end_time - start_time} seconds"
                        + " " * 30
                    )
                except Exception as e:
                    res = requests.post(
                        work_server + "/add_work",
                        json={"video_ids": [video_id], "priority": "requested"},
                    )
                    print(traceback.format_exc())
                    print("Requeueing")
                    time.sleep(15)
        except Exception as e:
            print(traceback.format_exc())
            time.sleep(5)


if __name__ == "__main__":

    threads = []
    concurrency = 1  # Force to 1 until chdir bug is fixed
    for _ in range(concurrency):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
