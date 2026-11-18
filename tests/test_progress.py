"""Tests de la barre de progression (aucun terminal requis)."""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from unittest import TestCase
from unittest.mock import patch

import progress


class ProgressTests(TestCase):
    def tearDown(self):
        progress._state['steps'] = []

    def test_render_shows_step_bar_count_and_label(self):
        with patch.dict(os.environ, {'SCAN_PROGRESS': 'json'}), \
             patch('sys.__stdout__', io.StringIO()):
            progress.start(['Workday publics', 'Index gratuit', 'Enregistrement'])
            progress.step('Index gratuit')
            progress.tick(30, 60, 'Hermes')
            text = progress.render()
        self.assertTrue(text.startswith('[2/3] Index gratuit'))
        self.assertIn('██████████░░░░░░░░░░', text)  # 50 % = 10 cases pleines sur 20
        self.assertIn('30/60', text)
        self.assertIn('Hermes', text)

    def test_json_mode_emits_lines_readable_by_the_app(self):
        fake = io.StringIO()
        with patch.dict(os.environ, {'SCAN_PROGRESS': 'json'}), patch('sys.__stdout__', fake):
            progress.start(['A', 'B'])
            progress.step('B')
            progress.tick(1, 4, 'x')
            progress.finish()
        lines = [l for l in fake.getvalue().splitlines() if l.startswith('@@PROGRESS ')]
        last_tick = json.loads(lines[-2][len('@@PROGRESS '):])
        self.assertEqual((last_tick['step'], last_tick['done'], last_tick['total']), (2, 1, 4))
        self.assertAlmostEqual(last_tick['overall'], 0.625)  # etape 2/2 a 25 %
        self.assertTrue(json.loads(lines[-1][len('@@PROGRESS '):])['done_all'])

    def test_tick_outside_a_scan_is_silent(self):
        out = io.StringIO()
        with redirect_stdout(out), patch('sys.__stdout__', out):
            progress.tick(1, 2, 'rien')
        self.assertEqual(out.getvalue(), '')
