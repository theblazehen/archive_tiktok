from sqlalchemy import (
    ARRAY,
    INTEGER,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    BigInteger,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
    LargeBinary,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()
metadata = Base.metadata


class VideoData(Base):
    __tablename__ = "video_data"

    id = Column(BigInteger, primary_key=True, unique=True)
    creator = Column(Text)  # Human name
    username = Column(Text)
    uploader_id = Column(BigInteger)
    uploaded_date = Column(DateTime)
    hashtags = Column(ARRAY(Text))
    description = Column(Text)
    view_count = Column(Integer)
    repost_count = Column(Integer)
    comment_count = Column(Integer)
    sound = Column(Text)
    thumbnail = Column(LargeBinary)  # "cover" in yt-dlp info
    info_full = Column(JSONB)
    credit_user = Column(Text)

    comment_cursor = Column(Integer, default=0)
    is_active = Column(
        Boolean,
        default=True,
    )
    first_scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    last_scraped_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserScrape(Base):
    __tablename__ = "user_scrape"

    username = Column(String(24), primary_key=True, unique=True)
    last_checked = Column(
        DateTime(True), server_default=text("to_timestamp((0)::double precision)")
    )
