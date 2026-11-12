from calc import add


def total(values):
    result = 0
    for value in values:
        result = add(result, value)
    return result


LABEL = "add stays text"
