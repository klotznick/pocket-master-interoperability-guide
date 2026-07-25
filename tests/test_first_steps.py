from __future__ import annotations

import argparse
import contextlib
import io
import math
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
import first_steps  # noqa: E402


def tlv(identifier: int, value: bytes) -> bytes:
    return struct.pack("<HH", identifier, len(value)) + value


def u32(value: int) -> bytes:
    return struct.pack("<I", value)


def encode_frame(
    command: int,
    subcommand: int,
    payload: bytes,
    *,
    declared_length: int | None = None,
) -> bytes:
    body = bytearray(
        [0, command, subcommand, len(payload) if declared_length is None else declared_length]
    )
    body.extend(payload)
    body[0] = first_steps.crc8(body)
    return bytes(part for byte in body for part in (byte >> 4, byte & 0x0F))


def global_settings_logical() -> bytes:
    fields = (
        tlv(0x0101, bytes([3, 3, 1, 1]))
        + tlv(0x0102, u32(2))
        + tlv(0x0201, bytes([0]))
        + tlv(0x0202, u32(77))
        + tlv(0x0203, bytes([100]))
        + tlv(0x0205, bytes([1]))
        + tlv(0x0301, bytes([0xF6]))
        + tlv(0x0401, bytes([0]))
        + tlv(0x0402, bytes([0xEC]))
        + tlv(0x0403, bytes([1]))
        + tlv(0x0404, bytes([1]))
        + tlv(0x0405, bytes([0]))
    )
    logical = b"\x12\x10" + fields
    assert len(logical) == 71
    return logical


def settings_fragments() -> list[bytes]:
    logical = global_settings_logical()
    return [logical[offset : offset + 19] for offset in range(0, len(logical), 19)]


def synthetic_prst(
    *,
    header_version: int = 2,
    record_version: int = 2,
    placeholder: int = 0xFFFFFFFF,
    raw_name: bytes = b"Synthetic",
    module_count: int = 10,
    parameter_slots: int = 8,
    enable_mask: int = 0x001,
    chain: bytes = bytes(range(10)),
    parameters: list[float] | None = None,
) -> bytes:
    if len(raw_name) > 16:
        raise ValueError("Synthetic name is wider than 16 bytes.")
    name_field = raw_name + bytes(16 - len(raw_name))
    parameter_values = parameters or [0.0] * 80
    if len(parameter_values) != 80:
        raise ValueError("Synthetic preset requires 80 parameter values.")

    format_section = tlv(0x0001, u32(record_version)) + tlv(0x0002, b"\x0AEMQ")
    layout_section = (
        tlv(0x1001, u32(module_count))
        + tlv(0x1002, u32(parameter_slots))
        + tlv(0x1003, u32(2))
    )
    global_section = tlv(0x2001, u32(65)) + tlv(0x2002, u32(120))
    module_section = (
        tlv(0x3001, u32(enable_mask))
        + tlv(0x3002, chain)
        + tlv(0x3003, b"".join(u32(index + 1) for index in range(10)))
        + tlv(0x3004, b"".join(struct.pack("<f", value) for value in parameter_values))
    )
    sections = (
        tlv(0x00FF, format_section)
        + tlv(0x0000, layout_section)
        + tlv(0x0001, global_section)
        + tlv(0x0002, module_section)
        + tlv(0x0003, bytes(8))
    )
    payload = u32(placeholder) + name_field + sections
    assert len(payload) == 494
    product_header = b"Pocket Master" + bytes(5)
    return (
        product_header
        + struct.pack("<H", header_version)
        + bytes([first_steps.crc8(payload)])
        + payload
    )


class FakePort:
    def __init__(self) -> None:
        self.sent: list[types.SimpleNamespace] = []

    def __enter__(self) -> "FakePort":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def send(self, message: types.SimpleNamespace) -> None:
        self.sent.append(message)


class FakeMido:
    def __init__(self, output: FakePort) -> None:
        self.output = output

    def open_output(self, _: str) -> FakePort:
        return self.output

    @staticmethod
    def Message(message_type: str, **values: object) -> types.SimpleNamespace:
        return types.SimpleNamespace(type=message_type, **values)


