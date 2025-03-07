#!/usr/bin/env python3
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>

import os
import sys
from typing import List, NoReturn, Optional

from kitty.cli import parse_args
from kitty.cli_stub import ClipboardCLIOptions

from ..tui.handler import Handler
from ..tui.loop import Loop


class Clipboard(Handler):

    def __init__(self, data_to_send: Optional[bytes], args: ClipboardCLIOptions):
        self.args = args
        self.clipboard_contents: Optional[str] = None
        self.data_to_send = data_to_send
        self.quit_on_write = False

    def initialize(self) -> None:
        if self.data_to_send is not None:
            self.cmd.write_to_clipboard(self.data_to_send, self.args.use_primary)
        if not self.args.get_clipboard:
            if self.args.wait_for_completion:
                # ask kitty for the TN terminfo capability and
                # only quit after a response is received
                self.print('\x1bP+q544e\x1b\\', end='')
                self.print('Waiting for completion...')
                return
            self.quit_on_write = True
            return
        self.cmd.request_from_clipboard(self.args.use_primary)

    def on_writing_finished(self) -> None:
        if self.quit_on_write:
            self.quit_loop(0)

    def on_clipboard_response(self, text: str, from_primary: bool = False) -> None:
        self.clipboard_contents = text
        self.quit_loop(0)

    def on_capability_response(self, name: str, val: str) -> None:
        self.quit_loop(0)

    def on_interrupt(self) -> None:
        self.quit_loop(1)

    def on_eot(self) -> None:
        self.quit_loop(1)


OPTIONS = r'''
--get-clipboard
default=False
type=bool-set
Output the current contents of the clipboard to STDOUT. Note that by default
kitty will prompt you asking to allow access to the clipboard. Can be controlled
by :opt:`clipboard_control`.


--use-primary
default=False
type=bool-set
Use the primary selection rather than the clipboard on systems that support it,
such as X11.


--wait-for-completion
default=False
type=bool-set
Wait till the copy to clipboard is complete before exiting. Useful if running
the kitten in a dedicated, ephemeral window.
'''.format
help_text = '''\
Read or write to the system clipboard.

To set the clipboard text, pipe in the new text on STDIN. Use the
:option:`--get-clipboard` option to output the current clipboard contents to
:file:`stdout`. Note that reading the clipboard will cause a permission
popup, see :opt:`clipboard_control` for details.
'''

usage = ''


def main(args: List[str]) -> NoReturn:
    cli_opts, items = parse_args(args[1:], OPTIONS, usage, help_text, 'kitty +kitten clipboard', result_class=ClipboardCLIOptions)
    if items:
        raise SystemExit('Unrecognized extra command line arguments')
    data: Optional[bytes] = None
    if not sys.stdin.isatty():
        data = sys.stdin.buffer.read()
        sys.stdin = open(os.ctermid())
    loop = Loop()
    handler = Clipboard(data, cli_opts)
    loop.loop(handler)
    if loop.return_code == 0 and handler.clipboard_contents:
        sys.stdout.write(handler.clipboard_contents)
        sys.stdout.flush()
    raise SystemExit(loop.return_code)


if __name__ == '__main__':
    main(sys.argv)
elif __name__ == '__doc__':
    cd = sys.cli_docs  # type: ignore
    cd['usage'] = usage
    cd['options'] = OPTIONS
    cd['help_text'] = help_text
