"""Account-local confirmation receipts bound to reviewed content.
"""
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sys

from .contracts import canonical, digest, read_json, validate
from .paths import read_bytes

KEY_PATH = Path.home() / '.static-comic-video' / 'confirmation.key'
KINDS = {'policy': 'imageDecision', 'plan': 'imageDecision', 'images': 'imageReview',
         'transitions': 'transitionDecision', 'preview': 'deliveryDecision', 'final': 'deliveryDecision'}


def payload(decision):
    return {k: v for k, v in decision.items() if k != 'human'}


def key(*, create=False):
    if create and not KEY_PATH.exists():
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with KEY_PATH.open('xb') as stream:
            stream.write(secrets.token_bytes(32))
    try:
        data = KEY_PATH.read_bytes()
    except FileNotFoundError as error:
        raise ValueError('Local confirmation key missing; use human-confirm interactively') from error
    if len(data) != 32:
        raise ValueError('Invalid local confirmation key')
    return data


def signed_fields(human):
    result = deepcopy(human)
    result['confirmation'].pop('signature', None)
    return result


def verify(human, scope, expected=None, *, item=None):
    receipt = human.get('confirmation')
    if not receipt or receipt.get('source') != 'local_terminal' or receipt.get('scope') != scope:
        raise ValueError('Verified local human confirmation required; caller-provided strings are not approval')
    signature = hmac.new(key(), canonical(signed_fields(human)), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, receipt.get('signature', '')):
        raise ValueError('Invalid local confirmation signature')
    confirmed = receipt['payload']
    if item is None:
        if expected is not None and confirmed != expected:
            raise ValueError('Human confirmation payload is stale or changed')
    elif ({k: v for k, v in confirmed.items() if k != 'items'} != expected
          or item not in confirmed.get('items', [])):
        raise ValueError('Human confirmation item is stale or changed')


def require_newer(human, previous):
    """Call only after both signatures and their same-object bindings validate."""
    if human == previous:
        return  # Exact retry is idempotent, not a new approval.
    current_at = datetime.fromisoformat(human['at'].replace('Z', '+00:00'))
    previous_at = datetime.fromisoformat(previous['at'].replace('Z', '+00:00'))
    if current_at <= previous_at:
        raise ValueError('Older confirmation cannot replace the current decision; confirm again')


def interactive(scope, decision):
    """Confirm a decision in an interactive terminal and sign its payload."""
    if scope not in KINDS:
        raise ValueError('Unknown confirmation scope')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('human-confirm requires an interactive terminal; redirected input is refused')
    result = deepcopy(decision)
    result['human'] = {'actor': getpass.getuser(), 'actor_role': 'human',
                       'at': datetime.now(timezone.utc).isoformat(),
                       'evidence': 'Explicit local terminal confirmation; not verified human identity'}
    validate(KINDS[scope], result)
    if scope in ('preview', 'final') and result['stage'] != scope:
        raise ValueError('Confirmation stage differs from scope')
    value = payload(result)
    token = digest({'scope': scope, 'payload': value})[:12]
    print('请先查看本期 review 图片/转场报告或实际视频。此操作只确认下面的决定。')
    print('预览批准须完整观看试听；正式画质须另行确认。输入其他内容将取消，不生成收据。')
    print(json.dumps({'scope': scope, 'decision': value}, ensure_ascii=False, indent=2))
    if input(f'确认上述决定请输入 CONFIRM {token}: ').strip() != f'CONFIRM {token}':
        raise ValueError('Human confirmation cancelled; no receipt issued')
    human = result['human']
    human['at'] = datetime.now(timezone.utc).isoformat()
    human['confirmation'] = {'source': 'local_terminal', 'scope': scope, 'payload': value}
    human['confirmation']['signature'] = hmac.new(key(create=True), canonical(signed_fields(human)), hashlib.sha256).hexdigest()
    return validate(KINDS[scope], result)


def main(argv):
    import argparse
    from .cache import publish
    parser = argparse.ArgumentParser(description='User-operated local confirmation; never run by an Agent to manufacture approval')
    parser.add_argument('--project', required=True)
    parser.add_argument('--scope', choices=KINDS, required=True)
    parser.add_argument('--input', required=True, help='Episode-relative proposed decision JSON')
    args = parser.parse_args(argv)
    root = Path(args.project).resolve(strict=True)
    decision = read_json(read_bytes(root, args.input, 4 * 1024 * 1024))
    print(f'审核项目：{root}\n建议文件：{args.input}')
    signed = interactive(args.scope, decision)
    name = f'review/human-confirmations/{digest(signed)}.json'
    publish(root, {name: canonical(signed) + b'\n'})
    return {'status': 'CONFIRMATION_RECORDED', 'scope': args.scope, 'input': name,
            'next': 'Apply this receipt with the matching images/transitions/approve command; current hashes are rechecked.'}
