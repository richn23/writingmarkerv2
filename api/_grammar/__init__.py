"""
Grammar detected (Range) -- ported from LENS (`language-awareness-pipeline`),
verified against LENS's own fixture set (92/92 matched). See docs/21 for the
port report, including one deliberate, documented divergence from live LENS
behavior (a LENS regex bug in resolveStructure()'s hasPast check; this port
keeps the correct match rather than replicating the bug).

Treated the same way `_engine`/`_intent` are treated -- protected, edits
requiring explicit approval -- per docs/21's flag-back (no objection raised).
"""
