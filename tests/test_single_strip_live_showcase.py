from __future__ import annotations

import hashlib
import random
import math
import colorsys
from pathlib import Path

import pytest

import light_engine.show.compositor as compositor
from light_engine.config import Config
from light_engine.effects import create_effect
from light_engine.mapping import Layout
from light_engine.models import AudioFeatures, EffectContext, VideoFeatures
from light_engine.outputs.transform import OutputTransform
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show

REPO = Path(__file__).resolve().parents[1]
SHOW_PATH = REPO / "config" / "acceptance" / "single-strip-live-showcase-v1" / "show.yaml"
PROFILE = REPO / "config" / "profiles" / "rk3588-host-service.yaml"
TARGET = "strip_31"
FPS = 30
FRAMES = 4140
SEED = 31109


@pytest.fixture(scope="module")
def loaded():
    with pytest.MonkeyPatch.context() as patch:
        config = Config(PROFILE)
        patch.setattr(Config, "_instance", config)
        layout = Layout.from_config(config)
        show = load_show(SHOW_PATH, TargetCatalog.from_layout(layout))
        yield config, layout, show


def _cue(show, cue_id):
    return next(cue for cue in show.cues if cue.id == cue_id)


def test_show_contract_and_exact_chapter_boundaries(loaded):
    config, layout, show = loaded
    assert show.id == "single-strip-live-showcase-v1"
    assert show.duration == pytest.approx(138.0)
    assert config.get("system.output_fps") == pytest.approx(FPS)
    strip = next(item for item in layout.strips if item.id == TARGET)
    assert strip.pixel_count == 10
    assert sum(item.pixel_count for item in layout.strips) == 107
    assert all(cue.target.kind == "digital_strip" and cue.target.id == TARGET for cue in show.cues)
    assert all(cue.audio_control is None and cue.audio_modulation is None for cue in show.cues)
    assert all(cue.color_source is None or cue.color_source.type == "spatial_palette" for cue in show.cues)
    expected_effects = [
        "static", "breath", "calm", "color_wipe", "single_dot", "chase",
        "theater_phase", "flowing_bands", "demo", "color_wave", "history_stream",
        "heat_fire", "coherent_noise_field", "step_pulse", "twinkle", "comet",
    ]
    ordered_families = []
    for cue in sorted(show.cues, key=lambda item: (item.start, item.end)):
        if cue.id.startswith("BLACK_"):
            continue
        if not ordered_families or ordered_families[-1] != cue.effect.id:
            ordered_families.append(cue.effect.id)
    assert ordered_families == expected_effects

    chapters = [
        ("static", 2, 8), ("breath", 8.4, 14.4), ("calm", 14.8, 19.8),
        ("color_wipe", 20.2, 28.2), ("single_dot", 28.6, 36.6),
        ("chase", 37, 45), ("theater_phase", 45.4, 51.4),
        ("flowing_bands", 51.8, 59.8), ("demo", 60.2, 68.2),
        ("color_wave", 68.6, 77.6), ("history_stream", 78, 86),
        ("heat_fire", 86.4, 96.4), ("coherent_noise_field", 96.8, 104.8),
        ("step_pulse", 105.2, 111.2), ("twinkle", 111.6, 123.6),
        ("comet", 124, 136),
    ]
    for effect_id, start, end in chapters:
        matching = [cue for cue in show.cues if cue.effect.id == effect_id and cue.start >= start and cue.end <= end]
        assert matching, effect_id
        assert min(cue.start for cue in matching) == pytest.approx(start)
        assert max(cue.end for cue in matching) == pytest.approx(end)
    black = [cue for cue in show.cues if cue.id.startswith("BLACK_")]
    assert [(cue.start, cue.end) for cue in black] == pytest.approx([
        (0, 2), (8, 8.4), (14.4, 14.8), (19.8, 20.2), (28.2, 28.6),
        (36.6, 37), (45, 45.4), (51.4, 51.8), (59.8, 60.2),
        (68.2, 68.6), (77.6, 78), (86, 86.4), (96.4, 96.8),
        (104.8, 105.2), (111.2, 111.6), (123.6, 124), (136, 138),
    ])
    assert all(cue.start * FPS == round(cue.start * FPS) and cue.end * FPS == round(cue.end * FPS) for cue in show.cues)

    assert [(cue.id, cue.start, cue.end, cue.color.color) for cue in show.cues if cue.id.startswith("STATIC_")] == [
        ("STATIC_red", 2, 3.5, (1.0, 0.0, 0.0)),
        ("STATIC_green", 3.5, 5, (0.0, 1.0, 0.0)),
        ("STATIC_blue", 5, 6.5, (0.0, 0.0, 1.0)),
        ("STATIC_cool_white", 6.5, 8, (0.85, 0.9, 1.0)),
    ]
    assert [(_cue(show, cue_id).effect.params, _cue(show, cue_id).color.color) for cue_id in ("BREATH_cyan", "BREATH_amber")] == [
        ({"period": 2, "waveform": "sine", "min_brightness": 0.05}, (0.05, 0.7, 0.85)),
        ({"period": 1, "waveform": "smoothstep", "min_brightness": 0.05}, (0.95, 0.32, 0.03)),
    ]
    assert _cue(show, "CALM_color_drift").effect.params == {"period": 2.5}
    assert _cue(show, "CALM_color_drift").color.color == (0.3, 0.12, 0.7)

    assert [_cue(show, name).effect.params for name in ("WIPE_start_cyan", "WIPE_end_amber", "WIPE_center_purple", "WIPE_edges_cyan_purple")] == [
        {"speed": 5}, {"speed": 5}, {"speed": 5, "edge_softness_px": 1, "progress_curve": "smoothstep"},
        {"speed": 5, "edge_softness_px": 1, "progress_curve": "smoothstep"},
    ]
    assert [_cue(show, name).effect.params["speed"] for name in ("COMET_ice_wrap", "COMET_amber_bounce", "COMET_cyan_violet_wrap")] == [9, 18, 27]
    assert [_cue(show, name).effect.params["density"] for name in ("TWINKLE_gold", "TWINKLE_palette", "TWINKLE_random")] == [0.6, 1, 1.4]
    assert all(cue.effect.speed == pytest.approx(1.0) for cue in show.cues if cue.id != "DEMO_cycle")
    assert _cue(show, "DEMO_cycle").effect.speed == pytest.approx(1.5)


