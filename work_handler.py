import glob
from datetime import datetime
from typing import Literal, Optional
import time
import redis.asyncio as redis
import internetarchive
import yt_dlp
import tempfile
from pathlib import Path
import zstd

from resources.db_models import VideoData
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession

import os
import re
import multiprocessing
from fastapi import FastAPI, File, Depends, Form, UploadFile
from pydantic import BaseModel
import json
from typing import List
import asyncpg

redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
redis_password = os.environ.get("REDIS_PASSWORD", "")

output_dump_dir = os.environ.get("OUTPUT_DIR", "/output/")

redcon = None
db = None

app = FastAPI()


@app.on_event("startup")
async def init() -> None:
    global redcon
    global db
    redcon = redis.Redis(host=redis_host, password=redis_password)

    pg_host = os.environ.get("PG_HOST", "127.0.0.1")
    pg_user = os.environ.get("PG_USERNAME", "postgres")
    pg_pass = os.environ.get("PG_PASS", "")
    pg_dbname = os.environ.get("PG_DB_NAME", "postgres")

    db = sqlalchemy.ext.asyncio.create_async_engine(
        f"postgresql+asyncpg://{pg_user}:{pg_pass}@{pg_host}/{pg_dbname}",
        poolclass=NullPool,
    )


class WorkItem(BaseModel):
    video_ids: Optional[List[int]] = []
    users: Optional[List[str]] = []
    priority: Optional[
        Literal["requested"]
        | Literal["requested_user"]
        | Literal["recheck"]
        | Literal["scraped"]
    ] = "requested"


class GetWork(BaseModel):
    blocking: Optional[bool] = True
    block_timeout: Optional[int] = 10
    job_type: Literal["video"] | Literal["user"]
    max_items: Optional[int] = 10


@app.post("/get_work")
async def get_work(getwork: GetWork) -> dict[str, list[int]] | None:
    if getwork.job_type == "video":
        if getwork.blocking:
            res = await redcon.blmpop(
                getwork.block_timeout,
                4,
                "videos_to_process_requested",
                "videos_to_process_requested_user",
                "videos_to_process_recheck",
                "videos_to_process_scraped",
                direction="left",
                count=getwork.max_items,
            )
            if res and res[1]:
                return {"video_ids": [int(x.decode("utf-8")) for x in res[1]]}
            else:
                return {"video_ids": []}
        else:
            res = await redcon.lmpop(
                4,
                "videos_to_process_requested",
                "videos_to_process_requested_user",
                "videos_to_process_recheck",
                "videos_to_process_scraped",
                direction="left",
                count=getwork.max_items,
            )
            if res and res[1]:
                return {"video_ids": [int(x.decode("utf-8")) for x in res[1]]}
            else:
                return {"video_ids": []}

    elif getwork.job_type == "user":
        users = []
        if getwork.blocking:
            try_count = getwork.block_timeout
        else:
            try_count = 1

        while try_count > 0:
            try_count = try_count - 1

            async with AsyncSession(db) as session:
                query = text(
                    "select * from user_scrape where (now() - last_checked) > '6 hours' order by last_checked asc limit :limit"
                )
                query = query.bindparams(limit=getwork.max_items)
                usernames = (await session.execute(query)).scalars().all()
                users.extend(usernames)

                # Inefficient but sqlalchemy is frustrating
                for user in usernames:
                    query = text(
                        "update user_scrape set last_checked = now() where username = :username"
                    )
                    query = query.bindparams(username=user)
                    await session.execute(query)
                    await session.commit()

            if users:
                return {"users": users}

            if len(usernames) == 0 and try_count > 0:
                time.sleep(1)
        return {"users": users}


class CompletedWorkVideo(BaseModel):
    id: int
    info: dict
    comments: dict


def hashtags_from_title(title) -> list:
    hashtags = re.findall("#\w+", title)
    subjects = [x.replace("#", "") for x in hashtags]
    return subjects


