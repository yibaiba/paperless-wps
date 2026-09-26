"""Transaction boundary shared by configuration HTTP routes."""


def commit(session, operation):
    result = operation()
    session.commit()
    return result
