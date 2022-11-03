from __future__ import annotations
from pydantic import BaseModel
from typing import List


class User(BaseModel):
    uid: str
    nickname: str
    unique_id: str


class Comment(BaseModel):
    cid: str  # Comment ID?
    text: str
    user: User
    create_time: int  # Unix time
    digg_count: int  # Likes
    reply_id: int
    reply_to_reply_id: int
    reply_comment: list[Comment] | None
    reply_comment_total: int | None
    comment_language: str


class Comments(BaseModel):
    __root__: list[Comment]