class CodecTests(unittest.TestCase):
    def test_known_settings_request_and_crc(self) -> None:
        self.assertEqual(
            first_steps.GLOBAL_SETTINGS_REQUEST_RAW,
            bytes.fromhex("F0 0B 09 00 01 00 00 00 02 01 02 01 00 F7"),
        )
        self.assertEqual(first_steps.crc8(bytes.fromhex("00 01 00 02 12 10")), 0xB9)
        command, subcommand, payload = first_steps.decode_sysex_data(
            first_steps.GLOBAL_SETTINGS_REQUEST_DATA
        )
        self.assertEqual((command, subcommand, payload), (1, 0, b"\x12\x10"))

    def test_decode_rejects_malformed_frames(self) -> None:
        valid = encode_frame(1, 0, b"\x12\x10")
        cases = {
            "odd nibble count": valid[:-1],
            "non-nibble byte": bytes([0x10, 0x00]),
            "short body": bytes([0, 0, 1, 0, 0, 0]),
            "length mismatch": encode_frame(1, 0, b"\x12\x10", declared_length=3),
            "CRC mismatch": bytes([valid[0] ^ 1]) + valid[1:],
        }
        for label, encoded in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(first_steps.ExampleError):
                    first_steps.decode_sysex_data(encoded)

    def test_tlv_parser_rejects_truncation_and_duplicates(self) -> None:
        with self.assertRaisesRegex(first_steps.ExampleError, "Truncated TLV"):
            first_steps.parse_tlvs(b"\x01")
        duplicated = tlv(1, b"a") + tlv(1, b"b")
        with self.assertRaisesRegex(first_steps.ExampleError, "Duplicate TLV"):
            first_steps.parse_tlvs(duplicated)


class SettingsTransferTests(unittest.TestCase):
    def test_complete_transfer_reassembles(self) -> None:
        accepted: dict[int, bytes] = {}
        for index, payload in enumerate(settings_fragments()):
            first_steps.accept_settings_fragment(accepted, index, payload)
        self.assertEqual(
            first_steps.reassemble_settings_fragments(accepted),
            global_settings_logical(),
        )

    def test_missing_fragment_is_rejected(self) -> None:
        accepted = {0: settings_fragments()[0]}
        with self.assertRaisesRegex(first_steps.ExampleError, "missing"):
            first_steps.reassemble_settings_fragments(accepted)

    def test_identical_duplicate_is_rejected_distinctly(self) -> None:
        payload = settings_fragments()[0]
        accepted = {0: payload}
        with self.assertRaisesRegex(
            first_steps.ExampleError, r"^Duplicate settings fragment"
        ):
            first_steps.accept_settings_fragment(accepted, 0, payload)

    def test_conflicting_duplicate_is_rejected_distinctly(self) -> None:
        payload = settings_fragments()[0]
        accepted = {0: payload}
        with self.assertRaisesRegex(
            first_steps.ExampleError, r"^Conflicting duplicate settings fragment"
        ):
            first_steps.accept_settings_fragment(accepted, 0, payload + b"\x00")

    def test_out_of_order_fragment_is_rejected(self) -> None:
        with self.assertRaisesRegex(first_steps.ExampleError, "Out-of-order"):
            first_steps.accept_settings_fragment({}, 1, settings_fragments()[1])

    def test_out_of_range_fragment_is_rejected(self) -> None:
        with self.assertRaisesRegex(first_steps.ExampleError, "outside"):
            first_steps.accept_settings_fragment({}, 4, b"unexpected")


