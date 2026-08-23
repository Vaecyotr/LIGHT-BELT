"""Small deterministic clean-room spatial-temporal coherent-noise primitive."""

from __future__ import annotations

import hashlib
import math


def derive_coherent_seed(base_seed: int, namespace: str) -> int:
    """Derive a reproducible 64-bit seed without using a process-global RNG."""

    if type(base_seed) is not int:
        raise TypeError("base_seed must be an integer")
    if not isinstance(namespace, str):
        raise TypeError("namespace must be a string")
    digest = hashlib.sha256(f"{base_seed}:{namespace}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _lattice_value(x_lattice: int, t_lattice: int, seed: int) -> float:
    """Return one deterministic pseudo-random lattice value in ``[0, 1]``."""

    # This local integer avalanche mix is deliberately an implementation
    # detail, designed here for this bounded native field.  It shares neither
    # a visual algorithm nor numeric compatibility constants with WLED or
    # FastLED, and avoids the per-pixel cryptographic-hash cost.
    mask = (1 << 64) - 1
    state = (seed & mask) ^ ((x_lattice & mask) * 0xD6E8FEB86659FD93 & mask)
    state ^= ((t_lattice & mask) * 0xA5A3564E27F6C5A9) & mask
    state ^= state >> 30
    state = (state * 0xBF58476D1CE4E5B9) & mask
    state ^= state >> 27
    state = (state * 0x94D049BB133111EB) & mask
    state ^= state >> 31
    return state / float(mask)


def coherent_noise_2d(x: float, t: float, *, seed: int = 0) -> float:
    """Sample smooth deterministic value noise at spatial ``x`` and time ``t``.

    Adjacent spatial and temporal samples share the four surrounding lattice
    values and use separable quintic interpolation.  The result is bounded in
    ``[0, 1]`` and has no dependency on Python's global random state or
    physical output topology.
    """

    if type(seed) is not int:
        raise TypeError("seed must be an integer")
    x = float(x)
    t = float(t)
    if not math.isfinite(x) or not math.isfinite(t):
        raise ValueError("coherent noise coordinates must be finite")
    x0 = math.floor(x)
    t0 = math.floor(t)
    x_fraction = x - x0
    t_fraction = t - t0
    x_fade = x_fraction * x_fraction * x_fraction * (
        x_fraction * (x_fraction * 6.0 - 15.0) + 10.0
    )
    t_fade = t_fraction * t_fraction * t_fraction * (
        t_fraction * (t_fraction * 6.0 - 15.0) + 10.0
    )
    lower = _lattice_value(x0, t0, seed) + (
        _lattice_value(x0 + 1, t0, seed) - _lattice_value(x0, t0, seed)
    ) * x_fade
    upper = _lattice_value(x0, t0 + 1, seed) + (
        _lattice_value(x0 + 1, t0 + 1, seed)
        - _lattice_value(x0, t0 + 1, seed)
    ) * x_fade
    return lower + (upper - lower) * t_fade
