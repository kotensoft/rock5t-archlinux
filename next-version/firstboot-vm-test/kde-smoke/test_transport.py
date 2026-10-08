#!/usr/bin/env python3
"""Offline tests of the actual KDE runner regex and collector UART drain order."""
import ast
import json
import os
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
RUNNER = ast.parse((HERE/'run_firstboot.py').read_text())
COLLECTOR = ast.parse((HERE/'verify_guest.py').read_text())
PATTERNS = [node.args[0].value for node in ast.walk(RUNNER)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 're'
            and node.func.attr == 'search' and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith('FIRSTBOOT_VM_RESULT=')]
assert len(PATTERNS) == 1, 'Expected one actual runner framing expression'
PATTERN = PATTERNS[0]


def frame(payload):
    return 'FIRSTBOOT_VM_RESULT=' + json.dumps(payload, sort_keys=True)


class FramingRegression(unittest.TestCase):
    def test_incomplete_4095_byte_frame_is_not_accepted(self):
        payload = {'checks': {'ok': True}, 'details': {'journal': 'x'*10000}}
        partial = frame(payload)[:4095]
        self.assertEqual(len(partial), 4095)
        self.assertIn('}', partial)
        self.assertIsNone(re.search(PATTERN, partial))
        actual = os.environ.get('ROCK5T_INCOMPLETE_FRAME_FIXTURE')
        if actual:
            observed = Path(actual).read_text(errors='replace')
            self.assertIn('FIRSTBOOT_VM_RESULT=', observed)
            self.assertIsNone(re.search(PATTERN, observed))

    def test_large_nested_result_and_escaped_journal_newlines(self):
        payload = {'checks': {'ok': True, 'nested': {'value': 4}},
                   'details': {'journal': ('line one\nline two {content}\r\n'*700)}}
        text = frame(payload)
        self.assertGreater(len(text), 4096)
        for ending in ('\n', '\r\n'):
            match = re.search(PATTERN, 'boot output\n'+text+ending)
            self.assertIsNotNone(match)
            self.assertEqual(json.loads(match.group(1)), payload)

    def test_complete_json_waits_for_its_line_terminator(self):
        payload = {'checks': {'nested': {'ok': True}}, 'details': {'done': True}}
        complete = frame(payload)
        self.assertIsNone(re.search(PATTERN, complete))
        self.assertEqual(json.loads(re.search(PATTERN, complete+'\n').group(1)), payload)


class DrainOrderRegression(unittest.TestCase):
    def test_flush_then_tcdrain_before_poweroff(self):
        calls = [n for n in ast.walk(COLLECTOR) if isinstance(n, ast.Call)]
        flush = [n for n in calls if ast.unparse(n.func) == 'output.flush']
        drain = [n for n in calls if ast.unparse(n.func) == 'termios.tcdrain']
        poweroff = [n for n in calls if ast.unparse(n.func) == 'subprocess.run'
                    and n.args and isinstance(n.args[0], ast.List)
                    and ast.literal_eval(n.args[0]) == ['systemctl', 'poweroff']]
        self.assertEqual((len(flush), len(drain), len(poweroff)), (1, 1, 1))
        self.assertEqual(ast.unparse(drain[0].args[0]), 'output.fileno()')
        self.assertLess(flush[0].lineno, drain[0].lineno)
        self.assertLess(drain[0].lineno, poweroff[0].lineno)


if __name__ == '__main__':
    unittest.main(verbosity=2)
