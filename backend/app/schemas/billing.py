from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    url: str