@app.post("/completed_work_video")
async def completed_work_video(
    id: int = Form(...),
    info: str = Form(...),
    comments: str = Form(...),
    captions: str = Form(...),
    credit_user: str = Form(...),
    comment_cursor: str = Form(...),
    video: UploadFile = UploadFile(...),
    thumbnail: UploadFile = UploadFile(...),
    animated_thumbnail: UploadFile = UploadFile(...),
):

    info = json.loads(info)
    comments = json.loads(comments)
    captions = json.loads(captions)
    comment_cursor = int(comment_cursor)

    # Add captions text to info
    if captions:
        info["captions_text"] = " ".join([x["text"] for x in captions["utterances"]])

    if not validate_video_id(id):
        return {"error": "Invalid video id"}

    # Make output dir
    out_dir = Path(output_dump_dir) / info["uploader_id"] / str(id)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "info.json", "w") as f:
        str_info = json.dumps(info)
        f.write(str_info)

    if captions:
        with open(out_dir / "captions.json.zst", "wb") as f:
            captions_compressed = zstd.compress(
                json.dumps(captions).encode("utf-8"), 19
            )
            f.write(captions_compressed)

    with open(out_dir / "comments.json.zst", "wb") as f:
        comments_compressed = zstd.compress(json.dumps(comments).encode("utf-8"), 19)
        f.write(comments_compressed)

    with open(out_dir / "video.mp4", "wb") as f:
        f.write(video.file.read())

    with open(out_dir / "thumbnail.jpg", "wb") as f:
        f.write(thumbnail.file.read())
        thumbnail.file.seek(0)  # Reset position for later

    with open(out_dir / "animated_thumbnail.webp", "wb") as f:
        f.write(animated_thumbnail.file.read())

    # Write needful to postgres
    # I think we can reuse cursor for comments. TODO for later

    vid_data = VideoData(
        id=id,
        creator=info.get("creator", info["uploader"]),
        username=info["uploader"],
        uploader_id=int(info["uploader_id"]),
        uploaded_date=datetime.fromtimestamp(info["timestamp"]),
        hashtags=hashtags_from_title(info["description"]),
        description=info["description"],
        view_count=info["view_count"],
        repost_count=info["repost_count"],
        comment_count=info["comment_count"],
        sound=info["track"],
        thumbnail=thumbnail.file.read(),
        info_full=info,
        credit_user=credit_user,
        comment_cursor=comment_cursor,
    )

    print(
        f"Received video for {vid_data.username} ({vid_data.uploader_id}) - {vid_data.id} - {vid_data.description}"
    )

    async with AsyncSession(db) as session:
        session.add(vid_data)
        await session.commit()


def validate_video_id(video_id) -> bool:
    length_check = len(str(video_id)) == 19

    return length_check


def validate_username(username) -> bool:
    username = username.replace("@", "")  # Remove @ if we have it

    regex_match = bool(re.match(r"^(?!.*\.\.)(?!.*\.$)[^\W][\w.]{2,24}$", username))

    return regex_match


@app.post("/add_work")
async def addwork(workitem: WorkItem) -> dict[str, str]:
    ret_msg = ""

    # Handle all video IDs
    submitted_video_ids = [
        video_id for video_id in workitem.video_ids if validate_video_id(video_id)
    ]

    work_queue_names = {
        "requested": "videos_to_process_requested",
        "requested_user": "videos_to_process_requested_user",
        "recheck": "videos_to_process_recheck",
        "scraped": "videos_to_process_scraped",
    }

    if len(submitted_video_ids) > 0:
        t1 = time.time()
        seen_ids = await redcon.smismember("seen_tiktok", *submitted_video_ids)
        t2 = time.time()
        print(f"Redis check took {t2-t1} seconds")
        new_ids = [id for id, seen in zip(submitted_video_ids, seen_ids) if not seen]
        t3 = time.time()
        print(f"Redis filter took {t3-t2} seconds")
        if len(new_ids) > 0:
            await redcon.sadd("seen_tiktok", *new_ids)
            t4 = time.time()
            print(f"Redis sadd took {t4-t3} seconds")
            await redcon.lpush(work_queue_names[workitem.priority], *new_ids)
            t5 = time.time()
            print(f"Redis lpush took {t5-t4} seconds")
        ret_msg += f"Added {len(new_ids)} videos for processing. "

    for username in [u for u in workitem.users if validate_username(u)]:
        await pg_con.execute(
            "INSERT INTO user_scrape (username) VALUES ($1) ON CONFLICT DO NOTHING",
            username,
        )

    if len(workitem.users) > 0:
        ret_msg += f"Added {len(workitem.users)} users for scraping. "

    return {"result": ret_msg}


@app.get("/queue_len_vid")
async def queue_len_vid():
    return {
        "requested": await redcon.llen("videos_to_process_requested"),
        "requested_user": await redcon.llen("videos_to_process_requested_user"),
        "recheck": await redcon.llen("videos_to_process_recheck"),
        "scraped": await redcon.llen("videos_to_process_scraped"),
    }
