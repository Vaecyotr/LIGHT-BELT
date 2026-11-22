"""Render local media through the authored Show into a mapped strip timeline."""

import argparse
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np

from light_engine.cli import _configure_engine_show
from light_engine.clock import OfflineRenderClock
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.mapping.resolve import sample_edge_pixels
from light_engine.outputs import NullOutput


PANEL_WIDTH = 568


def preview_panel(frame, strip_zones, video, audio):
    strips = [strip for node in frame.digital_frames for strip in node.outputs]
    canvas = np.full((360, PANEL_WIDTH, 3), 18, dtype=np.uint8)
    text_color = (220, 220, 220)
    def label(text, x, y, size=0.46):
        cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, size,
                    text_color, 1, cv2.LINE_AA)

    label("REGION", 8, 20)
    label("INPUT", 92, 20)
    label("STRIP", 150, 20)
    label("MAPPED OUTPUT", 255, 20)
    region_order = {"top": 0, "left": 1, "right": 2, "bottom": 3}
    strips.sort(key=lambda s: (region_order.get(strip_zones[s.strip_id], 4), s.strip_id))
    row_height = 275 // len(strips)
    for i, strip in enumerate(strips):
        y = 30 + i * row_height
        region = strip_zones[strip.strip_id]
        pixels = np.rint(np.asarray(strip.pixels)[:, ::-1] * 255).astype(np.uint8)
        label(region.upper(), 8, y + 18)
        label(strip.strip_id, 150, y + 18)
        if video is not None and video.edge_profiles.get(region):
            colors = sample_edge_pixels(video.edge_profiles[region], len(pixels))
            swatch = np.rint(np.asarray(colors)[:, ::-1] * 255).astype(np.uint8)
            canvas[y:y + row_height - 5, 92:140] = cv2.resize(
                swatch[None], (48, row_height - 5), interpolation=cv2.INTER_NEAREST)
        elif video is not None:
            color = video.zone_colors.get(region, video.average_rgb)
            canvas[y:y + row_height - 5, 92:135] = np.rint(np.array(color[::-1]) * 255)
        canvas[y:y + row_height - 5, 255:PANEL_WIDTH - 8] = cv2.resize(
            pixels[None, :, :], (PANEL_WIDTH - 263, row_height - 5), interpolation=cv2.INTER_NEAREST)
    level = audio.rms if audio else 0.0
    label(f"AUDIO RMS  {level:.2f}", 8, 325)
    canvas[311:326, 175:PANEL_WIDTH - 8] = 45
    canvas[311:326, 175:175 + round((PANEL_WIDTH - 183) * level)] = (100, 200, 225)
    label(f"Media {frame.timestamp:.2f} s", 8, 351)
    return canvas


def screen_extension(frame, panel, width):
    """Draw the four screen-surround outputs at their installed positions."""
    canvas = np.full((408, width + 56 + PANEL_WIDTH, 3), 18, dtype=np.uint8)
    canvas[24:384, width + 56:] = panel
    strips = {s.strip_id: s for node in frame.digital_frames for s in node.outputs}
    rails = {
        "strip_11": (26, 5, width, 17), "strip_21": (26, 386, width, 17),
        "strip_31": (5, 24, 19, 360), "strip_41": (width + 28, 24, 19, 360),
    }
    for sid, (x, y, w, h) in rails.items():
        rgb = np.asarray(strips[sid].pixels)
        bgr = np.rint(rgb[:, ::-1] * 255).astype(np.uint8)
        ribbon = bgr[None] if h < w else bgr[:, None]
        canvas[y:y+h, x:x+w] = cv2.resize(ribbon, (w, h), interpolation=cv2.INTER_NEAREST)
    return canvas


