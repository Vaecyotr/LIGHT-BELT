"""Historical Phase 31 pinned render identity; never refresh from current output."""

from light_engine.show import ShowRuntime, TargetResolver, load_show
from tests.test_cabin_v3_e2e_acceptance import SHOW, _catalog, _fixture, _layout, _replay_digest


def test_phase31_render_matches_recorded_digest():
    layout = _layout()
    runtime = ShowRuntime(load_show(SHOW, _catalog(layout)), TargetResolver.from_layout(layout), seed=29)
    assert _replay_digest(runtime, layout) == _fixture()["deterministic_replay_sha256"]
