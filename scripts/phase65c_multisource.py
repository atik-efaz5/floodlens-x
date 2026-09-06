"""Phase 6.5C: multi-source event registry. Never trains a model.

Does not call training or validation-promotion helpers.
Does not overwrite phase6.5-gfm-spatial-v2.1 tensors.
"""

from floodlens.ml.spatial.multisource import evaluate_phase65c

if __name__ == "__main__":
    import json

    report = evaluate_phase65c()
    s = report.get("summary") or {}
    print("gfm_only", s.get("gfm_only"))
    print("unique_secondary", s.get("additional_unique_events"), s.get("additional_unique_event_ids"))
    print("combined", s.get("combined_independent_events"))
    print("cube_eligible", s.get("cube_eligible"))
    print("official_gate_b", s.get("official_gate_b"))
    print("research", s.get("research_text"))
    print("compatibility", json.dumps(report.get("compatibility")))
    print("catalog_status", report.get("catalog_status"))
    print("spatial_ai", report.get("spatial_ai"))
