from pydantic import BaseModel, constr

Code = constr(regex=r"^[A-Z]{3}-\d{3}$")


class Item(BaseModel):
    code: Code
