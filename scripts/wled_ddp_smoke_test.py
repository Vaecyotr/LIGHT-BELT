"""Send a simple DDP RGB test pattern to one WLED device."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from light_engine.outputs.ddp_output import encode_ddp_packets


def _solid(count: int, color: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    return [color for _ in range(count)]


def _chase(count: int, frame: int) -> list[tuple[int, int, int]]:
    pixels: list[tuple[int, int, int]] = []
    head = frame % max(1, count)
    for index in range(count):
        distance = (index - head) % max(1, count)
        if distance == 0:
            pixels.append((255, 255, 255))
        elif distance < 4:
            level = max(0, 180 - distance * 45)
            pixels.append((level, 0, 0))
        else:
            pixels.append((0, 0, 20))
    return pixels


def send_pixels(
    *,
    host: str,
    port: int,
    pixels: list[tuple[int, int, int]],
    sequence: int,
    sock: socket.socket,
) -> int:
    sent = 0
    for packet in encode_ddp_packets(pixels, sequence=sequence):
        sock.sendto(packet, (host, port))
        sent += 1
    return sent


def main() -> int:
    parser = argparse.ArgumentParser(description="WLED DDP smoke test")
    parser.add_argument("--host", default="192.168.31.58", help="WLED device IP")
    parser.add_argument("--port", type=int, default=4048, help="WLED DDP UDP port")
    parser.add_argument("--pixels", type=int, default=50, help="Total WLED virtual LED count")
    parser.add_argument("--fps", type=float, default=30.0, help="Frames per second")
    parser.add_argument("--seconds", type=float, default=10.0, help="Test duration")
    parser.add_argument(
        "--pattern",
        choices=["rgb", "chase", "red", "green", "blue", "black"],
        default="rgb",
        help="Pattern to send",
    )
    args = parser.parse_args()

    frame_delay = 1.0 / max(1.0, args.fps)
    end_time = time.monotonic() + max(0.1, args.seconds)
    sequence = 1
    frames = 0
    packets = 0
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    fixed = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "black": (0, 0, 0),
    }

    print(
        f"Sending DDP {args.pattern} test to {args.host}:{args.port}, "
        f"pixels={args.pixels}, fps={args.fps:g}, seconds={args.seconds:g}"
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while time.monotonic() < end_time:
            if args.pattern == "rgb":
                pixels = _solid(args.pixels, palette[(frames // max(1, int(args.fps))) % 3])
            elif args.pattern == "chase":
                pixels = _chase(args.pixels, frames)
            else:
                pixels = _solid(args.pixels, fixed[args.pattern])
            packets += send_pixels(
                host=args.host,
                port=args.port,
                pixels=pixels,
                sequence=sequence,
                sock=sock,
            )
            frames += 1
            sequence += 1
            time.sleep(frame_delay)
        send_pixels(
            host=args.host,
            port=args.port,
            pixels=_solid(args.pixels, (0, 0, 0)),
            sequence=sequence,
            sock=sock,
        )

    print(f"Done. Sent {frames} frames and {packets} DDP packets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
