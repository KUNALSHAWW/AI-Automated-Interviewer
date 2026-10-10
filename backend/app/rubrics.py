"""Written rubrics with anchored 0-4 levels.

A dimension only gets a score when a verbatim quote from the presenter supports it; otherwise it is
reported as "not observed" (never a default 5 or 50). Organizers can submit their own rubric.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    id: str
    label: str
    weight: float
    anchors: tuple[str, str, str]  # what level 0 / 2 / 4 look like

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "weight": self.weight,
                "anchors": {"0": self.anchors[0], "2": self.anchors[1], "4": self.anchors[2]}}


@dataclass(frozen=True)
class Rubric:
    id: str
    title: str
    description: str
    dimensions: tuple[Dimension, ...]

    def dim_ids(self) -> list[str]:
        return [d.id for d in self.dimensions]

    def get(self, dim_id: str) -> Dimension | None:
        return next((d for d in self.dimensions if d.id == dim_id), None)

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description,
                "dimensions": [d.as_dict() for d in self.dimensions]}

    @classmethod
    def from_dict(cls, d: dict) -> "Rubric":
        """Inverse of as_dict(); used to restore the exact rubric a session was created with."""
        dims = tuple(Dimension(x["id"], x["label"], float(x["weight"]),
                               (x["anchors"]["0"], x["anchors"]["2"], x["anchors"]["4"])) for x in d["dimensions"])
        return cls(d["id"], d["title"], d.get("description", ""), dims)


PROJECT_VIVA = Rubric(
    id="project_viva",
    title="Project viva (student / bootcamp)",
    description="Oral defense of a student's own project: do they own and understand what they built?",
    dimensions=(
        Dimension("ownership", "Ownership and understanding", 0.25,
                  ("Cannot explain how own project works",
                   "Explains the flow but not why it was built that way",
                   "Walks through internals and can reason about changes")),
        Dimension("technical_depth", "Technical depth", 0.20,
                  ("Only names tools", "Explains what each tool does", "Explains mechanisms, limits and alternatives")),
        Dimension("design_tradeoffs", "Design decisions and trade-offs", 0.15,
                  ("No reasons given", "Gives one reason per choice", "Compares options and states costs")),
        Dimension("claim_accuracy", "Claims match the screen and the repo", 0.15,
                  ("Claims contradict what is shown or built", "Mostly consistent, some unverified claims",
                   "Every checked claim is backed by the screen or the repository")),
        Dimension("testing_reliability", "Testing and failure handling", 0.10,
                  ("No mention of testing or errors", "Mentions tests or error cases in general",
                   "Describes concrete tests, failure modes and fixes")),
        Dimension("communication", "Clarity of explanation", 0.15,
                  ("Hard to follow", "Understandable with prompting", "Structured, precise, adapts to the listener")),
    ),
)

HACKATHON = Rubric(
    id="hackathon_judging",
    title="Hackathon judging",
    description="Screening round for hackathon demos. Weights are modelled on feasibility/impact-heavy "
                "public rubrics (SIH internal rounds) and normalised; adjust to your event.",
    dimensions=(
        Dimension("problem_impact", "Problem clarity and impact", 0.20,
                  ("Problem or user unclear", "Problem clear, impact asserted", "Clear user, evidence of impact")),
        Dimension("feasibility", "Feasibility", 0.20,
                  ("Not buildable as described", "Buildable with gaps", "Working, deployable, realistic scope")),
        Dimension("innovation", "Novelty", 0.15,
                  ("Existing solution restated", "Familiar idea, new twist", "Clear differentiator vs alternatives")),
        Dimension("technical_depth", "Technical execution", 0.15,
                  ("Mostly mock-ups", "Core path works", "Robust implementation, understood trade-offs")),
        Dimension("scalability", "Scalability and sustainability", 0.15,
                  ("Not considered", "Mentioned", "Concrete plan or evidence")),
        Dimension("demo_ux", "Demo and user experience", 0.15,
                  ("Demo does not run", "Demo runs with friction", "Smooth end-to-end demo")),
    ),
)

MOCK_INTERVIEW = Rubric(
    id="mock_interview",
    title="Mock technical interview (practice)",
    description="Practice feedback on explaining a project to an interviewer.",
    dimensions=(
        Dimension("technical_depth", "Technical depth", 0.30,
                  ("Surface level", "Solid fundamentals", "Deep, can go several levels down")),
        Dimension("problem_solving", "Problem solving", 0.25,
                  ("No structured approach", "Reasonable approach", "Structured, considers edge cases")),
        Dimension("design_tradeoffs", "Design trade-offs", 0.20,
                  ("No reasons given", "One reason per choice", "Compares options and costs")),
        Dimension("communication", "Communication", 0.25,
                  ("Hard to follow", "Understandable", "Clear, concise, structured")),
    ),
)

PRESETS: dict[str, Rubric] = {r.id: r for r in (PROJECT_VIVA, HACKATHON, MOCK_INTERVIEW)}


def custom_rubric(payload: dict) -> Rubric:
    """Validate an organizer-supplied rubric: 2-10 dimensions, ids slug-like, weights normalised."""
    import re
    dims_in = payload.get("dimensions") or []
    if not 2 <= len(dims_in) <= 10:
        raise ValueError("A rubric needs between 2 and 10 dimensions")
    dims, seen = [], set()
    for d in dims_in:
        did = str(d.get("id", "")).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", did) or did in seen:
            raise ValueError(f"Bad or duplicate dimension id: {did!r}")
        seen.add(did)
        label = str(d.get("label", did)).strip()[:60] or did
        try:
            weight = float(d.get("weight", 1))
        except (TypeError, ValueError):
            raise ValueError(f"Weight for {did!r} must be a number") from None
        if weight <= 0:
            raise ValueError(f"Weight for {did!r} must be positive")
        a = d.get("anchors") or {}
        anchors = (str(a.get("0", "Not shown"))[:120], str(a.get("2", "Partly shown"))[:120],
                   str(a.get("4", "Clearly shown"))[:120])
        dims.append(Dimension(did, label, weight, anchors))
    total = sum(d.weight for d in dims)
    dims = [Dimension(d.id, d.label, round(d.weight / total, 4), d.anchors) for d in dims]
    return Rubric("custom", str(payload.get("title", "Custom rubric"))[:80],
                  str(payload.get("description", ""))[:200], tuple(dims))


def resolve(rubric_id: str | None, custom: dict | None) -> Rubric:
    if custom:
        return custom_rubric(custom)
    return PRESETS.get(rubric_id or "project_viva") or PROJECT_VIVA
