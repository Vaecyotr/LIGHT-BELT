# Phase 10 Acceptance Report

Scope: deterministic ten-second video-and-audio, no-hardware end-to-end
acceptance path for `video_audio_fusion` through RS-485 v2 memory transport,
UDP v2 memory transport, and JSON output.

Hardware verification: NOT HARDWARE VERIFIED.

## Acceptance Coverage

- Deterministic ten-second MP4 and WAV fixtures are generated during the test.
- `video_audio_fusion` is run with generated video and audio readers.
- Normal output is 300-301 logical frames at 30 FPS.
- Each normal frame emits six decoded RS-485 v2 packets and one decoded UDP v2
  datagram.
- Same-frame sequence values agree across RS-485 v2, UDP v2, and JSON output.
- JSON output is checked recursively for NaN and infinity.
- Latest-frame queues are empty after sends.
- Shutdown emits exactly one all-black SAFE_STATE frame.

## Commands

| Command | Return code | Result |
| --- | ---: | --- |
| `.\.python\Scripts\python.exe -c "import sys, pathlib, light_engine; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe', cwd/'.python'/'python.exe']; existing=[c for c in candidates if c.exists()]; assert existing, 'No bundled Python found'; assert any(c.resolve()==exe for c in existing), 'Executable mismatch'; assert exe.name.lower()=='python.exe'; assert str(pkg).startswith(str(cwd)); print('executable=', exe); print('package=', pkg); print('PROJECT_PYTHON_OK')"` | 0 | Bundled interpreter verified. |
| `.\.python\Scripts\python.exe -m pytest -q` | 0 | Baseline: 325 passed in 25.34s. |
| `.\.python\Scripts\python.exe -m pytest tests/test_e2e_acceptance.py -v` | 1 | Initial targeted run exposed an over-range generated-media path in `video_audio_fusion`; no production code was changed because Phase 10 forbids `light_engine/**`. |
| `.\.python\Scripts\python.exe -m pytest tests/test_e2e_acceptance.py -v` | 0 | Targeted: 1 passed in 5.20s. |
| `.\.python\Scripts\python.exe -m pytest -q` | 0 | Full suite: 326 passed in 28.24s. |
| `.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800` | 0 | 1800 frames in 60.70s; P50 3.11 ms, P95 3.85 ms, P99 4.46 ms. |
| `pio run -d firmware/stm32_rgbcct_node` | 1 | Blocked before compilation by `PermissionError` creating `C:\Users\19141\.platformio`. |
| `pio run -d firmware/esp32_ws2811_node` | 1 | Blocked before compilation by `PermissionError` creating `C:\Users\19141\.platformio`. |
| `$env:PLATFORMIO_CORE_DIR = (Join-Path (Get-Location) '.pio-core'); pio run -d firmware/stm32_rgbcct_node` | 1 | Retried with workspace-local PlatformIO core; blocked by `HTTPClientError` while installing `ststm32`. |
| `$env:PLATFORMIO_CORE_DIR = (Join-Path (Get-Location) '.pio-core'); pio run -d firmware/esp32_ws2811_node` | 1 | Retried with workspace-local PlatformIO core; blocked by `HTTPClientError` while installing `espressif32`. |
| `git diff --check` | 0 | Passed with line-ending warnings for firmware golden-vector files. |

## Limitations

- Firmware compilation did not complete in this sandbox because PlatformIO could
  not access its default user state directory, and the workspace-local retry
  required network platform installation that failed with `HTTPClientError`.
- The benchmark verifies this Windows machine only, not RK3588 hardware.
- The acceptance test uses explicit no-hardware memory transports; this is NOT
  HARDWARE VERIFIED.
