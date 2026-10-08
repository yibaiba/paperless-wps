from copy import deepcopy

from presales.quotation.calculation import adopt_prices

from ..drawing import project_drawing
from ..knowledge_snapshot import knowledge_snapshot
from ..schemas import Configuration
from ..snapshots import SnapshotResolver


def prepare_configuration(session, catalog, data, *, refresh=False):
    result = data.model_dump(mode="json") if isinstance(data, Configuration) else deepcopy(data)
    selected = {device["variant_id"] for device in result["devices"]}
    ids = selected if result.get("calculation_version") == 3 else None
    current = {variant["id"]: variant for variant in catalog.variants(ids=ids)}
    resolver = SnapshotResolver(session)
    resolver.preload(result["devices"])
    variants = {}
    for device in result["devices"]:
        variant = current.get(device["variant_id"])
        if variant is None:
            raise ValueError("设备引用的产品配置不存在")
        device["source_snapshot"] = resolver.source(device)
        if refresh or device["variant_snapshot"] is None:
            device["variant_snapshot"] = variant
        else:
            resolver.revision(device["variant_snapshot"], kind="variant")
        variants[device["id"]] = device["variant_snapshot"]
    result["knowledge_snapshot"], result["knowledge_snapshot_id"] = knowledge_snapshot(
        session, data=result, refresh=refresh
    )
    result["drawing_xml"] = project_drawing(result["drawing_xml"], devices=result["devices"])
    from presales.catalog_updates.project_prices import validate_references

    validate_references(session, result)
    return adopt_prices(result), variants, current
