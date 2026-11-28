from reporting.formatters.csv_fmt import format_csv

def test_csv():
    assert format_csv([{'a': 1}])
