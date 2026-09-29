"""Track explicit relationship edits separately from generated device ownership."""


def marked(data, collection, identity):
    return identity in data.get("manual_edits", {}).get(collection, [])


def mark(data, collection, identity, *, enabled=True):
    edits = data.get("manual_edits", {})
    identities = [i for i in edits.get(collection, []) if i != identity]
    return dict(
        data,
        manual_edits=dict(edits, **{collection: identities + ([identity] if enabled else [])}),
    )


def prune(data):
    edits = {}
    for collection, identities in data.get("manual_edits", {}).items():
        valid = {
            row["id"]
            for row in data[collection]
            if collection != "requirements" or row.get("device_id") or row.get("allocations")
        }
        edits[collection] = [i for i in identities if i in valid]
    return dict(data, manual_edits=edits)
