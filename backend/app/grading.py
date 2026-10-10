"""Final grading: deterministic aggregation of verified evidence + a small multi-model council.

Numbers come from code, not from an LLM's impression:
  * a dimension is "observed" only if at least one verified quote supports it;
  * observed_mean is the mean of those scores;
  * council members (different model families) may grade ONLY observed dimensions and must cite
    observation ids; the final score is the mean of observed_mean and the council median;
  * disagreement and thin coverage switch on `needs_human_review`.
The NYU Stern report (arXiv 2603.18221) found that a deliberating council of three models raised
inter-grader agreement from alpha 0.52 to 0.86; we use the same idea but never replace human review.
"""
from __future__ import annotations

import asyncio
import json
import statistics
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .providers.common import AllProvidersFailed, Usage
from .providers.llm import LLMClient, extract_json
from .rubrics import Rubric
from .settings import Settings

DISCLAIMER = ("AI-assisted, advisory feedback based only on what was said and shown in this session. "
              "It is not a hiring or grading decision; a human should review it, especially where flagged.")

BANDS = [(3.3, "Strong"), (2.5, "Proficient"), (1.5, "Developing"), (0.0, "Emerging")]


def band_for(score: float) -> str:
    return next(name for floor, name in BANDS if score >= floor)


# ---------------------------------------------------------------- deterministic aggregation
def aggregate(rubric: Rubric, observations: list[dict]) -> dict:
    """observations: dicts with dimension, score, quote, t, source, id. Returns per-dimension stats."""
    out = {}
    for d in rubric.dimensions:
        obs = [o for o in observations if o["dimension"] == d.id]
        out[d.id] = {
            "id": d.id, "label": d.label, "weight": d.weight, "n_obs": len(obs),
            "observed_mean": round(sum(o["score"] for o in obs) / len(obs), 2) if obs else None,
            "status": "observed" if obs else "not_observed",
            "evidence": [{"id": o["id"], "quote": o["quote"], "score": o["score"], "t": o.get("t", 0.0),
                          "source": o.get("source", "speech")} for o in obs],
        }
    return out


def overall(dims: dict) -> tuple[float | None, float]:
    observed = [d for d in dims.values() if d["final"] is not None]
    total_w = sum(d["weight"] for d in dims.values()) or 1.0
    cov = sum(d["weight"] for d in observed) / total_w
    if not observed:
        return None, 0.0
    w = sum(d["weight"] for d in observed)
    return round(sum(d["weight"] * d["final"] for d in observed) / w, 2), round(cov, 2)


# ---------------------------------------------------------------- council
class DimGrade(BaseModel):
    model_config = ConfigDict(extra="ignore")
    score: float | None = None
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)