class _TraceEffect:
    def __init__(self, inner, trace):
        self.inner = inner
        self.name = inner.name
        self.trace = trace

    def process(self, ctx):
        frame = self.inner.process(ctx)
        cue_id = str(ctx.mode_parameters.get("cue_id", ""))
        state = {}
        for key in ("_position", "_phase", "_positions", "_bounce_phases", "_pixels", "_spawn_remainders", "_color_event_indices", "_last_steps", "_strip_ticks"):
            if hasattr(self.inner, key):
                value = getattr(self.inner, key)
                state[key] = __import__("copy").deepcopy(value)
        state["demo_current"] = frame.metadata.get("demo_current")
        self.trace.setdefault(cue_id, []).append((ctx, frame, state))
        return frame

    def reset(self):
        return self.inner.reset()


def _render(loaded, *, with_media=False, trace=False):
    config, layout, show = loaded
    transform = OutputTransform(
        global_brightness=config.get("system.smoothing.max_brightness"),
        gamma=config.get("system.smoothing.gamma"),
        power_limit=config.get("outputs.transform.power_limit", 5.0),
        per_zone_warm_bias=config.get("outputs.transform.per_zone_warm_bias", {}),
        per_zone_cool_bias=config.get("outputs.transform.per_zone_cool_bias", {}),
    )
    events = {}
    original_compose = compositor.compose_frame
    original_rng = random.getstate()
    random.seed(SEED)
    if trace:
        def capture(base, contributions):
            events[base.timestamp] = tuple(contributions)
            return original_compose(base, contributions)
        compositor.compose_frame = capture
    effect_trace = {}
    digest = hashlib.sha256()
    frames = {}
    safe_tail = []
    try:
        factory = (lambda name: _TraceEffect(create_effect(name), effect_trace)) if trace else create_effect
        runtime = ShowRuntime.from_layout(show, layout, seed=SEED, effect_factory=factory)
        for index in range(FRAMES):
            t = index / FPS
            base = black_base_frame(timestamp=t, sequence=index, analog_zones=layout.zones, digital_strips=layout.strips)
            audio = AudioFeatures(timestamp=t, rms=(index % 5) / 4, loudness=(index % 7) / 6, onset=float(index % 13 == 0)) if with_media else None
            video = VideoFeatures(timestamp=t, average_rgb=((index % 3) / 2, 0.3, 0.7), dominant_rgb=(0.9, 0.1, 0.4), brightness=0.7, saturation=0.8) if with_media else None
            result = transform.apply_to_frame(runtime.render(EffectContext(timestamp=t, delta_time=1 / FPS, sequence=index, audio_features=audio, video_features=video), base))
            for strip in result.strips:
                pixels = strip.to_uint8()
                if strip.strip_id == TARGET:
                    digest.update(bytes(channel for pixel in pixels for channel in pixel))
                    if t >= 136:
                        safe_tail.append(pixels)
                    if index % 3 == 0:
                        for cue in show.cues:
                            if cue.start <= t < cue.end:
                                frames.setdefault(cue.id, []).append(pixels)
                else:
                    assert all(pixel == (0, 0, 0) for pixel in pixels)
        return digest.hexdigest(), frames, events, effect_trace, safe_tail
    finally:
        random.setstate(original_rng)
        compositor.compose_frame = original_compose


