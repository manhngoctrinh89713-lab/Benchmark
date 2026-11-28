from reporting.validators.schema import validate_rows

def test_schema():
    assert len(validate_rows([{'a': 1}])) == 1
