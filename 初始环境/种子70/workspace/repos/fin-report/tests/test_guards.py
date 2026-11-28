from reporting.guards.v2_export import run

def test_v2_guard():
    assert run([{'branch_id': 'br-a'}, {'branch_id': 'br-b'}], 'br-a') == [{'branch_id': 'br-a'}]