class Point(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    evidence: list[str] = Field(default_factory=list)


class CouncilGrade(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dimensions: dict[str, DimGrade] = Field(default_factory=dict)
    strengths: list[Point] = Field(default_factory=list)
    growth: list[Point] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


COUNCIL_SYSTEM = """You are one independent grader on a panel reviewing a recorded oral defense of a student's project.
Use ONLY the evidence packet. Each observation has an id like o3 and a verbatim quote.
Rules:
- Grade a dimension 0-4 only if it has observations; otherwise omit it. Anchors are in the packet.
- Cite the observation ids that justify each grade, strength and growth point. Do not invent ids or facts.
- Flags are hints raised during the interview; mention them only if the evidence supports them.
- Be fair and specific. Write for the student: plain, kind, concrete.
Reply with JSON only:
{"dimensions":{"<id>":{"score":0-4,"rationale":"<max 30 words>","evidence":["o3"]}},
 "strengths":[{"text":"<max 30 words>","evidence":["o1"]}],
 "growth":[{"text":"<max 30 words>","evidence":["o2"]}],
 "next_steps":["<max 3 concrete practice actions>"]}"""


def build_packet(rubric: Rubric, dims: dict, flags: list[dict], claims: dict, screens: list[dict],
                 qa: list[dict], repo_brief: str) -> str:
    lines = ["RUBRIC"]
    for d in rubric.dimensions:
        lines.append(f"- {d.id} ({d.label}): 0={d.anchors[0]}; 2={d.anchors[1]}; 4={d.anchors[2]}")
    lines.append("\nOBSERVATIONS (verified quotes)")
    for d in dims.values():
        if not d["evidence"]:
            lines.append(f"- {d['id']}: NOT OBSERVED")
            continue
        for e in d["evidence"]:
            lines.append(f"- {e['id']} [{d['id']}] score={e['score']} t={e['t']}s ({e['source']}): \"{e['quote']}\"")
    if flags:
        lines.append("\nFLAGS RAISED")
        lines += [f"- {f['kind']}: {f['detail']}" for f in flags[:10]]
    if claims:
        lines.append("\nAUTOMATED CLAIM CHECKS vs repository")
        lines.append(f"- mentioned and supported: {', '.join(claims.get('supported', [])) or 'none'}")
        lines.append(f"- mentioned but not found in repository evidence: {', '.join(claims.get('not_found', [])) or 'none'}")
        lines.append(f"- numeric claims without support: {', '.join(claims.get('unverified_metrics', [])) or 'none'}")
    if repo_brief:
        lines.append("\nREPOSITORY BRIEF\n" + repo_brief)
    if screens:
        lines.append("\nSCREENS SHOWN\n" + "\n".join(f"- {s.get('title', '')}: {s.get('summary', '')}" for s in screens[:6]))
    if qa:
        lines.append("\nQUESTIONS ASKED\n" + "\n".join(f"- {q['question']}" for q in qa[:12]))
    return "\n".join(lines)


async def council_grade(llm: LLMClient, settings: Settings, packet: str, usage: Usage | None = None
                        ) -> tuple[list[tuple[str, CouncilGrade]], list[str]]:
    members = settings.chain_available(settings.council_chain)[: settings.council_size]
    if not members:
        return [], ["no council model has an API key configured"]

    async def one(provider: str, model: str):
        msgs = [{"role": "system", "content": COUNCIL_SYSTEM}, {"role": "user", "content": packet}]
        for attempt in range(2):
            res = await llm.chat([(provider, model)], msgs, purpose=f"council {model}", json_mode=True,
                                 max_tokens=3000, temperature=0.1, timeout=90.0, usage=usage)
            try:
                return f"{provider}:{model}", CouncilGrade.model_validate(extract_json(res.text))
            except (ValueError, ValidationError):
                msgs = msgs + [{"role": "user", "content": "That was not valid JSON for the schema. Reply with the JSON object only."}]
        raise ValueError("invalid JSON twice")

    results = await asyncio.gather(*(one(p, m) for p, m in members), return_exceptions=True)
    grades, errors = [], []
    for (p, m), r in zip(members, results):
        if isinstance(r, tuple):
            grades.append(r)
        elif isinstance(r, AllProvidersFailed):
            errors.append(f"{p}:{m}: {r.errors[0].kind if r.errors else 'failed'}")
        else:
            errors.append(f"{p}:{m}: {type(r).__name__}")
    return grades, errors


# ---------------------------------------------------------------- finalize
def _merge_points(grades: list[tuple[str, CouncilGrade]], attr: str, valid_ids: set[str], limit: int = 3) -> list[dict]:
    """Merge strengths/growth across graders: group by cited evidence, rank by how many graders agree."""
    groups: dict[frozenset, dict] = {}
    for model, g in grades:
        for pt in getattr(g, attr):
            ids = frozenset(i for i in pt.evidence if i in valid_ids)
            if not ids or not pt.text.strip():
                continue  # a point with no checkable evidence is not reported
            grp = groups.setdefault(ids, {"text": pt.text.strip()[:240], "evidence": sorted(ids), "votes": 0})
            grp["votes"] += 1
    ranked = sorted(groups.values(), key=lambda x: (-x["votes"], -len(x["evidence"])))
    return ranked[:limit]


def finalize(rubric: Rubric, observations: list[dict], flags: list[dict], claims: dict,
             grades: list[tuple[str, CouncilGrade]], council_errors: list[str], *,
             duration_s: float, utterances: int, questions: int, screens: int, dropped_unverified: int,
             coverage_floor: float = 0.5) -> dict:
    dims = aggregate(rubric, observations)
    valid_ids = {o["id"] for o in observations}
    reasons: list[str] = []
    spreads, agree_flags = [], []
    for d in dims.values():
        d["council_scores"] = []
        d["rationales"] = []
        if d["status"] == "observed":
            for model, g in grades:
                dg = g.dimensions.get(d["id"])
                if dg and dg.score is not None and 0 <= dg.score <= 4:
                    d["council_scores"].append(round(float(dg.score), 1))
                    if dg.rationale.strip():
                        d["rationales"].append({"model": model, "text": dg.rationale.strip()[:240],
                                                "evidence": [i for i in dg.evidence if i in valid_ids]})
        if d["status"] != "observed":
            d["final"], d["spread"] = None, None
            continue
        pool = [d["observed_mean"]] + d["council_scores"]
        if d["council_scores"]:
            d["final"] = round((d["observed_mean"] + statistics.median(d["council_scores"])) / 2, 1)
        else:
            d["final"] = round(d["observed_mean"], 1)
        d["spread"] = round(max(pool) - min(pool), 1)
        if len(d["council_scores"]) >= 2:
            spreads.append(d["spread"])
            agree_flags.append(d["spread"] <= 1.0)
        if d["spread"] >= 1.5:
            reasons.append(f"Graders disagree on '{d['label']}' (spread {d['spread']}).")
        if d["n_obs"] == 1:
            d["note"] = "Based on a single observation."

    score, coverage = overall(dims)
    if score is None:
        reasons.append("No verified evidence was collected, so no score can be given.")
    elif coverage < coverage_floor:
        reasons.append(f"Only {round(coverage * 100)}% of the rubric weight was observed.")
    n_unobs = [d["label"] for d in dims.values() if d["status"] == "not_observed"]
    if flags:
        reasons.append(f"{len(flags)} consistency flag(s) were raised during the interview.")
    if claims.get("not_found"):
        reasons.append("Technologies mentioned but not found in the repository: " + ", ".join(claims["not_found"]) + ".")
    if len(grades) < 2:
        reasons.append("Fewer than two independent graders were available; treat the narrative with caution.")

    narrative_ok = bool(grades)
    result = {
        "overall": {
            "score": score,
            "pct": round(score / 4 * 100) if score is not None else None,
            "band": band_for(score) if (score is not None and coverage >= coverage_floor) else "Not enough evidence",
            "coverage": coverage,
        },
        "dimensions": list(dims.values()),
        "not_observed": n_unobs,
        "flags": flags,
        "claims": claims,
        "strengths": _merge_points(grades, "strengths", valid_ids) if narrative_ok else [],
        "growth": _merge_points(grades, "growth", valid_ids) if narrative_ok else [],
        "next_steps": list(dict.fromkeys(s.strip() for _, g in grades for s in g.next_steps if s.strip()))[:3],
        "review": {"needs_human_review": bool(reasons), "reasons": reasons},
        "process": {
            "duration_s": round(duration_s), "utterances": utterances, "questions": questions, "screens": screens,
            "observations": len(observations), "dropped_unverified": dropped_unverified,
            "council": [m for m, _ in grades], "council_errors": council_errors,
            "council_agreement": round(sum(agree_flags) / len(agree_flags), 2) if agree_flags else None,
            "narrative_status": "ok" if narrative_ok else "unavailable",
        },
        "disclaimer": DISCLAIMER,
    }
    return result
