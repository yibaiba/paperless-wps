from presales.application.hashing import digest


def configuration_hash(variant):
    return digest(
        {
            key: variant.get(key, [] if key != "product_id" else "")
            for key in (
                "product_id",
                "attributes",
                "series",
                "functions",
                "interfaces",
                "systems",
                "included_items",
            )
        }
    )
