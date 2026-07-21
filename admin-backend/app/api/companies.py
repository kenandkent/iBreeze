from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Company, Department, Employee

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/companies")
async def list_companies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.deleted_at.is_(None)))
    companies = result.scalars().all()
    return [
        {
            "company_id": c.company_id,
            "name": c.name,
            "status": c.status,
            "root_department_id": c.root_department_id,
            "leader_employee_id": c.leader_employee_id,
            "version": c.version,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in companies
    ]


@router.get("/companies/{company_id}")
async def get_company(company_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Company).where(Company.company_id == company_id, Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "company_id": company.company_id,
        "name": company.name,
        "status": company.status,
        "root_department_id": company.root_department_id,
        "leader_employee_id": company.leader_employee_id,
        "version": company.version,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


@router.get("/companies/{company_id}/departments")
async def list_departments(company_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Department).where(
            Department.company_id == company_id, Department.deleted_at.is_(None)
        )
    )
    departments = result.scalars().all()
    return [
        {
            "department_id": d.department_id,
            "company_id": d.company_id,
            "parent_id": d.parent_id,
            "name": d.name,
            "description": d.description,
            "leader_employee_id": d.leader_employee_id,
            "status": d.status,
            "version": d.version,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }
        for d in departments
    ]


@router.get("/companies/{company_id}/departments/{dept_id}")
async def get_department(company_id: str, dept_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Department).where(
            Department.department_id == dept_id,
            Department.company_id == company_id,
            Department.deleted_at.is_(None),
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return {
        "department_id": dept.department_id,
        "company_id": dept.company_id,
        "parent_id": dept.parent_id,
        "name": dept.name,
        "description": dept.description,
        "leader_employee_id": dept.leader_employee_id,
        "status": dept.status,
        "version": dept.version,
        "created_at": dept.created_at,
        "updated_at": dept.updated_at,
    }


@router.get("/companies/{company_id}/employees")
async def list_employees(company_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id, Employee.deleted_at.is_(None)
        )
    )
    employees = result.scalars().all()
    return [
        {
            "employee_id": e.employee_id,
            "company_id": e.company_id,
            "department_id": e.department_id,
            "name": e.name,
            "role_name": e.role_name,
            "employee_type": e.employee_type,
            "template_id": e.template_id,
            "manager_id": e.manager_id,
            "status": e.status,
            "version": e.version,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }
        for e in employees
    ]


@router.get("/companies/{company_id}/employees/{emp_id}")
async def get_employee(company_id: str, emp_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee).where(
            Employee.employee_id == emp_id,
            Employee.company_id == company_id,
            Employee.deleted_at.is_(None),
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {
        "employee_id": emp.employee_id,
        "company_id": emp.company_id,
        "department_id": emp.department_id,
        "name": emp.name,
        "role_name": emp.role_name,
        "employee_type": emp.employee_type,
        "template_id": emp.template_id,
        "manager_id": emp.manager_id,
        "status": emp.status,
        "version": emp.version,
        "created_at": emp.created_at,
        "updated_at": emp.updated_at,
    }
