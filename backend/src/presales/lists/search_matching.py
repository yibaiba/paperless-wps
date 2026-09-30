FUZZY_QUERY_MIN_LENGTH = 4
FUZZY_QUERY_MIN_COVERAGE_NUMERATOR = 2
FUZZY_QUERY_MIN_COVERAGE_DENOMINATOR = 3
FUZZY_FIELD_MATCH_BONUS = 5
FUZZY_COMPACTNESS_WINDOW = 6


def query_match_score(variant, query):
    terms = query.casefold().split()
    if not terms:
        return 0
    primary = _primary_values(variant)
    searchable_values = _searchable_values(variant)
    identity_values = _identity_values(variant)
    identity_text = "".join(identity_values)
    scores = [
        _term_score(term, primary, searchable_values, identity_values, identity_text)
        for term in terms
    ]
    return min(scores) if all(scores) else 0


def matches_query(variant, query):
    return not query.strip() or query_match_score(variant, query) > 0


def _term_score(term, primary, searchable_values, identity_values, identity_text):
    normalized = _normalize(term)
    if not normalized:
        return 0
    if normalized in primary:
        return 120
    if any(value.startswith(normalized) for value in primary):
        return 80
    if any(normalized in value for value in searchable_values):
        return 70
    field_score = max(
        (_han_bigram_score(normalized, value, field_match=True) for value in identity_values),
        default=0,
    )
    return field_score or _han_bigram_score(normalized, identity_text, field_match=False)


def _han_bigram_score(term, searchable, *, field_match):
    if len(term) < FUZZY_QUERY_MIN_LENGTH or not all(_is_han(char) for char in term):
        return 0
    bigrams = [term[index : index + 2] for index in range(len(term) - 1)]
    if bigrams[0] not in searchable or bigrams[-1] not in searchable:
        return 0
    hits = sum(bigram in searchable for bigram in bigrams)
    if hits * FUZZY_QUERY_MIN_COVERAGE_DENOMINATOR < (
        len(bigrams) * FUZZY_QUERY_MIN_COVERAGE_NUMERATOR
    ):
        return 0
    score = 40 + hits * 30 // len(bigrams)
    if field_match:
        comparable = "".join(char for char in searchable if _is_han(char))
        extra_length = max(0, len(comparable) - len(term))
        score += FUZZY_FIELD_MATCH_BONUS + max(0, FUZZY_COMPACTNESS_WINDOW - extra_length)
    return min(score, 79)


def _primary_values(variant):
    product = variant.get("product", {})
    return {
        _normalize(value)
        for value in (variant.get("name", ""), product.get("model", ""), product.get("name", ""))
        if value
    }


def _searchable_values(variant):
    product = variant.get("product", {})
    values = [
        variant.get("name", ""),
        product.get("model", ""),
        product.get("name", ""),
        product.get("category", ""),
        variant.get("description", ""),
        variant.get("series", []),
        variant.get("systems", []),
        variant.get("functions", []),
        variant.get("interfaces", []),
        variant.get("attributes", []),
    ]
    return [_normalize(value) for value in values if value]


def _identity_values(variant):
    product = variant.get("product", {})
    values = [
        variant.get("name", ""),
        product.get("model", ""),
        product.get("name", ""),
        product.get("category", ""),
        variant.get("series", []),
        variant.get("systems", []),
        variant.get("functions", []),
    ]
    return [_normalize(value) for value in values if value]


def _normalize(value):
    return "".join(char for char in str(value).casefold() if char.isalnum())


def _is_han(char):
    return "\u4e00" <= char <= "\u9fff"
