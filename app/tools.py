"""Utility functions and classes for AI CPO agent.

This module defines helper functions and scoring mechanisms used by the AI CPO agent.
"""

from typing import Dict, List, Any

class FeatureScorer:
    """Score features using RICE or ICE frameworks."""

    @staticmethod
    def rice_score(reach: float, impact: float, confidence: float, effort: float) -> float:
        """Calculate RICE score: (Reach * Impact * Confidence) / Effort."""
        if effort == 0:
            return 0.0
        return (reach * impact * confidence) / effort

    @staticmethod
    def ice_score(impact: float, confidence: float, ease: float) -> float:
        """Calculate ICE score: (Impact * Confidence * Ease)."""
        return impact * confidence * ease

def generate_prd(feature_name: str, description: str, problems: List[str], solution: str, metrics: List[str]) -> Dict[str, Any]:
    """Generate a simple product requirements document (PRD) as a dictionary."""
    return {
        "feature_name": feature_name,
        "description": description,
        "problems": problems,
        "proposed_solution": solution,
        "success_metrics": metrics,
    }

def build_roadmap(quarters: List[str], themes: List[str]) -> Dict[str, Any]:
    """Create a basic roadmap structure mapping quarters to product themes."""
    return dict(zip(quarters, themes))

def plan_sprint(tasks: List[str], duration_weeks: int) -> Dict[str, Any]:
    """Generate a sprint plan with tasks and duration."""
    return {"tasks": tasks, "duration_weeks": duration_weeks}

def triage_feature(feature: str, score: float, threshold: float = 1.0) -> str:
    """Return a decision string to build, delay, or drop based on score and threshold."""
    if score >= threshold:
        return "build"
    elif score >= threshold / 2:
        return "delay"
    else:
        return "drop"

def write_release_notes(version: str, changes: List[str]) -> str:
    """Generate a simple release notes string."""
    notes = f"## Release {version}\n\n"
    notes += "\n".join(f"- {change}" for change in changes)
    return notes
