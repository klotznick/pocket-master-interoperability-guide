# Pocket Master Interoperability Guide

Independent, unofficial interoperability notes for the Sonicake Pocket Master. This document records behavior established beyond the MIDI command table in the product manual. It is intended for owners and developers working with hardware they own or control.

It combines a practical standard-MIDI reference with narrowly scoped, independently authored observations of the vendor-specific editor protocol, stored-preset format, and tested read and write workflows. Published behavior, hardware-confirmed behavior, inference, and unknowns are distinguished throughout.

This project is not affiliated with or endorsed by Sonicake. Sonicake and Pocket Master are used only to identify the compatible product. Obtain manuals, applications, firmware, and drivers directly from Sonicake.

**Last updated:** July 24, 2026

## Scope

- Primary tested device firmware: Pocket Master V1.3.3
- Published baseline: Pocket Master firmware V1.3.0 MIDI table
- Primary standard-MIDI test channel: channel 1
- Connections observed: class-compliant USB MIDI and BLE MIDI through SONICLINK

These notes describe original observations and interoperability facts. They do not include vendor software, firmware, manuals, decompiled source, creative assets, access-control material, or complete factory-preset datasets.

## Safety

Read requests are generally lower risk, but live edits can cause sudden volume or tonal changes, and persistent writes can overwrite user presets. Before transmitting, confirm the exact connected product and firmware, close or disconnect other editors where possible, and reduce monitoring volume before testing live controls.

For persistent work, back up the destination and use a sacrificial P bank slot during development. Verify complete semantic readback rather than relying only on an acknowledgement, and prove the restoration path before depending on the workflow. Never select a write destination solely from stale UI state, a previously sent preset-selection CC, or an unverified cached address.

## Contents

