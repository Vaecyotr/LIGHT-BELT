# UDP v3 frame chunk contract

Status: Phase 32 software contract. **NOT HARDWARE VERIFIED.**

This contract extends the existing UDP v3 protocol without changing the
historical complete-frame message (`message_type = 0x01`) or its golden
vectors.  It does not add delivery acknowledgements, retransmission, or a
general reliable-UDP layer.

## Wire identity

Chunk datagrams use UDP v3 `message_type = 0x03`.  They retain the existing
29-byte big-endian header:

```text
magic:u16 version:u8 type:u8 node:u8 flags:u8 sequence:u32
media_timestamp_us:u64 apply_at_us:u64 chunk_count:u8 payload_length:u16
```

Each chunk entry is:

```text
output_id:u8 gpio:u8 total_pixel_count:u16 chunk_offset:u16
chunk_pixel_count:u16 chunk_payload_length:u16 rgb_payload
```

`chunk_payload_length` must equal `chunk_pixel_count * 3`.  The final four
bytes of every datagram are the existing Ethernet CRC-32 over its header and
payload.  A packet may contain one or more non-overlapping chunk entries, up
to the existing three configured physical outputs.

All datagrams for one logical node frame carry the same node ID, flags,
sequence, media timestamp, and optional apply time.  `SAFE_STATE`,
`KEY_FRAME`, and `SCHEDULED_APPLY` therefore belong to the complete logical
frame, not to an individual chunk.

## Packetization

The Host first attempts the historical complete-frame encoding.  When that
encoding would exceed the node's configured `max_udp_payload`, it emits chunk
datagrams.  `max_udp_payload` selects the largest chunk that fits; it is not a
strip-length limit.  Current u16 count and offset fields remain the protocol's
numeric boundary.

Every enabled node is fully encoded before the Host sends the first datagram
for a logical frame.  A scheduled session-start retry repeats the complete,
byte-identical ordered chunk set for that node.

## Reassembly and refresh

The receiver owns at most one incomplete logical frame.  It validates each
datagram before changing reassembly state and indexes data by complete frame
identity, output ID, and chunk offset.

A frame is complete only when every output declared by the receiver's current
configuration has exactly one value for every pixel in `[0,
total_pixel_count)`.  Only then may it enter the latest-complete-frame queue;
the physical output refreshes once for that complete node frame.

- Chunks may arrive out of order.
- A byte-identical duplicate or identical overlapping range is idempotent.
- A conflicting overlap, bad CRC, invalid range, unknown output, wrong GPIO,
  wrong total length, or mixed frame identity is rejected without exposing a
  partial frame.
- A strictly newer sequence discards an incomplete older frame and begins a
  new one.  Older traffic is rejected using uint32 wrap-aware ordering.
- Missing chunks leave the frame incomplete forever; there is no partial
  refresh.
- After a frame completes, duplicate traffic for that same identity cannot
  enqueue a second refresh.
- A valid sequence-1 `KEY_FRAME` retains the existing explicit session-reset
  role.

Framebuffer allocation is derived from the receiver's configured output
lengths.  Allocation failure is an explicit initialization failure, not a
product-level pixel-count rule.
