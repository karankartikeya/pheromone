from pydantic import validate_arguments


@validate_arguments
def discounted(price: float, percent: int = 10) -> float:
    return round(price * (100 - percent) / 100, 2)