- [Safety](#safety)
- [Standard MIDI command reference](#standard-midi-command-reference)
- [Findings beyond the manual](#findings-beyond-the-manual)
- [Vendor-specific SysEx overview](#vendor-specific-sysex-overview)
- [Stored presets and `.prst` structure](#stored-presets-and-prst-structure)
- [Known limits](#known-limits)
- [Contributing findings](#contributing-findings)
- [AI assistance](#ai-assistance)
- [License](#license)

## Labels

| Label | Meaning |
|:---|:---|
| **Manual** | Stated in the published MIDI table |
| **Confirmed** | Supported by repeated observation, an independent cross-check, or a bounded test with restoration |
| **Inferred** | Supported by evidence but not independently proved in all important respects |
| **Unknown** | Observed without enough evidence to assign a meaning |
| **Passive** | Does not transmit to the device |
| **Device read** | Transmits a read request without intending to change state |
| **Live** | Can alter the current unsaved sound or device state |
| **Persistent** | Can alter a saved user preset |

Evidence confidence and operational risk are separate. A persistent command can be confirmed and still require careful backup, verification, and restoration.

## Standard MIDI command reference

This section combines the published Pocket Master V1.3.0 MIDI table with behavior additionally tested on firmware V1.3.3. It is not exhaustive evidence for undocumented commands, MIDI channels other than channel 1, untested trigger semantics, or later firmware versions.

Standard Control Change messages contain three bytes:

```text
Bn cc vv
```

- `n` is the zero-based channel nibble. MIDI channel 1 uses `B0`.
- `cc` is the controller number.
- `vv` is the value.
- All byte examples below are hexadecimal and use MIDI channel 1.

Channel 1 is confirmed on the tested Pocket Master. Acceptance of the same commands on other channels has not been established.

### Presets, volume, and navigation

| Function | CC decimal | CC hex | Value decimal | Channel-1 bytes |
|:---|---:|---:|:---|:---|
| Select user preset P01–P50 | 1 | `01` | 1–50 | `B0 01 01` – `B0 01 32` |
| Select factory preset F01–F50 | 1 | `01` | 51–100 | `B0 01 33` – `B0 01 64` |
| Master Volume | 6 | `06` | 0–100 | `B0 06 00` – `B0 06 64` |
| Preset Volume | 7 | `07` | 0–100 | `B0 07 00` – `B0 07 64` |
| Previous bank | 22 | `16` | 0–127 | `B0 16 00` – `B0 16 7F` |
| Next bank | 23 | `17` | 0–127 | `B0 17 00` – `B0 17 7F` |
| Previous preset | 24 | `18` | 0–127 | `B0 18 00` – `B0 18 7F` |
| Next preset | 25 | `19` | 0–127 | `B0 19 00` – `B0 19 7F` |

Preset selection and the two volume controls were confirmed for tested targets or values on the tested device. The manual supplies the full ranges. The four navigation assignments remain vendor-documented only in this project; the manual does not explain their edge or momentary behavior, and their exact trigger semantics have not been isolated.

### Effect-module bypass

For every switch below, values `0–63` (`00–3F`) mean Off and `64–127` (`40–7F`) mean On.

| Module | Module ID | CC decimal | CC hex | Off example | On example |
|:---|---:|---:|---:|:---|:---|
| NR / Noise Gate | 0 | 43 | `2B` | `B0 2B 00` | `B0 2B 7F` |
| FX1 | 1 | 44 | `2C` | `B0 2C 00` | `B0 2C 7F` |
| DRV | 2 | 45 | `2D` | `B0 2D 00` | `B0 2D 7F` |
| AMP | 3 | 46 | `2E` | `B0 2E 00` | `B0 2E 7F` |
| IR | 4 | 47 | `2F` | `B0 2F 00` | `B0 2F 7F` |
| EQ | 5 | 48 | `30` | `B0 30 00` | `B0 30 7F` |
| FX2 | 6 | 49 | `31` | `B0 31 00` | `B0 31 7F` |
| DLY | 7 | 50 | `32` | `B0 32 00` | `B0 32 7F` |
| RVB | 8 | 51 | `33` | `B0 33 00` | `B0 33 7F` |

All nine original-module bypass assignments were confirmed on the tested device. There is no documented or confirmed standard MIDI bypass command for Clone. Do not assume that CC 52 controls it.

### Tuner and looper

| Function | CC decimal | CC hex | Value meaning | Channel-1 bytes |
|:---|---:|---:|:---|:---|
| Tuner | 58 | `3A` | 0–63 Off; 64–127 On | `B0 3A 00` / `B0 3A 7F` |
| Looper menu | 59 | `3B` | 0–63 Off; 64–127 On | `B0 3B 00` / `B0 3B 7F` |
| Looper Record | 60 | `3C` | 0–127; trigger behavior unspecified | `B0 3C 00` – `B0 3C 7F` |
| Looper Play/Stop | 62 | `3E` | 0–63 Stop; 64–127 Play | `B0 3E 00` / `B0 3E 7F` |
| Delete Loop | 64 | `40` | 0–127; trigger behavior unspecified | `B0 40 00` – `B0 40 7F` |
| Looper Recording Volume | 65 | `41` | 0–100 | `B0 41 00` – `B0 41 64` |
| Looper Playback Volume | 66 | `42` | 0–100 | `B0 42 00` – `B0 42 64` |
| Looper Placement | 67 | `43` | 0–63 Post; 64–127 Pre | `B0 43 00` / `B0 43 7F` |

Tuner, Looper menu, and Looper Play/Stop were confirmed on the tested device. Looper Record and Delete Loop remain vendor-documented only and have deliberately not been transmitted because the manual does not define whether they respond to a value, an edge, or a momentary press-and-release sequence. The two looper-volume ranges and Looper Placement are also supplied by the manual and were not independently confirmed by this project.

### Drum controls

| Function | CC decimal | CC hex | Value meaning | Channel-1 bytes |
|:---|---:|---:|:---|:---|
| Drum menu | 92 | `5C` | 0–63 Off; 64–127 On | `B0 5C 00` / `B0 5C 7F` |
| Drum Play/Stop | 93 | `5D` | 0–63 Stop; 64–127 Play | `B0 5D 00` / `B0 5D 7F` |
| Drum Rhythm | 94 | `5E` | Rhythm 0–9 | `B0 5E 00` – `B0 5E 09` |
| Drum Volume | 95 | `5F` | 0–100 | `B0 5F 00` – `B0 5F 64` |

Drum menu and Drum Play/Stop were confirmed on the tested device. For Drum Rhythm, values 0 and 1 were confirmed; the full `0–9` range comes from the manual. Drum Volume remains vendor-documented only in this project.

SONICLINK displays a substantially larger catalog of named styles or rhythms, but those entries must not be assumed to map one-to-one onto CC 94. In the published standard-MIDI interface, CC 94 defines numeric rhythm values `0–9`; values 0 and 1 were confirmed on the tested device. No standard-MIDI transmission of a displayed style name has been established.

### Implementation cautions

- Clamp transmitted values to the documented range.
- Require an explicit user action before transmitting.
- Treat Off/On ranges as ranges, not only the example values `00` and `7F`.
- Do not claim confirmed device state merely because a message was sent.
- Do not invent commands for gaps in the CC table.
- Keep standard Control Change handling separate from the vendor-specific SysEx editor protocol.

## Findings beyond the manual

### Preset numbering matches the device's internal directory

**Confirmed · Live**

The manual assigns CC 1 values 1–100 to presets P01–P50 and F01–F50. The device's vendor-specific preset directory uses zero-based absolute addresses 0–99. The two number systems align exactly:

| CC 1 value | Internal address | Displayed preset |
|---:|---:|:---|
| 1 | 0 | P01 |
| 50 | 49 | P50 |
| 51 | 50 | F01 |
| 100 | 99 | F50 |

```text
internal_address = CC_1_value - 1
```

This connects standard-MIDI preset selection to the directory and stored-preset address space. A successfully sent CC does not by itself confirm the device's current active address.

### The original bypass controls match internal module IDs

**Confirmed · Live**

The manual's consecutive bypass controls map exactly to original-module identifiers 0–8:

| Module ID | Module | CC | Off | On |
|---:|:---|---:|:---|:---|
| 0 | NR | 43 | 0–63 | 64–127 |
| 1 | FX1 | 44 | 0–63 | 64–127 |
| 2 | DRV | 45 | 0–63 | 64–127 |
| 3 | AMP | 46 | 0–63 | 64–127 |
| 4 | IR | 47 | 0–63 | 64–127 |
| 5 | EQ | 48 | 0–63 | 64–127 |
| 6 | FX2 | 49 | 0–63 | 64–127 |
| 7 | DLY | 50 | 0–63 | 64–127 |
| 8 | RVB | 51 | 0–63 | 64–127 |

All nine were exercised on MIDI channel 1 with bounded inverse-and-restore tests. The tested device returned module-aware vendor-specific feedback.

Firmware V1.3.3 contains Clone-related state, but the manual assigns no standard bypass CC to Clone. There is no evidence that CC 52 or another undocumented CC controls it.

### Standard bypass CCs produce vendor-specific state feedback

**Confirmed · Live**

The tested device responded to original-module bypass CCs with a vendor-specific message whose logical message begins with `12 49`:

```text
12 49 mm 00 00 00 ee 00 00 00
      ^^          ^^
      module ID   00 off / 01 on
```

This provides semantic state confirmation for the original modules. It should not be generalized to unrelated controls. Master Volume, for example, has no mapped immediate feedback message; it can instead be confirmed by a separate on-demand `12 10` global-settings read.

### MIDI edits and saved presets are different state

**Confirmed · Live**

Module and detailed parameter changes can alter the current sound without modifying the saved preset. Controlled experiments changed one live value, independently reread the stored preset to confirm it was unchanged, and then restored the live value.

```text
requested value -> unsaved live buffer -> optional explicit save -> stored P preset
```

A valid checksum, generic acknowledgement, audible change, or updated editor display does not by itself prove persistence.

### USB and BLE do not provide symmetrical observation

**Confirmed for NR and FX1 · Live**

USB-originated changes were visible in SONICLINK over BLE. In the tested concurrent session, BLE-originated changes were not echoed to the passive USB listener. A USB application therefore cannot assume that passive monitoring provides complete current state while another editor is active.

### Two looper actions remain underspecified

**Unknown · Potentially live**

The manual assigns `0–127` to CC 60 (Looper Record) and CC 64 (Delete Loop) without defining threshold, edge, or momentary-trigger behavior. These notes do not invent semantics for them.

## Vendor-specific SysEx overview

The Pocket Master vendor-specific editor protocol is separate from standard Control Change messages. It is transported over MIDI SysEx and supports detailed state reads, live editing, the preset-name directory, stored-preset transfer, and persistent P bank operations.

### Binary terminology

- **Raw SysEx frame:** transported bytes from `F0` through `F7`.
- **Nibble-encoded body:** encoded bytes between the framing bytes.
- **Decoded body:** bytes reconstructed from nibble pairs, including CRC, command, subcommand, length, and payload.
- **Fragment payload:** logical payload bytes carried by one decoded multipart frame.
- **Logical message:** complete payload after validated multipart reassembly.
- **Stored preset record:** 494-byte preset payload returned by `12 4F`.
- **`.prst` container:** 515-byte exported file containing the product prefix, container version, CRC, and stored preset record.

### Confirmed wire properties

**Confirmed · Passive to decode**

- The nibble-encoded body is carried inside a raw SysEx frame with framing `F0 [nibble-encoded body] F7`.
- Each decoded byte is transmitted as its high nibble followed by its low nibble: `decoded = (high << 4) | low`.
- The decoded body has the four-byte header `[crc8, command, subcommand, payload_length]`, followed by exactly `payload_length` fragment-payload bytes.
- Integrity uses CRC-8 with polynomial `0x07`, initial value `0x00`, and xor-out `0x00`.
- CRC calculation covers the complete decoded body while treating its CRC byte at offset zero as `00`.
- Detailed numeric parameters observed on the wire use IEEE-754 `float32_le` values.
- Multipart transfers normally carry at most 19 fragment-payload bytes per raw SysEx frame. The outer command is the fragment count and the subcommand is the zero-based fragment index.

### Multipart validation

A strict implementation should reject a transfer when framing bytes are invalid; encoded bytes fall outside the nibble range `00`–`0F`; decoded fragment-payload length disagrees with `payload_length`; a frame fails CRC validation; the outer fragment-count command changes during a transfer; or a fragment index is duplicated, missing, or outside the expected range.

After reassembly, it should also reject a logical message that is shorter than the field-specific minimum, begins with a field identifier other than the expected response, or leaves unexplained trailing bytes after strict structured decoding. The field-specific sizes in this guide apply only to the observed firmware and documented responses; they are not universal protocol guarantees.

### Confirmed logical fields

| Field | Established meaning | Operational role |
|:---|:---|:---|
| `12 10` | Tagged global settings, firmware, and preset-format block | Device read |
| `12 30` / `11 30` | Request/response pair returning a preset-shaped index that is not the active preset | Unknown semantics |
| `12 40` | Complete 100-entry preset-name directory | Device read |
| `12 43` | Current preset index used in a coordinated state refresh | Device read |
| `12 41` | Complete current live-buffer detail, including unsaved changes | Device read |
| `12 4F` | Stored-preset read by explicit absolute address | Device read |
| `12 42` | Preset Volume feedback | Live feedback |
| `12 45` | State flag correlated with unsaved edit (`01`) and save completion (`00`) | Supporting feedback only |
| `12 48` | Model-parameter feedback; first isolated as NR threshold | Live feedback |
| `12 49` | Original-module enabled state | Live feedback |
| `12 1B` | Mode-2 invalidation observed after rename/save, prompting a directory reread | Supporting feedback only |
| `14 08` | Generic transport acknowledgement; status `00` observed on success | Transport feedback only |

The observed `12 30`/`11 30` exchange is not an active-preset read: it returned a P02-shaped value while the pedal displayed P44.

The principal read requests are field-only except for the explicitly addressed stored-preset read:

| Logical request | Observed response | Reassembled logical-message size |
|:---|:---|---:|
| `12 10` | Four command-`04` fragments beginning `12 10` | 71 bytes |
| `12 40` | 106 command-`6A` fragments beginning `12 40` | 2,002 bytes |
| `12 43` | `12 43 + uint16_le(absolute preset index)` | 4 bytes |
| `12 41` | 26 command-`1A` fragments beginning `12 41` | 476 bytes |
| `12 4F + uint32_le(absolute preset index)` | 27 command-`1B` fragments beginning `12 4F` | 496 bytes |

The exact confirmed raw field-only requests are:

```text
12 10  F0 0B 09 00 01 00 00 00 02 01 02 01 00 F7
12 40  F0 00 0E 00 01 00 00 00 02 01 02 04 00 F7
12 43  F0 00 07 00 01 00 00 00 02 01 02 04 03 F7
12 41  F0 00 09 00 01 00 00 00 02 01 02 04 01 F7
```

For `12 43`, confirmed examples are `12 43 01 00` for P02 and `12 43 4B 00` for F26. The `12 41` live detail contains the same 474-byte TLV section body used inside a stored preset record, omitting the record's four-byte slot placeholder and 16-byte name.

A cautious consistency procedure reads `12 43`, then `12 41`, then `12 43` again. Accept the live-buffer result as belonging to the selected preset context only when the two surrounding preset-index reads agree. This coordinated refresh reduces race risk but does not prove that the device provides transaction isolation. A sent preset-selection CC is not active-state proof.

### Global settings read

**Confirmed on firmware V1.3.3 · Device read**

The previously unidentified `12 10` startup logical message is a 71-byte tagged global-settings block. After the `12 10` field ID, each record contains:

```text
uint16_le tag
uint16_le value_length
value[value_length]
```

The four multipart response fragments must be reassembled before the tag records are decoded.

| Tag | Setting | Encoding | Connected value or interpretation |
|:---|:---|:---|:---|
| `0101` | Firmware version | Four version bytes | V1.3.3 |
| `0102` | Preset format version | `int32_le` | 2 |
| `0201` | Tuner state | Boolean byte | Off |
| `0202` | Master Volume | `int32_le` | 77 |
| `0203` | Display Brightness | Unsigned byte | 100 |
| `0204` | Energy saving | Boolean/integer byte | Tag mapped statically |
| `0205` | Boot Anti-Touch Protection | Boolean byte | On |
| `0206` | Battery-only mode | Boolean/integer byte | Tag mapped statically |
| `0207` | Tuner tool | Integer byte | Tag mapped statically |
| `0208` | Loopback | Boolean/integer byte | Tag mapped statically |
| `0301` | Input Level | Signed int8 dB | -10 dB |
| `0401` | USB/FX record level | Signed int8 dB | 0 dB |
| `0402` | USB output/Monitor level | Signed int8 dB | -20 dB |
| `0403` | Reamp | Boolean byte | Present in decoded block |
| `0404` | USB record mode | Unsigned byte | Present in decoded block |
| `0405` | Bluetooth record level | Signed int8 dB | 0 dB |
| `0406` | Reamp-related mode | Integer byte | Tag mapped statically |

The connected test sent one vendor-specific read and no setting, preset, or Control Change write. The strict 71-byte layout has only been confirmed on firmware V1.3.3.

### Battery and charge requests appear transport-specific

**Static mapping confirmed · No USB response**

SONICLINK identifies field-only reads `12 3A` as charge status and `12 3B` as battery level. Repeated settled USB-MIDI probes observed no response to either request, while an adjacent `12 10` control read succeeded. Silence does not prove that either request is invalid: BLE-specific or other transport-specific behavior remains possible. They should not be presented as working USB commands without additional evidence.

### Writes are address-specific

**Confirmed only for individually tested operations · Live or Persistent**

The following logical write forms have been established. “Confirmed” applies only to the exact tested scope, not every value that can fit the byte layout.

| Field | Logical-message shape | Hardware-tested scope |
|:---|:---|:---|
| `11 48` | `11 48 + uint32_le(module_slot) + uint32_le(parameter) + float32_le(value)` | Bounded tests of the listed parameter addresses across NR, FX1, DRV, AMP, EQ, FX2, DLY, and RVB |
| `11 47` | `11 47 + uint32_le(module) + uint32_le(slot) + uint32_le(effect_id)` | DRV Scream ↔ Butter OD only |
| `11 44` | `11 44 + module_order[10]` | One adjacent FX2 ↔ DLY chain transition only |
| `11 4C` | `11 4C + uint32_le(P bank index) + utf8_name[10]` | P05 rename and exact restoration |
| `11 4A` | `11 4A + uint32_le(P bank index) + utf8_name[10]` | Saving the verified current live buffer back to the same P bank slot |
| `11 4B` | `11 4B + uint16_le(destination) + uint16_le(source)` | P05 → P27 copy and F27 → P27 byte-exact restoration |
| `11 4F` | `11 4F + transformed 515-byte .prst container` | Direct import to a selected P bank slot with exact readback and restoration |
| `11 11` | `11 11 + uint32_le(tag) + int32_le(value)` | Display Brightness 100 → 95 → 100 only |

The hardware-tested `11 48` parameter addresses are narrower than the general logical-message shape:

| Module / required effect | Effect ID (decimal / hex) | Parameter index → label | Tested implementation range and step |
|:---|---:|:---|:---|
| NR | none required | `0` THRE | `0…100`, step 1 |
| FX1 — COMP 2 | `1` / `0x00000001` | `0` Sustain; `1` Attack; `2` VOL; `3` Clip | `0…100`, step 1 |
| DRV — Scream / Green Drive | `50331648` / `0x03000000` | `0` Gain; `1` Tone; `2` VOL | `0…100`, step 1 |
| AMP — Dark Twin / Black Twin | `117440516` / `0x07000004` | `0` Gain; `1` VOL; `2` Bass; `3` Middle; `4` Treble; `5` Bright | `0…100`, step 1 |
| EQ — GT EQ 1 / Guitar EQ 1 | `16777269` / `0x01000035` | `0` 125Hz; `1` 400Hz; `2` 800Hz; `3` 1.6kHz; `4` 4kHz; `5` VOL | bands `-50…50`; VOL `0…100`; step 1 |
| FX2 — A-Chorus / Aozora Chorus | `67108864` / `0x04000000` | `0` Depth; `1` Rate; `2` Tone | Depth/Tone `0…100`, step 1; Rate `0.1…10`, step 0.1 |
| DLY — Pure / Pure Eko | `184549376` / `0x0B000000` | `0` Mix; `1` Time; `2` F.Back | Mix/F.Back `0…100`; Time `20…1000`; step 1 |
| RVB — Room | `201326592` / `0x0C000000` | `0` Mix; `2` Decay | `0…100`, step 1 |

Every row is specific to the listed module, effect ID, parameter index, implementation range, and step. Bounded hardware tests exercised starting and adjacent or representative values rather than every value in every listed range; the implementation bounds also reflect the recovered application behavior already recorded by the project. They are not claims about theoretical encoding limits, other models, or all slots. No rejection, clamping, safety, or ignore behavior is implied for unlisted values. In particular, RVB Decay is algorithm parameter index `2`, not `1`; unlisted slots and models remain unverified.

The only hardware-tested `11 47` model transition is bidirectional DRV `50331648` / `0x03000000` (Scream / Green Drive) ↔ `50331650` / `0x03000002` (Butter OD / Yellow Drive). The only hardware-tested `11 44` chain transition is the exact adjacent FX2/DLY pair:

```text
00 01 02 03 04 05 06 07 08 09
00 01 02 03 04 05 07 06 08 09
```

These are complete ten-module permutations for `NR, FX1, DRV, AMP, IR, EQ, FX2, DLY, RVB, Clone` and its adjacent FX2/DLY swap. No other effect pair or chain move is implied.

Save and rename use a zero-based P bank index and a fixed ten-byte UTF-8 name. The name is null-padded and must be nonempty, contain no embedded null, and fit in ten UTF-8 bytes without truncation. Factory destinations are rejected.

The recovered application mapping uses multiples of five from `0` through `100`. Hardware writing was confirmed only for the bounded `100 → 95 → 100` Display Brightness test. The verified target and restore logical messages were:

```text
11 11 03 02 00 00 5F 00 00 00  brightness 95
11 11 03 02 00 00 64 00 00 00  brightness 100
```

The final `12 10` snapshot after restoration matched the complete baseline byte-for-byte. Other statically mapped global-setting writes have not completed their own bounded hardware tests.

### Persistent-write preconditions

#### Save the current live buffer — `11 4A`

**Persistent:** this operation overwrites a saved P bank preset.

The confirmed workflow saves the freshly read current live state back to the same explicitly confirmed P bank destination. Before sending, confirm the zero-based destination index independently, back up that destination, and refresh the live state. A sent preset-selection CC is not sufficient destination proof. After saving, reread the complete destination stored preset record. Save As to a different P bank slot is not confirmed.

#### Copy a stored preset — `11 4B`

**Persistent:** this operation overwrites the destination P bank preset.

The source may be in the P or F bank, but the persistent destination must be in the P bank. Range-validate both addresses, explicitly confirm and back up the destination, and reread the complete destination stored preset record afterward. Updating stored state does not necessarily activate that state in the live buffer.

### Acknowledgements and semantic verification

`14 08` is transport-level feedback. An observed `14 08 00` acknowledgement is not independently sufficient proof that a requested live or persistent state was applied. Verification is operation-specific:

- For a live bypass or parameter change, require matching state feedback or a fresh live-buffer read.
- For rename, reread the complete preset-name directory.
- For save or copy, reread the complete destination stored preset record.
- For `.prst` import, require the expected terminal import status, a directory reread, and exact comparison with the target stored preset record.
- For restoration, compare against the captured baseline, byte-exact where applicable.

## Stored presets and `.prst` structure

**Confirmed for the tested format · Passive to parse**

A Manager-exported `.prst` container contains:

- an 18-byte `Pocket Master` product prefix with null padding;
- a `uint16_le` container-header version; observed values are 0 and 2;
- a one-byte CRC-8 covering the remaining bytes;
- a 494-byte stored preset record.

An explicit `12 4F` read returns the same 494-byte stored preset record. It begins with a four-byte `FF FF FF FF` slot placeholder and a fixed 16-byte name. The remaining sectioned TLV data uses `uint16_le` section identifiers, field identifiers, and lengths:

| Section | Field | Encoding | Meaning |
|:---|:---|:---|:---|
| `00FF` | `0001` | `uint32_le` | Record format version; observed `2` |
| `00FF` | `0002` | 4 opaque bytes | Observed `0A 45 4D 51` |
| `0000` | `1001` | `uint32_le` | Module count; observed `10` |
| `0000` | `1002` | `uint32_le` | Parameter slots per module; observed `8` |
| `0000` | `1003` | `uint32_le` | Unknown layout value; observed `2` |
| `0001` | `2001` | `uint32_le` | Preset level |
| `0001` | `2002` | `uint32_le` | Tempo in BPM |
| `0002` | `3001` | `uint32_le` | Module-enable bit mask |
| `0002` | `3002` | 10 bytes | Signal-chain module permutation |
| `0002` | `3003` | 10 × `uint32_le` | Effect IDs by module |
| `0002` | `3004` | 80 × `float32_le` | Eight parameter slots for each of ten modules |
| `0003` | — | 8 bytes | Observed all-zero trailer |

Two user-bank exports were compared with their corresponding factory records and matched across every semantic field and raw parameter slot. This establishes read-only parsing and comparison independently of the write path.

### Direct `.prst` import — `11 4F`

**Persistent:** this operation can overwrite a P bank preset. The tested workflow requires all of the following before success is claimed:

- an exact 515-byte `.prst` container;
- the correct 18-byte product prefix;
- an observed and accepted container-header version, currently 0 or 2;
- a valid payload CRC;
- `FF FF FF FF` in the stored preset record's slot-placeholder field;
- explicit confirmation of a P bank destination and a captured destination backup;
- complete validation of every multipart frame and the reassembled logical message;
- the tested import-specific terminal acknowledgement behavior;
- a complete preset-directory reread;
- exact comparison with the destination stored preset record;
- a proven restoration path.

The deployment transform replaces container bytes 0–3 (`Pock`) with the selected P bank destination's zero-based absolute index encoded as `uint32_le`, prefixes `11 4F`, and retains container bytes 4…514:

```text
11 4F + uint32_le(P bank destination) + .prst bytes 4...514
```

The resulting 517-byte logical message is split into 28 multipart command-`1C` frames with indices `00–1B`. The hardware-observed acknowledgement statuses were `00, 00, 00, 00, 01`; terminal status `01` marked completion for this tested import workflow. This status sequence must not be generalized to unrelated multipart writes or to firmware versions that were not tested. The test additionally required a complete directory reread, exact target-record equality, and byte-exact restoration of the destination. A separate implementation using the same validation and verification gate subsequently deployed both an unmodified `.prst` and a locally edited complete preset.

Saved-slot copy through `11 4B` is also confirmed. Copying a stored preset can update the destination record without immediately replacing an already loaded live buffer, so saved deployment and live activation must remain distinct.

## Known limits

- Acceptance of standard CCs on channels other than channel 1 is unknown.
- Standard MIDI does not provide independently mapped active-preset feedback after CC 1 selection.
- CC 60 and CC 64 trigger semantics are unknown.
- No standard MIDI mapping for Clone has been established.
- No response to `12 3A` charge or `12 3B` battery reads was observed over the tested USB transport; transport-specific behavior remains possible.
- Device Save As through `11 4A` to a different P bank slot has not completed its own bounded validation.
- Only Display Brightness has a hardware-confirmed `11 11` global-setting write; the other mapped settings remain read-only.
- IR/Clone transfer and firmware update are outside this public documentation scope.
- Findings should not be assumed to apply to firmware versions that were not tested.

## Contributing findings

Proposed findings should include:

- exact firmware version;
- host platform and version;
- SONICLINK version when relevant;
- connection type;
- starting state and exactly one changed variable;
- exact transmitted bytes;
- exact received bytes or a minimized decoded result;
- number of repetitions;
- independent readback and restoration result;
- whether another editor was connected;
- operational category: Passive, Device read, Live, or Persistent;
- confirmation that no vendor-owned binary or complete factory dataset is being submitted.

Names recovered through static inspection may guide testing but are not hardware confirmation. A successful send is not proof of state, and an acknowledgement is not proof of persistence. Conclusions must remain narrower than or equal to the demonstrated evidence.

Do not publish vendor applications, APKs, firmware, installers, manuals, decompiled source, proprietary creative assets, complete factory-preset datasets, factory IR files, credentials, personal identifiers, or access-control material. Preserve original captures privately and publish only minimized evidence necessary to reproduce an owner-controlled interoperability claim.

## AI assistance

AI tools assisted with drafting, editing, and analysis. The author directed the work and validated technical claims against documented observations and hardware tests.

## License

To the extent permitted by law, the author has dedicated the original material in this guide to the public domain under [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).

You may copy, modify, distribute, and use it for any purpose without permission or attribution.

This dedication applies only to material for which the author holds rights. Sonicake trademarks and third-party materials remain the property of their respective owners.

If executable source code is later added to the repository, it may be placed under a separate software license such as MIT or Apache-2.0. CC0 remains the license for the original guide material unless stated otherwise.

This guide is provided as-is, without warranty. Use device-control commands at your own risk.
