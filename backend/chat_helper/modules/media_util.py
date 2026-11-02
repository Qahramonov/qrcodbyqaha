"""Helpers to locate and download media referenced by a command (own message or the replied one)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiogram.types import Message

from ..commands.context import CommandContext, CommandError
from ..localization import p, tr

KINDS = ("voice", "video_note", "audio", "video", "animation", "photo", "sticker", "document")


@dataclass
class MediaRef:
    kind: str
    file_id: str
    file_size: int
    duration: int
    mime: str
    width: int = 0
    height: int = 0
    file_name: str = ""
    message: Message | None = None

    @property
    def is_image(self) -> bool:
        return self.kind == "photo" or (self.kind == "document" and self.mime.startswith("image/")) or \
            (self.kind == "sticker" and self.mime == "image/webp")

    @property
    def is_av(self) -> bool:
        return self.kind in ("voice", "video_note", "audio", "video", "animation") or \
            (self.kind == "document" and (self.mime.startswith("audio/") or self.mime.startswith("video/")))

    @property
    def has_video(self) -> bool:
        return self.kind in ("video_note", "video", "animation") or (self.kind == "document" and self.mime.startswith("video/"))


def media_of(m: Message | None) -> MediaRef | None:
    if m is None:
        return None
    if m.photo:
        ph = m.photo[-1]
        return MediaRef("photo", ph.file_id, ph.file_size or 0, 0, "image/jpeg", ph.width, ph.height, message=m)
    if m.voice:
        v = m.voice
        return MediaRef("voice", v.file_id, v.file_size or 0, v.duration or 0, v.mime_type or "audio/ogg", message=m)
    if m.video_note:
        v = m.video_note
        return MediaRef("video_note", v.file_id, v.file_size or 0, v.duration or 0, "video/mp4", v.length, v.length, message=m)
    if m.audio:
        a = m.audio
        return MediaRef("audio", a.file_id, a.file_size or 0, a.duration or 0, a.mime_type or "audio/mpeg",
                        file_name=a.file_name or "audio", message=m)
    if m.video:
        v = m.video
        return MediaRef("video", v.file_id, v.file_size or 0, v.duration or 0, v.mime_type or "video/mp4", v.width, v.height,
                        file_name=v.file_name or "video.mp4", message=m)
    if m.animation:
        a = m.animation
        return MediaRef("animation", a.file_id, a.file_size or 0, a.duration or 0, a.mime_type or "video/mp4", a.width, a.height, message=m)
    if m.sticker:
        s = m.sticker
        if s.is_animated or s.is_video:
            mime = "video/webm" if s.is_video else "application/x-tgsticker"
        else:
            mime = "image/webp"
        return MediaRef("sticker", s.file_id, s.file_size or 0, 0, mime, s.width, s.height, message=m)
    if m.document:
        d = m.document
        return MediaRef("document", d.file_id, d.file_size or 0, 0, d.mime_type or "application/octet-stream",
                        file_name=d.file_name or "file", message=m)
    return None


def find_media(ctx: CommandContext) -> MediaRef | None:
    return media_of(ctx.message) or media_of(ctx.reply)


def require_media(ctx: CommandContext, *, image: bool | None = None, av: bool | None = None) -> MediaRef:
    ref = find_media(ctx)
    if ref is None:
        raise CommandError(p(ctx.lang, "need_media"))
    if image and not ref.is_image:
        raise CommandError(tr(ctx.lang, "media_util.nuzhna_fotografiya_kartinka"))
    if av and not ref.is_av:
        raise CommandError(tr(ctx.lang, "media_util.nuzhno_golosovoe_audio_video_kruzhok"))
    max_bytes = ctx.app.config.media_max_input_mb * 1048576
    if ref.file_size and ref.file_size > max_bytes:
        raise CommandError(tr(ctx.lang, "media_util.fayl_slishkom_bolshoy_limit_mb", m=ctx.app.config.media_max_input_mb))
    if ref.duration and ref.duration > ctx.app.config.media_max_duration:
        raise CommandError(tr(ctx.lang, "media_util.slishkom_dlinnoe_media_limit",
                              s=ctx.app.config.media_max_duration))
    return ref


async def download(app: Any, ref: MediaRef, dest: Path) -> Path:
    await app.bot.download(ref.file_id, destination=dest)
    return dest
