#!/usr/bin/env python
# License: GPLv3 Copyright: 2021, Kovid Goyal <kovid at kovidgoyal.net>

import os
import re
import socket
import sys
import termios
import time
from functools import partial
from pprint import pformat
from typing import (
    IO, Callable, Dict, Generator, Iterable, Iterator, Optional, Set, Tuple
)

from kittens.tui.operations import colored, styled

from .cli import version
from .constants import (
    extensions_dir, is_macos, is_wayland, kitty_base_dir, kitty_exe, shell_path
)
from .fast_data_types import num_users, Color
from .options.types import Options as KittyOpts, defaults
from .options.utils import MouseMap
from .rgb import color_as_sharp
from .types import MouseEvent, SingleKey
from .typing import SequenceMap

ShortcutMap = Dict[Tuple[SingleKey, ...], str]


def green(x: str) -> str:
    return colored(x, 'green')


def yellow(x: str) -> str:
    return colored(x, 'yellow')


def title(x: str) -> str:
    return colored(x, 'blue', intense=True)


def mod_to_names(mods: int) -> Generator[str, None, None]:
    from .fast_data_types import (
        GLFW_MOD_ALT, GLFW_MOD_CAPS_LOCK, GLFW_MOD_CONTROL, GLFW_MOD_HYPER,
        GLFW_MOD_META, GLFW_MOD_NUM_LOCK, GLFW_MOD_SHIFT, GLFW_MOD_SUPER
    )
    modmap = {'shift': GLFW_MOD_SHIFT, 'alt': GLFW_MOD_ALT, 'ctrl': GLFW_MOD_CONTROL, ('cmd' if is_macos else 'super'): GLFW_MOD_SUPER,
              'hyper': GLFW_MOD_HYPER, 'meta': GLFW_MOD_META, 'num_lock': GLFW_MOD_NUM_LOCK, 'caps_lock': GLFW_MOD_CAPS_LOCK}
    for name, val in modmap.items():
        if mods & val:
            yield name


def print_shortcut(key_sequence: Iterable[SingleKey], defn: str, print: Callable[..., None]) -> None:
    from .fast_data_types import glfw_get_key_name
    keys = []
    for key_spec in key_sequence:
        names = []
        mods, is_native, key = key_spec
        names = list(mod_to_names(mods))
        if key:
            kname = glfw_get_key_name(0, key) if is_native else glfw_get_key_name(key, 0)
            names.append(kname or f'{key}')
        keys.append('+'.join(names))

    print('\t' + ' > '.join(keys), defn)


def print_shortcut_changes(defns: ShortcutMap, text: str, changes: Set[Tuple[SingleKey, ...]], print: Callable[..., None]) -> None:
    if changes:
        print(title(text))

        for k in sorted(changes):
            print_shortcut(k, defns[k], print)


def compare_keymaps(final: ShortcutMap, initial: ShortcutMap, print: Callable[..., None]) -> None:
    added = set(final) - set(initial)
    removed = set(initial) - set(final)
    changed = {k for k in set(final) & set(initial) if final[k] != initial[k]}
    print_shortcut_changes(final, 'Added shortcuts:', added, print)
    print_shortcut_changes(initial, 'Removed shortcuts:', removed, print)
    print_shortcut_changes(final, 'Changed shortcuts:', changed, print)


def flatten_sequence_map(m: SequenceMap) -> ShortcutMap:
    ans = {}
    for key_spec, rest_map in m.items():
        for r, action in rest_map.items():
            ans[(key_spec,) + (r)] = action
    return ans


def compare_mousemaps(final: MouseMap, initial: MouseMap, print: Callable[..., None]) -> None:
    added = set(final) - set(initial)
    removed = set(initial) - set(final)
    changed = {k for k in set(final) & set(initial) if final[k] != initial[k]}

    def print_mouse_action(trigger: MouseEvent, defn: str) -> None:
        names = list(mod_to_names(trigger.mods)) + [f'b{trigger.button+1}']
        when = {-1: 'repeat', 1: 'press', 2: 'doublepress', 3: 'triplepress'}.get(trigger.repeat_count, trigger.repeat_count)
        grabbed = 'grabbed' if trigger.grabbed else 'ungrabbed'
        print('\t', '+'.join(names), when, grabbed, defn)

    def print_changes(defns: MouseMap, changes: Set[MouseEvent], text: str) -> None:
        if changes:
            print(title(text))
            for k in sorted(changes):
                print_mouse_action(k, defns[k])

    print_changes(final, added, 'Added mouse actions:')
    print_changes(initial, removed, 'Removed mouse actions:')
    print_changes(final, changed, 'Changed mouse actions:')


