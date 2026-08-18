from __future__ import annotations

import unittest

from src.macos_api import (
    calculate_cpu_percent,
    parse_lsof_output,
    process_state_from_ps_stat,
    parse_ps_scheduling_output,
    parse_procargs_bytes,
    parse_vm_stat_output,
    parse_vmmap_output,
    status_to_code,
    status_to_name,
)


class ParserTests(unittest.TestCase):
    def test_procargs_parser(self) -> None:
        raw = (2).to_bytes(4, "little") + b"/usr/bin/python3\x00\x00python3\x00main.py\x00PATH=/usr/bin\x00"
        self.assertEqual(parse_procargs_bytes(raw), ["python3", "main.py"])

    def test_lsof_parser(self) -> None:
        text = "\n".join(
            [
                "p123",
                "cPython",
                "fcwd",
                "tDIR",
                "n/tmp",
                "f1",
                "tPIPE",
                "npipe",
            ]
        )
        parsed = parse_lsof_output(text)
        self.assertEqual(parsed["pid"], 123)
        self.assertEqual(parsed["command"], "Python")
        self.assertEqual(parsed["count"], 2)
        self.assertEqual(parsed["entries"][1]["type"], "PIPE")
        self.assertEqual(parsed["entries"][0]["target"], "/tmp")
        self.assertEqual(parsed["entries"][1]["target"], "pipe")

    def test_vm_stat_parser(self) -> None:
        text = "\n".join(
            [
                "Mach Virtual Memory Statistics: (page size of 16384 bytes)",
                "Pages free:                                     7010.",
                "Pages active:                                 288617.",
                "Swapouts:                                          0.",
            ]
        )
        parsed = parse_vm_stat_output(text)
        self.assertEqual(parsed["page_size"], 16384)
        self.assertEqual(parsed["pages_free"], 7010)
        self.assertEqual(parsed["pages_active"], 288617)
        self.assertEqual(parsed["swapouts"], 0)

    def test_vmmap_parser(self) -> None:
        text = "\n".join(
            [
                "__TEXT                 100000000-100004000    [   16K] r-x/r-x SM=COW  sample",
                "STACK GUARD            16B3E0000-16B3F0000    [   64K] ---/rwx SM=NUL  stack guard",
                "Writable regions: Total=64.0M written=12.0M(19%) resident=16.0M swapped_out=0K unallocated=48.0M",
            ]
        )
        parsed = parse_vmmap_output(text)
        self.assertEqual(parsed["regions"][0]["region"], "__TEXT")
        self.assertEqual(parsed["parsed_region_count"], 2)
        self.assertIn("Writable regions", parsed["summary"])

    def test_state_mappings(self) -> None:
        self.assertEqual(status_to_name(2), "SRUN")
        self.assertEqual(status_to_code(5), "Z")

    def test_ps_state_mapping(self) -> None:
        self.assertEqual(process_state_from_ps_stat("Ss"), ("S", "SSLEEP"))
        self.assertEqual(process_state_from_ps_stat("R+"), ("R", "SRUN"))
        self.assertEqual(process_state_from_ps_stat("Z"), ("Z", "SZOMB"))

    def test_cpu_delta(self) -> None:
        value = calculate_cpu_percent(1_000_000_000, 10.0, 1_500_000_000, 12.0)
        self.assertAlmostEqual(value, 25.0)

    def test_ps_scheduling_parser(self) -> None:
        parsed = parse_ps_scheduling_output("  651     651    1204      37\n")
        self.assertEqual(parsed["session_id"], 651)
        self.assertEqual(parsed["voluntary_context_switches"], 1204)
        self.assertEqual(parsed["involuntary_context_switches"], 37)

    def test_ps_scheduling_parser_preserves_partial_data(self) -> None:
        parsed = parse_ps_scheduling_output("73606      0     -     -\n")
        self.assertEqual(parsed["session_id"], 0)
        self.assertIsNone(parsed["voluntary_context_switches"])
        self.assertIsNone(parsed["involuntary_context_switches"])


if __name__ == "__main__":
    unittest.main()
