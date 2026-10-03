"""Maintenance uses the same fixed package gaps as the requirement description."""

from ..common import Entities
from ..definitions.gaps import knowledge_gaps


def package_gap_tasks(session, *, projects, project_id=None):
    packages = (
        {}
        if project_id
        else {(p["id"], p["revision"]): p for p in Entities(session).list("knowledge_package")}
    )
    uses = {}
    for project in projects:
        selected = {s.get("knowledge_package_id") for s in project["configuration"]["systems"]}
        for package in project.get("definitions", {}).get("packages", []):
            if package["id"] not in selected:
                continue
            key = (package["id"], package["revision"])
            packages[key] = package
            uses.setdefault(key, []).append(
                dict(
                    project_id=project["project_id"],
                    project_name=project["name"],
                    revision=project["revision"],
                    objects=[package["name"]],
                )
            )
    gaps, tasks = [], []
    for key, package in packages.items():
        for item in knowledge_gaps(package["definition"], package):
            gaps.append(item)
            tasks.append(
                dict(
                    id=item["id"],
                    kind="knowledge_package",
                    title=package["name"] + "：" + item["message"],
                    owner="知识维护者",
                    action=item["action"],
                    evidence=[dict(evidence=item["evidence"])],
                    impacts=uses.get(key, []),
                    project_count=len(uses.get(key, [])),
                    newer_knowledge_available=False,
                    gap=item,
                    maintenance_url=item["maintenance_url"],
                )
            )
    return gaps, tasks
