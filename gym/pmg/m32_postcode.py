from pydantic import BaseModel


class PostCode(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        s = str(v).replace(" ", "").upper()
        if len(s) != 5 or not s.isdigit():
            raise ValueError("invalid post code")
        return cls(s)


class Delivery(BaseModel):
    post_code: PostCode