@pytest.fixture(scope="module")
def replay(loaded):
    return _render(loaded, trace=True)


def test_all_4140_frames_are_repeatable_media_independent_and_black_safe(loaded, replay):
    digest, frames, _, _, safe_tail = replay
    _, _, show = loaded
    assert len(digest) == 64
    repeated = _render(loaded)
    media = _render(loaded, with_media=True)
    assert repeated[0] == digest
    assert media[0] == digest
    assert len(safe_tail) == 60
    assert all(pixel == (0, 0, 0) for frame in safe_tail for pixel in frame)
    for cue in (cue for cue in show.cues if cue.id.startswith("BLACK_")):
        assert cue.id in frames
        assert all(pixel == (0, 0, 0) for frame in frames[cue.id] for pixel in frame), cue.id
    for start, end in ((0, 2), (8, 8.4), (14.4, 14.8), (19.8, 20.2), (28.2, 28.6), (36.6, 37), (45, 45.4), (51.4, 51.8), (59.8, 60.2), (68.2, 68.6), (77.6, 78), (86, 86.4), (96.4, 96.8), (104.8, 105.2), (111.2, 111.6), (123.6, 124), (136, 138)):
        for frame_index in range(round(start * FPS), round(end * FPS)):
            t = frame_index / FPS
            # Black cues are explicit; final tail is 60 complete black frames.
            assert any(cue.start <= t < cue.end and cue.id.startswith("BLACK_") for cue in show.cues)
    assert len(frames) == len(show.cues)


