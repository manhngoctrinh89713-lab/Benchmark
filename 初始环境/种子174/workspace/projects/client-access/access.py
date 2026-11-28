DEPARTMENT_CUSTOMERS = {"A-101", "A-102", "B-201"}
PROJECT_SCOPE = {"A-101", "A-102"}

def can_view(customer_id):
    return customer_id in DEPARTMENT_CUSTOMERS and customer_id in PROJECT_SCOPE
