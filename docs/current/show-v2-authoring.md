# Show v2 authoring

Show v2 is the canonical writable format. The loader still reads v1 and
normalizes `effect.name/parameters` to the runtime `effect.id/params` model,
but new examples and serializers must emit v2.

Targets use exactly one shape: `analog_zone + id`, `digital_strip + id`,
`digital_set + ids`, `digital_group + id`, or `virtual_path + id`. A
`digital_set` is an explicit ordered list; a `digital_group` is a named catalog
entry. Neither contains controller, GPIO, host, port, packet offset, or other
physical topology.

An effect registration binds three things: a stable ID, a parameter validator,
and a renderer class. Adding an effect therefore consists of implementing its
renderer, registering that triple, and testing its parameters. Target dispatch
does not change. Cue color is a separate `ColorSpec`: `effect_default` leaves
the renderer default intact, `solid` supplies one RGB color, and `palette`
selects authored RGB entries deterministically from cue-local time.

Logical virtual paths may contain ordered analog and digital targets. Their
origin is one of `start`, `end`, `center`, or `edges`; the same modes are valid
on cues and bounded branches. A virtual-path cue with no authored `origin`
inherits the path origin; an explicit cue origin overrides it. Non-path cues
and normalized v1 cues default to `start`. The cabin example defines three
paths whose union covers all fourteen logical runs.

Branching is intentionally bounded. A branch names one Show v2 path member as
its completion trigger and one `digital_set` as its release target. Completion
is derived from cumulative logical run length divided by total path length,
then compared to normalized cue/path progress. It does not inspect or detect a
renderer's visible wavefront. All IDs in the set are rendered using the same
logical frame timestamp and sequence. This is not a general graph/DAG API.

For a visible chase that forks after one shared strip, do not use a bounded
branch as a wavefront detector. Author one virtual path per destination with
the same prefix, then run identical fixed `chase` cues over those paths. For
example, `strip_11 -> strip_12`, `strip_11 -> strip_91`, and `strip_11 ->
strip_92` share the same first ten logical coordinates. With identical start,
end, priority, origin, chase parameters, and static color, their contributions
on `strip_11` are identical; the next coordinate lands on the first pixel of
all three destination strips in the same logical frame. See
`config/examples/cabin-show-fork-v2.yaml`. Keep `color_source: static`; rainbow or
video coloring can differ across paths of different total lengths and is not
covered by this fork contract.

The cabin layout, run lengths, and wiring remain `NOT HARDWARE VERIFIED`.