def test_motion_wipe_comet_twinkle_and_spatial_effect_evidence(loaded, replay):
    _, _, show = loaded
    _, frames, _, trace, _ = replay
    for family in ("breath", "calm", "color_wipe", "single_dot", "chase", "theater_phase", "flowing_bands", "demo", "color_wave", "history_stream", "heat_fire", "coherent_noise_field", "step_pulse", "twinkle", "comet"):
        cues = [cue for cue in show.cues if cue.effect.id == family]
        assert cues, family
        assert any(len({tuple(frame) for frame in frames[cue.id]}) > 1 for cue in cues), f"{family}: output did not visibly change"

    for cue_id, expected_color in (("STATIC_red", (1, 0, 0)), ("STATIC_green", (0, 1, 0)), ("STATIC_blue", (0, 0, 1)), ("STATIC_cool_white", (.85, .9, 1))):
        cue_frames = frames[cue_id]
        assert cue_frames
        # OutputTransform applies gamma/brightness equally to every group of a static cue.
        assert all(len(set(frame)) == 1 for frame in cue_frames)
        assert all(max(frame[0]) > 0 for frame in cue_frames)
        if expected_color[0] == 0:
            assert all(pixel[0] == 0 for frame in cue_frames for pixel in frame)
        if expected_color[1] == 0:
            assert all(pixel[1] == 0 for frame in cue_frames for pixel in frame)
        if expected_color[2] == 0:
            assert all(pixel[2] == 0 for frame in cue_frames for pixel in frame)

    for cue_id, period, min_local, max_local in (("BREATH_cyan", 2, 1.5, .5), ("BREATH_amber", 1, .75, .25)):
        samples = trace[cue_id]
        def sample_near(local_time):
            return min(samples, key=lambda item: abs(item[0].mode_parameters["cue_local_time"] - local_time))[1].strips[0].pixels[0]
        color = _cue(show, cue_id).color.color
        low = sample_near(min_local)
        high = sample_near(max_local)
        low_gain = max(low[channel] / color[channel] for channel in range(3) if color[channel] > 0)
        high_gain = max(high[channel] / color[channel] for channel in range(3) if color[channel] > 0)
        assert low_gain == pytest.approx(.05, abs=.02)
        assert high_gain == pytest.approx(1.0, abs=.02)
        observed = [max(frame[0]) for frame in frames[cue_id]]
        assert len(observed) > 1

    calm_trace = trace["CALM_color_drift"]
    calm_rgb = [sample[1].strips[0].pixels[0] for sample in calm_trace]
    assert len({tuple(pixel) for pixel in calm_rgb}) > 100
    assert max(max(pixel) for pixel in calm_rgb) <= .35 + 1e-9

    for cue_id in ("CHASE_forward_amber", "CHASE_bounce_rainbow"):
        colors = {tuple(pixel) for frame in frames[cue_id] for pixel in frame if max(pixel) > 0}
        if cue_id.endswith("rainbow"):
            hues = {round(colorsys.rgb_to_hsv(*(channel / 255 for channel in pixel))[0] * 360) for pixel in colors}
            assert len(hues) >= 5, "rainbow chase did not emit multiple hues"
        else:
            normalized = [tuple(channel / max(pixel) for channel in pixel) for pixel in colors]
            anchor = normalized[0]
            assert all(all(channel == pytest.approx(reference, abs=.03) for channel, reference in zip(pixel, anchor)) for pixel in normalized), "static chase hue changed across trail intensities"

    for cue_id in ("WIPE_start_cyan", "WIPE_end_amber", "WIPE_center_purple", "WIPE_edges_cyan_purple"):
        pixels = frames[cue_id]
        assert len(pixels) >= 18
        lit_at_start = [index for index, pixel in enumerate(pixels[0]) if max(pixel) > 0]
        assert len(lit_at_start) <= 2, f"{cue_id}: progress was not reset at cue entry"
        assert all(max(pixel) > 0 for pixel in pixels[-1]), f"{cue_id}: ten groups were not fully covered before cue end"
        assert pixels[0] != pixels[17], f"{cue_id}: wipe did not restart/progress"
        assert pixels[-1] == pixels[-2], f"{cue_id}: wipe failed to fill by cue end"

    for cue_id, expected_speed in (("COMET_ice_wrap", 9), ("COMET_amber_bounce", 18), ("COMET_cyan_violet_wrap", 27)):
        cue = _cue(show, cue_id)
        legacy_wrap = (
            cue.effect.params.get("count", 1) == 1
            and cue.effect.params.get("trajectory", "wrap") == "wrap"
            and cue.effect.params.get("tail_length", 0.0) > 0.0
        )
        samples = trace[cue_id]
        assert len(samples) == round((cue.end - cue.start) * FPS)
        head_positions = []
        for ctx, frame, _ in samples:
            raw = frame.strips[0].pixels
            head = max(range(10), key=lambda index: max(raw[index]))
            expected_head_gain = cue.effect.params["decay"] if legacy_wrap else 1.0
            assert max(raw[head]) == pytest.approx(expected_head_gain, abs=1e-9)
            head_positions.append(head)
        if legacy_wrap:
            positions = [sample[2]["_positions"][TARGET] for sample in samples]
            assert positions[1] - positions[0] == pytest.approx(expected_speed / FPS, abs=1e-6)
            assert head_positions == [int(position) % 10 for position in positions]
            assert all((b - a) % 12 == pytest.approx(expected_speed / FPS, abs=1e-6) for a, b in zip(positions, positions[1:]))
            first_raw = samples[0][1].strips[0].pixels
            tail_groups = int(10 * cue.effect.params["tail_length"])
            expected_profile = [cue.effect.params["decay"] * (1 - offset / tail_groups) for offset in range(tail_groups)]
            observed_profile = [max(first_raw[(head_positions[0] - offset) % 10]) for offset in range(tail_groups)]
            assert observed_profile == pytest.approx(expected_profile, abs=1e-9)
        else:
            # The moving-emitter branch derives each head from cue-local motion time.
            cue_time = [ctx.mode_parameters["cue_local_time"] for ctx, _, _ in samples]
            expected_positions = []
            for local_time in cue_time:
                distance = local_time * expected_speed
                if cue_id == "COMET_amber_bounce":
                    offset = distance % 18
                    position = offset if offset <= 9 else 18 - offset
                else:
                    position = distance % 10
                expected_positions.append(int(position))
            assert head_positions == expected_positions, cue_id
            assert any(a != b for a, b in zip(head_positions, head_positions[1:])), cue_id
            # The bounce emitter has a full-strength head and a distance-shaped tail.
            first_raw = samples[0][1].strips[0].pixels
            tail_groups = int(10 * cue.effect.params["tail_length"])
            decay = cue.effect.params["decay"]
            expected_profile = [1.0] + [
                (1 - offset / (tail_groups + 1)) * decay**offset
                for offset in range(1, tail_groups + 1)
            ]
            observed_profile = [max(first_raw[(head_positions[0] - offset) % 10]) for offset in range(tail_groups + 1)]
            assert observed_profile == pytest.approx(expected_profile, abs=1e-9)

    for cue_id, rate in (("TWINKLE_gold", 6), ("TWINKLE_palette", 10), ("TWINKLE_random", 14)):
        cue = _cue(show, cue_id)
        samples = trace[cue_id]
        assert len(samples) == 4 * FPS
        assert samples[-1][2]["_color_event_indices"].get(TARGET, 0) == rate * 4
        assert any(sample[2]["_pixels"].get(TARGET) for sample in samples)
        # Verify a retained, unrefreshed event decays over successive 30 FPS frames.
        decay = math.exp(-1 / FPS / cue.effect.params["fade_time"])
        found_decay = False
        for earlier, later in zip(samples, samples[1:]):
            before = earlier[2]["_pixels"][TARGET]
            after = later[2]["_pixels"][TARGET]
            if any(0 < before[index][0] < 1 and after[index] == pytest.approx(tuple(channel * decay for channel in before[index])) for index in range(10)):
                found_decay = True
                break
        assert found_decay, f"{cue_id}: no retained event showed the specified exponential decay"

    for cue_id in ("NOISE_cyan", "NOISE_violet"):
        pixels = frames[cue_id]
        assert any(len(set(frame)) > 2 for frame in pixels), f"{cue_id}: spatial contrast collapsed"
        assert any(frame != pixels[0] for frame in pixels[1:]), f"{cue_id}: field did not drift"


