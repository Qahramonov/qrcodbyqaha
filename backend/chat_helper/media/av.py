"""Audio/video operations on top of FFmpeg. Each op returns (output_path, send_kind, send_extra)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .ffmpeg import FFmpeg, MediaError, atempo_chain, volume_gain_db

SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 5.0)
VIDEO_MAX_SIDE = 720
NOTE_SIZE = 384

Result = tuple[Path, str, dict[str, Any]]


def _audio_out(kind: str, out_dir: Path) -> tuple[Path, list[str], str]:
    """Pick container/codec preserving the Telegram media type."""
    if kind == "voice":
        return out_dir / "result.ogg", ["-c:a", "libopus", "-b:a", "64k", "-ac", "1", "-ar", "48000"], "voice"
    return out_dir / "result.mp3", ["-c:a", "libmp3lame", "-q:a", "4"], "audio"


def _video_codec(crf: int = 26) -> list[str]:
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def _scale(max_side: int = VIDEO_MAX_SIDE) -> str:
    return f"scale='min({max_side},iw)':'min({max_side},ih)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2"


NOTE_FILTER = f"crop='min(iw,ih)':'min(iw,ih)',scale={NOTE_SIZE}:{NOTE_SIZE}"


class AV:
    def __init__(self, ff: FFmpeg, max_reverse: int = 60) -> None:
        self.ff = ff
        self.max_reverse = max_reverse

    async def _send_extra(self, out: Path, kind: str) -> dict[str, Any]:
        info = await self.ff.probe(out)
        dur = max(1, int(round(info["duration"])))
        if kind == "video_note":
            return {"duration": min(dur, 60), "length": NOTE_SIZE}
        if kind in ("video", "animation"):
            return {"duration": dur, "width": info["width"], "height": info["height"]}
        if kind in ("voice", "audio"):
            return {"duration": dur}
        return {}

    async def reverse(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        info = await self.ff.probe(src)
        if info["has_video"] and kind in ("video", "video_note", "animation", "document"):
            if info["duration"] > self.max_reverse:
                raise MediaError(f"video too long for reverse (max {self.max_reverse}s)")
            out = out_dir / "result.mp4"
            vf = (NOTE_FILTER if kind == "video_note" else _scale(640)) + ",reverse"
            args = ["-i", str(src), "-vf", vf]
            args += ["-af", "areverse", "-c:a", "aac", "-b:a", "96k"] if info["has_audio"] and kind != "animation" else ["-an"]
            args += _video_codec(27) + [str(out)]
            await self.ff.run(args, **kw)
            send = kind if kind in ("video_note", "animation") else "video"
            return out, send, await self._send_extra(out, send)
        if not info["has_audio"]:
            raise MediaError("no audio stream")
        out, codec, send = _audio_out(kind, out_dir)
        await self.ff.run(["-i", str(src), "-vn", "-af", "areverse", *codec, str(out)], **kw)
        return out, send, await self._send_extra(out, send)

    async def speed(self, src: Path, kind: str, out_dir: Path, factor: float, **kw: Any) -> Result:
        if not 0.25 <= factor <= 5.0:
            raise MediaError("speed must be 0.25..5")
        info = await self.ff.probe(src)
        if info["duration"] / factor > 600:
            raise MediaError("result would be too long")
        if info["has_video"] and kind in ("video", "video_note", "animation", "document"):
            out = out_dir / "result.mp4"
            vf = (NOTE_FILTER + "," if kind == "video_note" else _scale() + ",") + f"setpts=PTS/{factor}"
            args = ["-i", str(src), "-vf", vf]
            args += ["-af", atempo_chain(factor), "-c:a", "aac", "-b:a", "96k"] if info["has_audio"] and kind != "animation" else ["-an"]
            args += _video_codec() + [str(out)]
            await self.ff.run(args, **kw)
            send = kind if kind in ("video_note", "animation") else "video"
            return out, send, await self._send_extra(out, send)
        out, codec, send = _audio_out(kind, out_dir)
        await self.ff.run(["-i", str(src), "-vn", "-af", atempo_chain(factor), *codec, str(out)], **kw)
        return out, send, await self._send_extra(out, send)

    async def _audio_filter(self, src: Path, kind: str, out_dir: Path, af: str, **kw: Any) -> Result:
        info = await self.ff.probe(src)
        if not info["has_audio"]:
            raise MediaError("no audio stream")
        if info["has_video"] and kind in ("video", "video_note"):
            out = out_dir / "result.mp4"
            await self.ff.run(["-i", str(src), "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)], **kw)
            return out, kind, await self._send_extra(out, kind)
        out, codec, send = _audio_out(kind, out_dir)
        await self.ff.run(["-i", str(src), "-vn", "-af", af, *codec, str(out)], **kw)
        return out, send, await self._send_extra(out, send)

    async def volume(self, src: Path, kind: str, out_dir: Path, level: float = 25, **kw: Any) -> Result:
        return await self._audio_filter(src, kind, out_dir, f"volume={volume_gain_db(level)}dB", **kw)

    async def normalize(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        return await self._audio_filter(src, kind, out_dir, "loudnorm=I=-16:TP=-1.5:LRA=11", **kw)

    async def denoise(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        return await self._audio_filter(src, kind, out_dir, "highpass=f=70,lowpass=f=12000,afftdn=nf=-25", **kw)

    async def to_mp3(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        out = out_dir / "audio.mp3"
        await self.ff.run(["-i", str(src), "-vn", "-c:a", "libmp3lame", "-q:a", "3", str(out)], **kw)
        return out, "audio", await self._send_extra(out, "audio")

    async def to_voice(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        out = out_dir / "voice.ogg"
        await self.ff.run(["-i", str(src), "-vn", "-c:a", "libopus", "-b:a", "48k", "-ac", "1", "-ar", "48000", "-t", "600", str(out)], **kw)
        return out, "voice", await self._send_extra(out, "voice")

    async def to_circle(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        info = await self.ff.probe(src)
        if not info["has_video"]:
            raise MediaError("video required")
        out = out_dir / "note.mp4"
        args = ["-i", str(src), "-t", "60", "-vf", NOTE_FILTER]
        args += ["-c:a", "aac", "-b:a", "96k"] if info["has_audio"] else ["-an"]
        await self.ff.run(args + _video_codec(26) + [str(out)], **kw)
        return out, "video_note", await self._send_extra(out, "video_note")

    async def to_gif(self, src: Path, kind: str, out_dir: Path, **kw: Any) -> Result:
        info = await self.ff.probe(src)
        if not info["has_video"]:
            raise MediaError("video required")
        out = out_dir / "animation.mp4"
        await self.ff.run(["-i", str(src), "-t", "15", "-an", "-vf", _scale(480)] + _video_codec(28) + [str(out)], **kw)
        return out, "animation", await self._send_extra(out, "animation")

    async def watermark(self, src: Path, kind: str, out_dir: Path, layer_png: Path, **kw: Any) -> Result:
        """Overlay a full-frame transparent PNG (see image.watermark_layer); keeps video notes round."""
        info = await self.ff.probe(src)
        if not info["has_video"]:
            raise MediaError("video required")
        out = out_dir / "watermarked.mp4"
        note = kind == "video_note"
        fc = "[1:v][0:v]scale2ref[wm][base];[base][wm]overlay=0:0" + (f",{NOTE_FILTER}" if note else f",{_scale()}")
        args = ["-i", str(src), "-i", str(layer_png), "-filter_complex", fc, "-t", "60" if note else "600"]
        args += ["-c:a", "aac", "-b:a", "96k"] if info["has_audio"] else ["-an"]
        await self.ff.run(args + _video_codec(26) + [str(out)], **kw)
        send = "video_note" if note else ("animation" if kind == "animation" else "video")
        return out, send, await self._send_extra(out, send)

    async def trim(self, src: Path, kind: str, out_dir: Path, start: float, end: float | None, **kw: Any) -> Result:
        info = await self.ff.probe(src)
        dur = info["duration"]
        if start < 0 or start >= max(dur, 0.01) or (end is not None and end <= start):
            raise MediaError("bad trim range")
        rng = ["-ss", f"{start:.3f}"] + (["-to", f"{min(end, dur):.3f}"] if end is not None else [])
        if info["has_video"] and kind in ("video", "video_note", "animation", "document"):
            out = out_dir / "result.mp4"
            vf = NOTE_FILTER if kind == "video_note" else _scale()
            args = ["-i", str(src), *rng, "-vf", vf]
            args += ["-c:a", "aac", "-b:a", "128k"] if info["has_audio"] and kind != "animation" else ["-an"]
            await self.ff.run(args + _video_codec() + [str(out)], **kw)
            send = kind if kind in ("video_note", "animation") else "video"
            return out, send, await self._send_extra(out, send)
        out, codec, send = _audio_out(kind, out_dir)
        await self.ff.run(["-i", str(src), *rng, "-vn", *codec, str(out)], **kw)
        return out, send, await self._send_extra(out, send)

    async def compress(self, src: Path, kind: str, out_dir: Path, level: int = 2, **kw: Any) -> Result:
        info = await self.ff.probe(src)
        if info["has_video"]:
            crf = {1: 26, 2: 30, 3: 34}.get(level, 30)
            side = {1: 720, 2: 540, 3: 360}.get(level, 540)
            out = out_dir / "compressed.mp4"
            args = ["-i", str(src), "-vf", NOTE_FILTER if kind == "video_note" else _scale(side)]
            args += ["-c:a", "aac", "-b:a", "64k"] if info["has_audio"] else ["-an"]
            await self.ff.run(args + _video_codec(crf) + [str(out)], **kw)
            send = "video_note" if kind == "video_note" else "video"
            return out, send, await self._send_extra(out, send)
        out = out_dir / ("compressed.ogg" if kind == "voice" else "compressed.mp3")
        codec = ["-c:a", "libopus", "-b:a", f"{[32, 24, 16][min(max(level, 1), 3) - 1]}k"] if kind == "voice" else \
            ["-c:a", "libmp3lame", "-b:a", f"{[96, 64, 40][min(max(level, 1), 3) - 1]}k"]
        await self.ff.run(["-i", str(src), "-vn", *codec, str(out)], **kw)
        send = "voice" if kind == "voice" else "audio"
        return out, send, await self._send_extra(out, send)

    async def convert(self, src: Path, kind: str, out_dir: Path, fmt: str, **kw: Any) -> Result:
        fmt = fmt.lower().lstrip(".")
        audio = {"mp3": ["-c:a", "libmp3lame", "-q:a", "3"], "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
                 "opus": ["-c:a", "libopus", "-b:a", "96k"], "wav": ["-c:a", "pcm_s16le"], "m4a": ["-c:a", "aac", "-b:a", "160k"],
                 "flac": ["-c:a", "flac"]}
        if fmt in audio:
            out = out_dir / f"converted.{fmt}"
            await self.ff.run(["-i", str(src), "-vn", *audio[fmt], str(out)], **kw)
            return out, "document" if fmt in ("wav", "flac", "opus", "ogg") else "audio", {}
        info = await self.ff.probe(src)
        if not info["has_video"]:
            raise MediaError("unsupported target format for audio")
        if fmt == "mp4":
            out = out_dir / "converted.mp4"
            args = ["-i", str(src), "-vf", _scale(1280)] + (["-c:a", "aac"] if info["has_audio"] else ["-an"])
            await self.ff.run(args + _video_codec() + [str(out)], **kw)
            return out, "video", await self._send_extra(out, "video")
        if fmt == "webm":
            if info["duration"] > 60:
                raise MediaError("webm conversion limited to 60s on mobile")
            out = out_dir / "converted.webm"
            args = ["-i", str(src), "-vf", _scale(640), "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "36", "-deadline", "realtime",
                    "-cpu-used", "8"] + (["-c:a", "libopus"] if info["has_audio"] else ["-an"])
            await self.ff.run(args + [str(out)], **kw)
            return out, "document", {}
        if fmt == "gif":
            out = out_dir / "converted.gif"
            await self.ff.run(["-i", str(src), "-t", "15", "-vf", "fps=12,scale='min(480,iw)':-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
                               str(out)], **kw)
            return out, "document", {}
        raise MediaError("unsupported format")

    async def merge(self, sources: list[Path], kinds: list[str], out_dir: Path, **kw: Any) -> Result:
        if not 2 <= len(sources) <= 10:
            raise MediaError("merge needs 2..10 files")
        infos = [await self.ff.probe(s) for s in sources]
        all_video = all(i["has_video"] for i in infos)
        if all_video:
            w = infos[0]["width"] - infos[0]["width"] % 2 or 640
            h = infos[0]["height"] - infos[0]["height"] % 2 or 360
            w, h = min(w, 1280), min(h, 1280)
            has_audio = all(i["has_audio"] for i in infos)
            inputs: list[str] = []
            chains = []
            for idx, s in enumerate(sources):
                inputs += ["-i", str(s)]
                chains.append(f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{idx}]")
            concat_in = "".join(f"[v{i}]" + (f"[{i}:a]" if has_audio else "") for i in range(len(sources)))
            fc = ";".join(chains) + f";{concat_in}concat=n={len(sources)}:v=1:a={1 if has_audio else 0}[v]" + ("[a]" if has_audio else "")
            out = out_dir / "merged.mp4"
            args = inputs + ["-filter_complex", fc, "-map", "[v]"] + (["-map", "[a]", "-c:a", "aac"] if has_audio else ["-an"])
            await self.ff.run(args + _video_codec() + [str(out)], timeout=self.ff.timeout * 2, **kw)
            return out, "video", await self._send_extra(out, "video")
        if not all(i["has_audio"] for i in infos):
            raise MediaError("all files need audio")
        inputs = []
        for s in sources:
            inputs += ["-i", str(s)]
        fc = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono[a{i}];" for i in range(len(sources)))
        fc += "".join(f"[a{i}]" for i in range(len(sources))) + f"concat=n={len(sources)}:v=0:a=1[a]"
        send_voice = all(k == "voice" for k in kinds)
        out, codec, send = _audio_out("voice" if send_voice else "audio", out_dir)
        await self.ff.run(inputs + ["-filter_complex", fc, "-map", "[a]", *codec, str(out)], **kw)
        return out, send, await self._send_extra(out, send)

    async def extract_audio(self, src: Path, out_dir: Path, **kw: Any) -> Path:
        out = out_dir / "audio.ogg"
        await self.ff.run(["-i", str(src), "-vn", "-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-ar", "16000", str(out)], **kw)
        return out

    async def make_test_media(self, out_dir: Path, kind: str) -> Path:
        """Synthetic sample (sine tone / test pattern) for the APK effects demo and self-tests."""
        if kind in ("voice", "audio"):
            out = out_dir / ("sample.ogg" if kind == "voice" else "sample.mp3")
            codec = ["-c:a", "libopus"] if kind == "voice" else ["-c:a", "libmp3lame"]
            await self.ff.run(["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-f", "lavfi", "-i", "sine=frequency=660:duration=3",
                               "-filter_complex", "[0][1]amix=inputs=2,volume=0.5", *codec, str(out)])
            return out
        out = out_dir / "sample.mp4"
        await self.ff.run(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=3", "-f", "lavfi", "-i", "sine=frequency=500:duration=3",
                           "-shortest", "-c:a", "aac"] + _video_codec(30) + [str(out)])
        return out


async def gather_limited(coros: list, limit: int = 2) -> list:
    sem = asyncio.Semaphore(limit)

    async def run(c):
        async with sem:
            return await c
    return await asyncio.gather(*(run(c) for c in coros))
