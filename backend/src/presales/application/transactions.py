def commit(session, operation):
    result = operation()
    session.commit()
    return result