def compare_opts(opts: KittyOpts, print: Callable[..., None]) -> None:
    from .config import load_config
    print()
    print('Config options different from defaults:')
    default_opts = load_config()
    ignored = ('keymap', 'sequence_map', 'mousemap', 'map', 'mouse_map')
    changed_opts = [
        f for f in sorted(defaults._fields)
        if f not in ignored and getattr(opts, f) != getattr(defaults, f)
    ]
    field_len = max(map(len, changed_opts)) if changed_opts else 20
    fmt = f'{{:{field_len:d}s}}'
    colors = []
    for f in changed_opts:
        val = getattr(opts, f)
        if isinstance(val, dict):
            print(f'{title(f)}:')
            if f == 'symbol_map':
                for k in sorted(val):
                    print(f'\tU+{k[0]:04x} - U+{k[1]:04x} → {val[k]}')
            else:
                print(pformat(val))
        else:
            val = getattr(opts, f)
            if isinstance(val, Color):
                colors.append(fmt.format(f) + ' ' + color_as_sharp(val) + ' ' + styled('  ', bg=val))
            else:
                print(fmt.format(f), str(getattr(opts, f)))

    compare_mousemaps(opts.mousemap, default_opts.mousemap, print)
    final_, initial_ = opts.keymap, default_opts.keymap
    final: ShortcutMap = {(k,): v for k, v in final_.items()}
    initial: ShortcutMap = {(k,): v for k, v in initial_.items()}
    final_s, initial_s = map(flatten_sequence_map, (opts.sequence_map, default_opts.sequence_map))
    final.update(final_s)
    initial.update(initial_s)
    compare_keymaps(final, initial, print)
    if colors:
        print(f'{title("Colors")}:', end='\n\t')
        print('\n\t'.join(sorted(colors)))


class IssueData:

    def __init__(self) -> None:
        self.uname = os.uname()
        self.s, self.n, self.r, self.v, self.m = self.uname
        self.hostname = self.o = socket.gethostname()
        _time = time.localtime()
        self.formatted_time = self.d = time.strftime('%a %b %d %Y', _time)
        self.formatted_date = self.t = time.strftime('%H:%M:%S', _time)
        try:
            self.tty_name = format_tty_name(os.ttyname(sys.stdin.fileno()))
        except OSError:
            self.tty_name = '(none)'
        self.l = self.tty_name  # noqa
        self.baud_rate = termios.tcgetattr(sys.stdin.fileno())[5]
        self.b = str(self.baud_rate)
        try:
            self.num_users = num_users()
        except RuntimeError:
            self.num_users = -1
        self.u = str(self.num_users)
        self.U = self.u + ' user' + ('' if self.num_users == 1 else 's')

    def translate_issue_char(self, char: str) -> str:
        try:
            return str(getattr(self, char)) if len(char) == 1 else char
        except AttributeError:
            return char

    def parse_issue_file(self, issue_file: IO[str]) -> Iterator[str]:
        last_char: Optional[str] = None
        while True:
            this_char = issue_file.read(1)
            if not this_char:
                break
            if last_char == '\\':
                yield self.translate_issue_char(this_char)
            elif last_char is not None:
                yield last_char
            # `\\\a` should not match the last two slashes,
            # so make it look like it was `\?\a` where `?`
            # is some character other than `\`.
            last_char = None if last_char == '\\' else this_char
        if last_char is not None:
            yield last_char


def format_tty_name(raw: str) -> str:
    return re.sub(r'^/dev/([^/]+)/([^/]+)$', r'\1\2', raw)


def debug_config(opts: KittyOpts) -> str:
    from io import StringIO
    out = StringIO()
    p = partial(print, file=out)
    p(version(add_rev=True))
    p(' '.join(os.uname()))
    if is_macos:
        import subprocess
        p(' '.join(subprocess.check_output(['sw_vers']).decode('utf-8').splitlines()).strip())
    if os.path.exists('/etc/issue'):
        with open('/etc/issue', encoding='utf-8', errors='replace') as f:
            p(end=''.join(IssueData().parse_issue_file(f)))
    if os.path.exists('/etc/lsb-release'):
        with open('/etc/lsb-release', encoding='utf-8', errors='replace') as f:
            p(f.read().strip())
    if not is_macos:
        p('Running under:' + green('Wayland' if is_wayland() else 'X11'))
    p(green('Frozen:'), 'True' if getattr(sys, 'frozen', False) else 'False')
    p(green('Paths:'))
    p(yellow('  kitty:'), os.path.realpath(kitty_exe()))
    p(yellow('  base dir:'), kitty_base_dir)
    p(yellow('  extensions dir:'), extensions_dir)
    p(yellow('  system shell:'), shell_path)
    if opts.config_paths:
        p(green('Loaded config files:'))
        p(' ', '\n  '.join(opts.config_paths))
    if opts.config_overrides:
        p(green('Loaded config overrides:'))
        p(' ', '\n  '.join(opts.config_overrides))
    compare_opts(opts, p)
    return out.getvalue()
