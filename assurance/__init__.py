"""Market Zero closed-loop assurance kernel (SPEC_WP12).

Escaped miss -> recorded incident -> failing regression -> protected gate -> CI ->
monitored exception. The kernel may PROPOSE rules + tests; it may not autonomously
weaken or rewrite its own success criteria (protected-surface changes need owner review).
"""
