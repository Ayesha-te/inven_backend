from typing import Set

from rest_framework import permissions

from .plan_limits import get_plan_label, normalize_subscription_plan


PLAN_LEVELS = {
    'BASIC': 0,
    'STARTER': 1,
    'PRO': 2,
}


def get_plan_level(plan_name: str) -> int:
    normalized_plan = normalize_subscription_plan(plan_name)
    return PLAN_LEVELS.get(normalized_plan, PLAN_LEVELS['BASIC'])


def get_all_features(plan_name: str) -> Set[str]:
    from django.conf import settings

    normalized_plan = normalize_subscription_plan(plan_name)
    plan_config = settings.SUBSCRIPTION_PLANS.get(
        normalized_plan,
        settings.SUBSCRIPTION_PLANS['BASIC'],
    )

    features = set(plan_config.get('features', []))
    inherited_plan = plan_config.get('inherits')
    if inherited_plan:
        features.update(get_all_features(inherited_plan))

    return features

class PlanPermission(permissions.BasePermission):
    """
    Permission class to restrict access based on user subscription plan.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Superusers can do anything
        if request.user.is_superuser:
            return True
            
        required_plan = normalize_subscription_plan(getattr(view, 'required_plan', 'BASIC'))
        user_plan = normalize_subscription_plan(request.user.subscription_plan)
        user_level = get_plan_level(user_plan)
        required_level = get_plan_level(required_plan)

        if user_level < required_level:
            self.message = (
                f"Your '{get_plan_label(user_plan)}' plan does not meet the '{get_plan_label(required_plan)}' plan requirement. "
                "Please upgrade your subscription."
            )

        return user_level >= required_level


class HasSubscriptionFeature(permissions.BasePermission):
    """
    Allows access only to users with a specific feature in their subscription plan.
    The view must have a `required_feature` attribute.
    e.g., required_feature = 'barcode_scanner_support'
    """
    
    def has_permission(self, request, view):
        from django.conf import settings
        
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
            
        required_feature = getattr(view, 'required_feature', None)
        if not required_feature:
            # If no feature is required, grant access.
            # Or you could deny access by default: return False
            return True

        user_plan = normalize_subscription_plan(request.user.subscription_plan)
        user_features = get_all_features(user_plan)

        if required_feature in user_features:
            return True
            
        self.message = f"Your '{get_plan_label(user_plan)}' plan does not include the '{required_feature}' feature. Please upgrade your plan."
        return False
