r"""
Port of LENS's `splitSentences` (src/lib/analysis.ts:599-608).

JS: ``text.split(/(?<=[.!?]["'"''»)\]]*)\s+/)`` -- a VARIABLE-width
lookbehind, which Python's `re` module does not support (only fixed-width
lookbehind is allowed). Reimplemented as an explicit scan for the same split
points: cut immediately after a terminator plus any closing quotes/brackets,
resume after the following whitespace. Same result, no lookbehind needed.
"""

import re

_SENT_BOUNDARY = re.compile(r'([.!?][\"\'”’»)\]]*)(\s+)')


def split_sentences(text):
    out = []
    pos = 0
    for m in _SENT_BOUNDARY.finditer(text):
        out.append(text[pos:m.end(1)])
        pos = m.end(2)
    out.append(text[pos:])
    return [s.strip() for s in out if s.strip()]
