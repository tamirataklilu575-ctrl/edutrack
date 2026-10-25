"""Helpers for splitting long lists into pages."""


def page_window(page, pages, edge=1, around=2):
    """Return the page numbers to show, with ``None`` marking a gap ("...").

    Always shows the first and last pages and a few pages around the current
    one, for example: [1, None, 8, 9, 10, 11, 12, None, 20].
    """
    wanted = set(range(1, edge + 1))
    wanted |= set(range(pages - edge + 1, pages + 1))
    wanted |= set(range(page - around, page + around + 1))
    numbers = sorted(n for n in wanted if 1 <= n <= pages)

    result = []
    previous = 0
    for number in numbers:
        if previous:
            gap = number - previous
            if gap == 2:
                # A gap of one page is shorter to show than to hide.
                result.append(previous + 1)
            elif gap > 2:
                result.append(None)
        result.append(number)
        previous = number
    return result


def paginate(total, page, per_page):
    """Work out which slice of ``total`` items belongs on ``page``.

    The page number is clamped into a valid range, so a bad request such as
    page 0 or page 999 still returns a real page.
    """
    pages = max(1, -(-total // per_page))  # divide, rounding up
    page = min(max(page, 1), pages)
    offset = (page - 1) * per_page

    return {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page,
        "offset": offset,
        "first": offset + 1 if total else 0,
        "last": min(offset + per_page, total),
        "has_prev": page > 1,
        "has_next": page < pages,
        "window": page_window(page, pages),
    }