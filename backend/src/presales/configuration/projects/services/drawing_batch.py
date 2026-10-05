"""Defer only drawing serialization between edits that cannot observe the drawing."""

DRAWING_INDEPENDENT_ACTIONS = frozenset(
    {
        "quotation_set",
        "quotation_replace",
        "description_set",
        "section_set",
        "price_set",
        "price_readopt",
        "purchase_set",
        "supply_set",
        "author_set",
    }
)


class DrawingBatchError(ValueError):
    def __init__(self, pending, error):
        self.index, self.operation = pending
        super().__init__(str(error))


class DeviceIndex:
    """Indexes and mutates only the private device list owned by one edit transaction."""

    def __init__(self, items):
        self.positions = {item["id"]: index for index, item in enumerate(items)}

    def find(self, items, identity):
        position = self.positions.get(identity)
        return items[position] if position is not None else None

    def replace(self, items, value):
        position = self.positions.get(value["id"])
        if position is not None:
            items[position] = value
            return
        self.positions[value["id"]] = len(items)
        items.append(value)


class DeviceDrawingBatch:
    def __init__(self, *, put_device, project_sequence):
        self.put_device = put_device
        self.project_sequence = project_sequence
        self.initialized = False
        self.device_index = None
        self.additions = []
        self.pending = None

    def apply(self, data, *, operation, index):
        if not self.initialized:
            # Validate the original XML at the first edit, as the unbatched path does.
            self.device_index = DeviceIndex(data["devices"])
            result = self.put_device(data, operation, device_index=self.device_index)
            self.initialized = True
            return result
        identity = operation.value.id
        is_new = self.device_index.find(data["devices"], identity) is None
        result = self.put_device(
            data, operation, update_drawing=False, device_index=self.device_index
        )
        if is_new:
            self.additions.append(identity)
        if self.pending is None:
            self.pending = (index, operation)
        return result

    def flush(self, data):
        if self.pending is not None:
            try:
                data["drawing_xml"] = self.project_sequence(
                    data["drawing_xml"], devices=data["devices"], add_ids=self.additions
                )
            except ValueError as error:
                raise DrawingBatchError(self.pending, error) from error
        self.initialized = False
        self.pending = None
        self.device_index = None
        self.additions.clear()
