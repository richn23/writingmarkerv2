"""
The LLM intent layer.

The model proposes, the engine disposes. Nothing in this package can change a
score on its own: every proposal is checked against the deterministic engine's
own form test before it is allowed to touch a token stream, and anything that
fails is discarded and logged.

Kept out of api/_engine on purpose. The engine is calibrated and must stay
byte-identical; this package only ever reads from it.
"""
