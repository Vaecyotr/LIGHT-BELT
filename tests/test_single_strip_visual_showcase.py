"""Structural contract for the single-strip visual showcase v2.

The show YAML is deliberately the only orchestration source.  These checks use
the parsed show rather than maintaining a second registry or coverage manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_engine.config import Config
from light_engine.mapping import Layout
from light_engine.show import TargetCatalog, load_show


REPO = Path(__file__).resolve().parents[1]
SHOW_PATH = REPO / "config" / "acceptance" / "single-strip-visual-showcase-v2" / "show.yaml"
PROFILE = REPO / "config" / "profiles" / "rk3588-host-service.yaml"
TARGET = "strip_43"
FPS = 30


@pytest.fixture(scope="module")
def show():
    Config.reset()
    config = Config.get_instance(PROFILE)
    return load_show(SHOW_PATH, TargetCatalog.from_layout(Layout.from_config(config)))


def _cue(show, cue_id: str):
    return next(cue for cue in show.cues if cue.id == cue_id)


def test_show_is_a_single_target_356_point_8_second_74_cue_program(show) -> None:
    assert show.id == "single-strip-visual-showcase-v2"
    assert show.duration == pytest.approx(356.8)
    assert len(show.cues) == 74
    assert all(cue.target.kind == "digital_strip" and cue.target.id == TARGET for cue in show.cues)
    assert not show.virtual_paths
    assert all(cue.effect.id not in {"video", "audio", "video_audio_fusion"} for cue in show.cues)
    assert int(show.duration * FPS) == 10_704
    assert all(cue.effect.speed <= 9.5 for cue in show.cues)
    assert all(cue.effect.intensity == 1 for cue in show.cues if cue.id.startswith(("CAL_", "FX_", "SEP_", "SAFE_")))
    assert all(not cue.branches and cue.audio_control is None and cue.audio_modulation is None and cue.parameter_modulation is None for cue in show.cues)
    assert all(cue.color_source is None or cue.color_source.type not in {"video_average", "video_dominant", "audio_spectrum_palette", "dominant_frequency_palette"} for cue in show.cues)


def test_core_variants_preserve_the_frozen_family_speed_and_origin_contract(show) -> None:
    core = [cue for cue in show.cues if cue.id.startswith("FX_")]
    assert len(core) == 49
    variants = [cue for cue in core if not ("_r" in cue.id)]
    # Wipe repeats are cues, not additional A--D variants.
    assert len(variants) == 44

    speeds = (2.5, 5.0, 7.5, 9.5)
    families = {
        "color_wave", "single_dot", "chase", "comet", "color_wipe",
        "flowing_bands", "heat_fire", "history_stream", "coherent_noise_field",
    }
    for family in families:
        authored = [cue for cue in core if cue.effect.id == family and "_r" not in cue.id]
        assert [cue.effect.speed for cue in authored] == list(speeds), family
    assert [_cue(show, f"FX_breath_{v}").effect.params["period"] for v in "ABCD"] == [8, 4, 2, 1.2]
    assert [_cue(show, f"FX_twinkle_{v}").effect.params["density"] for v in "ABCD"] == [0.10, 0.25, 0.50, 0.80]
    assert [_cue(show, f"FX_twinkle_{v}").effect.params["fade_time"] for v in "ABCD"] == [1.2, 0.8, 0.5, 0.3]
    assert _cue(show, "CAL_group_19").origin == "end"
    assert [_cue(show, f"FX_color_wipe_{v}").origin for v in "ABCD"] == ["start", "end", "center", "edges"]


def test_wipe_replays_complete_and_c5_timeline_is_continuous(show) -> None:
    expected = {
        "A": ["FX_color_wipe_A"],
        "B": ["FX_color_wipe_B", "FX_color_wipe_B_r1"],
        "C": ["FX_color_wipe_C", "FX_color_wipe_C_r1", "FX_color_wipe_C_r2"],
        "D": ["FX_color_wipe_D", "FX_color_wipe_D_r1", "FX_color_wipe_D_r2"],
    }
    for variant, ids in expected.items():
        cues = [_cue(show, cue_id) for cue_id in ids]
        assert all(cue.effect.params["speed"] == pytest.approx(1.4) for cue in cues), variant
        assert all(cue.end - cue.start >= 19 / (1.4 * cue.effect.speed) + 0.3 for cue in cues), variant

    c5 = [_cue(show, cue_id) for cue_id in expected["C"]]
    assert c5[0].start == pytest.approx(162.4) and c5[-1].end == pytest.approx(169.4)
    for previous, current in zip(c5, c5[1:]):
        assert previous.end == pytest.approx(current.start)
        assert previous.color_source.keyframes[-1].color == pytest.approx(current.color_source.keyframes[0].color)
    assert [len(cue.color_source.keyframes) for cue in c5] == [2, 3, 2]


def test_separators_fades_history_and_color_wave_are_explicit(show) -> None:
    separators = [cue for cue in show.cues if cue.id.startswith("SEP_")]
    assert len(separators) == 12
    assert all(cue.end - cue.start == pytest.approx(0.4) for cue in separators)
    assert all(cue.color.color == (0.0, 0.0, 0.0) for cue in separators)
    assert all(cue.transition.fade_in == cue.transition.fade_out == 0 for cue in separators)
    visible = [cue for cue in show.cues if cue.id.startswith(("CAL_", "FX_"))]
    assert all(cue.transition.fade_in == pytest.approx(0.1) and cue.transition.fade_out == pytest.approx(0.1) for cue in visible)

    waves = [_cue(show, f"FX_color_wave_{v}") for v in "ABCD"]
    assert [cue.effect.params["hue_span_degrees"] for cue in waves] == [60, 140, 240, 360]
    assert [cue.effect.params["waveform"] for cue in waves] == ["sine", "triangle", "linear", "saw"]
    histories = [_cue(show, f"FX_history_stream_{v}") for v in "ABCD"]
    assert [cue.effect.params["direction"] for cue in histories] == ["forward", "reverse", "forward", "reverse"]
    assert [len(cue.effect.params["color_timeline"]["keyframes"]) for cue in histories] == [3, 3, 3, 4]
    assert [point["time"] for point in histories[-1].effect.params["color_timeline"]["keyframes"]] == [0, 2.31, 4.62, 7]
    assert all(cue.color_source is None for cue in waves + histories)
    assert all(_cue(show, f"FX_twinkle_{v}").effect.params["event_width_px"] == 1.0 and _cue(show, f"FX_twinkle_{v}").effect.params["blur_radius_px"] == 0 for v in "ABCD")


def test_finale_has_expected_layering_and_safe_black_tail(show) -> None:
    finale = [_cue(show, cue_id) for cue_id in (
        "FIN_noise_S1", "FIN_noise_S2", "FIN_twinkle", "FIN_comet_S3", "FIN_noise_S3", "FIN_comet_S4",
    )]
    assert [(cue.id, cue.start, cue.end, cue.effect.speed) for cue in finale] == [
        ("FIN_noise_S1", 326.8, 333.8, 2.5), ("FIN_noise_S2", 333.8, 347.8, 5.0),
        ("FIN_twinkle", 333.8, 354.8, 1.0), ("FIN_comet_S3", 340.8, 347.8, 7.5),
        ("FIN_noise_S3", 347.8, 354.8, 7.5), ("FIN_comet_S4", 347.8, 354.8, 9.5),
    ]
    assert [cue.transition.blend for cue in finale] == ["replace", "replace", "add", "add", "replace", "add"]
    survivors = [_cue(show, cue_id) for cue_id in ("FIN_noise_S3", "FIN_twinkle", "FIN_comet_S4")]
    assert all(cue.transition.fade_out == pytest.approx(3) for cue in survivors)
    safe = _cue(show, "SAFE_black")
    assert safe.start == pytest.approx(354.8)
    assert safe.end == pytest.approx(356.8)
    assert safe.color.color == (0.0, 0.0, 0.0)


def test_fixed_boundaries_and_authoring_details_are_frame_aligned(show) -> None:
    # Exact block starts protect the intended pacing and 30 FPS offline replay.
    assert [_cue(show, f"FX_{family}_A").start for family in (
        "breath", "color_wave", "single_dot", "chase", "comet", "color_wipe", "flowing_bands", "twinkle", "heat_fire", "history_stream", "coherent_noise_field"
    )] == pytest.approx([12.4, 42.8, 71.2, 95.6, 120.0, 148.4, 176.8, 201.2, 229.6, 262.0, 294.4])
    for cue in show.cues:
        start_frame, end_frame = round(cue.start * FPS), round(cue.end * FPS)
        assert cue.start == start_frame / FPS and cue.end == end_frame / FPS, cue.id
        active = [frame for frame in range(10_704) if cue.start <= frame / FPS < cue.end]
        assert len(active) == end_frame - start_frame, f"{cue.id}: activation hole at a frame boundary"
    assert all(len([frame for frame in range(10_704) if _cue(show, name).start <= frame/FPS < _cue(show, name).end]) == 70 for name in ("FX_color_wipe_C", "FX_color_wipe_C_r1", "FX_color_wipe_C_r2", "FX_color_wipe_D", "FX_color_wipe_D_r1", "FX_color_wipe_D_r2"))
    assert [_cue(show, f"FX_breath_{v}").effect.speed for v in "ABCD"] == [1, 1, 1, 1]
    assert [_cue(show, f"FX_twinkle_{v}").effect.speed for v in "ABCD"] == [1, 1, 1, 1]
    assert _cue(show, "CAL_group_0").origin == "start"
    assert all(_cue(show, cue_id).transition.fade_in == 0 for cue_id in ("FIN_noise_S2", "FIN_noise_S3", "FIN_comet_S4"))
    assert _cue(show, "FIN_noise_S3").transition.fade_out == _cue(show, "FIN_comet_S4").transition.fade_out == 3
    assert [(cue.priority, cue.effect.intensity) for cue in [_cue(show, cue_id) for cue_id in ("FIN_noise_S1", "FIN_noise_S2", "FIN_noise_S3", "FIN_twinkle", "FIN_comet_S3", "FIN_comet_S4")]] == [(10, .3), (10, .3), (10, .3), (20, .2), (30, .4), (30, .4)]


def test_frozen_palette_parameters_separators_and_finale_contract(show) -> None:
    c1=(.05,.70,.85); c2=(.90,.32,.03); c3=((.90,.15,.02),(.95,.60,.08),(.50,.05,.85),(0,.72,.90)); c4=((.02,.06,.45),(0,.70,.85),(.40,.08,.80)); hc=((.95,.12,.02),(.05,.85,.95),(.85,.05,.65),(.95,.90,.65)); warm=(.95,.82,.55); cool=(.85,.90,1.)
    assert [_cue(show,f"FX_breath_{v}").color.color for v in "ABD"] == [c1,c2,cool]
    assert _cue(show,"FX_breath_C").color_source.keyframes[0].color == (.02,.08,.6)
    assert [_cue(show,f"FX_comet_{v}").effect.params["count"] for v in "ABCD"] == [1,1,2,3]
    assert [_cue(show,f"FX_comet_{v}").effect.params["tail_length"] for v in "ABCD"] == [.15,.20,.15,.10]
    assert [_cue(show,f"FX_comet_{v}").effect.params["phase_spacing"] for v in "ABCD"] == [1,1,.5,pytest.approx(1/3)]
    assert [_cue(show,f"FX_twinkle_{v}").color.color for v in "AB"] == [warm,c1]
    assert _cue(show,"FX_color_wipe_A").color.color == c1 and _cue(show,"FX_color_wipe_B").color.color == c2
    assert _cue(show,"FX_comet_D").color_source.palette == hc
    assert _cue(show,"FX_single_dot_C").color_source.palette == c3 and _cue(show,"FX_single_dot_D").color_source.palette == c4
    assert [_cue(show,f"SEP_{i:02d}").start for i in range(1,13)] == [12,42.4,70.8,95.2,119.6,148,176.4,200.8,229.2,261.6,294,326.4]
    assert all(_cue(show,f"SEP_{i:02d}").end-_cue(show,f"SEP_{i:02d}").start==pytest.approx(.4) for i in range(1,13))
    for cue in [c for c in show.cues if c.effect.id=="color_wipe" and c.id.startswith("FX_")]:
        assert 19/(cue.effect.params["speed"]*cue.effect.speed)+.3+cue.transition.fade_out <= cue.end-cue.start
    histories=[_cue(show,f"FX_history_stream_{v}") for v in "ABCD"]
    assert [list(h.effect.params["color_timeline"]["keyframes"]) for h in histories] == [
        [{"time":0,"color":(.8,.04,.01)},{"time":5.5,"color":(.95,.28,.02)},{"time":11,"color":(.95,.7,.08)}],
        [{"time":0,"color":(.02,.04,.35)},{"time":3.5,"color":(0,.72,.85)},{"time":7,"color":(.45,.05,.75)}],
        [{"time":0,"color":(.9,.03,.02)},{"time":3.5,"color":(.03,.85,.08)},{"time":7,"color":(.02,.1,.9)}],
        [{"time":0,"color":(.95,.6,.04)},{"time":2.31,"color":(.85,.04,.65)},{"time":4.62,"color":(.03,.85,.95)},{"time":7,"color":(.85,.9,1.)}],
    ]
