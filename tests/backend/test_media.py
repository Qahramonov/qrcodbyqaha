"""Media Studio with real FFmpeg & Pillow: reverse, speed, volume, frames, memes, blur, formats, errors, cancellation, queue."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
from conftest import CONTACT, OWNER
from fakes import biz_message, business_connection, update_business_message, update_connection
from PIL import Image

from chat_helper.media import image as I
from chat_helper.media.av import AV
from chat_helper.media.ffmpeg import FFmpeg, MediaError, atempo_chain, volume_gain_db
from chat_helper.modules.media_cmds import parse_meme

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def av():
    return AV(FFmpeg(timeout=60), max_reverse=60)


@needs_ffmpeg
async def test_reverse_voice_and_video_note(av, tmp_path: Path):
    src = await av.make_test_media(tmp_path, "voice")
    out, kind, extra = await av.reverse(src, "voice", tmp_path)
    assert kind == "voice" and out.suffix == ".ogg" and extra["duration"] >= 2
    vsrc = await av.make_test_media(tmp_path, "video")
    out, kind, extra = await av.reverse(vsrc, "video_note", tmp_path)
    info = await av.ff.probe(out)
    assert kind == "video_note" and info["width"] == info["height"] == 384 and extra["length"] == 384


@needs_ffmpeg
async def test_speed_keeps_type_and_changes_duration(av, tmp_path: Path):
    src = await av.make_test_media(tmp_path, "audio")
    out, kind, extra = await av.speed(src, "audio", tmp_path, 2.0)
    info = await av.ff.probe(out)
    assert kind == "audio" and 1.2 <= info["duration"] <= 1.9
    out, kind, _ = await av.speed(src, "voice", tmp_path, 0.5)
    assert kind == "voice" and (await av.ff.probe(out))["duration"] >= 5
    with pytest.raises(MediaError):
        await av.speed(src, "audio", tmp_path, 9)


def test_volume_scale_and_atempo():
    assert volume_gain_db(0) == 0 and volume_gain_db(25) == 7.5 and volume_gain_db(100) == 30 and volume_gain_db(500) == 30
    assert atempo_chain(4).count("atempo") == 2 and atempo_chain(0.25).count("atempo") == 2


@needs_ffmpeg
async def test_volume_circle_gif_mp3(av, tmp_path: Path):
    vsrc = await av.make_test_media(tmp_path, "video")
    out, kind, _ = await av.volume(vsrc, "video", tmp_path, 25)
    assert kind == "video" and out.exists()
    out, kind, extra = await av.to_circle(vsrc, "video", tmp_path)
    assert kind == "video_note" and extra["length"] == 384
    out, kind, _ = await av.to_gif(vsrc, "video", tmp_path)
    assert kind == "animation" and not (await av.ff.probe(out))["has_audio"]
    out, kind, _ = await av.to_mp3(vsrc, "video", tmp_path)
    assert kind == "audio" and out.suffix == ".mp3"
    out, kind, _ = await av.trim(vsrc, "video", tmp_path, 0.5, 2.0)
    assert 1.2 <= (await av.ff.probe(out))["duration"] <= 1.8


@needs_ffmpeg
async def test_ffmpeg_error_on_garbage(av, tmp_path: Path):
    bad = tmp_path / "bad.ogg"
    bad.write_bytes(b"not a media file")
    with pytest.raises(MediaError):
        await av.reverse(bad, "voice", tmp_path)


@needs_ffmpeg
async def test_cancellation_kills_ffmpeg(av, tmp_path: Path):
    ev = asyncio.Event()

    async def cancel_soon():
        await asyncio.sleep(0.2)
        ev.set()
    asyncio.create_task(cancel_soon())
    with pytest.raises(MediaError):
        await av.ff.run(["-f", "lavfi", "-i", "sine=duration=600", "-f", "null", "-"], cancel=ev, timeout=30)


@needs_ffmpeg
async def test_timeout(av):
    with pytest.raises(MediaError, match="timeout"):
        await av.ff.run(["-f", "lavfi", "-re", "-i", "sine=duration=600", "-f", "null", "-"], timeout=1)


def test_image_tools(tmp_path: Path):
    im = I.demo_image((320, 240))
    for style in I.FRAME_STYLES:
        out = I.frame(im, style)
        assert out.size[0] > im.size[0]
    m = I.meme(im, "TOP", "bottom")
    assert m.size[0] >= 320
    assert I.blur(im, 5).size == im.size and I.pixelate(im, 8).size == im.size
    assert I.resize(im, "50%").size == (160, 120) and I.resize(im, "x120").size == (160, 120)
    assert I.crop(im, "1:1").size == (240, 240)
    assert I.rotate(im, 90).size == (240, 320)
    assert I.sticker(im).size[0] == 512
    with pytest.raises(MediaError):
        I.crop(im, "0,0,9999,10")
    path = I.save_image(im, tmp_path, "x", "webp")
    assert Image.open(path).format == "WEBP"
    with pytest.raises(MediaError):
        I.open_image(tmp_path / "missing.png")


def test_meme_syntax():
    assert parse_meme("текст") == (None, "текст")
    assert parse_meme("up ВЕРХ") == ("ВЕРХ", None)
    assert parse_meme("down НИЗ") == (None, "НИЗ")
    assert parse_meme("up верх | down низ") == ("верх", "низ")


@needs_ffmpeg
async def test_reverse_command_end_to_end(env):
    from aiogram.types import Voice
    bc = business_connection("bc1", OWNER)
    env.session.connections["bc1"] = bc
    await env.feed(update_connection(bc))
    d = env.app.media.files.job_dir("t")
    sample = await env.app.media.av.make_test_media(d, "voice")
    env.session.files["VOICE1"] = sample.read_bytes()
    voice_msg = biz_message("bc1", CONTACT, CONTACT, None, voice=Voice(file_id="VOICE1", file_unique_id="v1", duration=3))
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".reverse", reply_to=voice_msg, first_name="Owner")))
    for _ in range(100):
        if env.session.calls("SendVoice"):
            break
        await asyncio.sleep(0.1)
    sv = env.session.calls("SendVoice")
    assert sv and sv[0].business_connection_id == "bc1" and sv[0].reply_parameters.message_id == voice_msg.message_id
    for _ in range(20):
        if env.session.calls("DeleteBusinessMessages"):
            break
        await asyncio.sleep(0.05)
    assert env.session.calls("DeleteBusinessMessages")  # command removed (right can_delete_all_messages)
    job = await env.app.db.fetchone("SELECT * FROM media_jobs")
    assert job["status"] == "done"


async def test_media_size_limit(env):
    from aiogram.types import Voice
    bc = business_connection("bc1", OWNER)
    env.session.connections["bc1"] = bc
    await env.feed(update_connection(bc))
    big = biz_message("bc1", CONTACT, CONTACT, None, voice=Voice(file_id="BIG", file_unique_id="b", duration=3, file_size=50 * 1024 * 1024))
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".reverse", reply_to=big, first_name="Owner")))
    assert any("слишком большой" in t for t in env.session.sent_texts())


async def test_path_traversal_blocked(tmp_path: Path):
    from chat_helper.security.sanitize import safe_filename, safe_join
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../../etc/passwd")
    assert "/" not in safe_filename("../../evil.sh")


@needs_ffmpeg
async def test_remaining_av_operations_smoke(av, tmp_path: Path):
    """normalize, denoise, voice, compress, convert (audio+video), merge (audio+video), extract — each produces valid media."""
    for d in ("a", "v", "v2"):
        (tmp_path / d).mkdir()
    a = await av.make_test_media(tmp_path / "a", "audio")
    v = await av.make_test_media(tmp_path / "v", "video")
    v2 = await av.make_test_media(tmp_path / "v2", "video")
    checks = [
        (await av.normalize(a, "audio", tmp_path / "a"), "audio"),
        (await av.denoise(a, "audio", tmp_path / "a"), "audio"),
        (await av.to_voice(v, "video", tmp_path / "v"), "voice"),
        (await av.compress(v, "video", tmp_path / "v", 3), "video"),
        (await av.compress(a, "voice", tmp_path / "a", 2), "voice"),
        (await av.convert(a, "audio", tmp_path / "a", "wav"), "document"),
        (await av.convert(v, "video", tmp_path / "v", "webm"), "document"),
        (await av.convert(v, "video", tmp_path / "v", "gif"), "document"),
        (await av.merge([v, v2], ["video", "video"], tmp_path / "v"), "video"),
        (await av.merge([a, a], ["voice", "voice"], tmp_path / "a"), "voice"),
    ]
    for (out, kind, _), expect in checks:
        assert kind == expect, (out, kind)
        info = await av.ff.probe(out)
        assert out.stat().st_size > 0 and info["duration"] > 0, out
    single = (await av.ff.probe(v))["duration"]
    merged = checks[8][0][0]
    assert (await av.ff.probe(merged))["duration"] >= single * 1.8
    ex = await av.extract_audio(v, tmp_path / "v")
    info = await av.ff.probe(ex)
    assert info["has_audio"] and not info["has_video"]
    with pytest.raises(MediaError):
        await av.convert(a, "audio", tmp_path / "a", "mp4")


def test_photo_filters_keep_size_and_change_pixels():
    im = I.demo_image((200, 150))
    for fn in (I.bw, I.sepia, I.sharpen, lambda x: I.noise(x, 30), lambda x: I.brightness(x, 1.5),
               lambda x: I.contrast(x, 1.5), lambda x: I.mirror(x, "h"), lambda x: I.watermark(x, "Chat helper")):
        out = fn(im)
        assert out.size == im.size
        assert out.convert("RGB").tobytes() != im.convert("RGB").tobytes()
