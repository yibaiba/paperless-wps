def page(items, request):
    end = request.offset + request.limit
    return dict(
        items=items[request.offset:end],
        total=len(items),
        offset=request.offset,
        next_offset=end if end < len(items) else None,
    )
