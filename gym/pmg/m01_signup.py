from pydantic import BaseModel, validator


class Signup(BaseModel):
    email: str
    password: str
    password_confirm: str

    @validator("password_confirm")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("passwords do not match")
        return v
