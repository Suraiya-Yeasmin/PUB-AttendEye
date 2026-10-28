"""AttendEye TrustScore: the decision policy and its human-readable explanations.

The score describes how certain the *recognition attempt* is, not anything about a person.
The similarity shown is the raw cosine similarity between two SFace embeddings (range -1..1). It is
NOT a probability. The thresholds are operating points that must be tuned with the System Evaluation page.
"""
from dataclasses import dataclass

ACCEPTED = "accepted"
NEEDS_REVIEW = "needs_review"
UNKNOWN = "unknown"
POOR_QUALITY = "poor_quality"
DUPLICATE = "duplicate"
SESSION_INACTIVE = "session_inactive"
ERROR = "error"
PENDING = "pending"  # transient UI state: waiting for consecutive-frame confirmation

DECISION_LABELS = {
    ACCEPTED: "Accepted Match",
    NEEDS_REVIEW: "Needs Teacher Review",
    UNKNOWN: "Unknown Identity",
    POOR_QUALITY: "Poor Image Quality",
    DUPLICATE: "Duplicate Attendance",
    SESSION_INACTIVE: "Session Not Active",
    ERROR: "Processing Error",
    PENDING: "Recognition Pending",
}

SIMILARITY_EXPLAINER = ("Cosine similarity between the live face embedding and the closest enrolled template "
                        "(range -1 to 1; higher means more alike). It is a distance-based score, not a probability.")


@dataclass
class Policy:
    accept: float
    review: float
    margin: float

    @classmethod
    def from_settings(cls, s: dict) -> "Policy":
        return cls(s["accept_threshold"], s["review_threshold"], s["margin"])


def decide(similarity: float | None, runner_up: float | None, p: Policy) -> tuple[str, str]:
    if similarity is None:
        return UNKNOWN, "No face templates are enrolled, so no identity can be proposed."
    if similarity < p.review:
        return UNKNOWN, (f"Best similarity {similarity:.2f} is below the review threshold {p.review:.2f}; "
                         "no enrolled student is a plausible match.")
    if similarity < p.accept:
        return NEEDS_REVIEW, (f"Similarity {similarity:.2f} is above the review threshold ({p.review:.2f}) "
                              f"but below the automatic-accept threshold ({p.accept:.2f}).")
    if runner_up is not None and similarity - runner_up < p.margin:
        return NEEDS_REVIEW, (f"Another enrolled student is also similar (gap {similarity - runner_up:.2f} "
                              f"is below the required margin {p.margin:.2f}).")
    return ACCEPTED, (f"Similarity {similarity:.2f} meets the accept threshold {p.accept:.2f} "
                      "with a clear margin over the next-best template.")
