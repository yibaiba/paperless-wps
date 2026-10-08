"""Response-only usage views; calculation and persisted checks retain full traces."""

SUMMARY_CONSUMER_FIELDS = (
    "requirement_id",
    "system_id",
    "system_name",
    "role",
    "via",
    "demand_id",
    "fulfilled_by_demand_ids",
)


def summarize_usage(usage):
    return dict(
        device_id=usage["device_id"],
        consumers=[
            {key: consumer[key] for key in SUMMARY_CONSUMER_FIELDS if key in consumer}
            for consumer in usage["consumers"]
        ],
        quantity_summary=usage.get("quantity_summary"),
        missing_information=usage.get("missing_information", []),
    )


def usage_response(checked, *, detail):
    if detail == "full":
        return checked
    return dict(
        checked,
        checks=[check for check in checked.get("checks", []) if check["status"] != "pass"],
        device_usages=[summarize_usage(usage) for usage in checked.get("device_usages", [])],
    )
