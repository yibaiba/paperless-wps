"""Stable suppression identity excludes cursor movement and ephemeral proposal IDs."""

from presales.rules.calculation import digest


def semantic(value):
    if isinstance(value, list):
        result = [semantic(v) for v in value]
        if all(isinstance(v, dict) and "id" in v for v in result):
            result.sort(key=lambda v: v["id"])
        return result
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in {"proposal_id", "drawing_xml"}}
    return value


def action_context(projection, request):
    partition = projection["repository"].evaluation_scope.partition(
        projection["checked"]["configuration"], session=projection["repository"].session
    )
    selected = partition.selected.model_dump(mode="json")
    rooms = {s["room_id"] for s in selected["systems"]}
    selected["rooms"] = [room for room in selected["rooms"] if room["id"] in rooms]
    selected["room_inputs"] = {
        key: value for key, value in selected["room_inputs"].items() if key in rooms
    }
    requirements = {r["id"] for r in selected["requirements"]}
    selected["generation"]["preferences"] = [
        p for p in selected["generation"]["preferences"] if p["requirement_id"] in requirements
    ]
    return digest(
        [
            request.binding_id,
            request.scope.system_id,
            request.template_profile_revision,
            projection["versions"],
            semantic(selected),
        ]
    )


def with_identity(item, *, business_context):
    return dict(
        item,
        semantic_action_id=digest(semantic(item["changes"])),
        business_context_fingerprint=business_context,
    )


def is_dismissed(item, edits):
    for edit in reversed(edits):
        if edit.kind not in {"undo", "dismiss"}:
            continue
        if edit.semantic_action_id and edit.business_context_fingerprint:
            if (
                edit.semantic_action_id == item["semantic_action_id"]
                and edit.business_context_fingerprint == item["business_context_fingerprint"]
            ):
                return True
        elif edit.suggestion_id == item["id"]:
            return True  # Existing journals can still suppress their exact original suggestion.
    return False
