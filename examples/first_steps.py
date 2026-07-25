#!/usr/bin/env python3
"""Small, conservative Pocket Master interoperability exercises.

Live MIDI commands require Mido with its RtMidi port backend:
    python -m pip install "mido[ports-rtmidi]"

Offline .prst inspection uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
import time
from pathlib import Path
from typing import Any


MODULE_NAMES = ("NR", "FX1", "DRV", "AMP", "IR", "EQ", "FX2", "DLY", "RVB", "Clone")
GLOBAL_TAG_NAMES = {
    0x0101: "Firmware version",
    0x0102: "Preset format version",
    0x0201: "Tuner state",
    0x0202: "Master Volume",
    0x0203: "Display Brightness",
    0x0205: "Anti-Touch Protection",
    0x0301: "Input Level",
    0x0401: "USB/FX record level",
    0x0402: "USB output/Monitor level",
    0x0403: "Reamp",
    0x0404: "USB record mode",
    0x0405: "Bluetooth record level",
}
GLOBAL_SETTINGS_REQUEST_DATA = bytes.fromhex("0B 09 00 01 00 00 00 02 01 02 01 00")
GLOBAL_SETTINGS_REQUEST_RAW = bytes([0xF0]) + GLOBAL_SETTINGS_REQUEST_DATA + bytes([0xF7])
MIDI_POST_OPEN_SETTLE_SECONDS = 0.15
MIDI_RETRY_COOLDOWN_SECONDS = 10.0


class ExampleError(RuntimeError):
    """A concise, user-facing failure."""


def positive_finite_seconds(value: str | float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("timeout must be a number") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and greater than zero")
    return seconds


def require_mido() -> Any:
    try:
        import mido
    except ImportError as error:
        raise ExampleError(
            'Live MIDI examples require Mido. Install it with: '
            'python -m pip install "mido[ports-rtmidi]"'
        ) from error
    return mido


def crc8(data: bytes | bytearray) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def list_ports(_: argparse.Namespace) -> None:
    mido = require_mido()
    inputs = mido.get_input_names()
    outputs = mido.get_output_names()

    print("MIDI inputs:")
    for name in inputs:
        print(f"  {name}")
    if not inputs:
        print("  (none)")

    print("\nMIDI outputs:")
    for name in outputs:
        print(f"  {name}")
    if not outputs:
        print("  (none)")

    print(
        "\nUse the complete, exact port names shown here with --in and --out. "
        "Do not select a virtual, network, or similarly named endpoint."
    )


def toggle_nr(args: argparse.Namespace) -> None:
    starting_on = args.starting == "on"
    target_value = 0 if starting_on else 127
    restore_value = 127 if starting_on else 0

    print("Risk: Live — changes the unsaved NR state; sends no preset-save command.")
    print(f"Output: {args.out}")
    print(f"Recorded starting state: NR {args.starting.upper()}")
    print(
        f"Target bytes:  B0 2B {target_value:02X}\n"
        f"Restore bytes: B0 2B {restore_value:02X}"
    )
    if args.dry_run:
        print("Dry run: no MIDI library loaded, no port opened, and no message sent.")
        return

    mido = require_mido()
    if input("Type TOGGLE to send the target and prepare an automatic restore: ") != "TOGGLE":
        raise ExampleError("Cancelled before sending anything.")

    with mido.open_output(args.out) as output:
        changed = False
        try:
            output.send(
                mido.Message(
                    "control_change",
                    channel=0,
                    control=43,
                    value=target_value,
                )
            )
            changed = True
            input("Observe the NR state, then press Enter to restore it: ")
        finally:
            if changed:
                output.send(
                    mido.Message(
                        "control_change",
                        channel=0,
                        control=43,
                        value=restore_value,
                    )
                )
                print(
                    f"Restore message sent: B0 2B {restore_value:02X}; "
                    "verify the original state on the device."
                )


def decode_sysex_data(data: bytes) -> tuple[int, int, bytes]:
    if len(data) % 2:
        raise ExampleError("Received an odd number of encoded nibbles.")
    if any(byte > 0x0F for byte in data):
        raise ExampleError("Received a non-nibble byte inside the SysEx body.")

    body = bytes((data[index] << 4) | data[index + 1] for index in range(0, len(data), 2))
    if len(body) < 4:
        raise ExampleError("Decoded SysEx body is shorter than four bytes.")
    if body[3] != len(body) - 4:
        raise ExampleError("Decoded SysEx payload length does not match its header.")

    stored_crc = body[0]
    crc_input = bytes([0]) + body[1:]
    calculated_crc = crc8(crc_input)
    if stored_crc != calculated_crc:
        raise ExampleError(
            f"SysEx CRC mismatch: received {stored_crc:02X}, calculated {calculated_crc:02X}."
        )
    return body[1], body[2], body[4:]


def parse_tlvs(data: bytes) -> dict[int, bytes]:
    fields: dict[int, bytes] = {}
    offset = 0
    while offset < len(data):
        if offset + 4 > len(data):
            raise ExampleError(f"Truncated TLV header at offset {offset}.")
        identifier, length = struct.unpack_from("<HH", data, offset)
        start = offset + 4
        end = start + length
        if end > len(data):
            raise ExampleError(f"TLV {identifier:04X} extends beyond the available data.")
        if identifier in fields:
            raise ExampleError(f"Duplicate TLV identifier {identifier:04X}.")
        fields[identifier] = data[start:end]
        offset = end
    return fields


def describe_global_value(tag: int, value: bytes) -> str:
    if tag == 0x0101 and len(value) == 4:
        prefix = "B" if value[3] == 0 else "V"
        return f"{prefix}{value[2]}.{value[1]}.{value[0]}"
    if tag in {0x0102, 0x0202} and len(value) == 4:
        return str(int.from_bytes(value, "little", signed=True))
    if tag in {0x0301, 0x0401, 0x0402, 0x0405} and len(value) == 1:
        return f"{int.from_bytes(value, 'little', signed=True)} dB"
    if len(value) == 1:
        return str(value[0])
    return value.hex(" ").upper()


def accept_settings_fragment(
    fragments: dict[int, bytes], subcommand: int, payload: bytes
) -> None:
    if subcommand not in range(4):
        raise ExampleError(f"Settings fragment index {subcommand:02X} is outside 00...03.")
    if subcommand in fragments:
        if fragments[subcommand] == payload:
            raise ExampleError(f"Duplicate settings fragment index {subcommand:02X}.")
        raise ExampleError(f"Conflicting duplicate settings fragment index {subcommand:02X}.")
    expected = len(fragments)
    if subcommand != expected:
        raise ExampleError(
            f"Out-of-order settings fragment index {subcommand:02X}; "
            f"expected {expected:02X}."
        )
    fragments[subcommand] = payload


def reassemble_settings_fragments(fragments: dict[int, bytes]) -> bytes:
    missing = [index for index in range(4) if index not in fragments]
    if missing:
        raise ExampleError(
            f"Timed out before receiving all four settings fragments; missing {missing}."
        )
    logical = b"".join(fragments[index] for index in range(4))
    if len(logical) != 71 or not logical.startswith(b"\x12\x10"):
        raise ExampleError(
            f"Unexpected reassembled response: {len(logical)} bytes, "
            f"prefix {logical[:2].hex(' ').upper()}."
        )
    return logical


def read_settings(args: argparse.Namespace) -> None:
    try:
        timeout = positive_finite_seconds(args.timeout)
    except argparse.ArgumentTypeError as error:
        raise ExampleError(str(error)) from error

    print("Risk: Device read — sends one settings request and no state-changing command.")
    print(f"Input:  {args.input}")
    print(f"Output: {args.out}")
    print("Logical request: 12 10")
    print(f"Raw SysEx:       {GLOBAL_SETTINGS_REQUEST_RAW.hex(' ').upper()}")
    if args.dry_run:
        print("Dry run: no MIDI library loaded, no port opened, and no message sent.")
        return

    mido = require_mido()
    fragments: dict[int, bytes] = {}
    print(
        "Opening a fresh input/output session, settling briefly, and discarding "
        "stale pending input before one request..."
    )
    try:
        with (
            mido.open_input(args.input) as midi_input,
            mido.open_output(args.out) as midi_output,
        ):
            time.sleep(MIDI_POST_OPEN_SETTLE_SECONDS)
            stale_count = sum(1 for _ in midi_input.iter_pending())
            if stale_count:
                print(f"Discarded {stale_count} stale pending MIDI message(s).")

            midi_output.send(mido.Message("sysex", data=GLOBAL_SETTINGS_REQUEST_DATA))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and len(fragments) < 4:
                for message in midi_input.iter_pending():
                    if message.type != "sysex":
                        continue
                    command, subcommand, payload = decode_sysex_data(
                        bytes(message.data)
                    )
                    if command == 0x04:
                        accept_settings_fragment(fragments, subcommand, payload)
                time.sleep(0.01)

        logical = reassemble_settings_fragments(fragments)
    except ExampleError as error:
        raise ExampleError(
            f"{error} MIDI ports are closed. Do not retry automatically; wait at "
            f"least {MIDI_RETRY_COOLDOWN_SECONDS:g} seconds with the ports closed, "
            "then start a fresh operator-authorized session."
        ) from error

    print("Received 4 valid fragments.")
    print("Reassembled response: 71 bytes beginning 12 10.")
    fields = parse_tlvs(logical[2:])
    for tag in sorted(fields):
        name = GLOBAL_TAG_NAMES.get(tag, "Unmapped tag")
        value = fields[tag]
        print(
            f"  {tag:04X}  {name:<28} "
            f"{describe_global_value(tag, value)} "
            f"(raw {value.hex(' ').upper()})"
        )


def require_field(fields: dict[int, bytes], identifier: int, length: int | None = None) -> bytes:
    if identifier not in fields:
        raise ExampleError(f"Required TLV {identifier:04X} is missing.")
    value = fields[identifier]
    if length is not None and len(value) != length:
        raise ExampleError(
            f"TLV {identifier:04X} has {len(value)} bytes; expected {length}."
        )
    return value


def inspect_prst(args: argparse.Namespace) -> None:
    path = Path(args.file)
    size = path.stat().st_size
    if size != 515:
        raise ExampleError(f"{path.name} has {size} bytes; expected 515.")
    data = path.read_bytes()

    expected_header = b"Pocket Master" + bytes(5)
    if data[:18] != expected_header:
        raise ExampleError("The 18-byte Pocket Master product header does not match.")

    header_version = int.from_bytes(data[18:20], "little")
    if header_version not in {0, 2}:
        raise ExampleError(f"Unsupported observed container-header version {header_version}.")

    payload = data[21:]
    stored_crc = data[20]
    calculated_crc = crc8(payload)
    if stored_crc != calculated_crc:
        raise ExampleError(
            f"Payload CRC mismatch: stored {stored_crc:02X}, calculated {calculated_crc:02X}."
        )
    if payload[:4] != b"\xFF\xFF\xFF\xFF":
        raise ExampleError("Stored-preset slot placeholder is not FFFFFFFF.")

    raw_name = payload[4:20].split(b"\0", 1)[0]
    try:
        name = raw_name.decode("utf-8")
    except UnicodeDecodeError:
        name = "<not valid UTF-8; see raw bytes>"

    sections = parse_tlvs(payload[20:])
    format_fields = parse_tlvs(require_field(sections, 0x00FF))
    layout_fields = parse_tlvs(require_field(sections, 0x0000))
    global_fields = parse_tlvs(require_field(sections, 0x0001))
    module_fields = parse_tlvs(require_field(sections, 0x0002))
    if require_field(sections, 0x0003, 8) != bytes(8):
        raise ExampleError("Preset trailer is not the observed eight zero bytes.")

    record_version = int.from_bytes(require_field(format_fields, 0x0001, 4), "little")
    if record_version != 2:
        raise ExampleError(
            f"Unsupported stored-preset record version {record_version}; "
            "only observed version 2 is interpreted."
        )
    require_field(format_fields, 0x0002, 4)
    module_count = int.from_bytes(require_field(layout_fields, 0x1001, 4), "little")
    parameter_slots = int.from_bytes(require_field(layout_fields, 0x1002, 4), "little")
    require_field(layout_fields, 0x1003, 4)
    if (module_count, parameter_slots) != (10, 8):
        raise ExampleError(
            f"Unsupported layout: {module_count} modules × {parameter_slots} parameters."
        )

    preset_level = int.from_bytes(require_field(global_fields, 0x2001, 4), "little")
    tempo = int.from_bytes(require_field(global_fields, 0x2002, 4), "little")
    enable_mask = int.from_bytes(require_field(module_fields, 0x3001, 4), "little")
    if enable_mask & ~0x03FF:
        raise ExampleError(
            f"Module-enable mask {enable_mask:08X} sets bits outside known modules 0...9."
        )
    chain = list(require_field(module_fields, 0x3002, 10))
    if sorted(chain) != list(range(10)):
        raise ExampleError("Signal chain is not a complete ten-module permutation.")
    effect_bytes = require_field(module_fields, 0x3003, 40)
    parameter_bytes = require_field(module_fields, 0x3004, 320)

    print(f"File:            {path}")
    print(f"Container:       valid, version {header_version}, CRC {stored_crc:02X}")
    print(f"Preset:          {name}")
    print(f"Preset name raw: {raw_name.hex(' ').upper() or '(empty)'}")
    print(f"Record version:  {record_version}")
    print(f"Preset level:    {preset_level}")
    print(f"Tempo:           {tempo} BPM")
    print("Signal chain:    " + " → ".join(MODULE_NAMES[module] for module in chain))
    print("Modules:")
    for module_id, module_name in enumerate(MODULE_NAMES):
        effect_id = int.from_bytes(
            effect_bytes[module_id * 4 : module_id * 4 + 4], "little"
        )
        parameter_base = module_id * 32
        parameters = struct.unpack_from("<8f", parameter_bytes, parameter_base)
        state = "on" if enable_mask & (1 << module_id) else "bypassed"
        position = chain.index(module_id)
        formatted: list[str] = []
        for parameter_index, value in enumerate(parameters):
            raw_start = parameter_base + parameter_index * 4
            raw_value = parameter_bytes[raw_start : raw_start + 4]
            if math.isfinite(value):
                formatted.append(f"{value:g}")
            else:
                formatted.append(
                    f"{value} (raw {raw_value.hex(' ').upper()})"
                )
        formatted_parameters = ", ".join(formatted)
        print(
            f"  {position:>2}  {module_name:<5} {state:<8} "
            f"effect {effect_id:<10} params [{formatted_parameters}]"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Conservative first exercises for Pocket Master interoperability."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ports_parser = subparsers.add_parser("ports", help="List available MIDI ports.")
    ports_parser.set_defaults(handler=list_ports)

    toggle_parser = subparsers.add_parser(
        "toggle-nr", help="Toggle NR once and restore its recorded starting state."
    )
    toggle_parser.add_argument("--out", required=True, help="Exact MIDI output port name.")
    toggle_parser.add_argument(
        "--starting",
        choices=("on", "off"),
        required=True,
        help="NR state observed before running the command.",
    )
    toggle_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print risk and exact bytes without loading MIDI or opening a port.",
    )
    toggle_parser.set_defaults(handler=toggle_nr)

    settings_parser = subparsers.add_parser(
        "read-settings", help="Send the read-only 12 10 settings request."
    )
    settings_parser.add_argument("--in", dest="input", required=True, help="Exact MIDI input.")
    settings_parser.add_argument("--out", required=True, help="Exact MIDI output.")
    settings_parser.add_argument(
        "--timeout",
        type=positive_finite_seconds,
        default=3.0,
        help="Finite receive timeout greater than zero, in seconds (default: 3).",
    )
    settings_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print risk and exact bytes without loading MIDI or opening a port.",
    )
    settings_parser.set_defaults(handler=read_settings)

    preset_parser = subparsers.add_parser(
        "inspect-prst", help="Validate and summarize a local .prst file without MIDI."
    )
    preset_parser.add_argument("file", help="Path to a 515-byte .prst file.")
    preset_parser.set_defaults(handler=inspect_prst)

    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
        return 0
    except (ExampleError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
