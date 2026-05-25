from typing import Optional


PLAN_ALIASES = {
    "FREE": "STARTER",
    "OTHER": "PREMIUM",
    "PRO": "PREMIUM",
}


PLAN_LIMITS = {
    "STARTER": {
        "max_stores": 1,
        "max_products": 50,
    },
    "BASIC": {
        "max_stores": 1,
        "max_products": 100,
    },
    "STANDARD": {
        "max_stores": 5,
        "max_products": None,
    },
    "PREMIUM": {
        "max_stores": None,
        "max_products": None,
    },
}


def normalize_subscription_plan(plan: Optional[str]) -> str:
    normalized = str(plan or "STARTER").upper()
    return PLAN_ALIASES.get(normalized, normalized)


def get_plan_limits(plan: Optional[str]) -> dict:
    normalized = normalize_subscription_plan(plan)
    return PLAN_LIMITS.get(normalized, PLAN_LIMITS["STARTER"])


def get_max_stores(plan: Optional[str]) -> Optional[int]:
    return get_plan_limits(plan)["max_stores"]


def get_max_products(plan: Optional[str]) -> Optional[int]:
    return get_plan_limits(plan)["max_products"]
