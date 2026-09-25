"""Source preservation, strict JSON validation and per-case persona snapshots.

The discarded model-generated numeric projection is intentionally not part of this module.
K's semantic contracts live in person_evidence/person_scope/person_environment.
"""
from __future__ import annotations
import math
import json
import re
from app.schemas.persona import Persona, RouteFamiliarity, EnvResponse
from app.schemas.prediction import PriorParams

SOURCE_PRECEDENCE = '''각 notes.provenance를 확인한다. guardian_original은 보호자 직접 기록이고 model_extracted_unverified는 이전 AI의 미검증 추출·요약이다. 두 종류가 같은 사실에 관해 다르면 보호자 원문을 우선하며 이를 두 보호자의 미해결 상충으로 만들지 않는다. AI 요약에만 있는 행동을 보호자가 관찰한 사실로 확정하지 않는다. 보호자 원문끼리의 정정·시간 차이·실제 상충은 문맥으로 판단한다. 입력 배열 순서나 N 번호는 관찰 시각이 아니다. 서로 다른 특성은 모순으로 취급하지 않는다.'''


def evidence_notes(payload):
    """Original quotes are the evidence set; derived notes remain in the audit.

    A machine summary is not an additional observer. For legacy records without
    quotes, retain its unverified provenance rather than silently relabeling it.
    """
    notes = [{"id": n["id"], "text": n["text"],
             "provenance": "guardian_original" if any(
                 s["kind"].startswith("guardian") for s in n.get("sources", []))
             else "model_extracted_unverified"}
            for n in payload["notes"]]
    originals = [n for n in notes if n['provenance'] == 'guardian_original']
    return originals or notes

def _obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _enum(values):
    return {"type": "string", "enum": list(values)}


def build_payload(persona: Persona, report, research: list[dict], sar: PriorParams) -> dict:
    notes, index = [], {}
    # Preserve all source associations for identical words used in different slots.
    sources = [("guardian_quote", persona.onboarding_quotes), ("guardian_axis_quote", persona.axis_quotes),
               ("extracted_axis_note", persona.axis_evidence), ("extracted_note", {"behavior": persona.behavior_notes})]
    if persona.guardian_edited_notes is not None:
        sources = [("guardian_edit", {"behavior": persona.guardian_edited_notes})]
    for kind, groups in sources:
        for slot, values in groups.items():
            for text in values:
                if text not in index:
                    item = {"id": f"N{len(notes)}", "text": text, "sources": []}
                    notes.append(item); index[text] = item
                index[text]["sources"].append({"kind": kind, "slot": slot})
    return {"person": {"type": persona.type.value, "age": persona.age}, "notes": notes,
            "places": [{"label": p.label, "evidence": p.evidence.value, "origin_slot": p.origin_slot} for p in persona.attraction_points],
            "incident": ({"last_seen_time": report.lkp_time.isoformat(), "context": report.situation}
                         if report is not None else {"status":"not_reported","last_seen_time":None,"context":"신고 전 사전 준비. 현재 사건을 가정하지 않음."}),
            "research": [{**r, "id": f"R{i}",
                          "evidence_scope": "research_excerpt_not_personal_observation"}
                         for i, r in enumerate(research) if r.get("kind") == "paper"],
            "retrieval_audit": [{"id": f"R{i}", "source": r.get("source", ""),
                                 "kind": r.get("kind", ""),
                                 "use": "primary_excerpt" if r.get("kind") == "paper" else "excluded_derived_or_unclassified"}
                                for i, r in enumerate(research)],
            "existing_compiled_features": {k: persona.model_dump(mode="json")[k] for k in ("axis_scores", "route_familiarity", "env_responses", "behavior_tendency")},
            "SAR_reference": {
                "status": "unvalidated_numeric_proposal_not_personal_evidence",
                "strategy_probs": sar.strategy_probs,
                "attraction_weights": sar.attraction_weights,
                "radius_lognormal": sar.radius_lognormal.model_dump()} if sar is not None else {"status":"not_generated_before_incident"}
            }


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def decode_json_content(content):
    """Read one complete final JSON value without repairing its keys or semantics.

    Some provider replies retain a reasoning delimiter or wrap the final object in
    a Markdown fence despite parse_reasoning=True. Accept that explicit envelope,
    but never scrape an arbitrary brace span or choose between multiple answers.
    """
    if not isinstance(content,str):
        raise ValueError('missing_json_content')
    text=content.strip()
    try:
        return json.loads(text,object_pairs_hook=_unique)
    except json.JSONDecodeError:
        pass
    if '</think>' in text:
        text=text.rsplit('</think>',1)[1].strip()
        try:
            return json.loads(text,object_pairs_hook=_unique)
        except json.JSONDecodeError:
            pass
    fences=list(re.finditer(r'```(?:json)?\s*\n(.*?)\n```',text,re.DOTALL))
    if len(fences)!=1 or text[fences[0].end():].strip():
        raise ValueError('missing_or_ambiguous_final_json')
    return json.loads(fences[0].group(1),object_pairs_hook=_unique)


def _validate_shape(value, schema):
    """Validate the small schema vocabulary generated above, with no coercion."""
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValueError("object fields do not match contract")
        for key, child in schema["properties"].items(): _validate_shape(value[key], child)
    elif kind == "array":
        if not isinstance(value, list): raise ValueError("expected array")
        for child in value: _validate_shape(child, schema["items"])
    elif kind == "string":
        if not isinstance(value, str): raise ValueError("expected string")
        if "enum" in schema and value not in schema["enum"]: raise ValueError("unknown enum")
    elif kind == "number":
        if type(value) not in (float, int) or not math.isfinite(value): raise ValueError("invalid number")
    else:
        raise ValueError("unsupported schema type")


def simulation_persona(persona: Persona | None, prior: PriorParams) -> Persona | None:
    """Apply the same snapshot for initial prediction and time previews; no mutation."""
    patch = prior.persona_adjustments
    if persona is None or not patch: return persona
    if patch.get("persona_id") != persona.id: raise ValueError("personalization belongs to another person")
    return persona.model_copy(deep=True, update={"axis_scores": dict(patch["axis_scores"]),
        "route_familiarity": [RouteFamiliarity.model_validate(r) for r in patch["route_familiarity"]],
        "env_responses": [EnvResponse.model_validate(r) for r in patch["env_responses"]]})