def test_live_effect_periods_steps_and_physical_path_evidence(loaded, replay):
    _, _, show = loaded
    _, frames, _, trace, _ = replay

    for cue_id, speed, direction in (("DOT_forward_white", 6, "forward"), ("DOT_bounce_gold", 10, "bounce")):
        cue = _cue(show, cue_id)
        for ctx, frame, _ in trace[cue_id]:
            step = math.floor(ctx.mode_parameters["cue_local_time"] * speed + 1e-9)
            position = step % 10
            if direction == "bounce":
                phase = step % 18
                position = phase if phase < 10 else 18 - phase
            assert max(range(10), key=lambda i: max(frame.strips[0].pixels[i])) == position

    for cue_id, speed, direction in (("CHASE_forward_amber", 6, "forward"), ("CHASE_bounce_rainbow", 9, "bounce")):
        samples = trace[cue_id]
        positions = [state["_position"] for _, _, state in samples]
        if direction == "forward":
            assert positions[1] - positions[0] == pytest.approx(speed / FPS)
        else:
            phases = [state["_bounce_phases"][TARGET] for _, _, state in samples]
            assert phases[1] - phases[0] == pytest.approx(speed / FPS)
        assert all(any(max(pixel) == 0 for pixel in frame.strips[0].pixels) for _, frame, _ in samples)

    for cue_id, speed in (("THEATER_cyan", 4), ("THEATER_magenta", 7.5)):
        for ctx, frame, _ in trace[cue_id]:
            phase = math.floor(ctx.mode_parameters["cue_local_time"] * speed + 1e-9) % 3
            pixels = frame.strips[0].pixels
            lit = [index for index, pixel in enumerate(pixels) if max(pixel) > 0]
            assert lit == list(range(phase, 10, 3))

    for cue_id, rate, direction in (("BANDS_forward_cyan", 3, "forward"), ("BANDS_reverse_pink", 4.5, "reverse")):
        cue = _cue(show, cue_id)
        expected_positions = []
        for ctx, frame, _ in trace[cue_id]:
            step = math.floor(ctx.mode_parameters["cue_local_time"] * rate)
            band = None if step == 0 else (step - 1) % 5
            if direction == "reverse" and band is not None:
                band = 4 - band
            expected_positions.append(band)
            if band is not None:
                assert max(frame.strips[0].pixels[band * 2]) > max(frame.strips[0].pixels[(band * 2 + 2) % 10])
        assert len(set(expected_positions)) >= 5

    for cue_id, speed in (("WAVE_sine", .45), ("WAVE_triangle", .70), ("WAVE_reverse_saw", -.85)):
        phases = [state["_phase"] for _, _, state in trace[cue_id]]
        assert phases[1] - phases[0] == pytest.approx(speed / FPS, abs=1e-9)
        assert phases[-1] - phases[0] == pytest.approx(speed * (len(phases) - 1) / FPS, abs=1e-7)

    for cue_id in ("HISTORY_forward", "HISTORY_reverse"):
        samples = trace[cue_id]
        steps = [state["_last_steps"].get(TARGET, -1) for _, _, state in samples]
        assert steps[-1] == math.floor((len(samples) - 1) / FPS * 6)
        assert steps[-1] == 23  # End is exclusive; final rendered cue time is 3.966…s.
        assert steps[45] >= 9  # At 1.5s, 9 steps have populated the ten-group history.
        assert steps[1] - steps[0] in (0, 1)

    for cue_id in ("FIRE_native",):
        cue = _cue(show, cue_id)
        samples = trace[cue_id]
        ticks = [state["_strip_ticks"][TARGET] for _, _, state in samples]
        assert ticks[-1] == round((cue.end - cue.start - 1 / FPS) * 60)
        assert any(max(frame.strips[0].pixels[index]) > 0 for _, frame, _ in samples for index in range(3, 10))
        assert any(sample[1].strips[0].pixels != samples[0][1].strips[0].pixels for sample in samples[1:])

    for cue_id, period, duty in (("STEP_purple_magenta", .8, .4), ("STEP_blue_cyan", .6, .55)):
        cue = _cue(show, cue_id)
        samples = trace[cue_id]
        states = [max(frame.strips[0].pixels[0]) for _, frame, _ in samples]
        changes = [i for i in range(1, len(states)) if states[i] != states[i - 1]]
        assert len(changes) == pytest.approx(2 * (cue.end - cue.start) / period, abs=1)
        assert changes[0] == pytest.approx(round(period * (1 - duty) * FPS), abs=1)

    demo = trace["DEMO_cycle"]
    switches = [(ctx.mode_parameters["cue_local_time"], state["demo_current"]) for ctx, _, state in demo]
    observed = []
    for _, name in switches:
        if not observed or observed[-1] != name:
            observed.append(name)
    assert observed[:4] == ["single_dot", "theater_phase", "color_wave", "breath"]
    assert [time for time, name in switches if name == "theater_phase"][0] == pytest.approx(2, abs=1 / FPS + 1e-9)

    # Ten-group spatial coherence must retain a visible brightness envelope.
    for cue_id in ("NOISE_cyan", "NOISE_violet"):
        for _, frame, _ in trace[cue_id][::30]:
            envelope = [max(pixel) for pixel in frame.strips[0].pixels]
            assert max(envelope) - min(envelope) > .02
