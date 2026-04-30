"""
SQLAlchemy ORM models for the Instagram DM Automation Tool.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    """User account for dashboard authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(String(100), nullable=True)
    avatar_url = Column(Text, nullable=True)
    role = Column(String(20), default="user", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login = Column(DateTime, nullable=True)
    last_ip = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Config(Base):
    """
    Table storing Instagram / Facebook API credentials.
    Each user has one configuration row.
    """
    __tablename__ = "config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    access_token = Column(Text, nullable=True)
    page_id = Column(String(100), nullable=True)
    instagram_account_id = Column(String(100), nullable=True)

    # OAuth profile fields
    ig_username = Column(String(100), nullable=True)
    ig_profile_pic = Column(Text, nullable=True)
    ig_followers = Column(Integer, nullable=True)
    ig_account_type = Column(String(50), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    oauth_connected = Column(Boolean, default=False)

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Campaign(Base):
    """
    A campaign links an Instagram Post/Story to trigger keywords,
    a comment reply template, and a DM message template.
    """
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    campaign_type = Column(String(20), nullable=False, default="comment")
    post_id = Column(String(100), nullable=True, index=True)
    story_id = Column(String(100), nullable=True, index=True)
    post_thumbnail_url = Column(Text, nullable=True)
    post_caption = Column(Text, nullable=True)
    keywords = Column(Text, nullable=False)
    comment_reply_text = Column(Text, nullable=True)
    dm_message_text = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # CTA button fields (optional)
    cta_enabled = Column(Boolean, default=False, nullable=False)
    cta_label = Column(String(100), nullable=True)
    cta_url = Column(Text, nullable=True)

    # Follow check fields (optional)
    require_follow = Column(Boolean, default=False, nullable=False)
    not_following_message = Column(Text, nullable=True)

    # Opening DM (sent before main DM)
    opening_dm_enabled = Column(Boolean, default=False, nullable=False)
    opening_dm_text = Column(Text, nullable=True)

    # Ask for email
    ask_email_enabled = Column(Boolean, default=False, nullable=False)
    ask_email_message = Column(Text, nullable=True)

    # Analytics counters
    trigger_count = Column(Integer, default=0, nullable=False)
    reply_sent_count = Column(Integer, default=0, nullable=False)
    dm_sent_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    processed_comments = relationship(
        "ProcessedComment", back_populates="campaign", cascade="all, delete-orphan"
    )


class ProcessedComment(Base):
    """
    Tracks every comment/story-reply that has been processed.
    Includes granular status for reply and DM actions, enabling retries.
    """
    __tablename__ = "processed_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(String(100), unique=True, nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    user_id = Column(String(100), nullable=True)
    username = Column(String(100), nullable=True)
    comment_text = Column(Text, nullable=True)
    action_taken = Column(String(20), nullable=False)  # "reply", "dm", "both", "none"

    # Granular status for retry support
    reply_status = Column(String(10), default="none")  # "sent", "failed", "none"
    dm_status = Column(String(10), default="none")      # "sent", "failed", "none"
    reply_error = Column(Text, nullable=True)
    dm_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaign = relationship("Campaign", back_populates="processed_comments")


class ErrorLog(Base):
    """Stores API errors and webhook processing failures."""
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(10), nullable=False, default="ERROR")
    source = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    campaign_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
