"""Preview/apply source-backed booking roles and quantity review, preserving history."""

import signal

from maintain_booking_mapping import main
from paperless_review.booking_scope import build_scope_plan

if __name__ == "__main__":
    signal.alarm(60)
    main(build_plan=build_scope_plan, description=__doc__)
