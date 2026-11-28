from reporting.exporter import export_to_csv

def handle_export(req):
    return export_to_csv(req['rows'], req['branch'])
