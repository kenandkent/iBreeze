"""Employee domain service tests."""
import pytest
from ibreeze.employee import (
    create_employee,
    list_employees,
    get_employee,
    update_employee,
    delete_employee,
    create_department,
    list_departments,
    get_department,
)
from ibreeze.schemas import (
    EmployeeUpdate,
    EmployeeStatus,
)


def test_create_employee():
    emp = create_employee(company_id="c1", name="Alice", role="admin", email="alice@test.com")
    assert emp.name == "Alice"
    assert emp.company_id == "c1"
    assert emp.role == "admin"
    assert emp.email == "alice@test.com"
    assert emp.status == EmployeeStatus.ACTIVE
    assert emp.is_deleted is False


def test_list_employees():
    create_employee(company_id="c1", name="Bob")
    create_employee(company_id="c1", name="Carol")
    results = list_employees(company_id="c1")
    assert len(results) >= 2


def test_list_employees_filter_by_role():
    create_employee(company_id="c1", name="Admin User", role="admin")
    create_employee(company_id="c1", name="Member User", role="member")
    admins = list_employees(company_id="c1", role="admin")
    assert all(e.role == "admin" for e in admins)


def test_get_employee():
    emp = create_employee(company_id="c1", name="Dave")
    fetched = get_employee(emp.id)
    assert fetched.id == emp.id
    assert fetched.name == "Dave"


def test_get_employee_not_found():
    with pytest.raises(KeyError):
        get_employee("nonexistent-id")


def test_update_employee():
    emp = create_employee(company_id="c1", name="Eve", role="member")
    updated = update_employee(emp.id, EmployeeUpdate(name="Eve Updated", role="admin"))
    assert updated.name == "Eve Updated"
    assert updated.role == "admin"


def test_delete_employee():
    emp = create_employee(company_id="c1", name="Frank")
    delete_employee(emp.id)
    with pytest.raises(KeyError):
        get_employee(emp.id)


def test_create_department():
    dept = create_department(company_id="c1", name="Engineering")
    assert dept.name == "Engineering"
    assert dept.company_id == "c1"
    assert dept.parent_id is None
    assert dept.is_deleted is False


def test_create_department_with_parent():
    parent = create_department(company_id="c1", name="Parent Dept")
    child = create_department(company_id="c1", name="Child Dept", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_list_departments():
    create_department(company_id="c1", name="HR")
    create_department(company_id="c1", name="Finance")
    results = list_departments(company_id="c1")
    assert len(results) >= 2


def test_get_department():
    dept = create_department(company_id="c1", name="Support")
    fetched = get_department(dept.id)
    assert fetched.id == dept.id
    assert fetched.name == "Support"


def test_create_employee_with_department():
    dept = create_department(company_id="c1", name="Engineering")
    emp = create_employee(company_id="c1", name="Grace", department_id=dept.id, role="developer")
    assert emp.department_id == dept.id
    assert emp.role == "developer"
    fetched = get_employee(emp.id)
    assert fetched.department_id == dept.id
