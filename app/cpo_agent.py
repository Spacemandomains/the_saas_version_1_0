from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import google.generativeai as genai
from jsonschema import validate, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"
SCHEMAS_DIR = REPO_ROOT / "schemas"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_system_prompt() -> str:
    system_md = read_text(PROMPTS_DIR / "system.md")
    policies_md = read_text(PROMPTS_DIR / "policies.md")  # optional, if present
    combined = system_md.strip()
    if policies_md.strip():
        combined += "\n\n" + policies_md.strip()
    return combined.strip()


def load_schema(doc_type: str) -> Dict[str, Any]:
    schema_map = {
        "prd": SCHEMAS_DIR / "prd.schema.json",
        "roadmap": SCHEMAS_DIR / "roadmap.schema.json",
        "sprint": SCHEMAS_DIR / "sprint.schema.json",
        "recap": SCHEMAS_DIR / "recap.schema.json",
        "feature_spec": SCHEMAS_DIR / "feature_spec.schema.json",
        "user_stories": SCHEMAS_DIR / "user_stories.schema.json",
        "technical_handoff": SCHEMAS_DIR / "technical_handoff.schema.json",
        "release_notes": SCHEMAS_DIR / "release_notes.schema.json",
        "strategy_memo": SCHEMAS_DIR / "strategy_memo.schema.json",
    }
    p = schema_map.get(doc_type)
    if not p or not p.exists():
        return {"type": "object"}
    return json.loads(p.read_text(encoding="utf-8"))


def extract_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()

    # Try direct JSON parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Recovery: grab first {...} block
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return valid JSON.")
    return json.loads(raw[start : end + 1])


class CPOAgent:
    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)

        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.model = genai.GenerativeModel(self.model_name)
        self.system_prompt = load_system_prompt()

    def generate(
        self,
        *,
        doc_type: str,
        product_brief: str,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        schema = load_schema(doc_type)

        context_block = ""
        if context:
            if context.get("icp"):
                context_block += f"\nICP & VALUE PROPOSITION:\n{json.dumps(context['icp'], ensure_ascii=False, indent=2)}\n"
            if context.get("pmf_signals"):
                context_block += f"\nPRODUCT-MARKET FIT SIGNALS:\n{json.dumps(context['pmf_signals'], ensure_ascii=False, indent=2)}\n"
            if context.get("metrics"):
                context_block += f"\nKEY METRICS:\n{json.dumps(context['metrics'], ensure_ascii=False, indent=2)}\n"

        prompt = f"""
SYSTEM:
{self.system_prompt}

PRODUCT BRIEF:
{product_brief}
{context_block}
REQUEST TYPE:
{doc_type}

INPUTS (JSON):
{json.dumps(inputs, ensure_ascii=False, indent=2)}

SCHEMA (JSON):
{json.dumps(schema, ensure_ascii=False, indent=2)}

STRICT OUTPUT RULES:
- Return ONLY valid JSON.
- No markdown. No code fences. No commentary.
- The JSON should match the schema.
"""

        resp = self.model.generate_content(prompt)
        raw = (resp.text or "").strip()

        parsed = extract_json(raw)

        try:
            validate(instance=parsed, schema=schema)
        except ValidationError as e:
            parsed["_schema_validation_error"] = str(e)

        return parsed

    def challenge(
        self,
        *,
        doc_type: str,
        product_brief: str,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context_block = ""
        if context:
            if context.get("icp"):
                context_block += f"\nICP & VALUE PROPOSITION:\n{json.dumps(context['icp'], ensure_ascii=False, indent=2)}\n"
            if context.get("pmf_signals"):
                context_block += f"\nPRODUCT-MARKET FIT SIGNALS:\n{json.dumps(context['pmf_signals'], ensure_ascii=False, indent=2)}\n"
            if context.get("metrics"):
                context_block += f"\nKEY METRICS:\n{json.dumps(context['metrics'], ensure_ascii=False, indent=2)}\n"

        prompt = f"""
SYSTEM:
{self.system_prompt}

You are operating in EXECUTIVE CHALLENGE MODE. As CPO, this is where you earn your title — pushing back on vague or incomplete product thinking. You protect the product from bad decisions by forcing clarity before execution begins.

PRODUCT BRIEF:
{product_brief}
{context_block}
The founder wants to create a {doc_type} document with these inputs:
{json.dumps(inputs, ensure_ascii=False, indent=2)}

Your task:
1. Identify what is vague, missing, or potentially misguided about this request.
2. Ask 3-5 pointed, specific clarifying questions that would strengthen the output.
3. Flag any "shiny object syndrome" risks — is this the right thing to build right now?
4. Rate the clarity of the request on a scale of 1-10.
5. Provide a brief recommendation on whether to proceed, refine, or reconsider.

STRICT OUTPUT RULES:
- Return ONLY valid JSON.
- No markdown. No code fences. No commentary.
- Use this exact JSON structure:
{{
  "clarity_score": <number 1-10>,
  "overall_assessment": "<string>",
  "questions": [
    {{ "question": "<string>", "why_it_matters": "<string>" }}
  ],
  "risks": ["<string>"],
  "recommendation": "<proceed | refine | reconsider>",
  "recommendation_rationale": "<string>"
}}
"""

        resp = self.model.generate_content(prompt)
        raw = (resp.text or "").strip()
        return extract_json(raw)

    def analyze_metrics(
        self,
        *,
        product_brief: str,
        metrics: list,
        pmf_signals: list,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt = f"""
SYSTEM:
{self.system_prompt}

You are analyzing product metrics data to provide strategic product insights. As CPO, metrics are how you measure whether the product strategy is working. You connect data to decisions — what the numbers say about the product's health, where the product is relative to PMF, and what the founder should change.

PRODUCT BRIEF:
{product_brief}

METRICS DATA (historical snapshots):
{json.dumps(metrics, ensure_ascii=False, indent=2)}

PMF SIGNALS:
{json.dumps(pmf_signals, ensure_ascii=False, indent=2)}

Analyze this data and provide:
1. **Health Score** - Overall product health 1-100
2. **Key Insights** - 3-5 most important observations from the data
3. **Trends** - What direction are the key metrics moving?
4. **Warnings** - Any concerning patterns (churn spikes, declining activation, etc.)
5. **Recommendations** - 3-5 specific actions to improve metrics
6. **PMF Assessment** - Based on signals, how close is this product to PMF?

STRICT OUTPUT RULES:
- Return ONLY valid JSON.
- No markdown. No code fences. No commentary.
- Use this exact JSON structure:
{{
  "health_score": <number 1-100>,
  "health_label": "<strong | healthy | needs_attention | critical>",
  "key_insights": ["<string>"],
  "trends": [
    {{ "metric": "<string>", "direction": "<up | down | flat>", "note": "<string>" }}
  ],
  "warnings": ["<string>"],
  "recommendations": [
    {{ "action": "<string>", "impact": "<high | medium | low>", "effort": "<high | medium | low>" }}
  ],
  "pmf_assessment": {{
    "score": <number 1-10>,
    "label": "<pre-pmf | approaching | achieved | strong>",
    "rationale": "<string>"
  }}
}}
"""

        resp = self.model.generate_content(prompt)
        raw = (resp.text or "").strip()
        return extract_json(raw)