class CommandSafetyTests(unittest.TestCase):
    def test_toggle_dry_run_never_loads_mido_or_prompts(self) -> None:
        args = argparse.Namespace(
            out="Pocket Master", starting="on", dry_run=True
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                first_steps, "require_mido", side_effect=AssertionError("loaded Mido")
            ),
            mock.patch("builtins.input", side_effect=AssertionError("prompted")),
            contextlib.redirect_stdout(output),
        ):
            first_steps.toggle_nr(args)
        self.assertIn("Risk: Live", output.getvalue())
        self.assertIn("B0 2B 00", output.getvalue())
        self.assertIn("no port opened", output.getvalue())

    def test_settings_dry_run_never_loads_mido_or_opens_ports(self) -> None:
        args = argparse.Namespace(
            input="Pocket Master",
            out="Pocket Master",
            timeout=3.0,
            dry_run=True,
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                first_steps, "require_mido", side_effect=AssertionError("loaded Mido")
            ),
            contextlib.redirect_stdout(output),
        ):
            first_steps.read_settings(args)
        self.assertIn("Risk: Device read", output.getvalue())
        self.assertIn(
            first_steps.GLOBAL_SETTINGS_REQUEST_RAW.hex(" ").upper(),
            output.getvalue(),
        )
        self.assertIn("no port opened", output.getvalue())

    def test_toggle_sends_target_then_restore(self) -> None:
        port = FakePort()
        args = argparse.Namespace(
            out="Pocket Master", starting="on", dry_run=False
        )
        output = io.StringIO()
        with (
            mock.patch.object(first_steps, "require_mido", return_value=FakeMido(port)),
            mock.patch("builtins.input", side_effect=["TOGGLE", ""]),
            contextlib.redirect_stdout(output),
        ):
            first_steps.toggle_nr(args)
        self.assertEqual([message.value for message in port.sent], [0, 127])
        self.assertIn("verify the original state", output.getvalue())

    def test_interruption_still_attempts_restore(self) -> None:
        port = FakePort()
        args = argparse.Namespace(
            out="Pocket Master", starting="off", dry_run=False
        )
        with (
            mock.patch.object(first_steps, "require_mido", return_value=FakeMido(port)),
            mock.patch("builtins.input", side_effect=["TOGGLE", KeyboardInterrupt]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(KeyboardInterrupt):
                first_steps.toggle_nr(args)
        self.assertEqual([message.value for message in port.sent], [127, 0])


class PresetInspectorTests(unittest.TestCase):
    def run_inspector(self, data: bytes) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.prst"
            path.write_bytes(data)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                first_steps.inspect_prst(argparse.Namespace(file=str(path)))
            return output.getvalue()

    def assert_inspector_error(self, data: bytes, pattern: str) -> None:
        with self.assertRaisesRegex(first_steps.ExampleError, pattern):
            self.run_inspector(data)

    def test_valid_synthetic_container_versions(self) -> None:
        for header_version in (0, 2):
            with self.subTest(header_version=header_version):
                output = self.run_inspector(
                    synthetic_prst(header_version=header_version)
                )
                self.assertIn(f"valid, version {header_version}", output)
                self.assertIn("Preset:          Synthetic", output)

    def test_size_prefix_crc_and_placeholder_failures(self) -> None:
        valid = synthetic_prst()
        self.assert_inspector_error(valid[:-1], "expected 515")

        invalid_prefix = b"X" + valid[1:]
        self.assert_inspector_error(invalid_prefix, "product header")

        invalid_crc = valid[:20] + bytes([valid[20] ^ 1]) + valid[21:]
        self.assert_inspector_error(invalid_crc, "CRC mismatch")

        self.assert_inspector_error(
            synthetic_prst(placeholder=0), "slot placeholder"
        )

    def test_unsupported_record_version_is_rejected_before_interpretation(self) -> None:
        self.assert_inspector_error(
            synthetic_prst(record_version=3), "record version 3"
        )

    def test_layout_and_chain_failures(self) -> None:
        self.assert_inspector_error(
            synthetic_prst(module_count=9), "Unsupported layout"
        )
        self.assert_inspector_error(
            synthetic_prst(chain=bytes([0, 0, 2, 3, 4, 5, 6, 7, 8, 9])),
            "[Ss]ignal chain",
        )

    def test_enable_mask_rejects_bits_above_known_modules(self) -> None:
        self.assert_inspector_error(
            synthetic_prst(enable_mask=1 << 10), "outside known modules"
        )

    def test_non_utf8_name_is_preserved_as_raw_bytes(self) -> None:
        output = self.run_inspector(synthetic_prst(raw_name=b"\xFFName"))
        self.assertIn("Preset:          <not valid UTF-8; see raw bytes>", output)
        self.assertIn("Preset name raw: FF 4E 61 6D 65", output)

    def test_non_finite_parameter_is_preserved_with_raw_bytes(self) -> None:
        values = [0.0] * 80
        values[0] = math.nan
        output = self.run_inspector(synthetic_prst(parameters=values))
        self.assertRegex(output, r"nan \(raw [0-9A-F ]{11}\)")


if __name__ == "__main__":
    unittest.main()