def render(args):
    config = Config.get_instance(args.profile)
    fps = config.get("system.output_fps")
    engine = Engine(config, clock=OfflineRenderClock(fps))
    duration = _configure_engine_show(engine, str(args.show))
    if args.preview and not 0 <= args.preview[0] < args.preview[1] <= duration:
        raise ValueError("Preview interval must lie within the Show duration")
    engine.load_video(str(args.video))
    engine.load_audio(str(args.audio))
    source_w, source_h = engine._video_reader.resolution
    screen_width = max(2, 2 * round(180 * source_w / source_h))
    # A column samples every quarter second. Rows follow node/output order
    # and retain each physical group's actual RGB code after output transforms.
    width = min(4096, max(1, round(duration * 4)))
    timeline = None
    previous_column = -1
    nodes = 0
    strip_zones = {s.id: s.video_zone for s in engine._layout.strips}
    writer = None
    preview_start = None

    def record(frame):
        nonlocal timeline, previous_column, nodes, preview_start
        if frame.metadata.get("SAFE_STATE"):
            return
        if writer is not None and args.preview[0] <= frame.timestamp + 1e-8 < args.preview[1]:
            if preview_start is None:
                preview_start = frame.timestamp
            panel_frame = preview_panel(frame, strip_zones, engine._latest_video, engine._latest_audio)
            writer.write(screen_extension(frame, panel_frame, screen_width) if args.screen_edges else panel_frame)
        column = min(width - 1, int(frame.timestamp / duration * width))
        if column == previous_column:
            return
        groups = [pixel for node in frame.digital_frames for output in node.outputs
                  for pixel in output.pixels]
        if not groups:
            raise ValueError("Expected a profile with mapped digital strip outputs")
        if timeline is None:
            nodes = len(frame.digital_frames)
            timeline = np.zeros((len(groups), width, 3), dtype=np.uint8)
        timeline[:, column] = np.rint(np.asarray(groups)[:, ::-1] * 255).astype(np.uint8)
        previous_column = column

    output = NullOutput()
    output.send_frame = record
    engine._outputs = {"recording": output}
    with TemporaryDirectory() as folder:
        panel = Path(folder) / "groups.avi"
        try:
            if args.preview:
                size = (screen_width + 56 + PANEL_WIDTH, 408) if args.screen_edges else (PANEL_WIDTH, 360)
                writer = cv2.VideoWriter(str(panel), cv2.VideoWriter_fourcc(*"FFV1"), fps, size)
                if not writer.isOpened():
                    raise RuntimeError("Could not create the lossless strip preview")
            with patch("light_engine.engine.time.sleep", new=lambda _: None):
                engine.run(duration=duration)
        finally:
            if writer is not None:
                writer.release()
        if args.preview:
            if preview_start is None:
                raise RuntimeError("No media frames reached the requested preview interval")
            compose = ("[1:v][v]overlay=x=26:y=24:shortest=1" if args.screen_edges
                       else "[v][1:v]hstack=shortest=1")
            subprocess.run([
                "ffmpeg", "-nostdin", "-n", "-v", "error", "-ss", str(preview_start), "-i", str(args.video),
                "-i", str(panel), "-ss", str(preview_start), "-i", str(args.audio),
                "-filter_complex", f"[0:v]fps={fps},scale={screen_width}:360,setsar=1[v];{compose}[out]",
                "-map", "[out]", "-map", "2:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(args.output.with_suffix(".mp4")),
            ], check=True)
    if timeline is None or not cv2.imwrite(str(args.output), timeline):
        raise RuntimeError("Could not save the strip timeline")
    print(json.dumps({"nodes": nodes, "groups": timeline.shape[0],
                      "show_seconds": duration, **engine.get_fps_stats()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("video", "audio", "show", "profile", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--preview", type=float, nargs=2, metavar=("START", "END"),
                        help="Also write an MP4 of source picture, selected audio and mapped strips")
    parser.add_argument("--screen-edges", action="store_true",
                        help="Position the production screen-surround strips around the source image")
    render(parser.parse_args())
