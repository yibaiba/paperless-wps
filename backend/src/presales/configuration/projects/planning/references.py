"""Remove generation references in the same operation as their owning objects."""


def remove_generation_references(generation, removed_ids):
    return dict(
        generation,
        preferences=[
            dict(
                preference,
                reusable_device_ids=[
                    identity
                    for identity in preference["reusable_device_ids"]
                    if identity not in removed_ids
                ],
            )
            for preference in generation["preferences"]
            if preference["requirement_id"] not in removed_ids
        ],
        sources=[
            source for source in generation["sources"] if source["object_id"] not in removed_ids
        ],
        features_confirmed=[
            identity for identity in generation["features_confirmed"] if identity not in removed_ids
        ],
    )
