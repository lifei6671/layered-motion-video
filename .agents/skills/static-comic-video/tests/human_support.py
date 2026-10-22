"""Simulated chat/terminal confirmations with a disposable TEST-ONLY account key.

Never install a test key in the user's authority directory. Verification itself
is not mocked; production receipts cannot validate under this ephemeral key.
"""
import atexit
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from static_comic import human_review
from static_comic.contracts import digest

_temp = tempfile.TemporaryDirectory(prefix='sc-confirmation-TEST-ONLY-')
_patch = patch.object(human_review, 'KEY_PATH', Path(_temp.name) / 'test-only.key')
_patch.start()
atexit.register(_temp.cleanup)
atexit.register(_patch.stop)


def simulated(scope, decision, *, source='conversation'):
    value = human_review.payload(decision)
    if source == 'conversation':
        return human_review.conversation(scope, decision, {
            'thread_id': 'SYNTHETIC-TEST-ONLY',
            'user_message': 'SYNTHETIC TEST ONLY: explicit decision for the displayed object',
            'scope': scope, 'decision_sha256': digest(value),
        })
    token = digest({'scope': scope, 'payload': value})[:12]
    with patch('sys.stdin.isatty', return_value=True), redirect_stdout(StringIO()) as stream:
        with patch.object(stream, 'isatty', return_value=True), patch('builtins.input', return_value=f'CONFIRM {token}'), \
                patch('getpass.getuser', return_value='SYNTHETIC TEST ONLY'):
            return human_review.interactive(scope, decision)
