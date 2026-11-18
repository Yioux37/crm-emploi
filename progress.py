"""Barre de progression du scan, visible dans le terminal ET dans l'app Streamlit.

Rendu dans le terminal :
    [3/6] Index gratuit  ██████████░░░░░░░░░░  24/60  ·  "Hermes" directeur supply chain  ·  ~1 min restante

Pourquoi un petit module maison plutot que tqdm ou rich ?
  - Le scan enchaine plusieurs etapes (Workday, ATS, index, LinkedIn...) qui
    ont chacune leur propre boucle : il faut une seule barre partagee entre
    plusieurs fichiers, avec le nom de l'etape. tqdm gere une boucle a la fois.
  - rich ferait tres bien l'affaire mais ajoute une dependance pour une
    seule ligne de texte.
  - Ici : zero installation, et trois modes d'affichage selon l'endroit ou le
    scan tourne (terminal, journal GitHub Actions, app Streamlit).

Les trois modes :
  1. Terminal interactif : une ligne redessinee sur place (\r). Les messages
     normaux (print) s'affichent AU-DESSUS de la barre, qui reste en bas.
  2. Journal non interactif (GitHub Actions, fichier) : une ligne simple a
     chaque etape et tous les ~25 %, pour ne pas inonder le journal.
  3. App Streamlit (variable SCAN_PROGRESS=json) : lignes "@@PROGRESS {...}"
     lues par app.py pour animer st.progress.
"""
from __future__ import annotations

import json
import os
import sys
import time

BAR_WIDTH = 20
_state = {'steps': [], 'index': 0, 'done': 0, 'total': 0, 'label': '',
          'step_started': 0.0, 'scan_started': 0.0, 'last_logged': -1}


def _mode() -> str:
    if os.getenv('SCAN_PROGRESS', '').lower() == 'json':
        return 'json'
    stream = sys.__stdout__
    return 'tty' if stream is not None and stream.isatty() else 'log'


class _BarAwareStdout:
    """Remplace sys.stdout en mode terminal : chaque print efface la barre,
    s'ecrit normalement, puis la barre est redessinee en dessous."""

    def __init__(self, stream):
        self._stream = stream
        self._pending = ''

    def write(self, text):
        self._pending += text
        if '\n' in self._pending:
            lines, self._pending = self._pending.rsplit('\n', 1)
            self._stream.write('\r\033[K' + lines + '\n')
            _draw()
        return len(text)

    def flush(self):
        self._stream.flush()

    def __getattr__(self, name):  # isatty, encoding... delegues au vrai terminal
        return getattr(self._stream, name)


def _eta() -> str:
    done, total = _state['done'], _state['total']
    if done <= 0 or total <= done:
        return ''
    elapsed = time.monotonic() - _state['step_started']
    remaining = elapsed / done * (total - done)
    if remaining < 60:
        return f'~{int(remaining) + 1} s restantes'
    return f'~{round(remaining / 60)} min restante(s)'


def render() -> str:
    """Texte de la barre (fonction pure, testable)."""
    steps = _state['steps']
    if not steps:
        return ''
    head = f"[{_state['index'] + 1}/{len(steps)}] {steps[_state['index']]}"
    done, total = _state['done'], _state['total']
    if total:
        filled = int(BAR_WIDTH * done / total)
        bar = '█' * filled + '░' * (BAR_WIDTH - filled)
        parts = [f'{head}  {bar}  {done}/{total}']
        if _state['label']:
            parts.append(_state['label'][:45])
        if _eta():
            parts.append(_eta())
        return '  ·  '.join(parts)
    return head + '  …'


def _overall() -> float:
    """Avancement global entre 0 et 1 (chaque etape pese autant)."""
    steps = len(_state['steps']) or 1
    inside = _state['done'] / _state['total'] if _state['total'] else 0
    return min(1.0, (_state['index'] + inside) / steps)


def _draw():
    mode = _mode()
    if not _state['steps']:
        return
    if mode == 'tty':
        out = sys.__stdout__
        out.write('\r\033[K' + render())
        out.flush()
    elif mode == 'json':
        payload = {'step': _state['index'] + 1, 'steps': len(_state['steps']),
                   'name': _state['steps'][_state['index']], 'done': _state['done'],
                   'total': _state['total'], 'label': _state['label'][:60],
                   'overall': round(_overall(), 3), 'eta': _eta()}
        sys.__stdout__.write('@@PROGRESS ' + json.dumps(payload, ensure_ascii=False) + '\n')
        sys.__stdout__.flush()
    else:
        quarter = int(4 * _state['done'] / _state['total']) if _state['total'] else -1
        if quarter != _state['last_logged']:
            _state['last_logged'] = quarter
            sys.__stdout__.write('▶ ' + render() + '\n')
            sys.__stdout__.flush()


def start(steps: list[str]) -> None:
    _state.update(steps=list(steps), index=0, done=0, total=0, label='',
                  step_started=time.monotonic(), scan_started=time.monotonic(), last_logged=-1)
    if _mode() == 'tty' and not isinstance(sys.stdout, _BarAwareStdout):
        sys.stdout = _BarAwareStdout(sys.stdout)
    _draw()


def step(name: str) -> None:
    """Passe a l'etape `name` (doit figurer dans la liste donnee a start)."""
    if name in _state['steps']:
        _state['index'] = _state['steps'].index(name)
    _state.update(done=0, total=0, label='', step_started=time.monotonic(), last_logged=-1)
    _draw()


def tick(done: int, total: int, label: str = '') -> None:
    """A appeler dans les boucles : `done` elements traites sur `total`."""
    if not _state['steps']:
        return  # module utilise hors d'un scan (tests, import) : rien a afficher
    _state.update(done=max(0, done), total=max(0, total), label=str(label or ''))
    _draw()


def finish(message: str = '') -> None:
    if not _state['steps']:
        return
    minutes, seconds = divmod(int(time.monotonic() - _state['scan_started']), 60)
    if isinstance(sys.stdout, _BarAwareStdout):
        sys.stdout.flush()
        sys.stdout = sys.stdout._stream
    if _mode() == 'tty':
        sys.__stdout__.write('\r\033[K')
    if _mode() == 'json':
        sys.__stdout__.write('@@PROGRESS ' + json.dumps({'overall': 1.0, 'done_all': True}) + '\n')
    sys.__stdout__.write(f'✅ Scan termine en {minutes} min {seconds:02d} s. {message}\n')
    sys.__stdout__.flush()
    _state['steps'] = []
