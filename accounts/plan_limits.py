from typing import Optional


PLAN_ALIASES = {
    "FREE": "BASIC",
    "STANDARD": "STARTER",
    "PREMIUM": "PRO",
    "OTHER": "PRO",
}

PLAN_LABELS = {
    "BASIC": "Basic",
    "STARTER": "Starter",
    "PRO": "Pro",
}


PLAN_LIMITS = {
    "BASIC": {
        "max_stores": 1,
        "max_products": 100,
    },
    "STARTER": {
        "max_stores": 3,
        "max_products": 1000,
    },
    "PRO": {
        "max_stores": None,
        "max_products": None,
    },
}


def normalize_subscription_plan(plan: Optional[str]) -> str:
    normalized = str(plan or "BASIC").upper()
    return PLAN_ALIASES.get(normalized, normalized)


def get_plan_limits(plan: Optional[str]) -> dict:
    normalized = normalize_subscription_plan(plan)
    return PLAN_LIMITS.get(normalized, PLAN_LIMITS["BASIC"])


def get_plan_label(plan: Optional[str]) -> str:
    normalized = normalize_subscription_plan(plan)
    return PLAN_LABELS.get(normalized, "Basic")


def get_max_stores(plan: Optional[str]) -> Optional[int]:
    return get_plan_limits(plan)["max_stores"]


def get_max_products(plan: Optional[str]) -> Optional[int]:
    return get_plan_limits(plan)["max_products"]
