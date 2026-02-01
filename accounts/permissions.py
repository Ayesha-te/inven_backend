from rest_framework import permissions

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
            
        required_plan = getattr(view, 'required_plan', 'BASIC')
        user_plan = request.user.subscription_plan
        
        # Plan hierarchy: BASIC < STARTER < PRO
        plan_levels = {
            'BASIC': 0,
            'STARTER': 1,
            'PRO': 2
        }
        
        user_level = plan_levels.get(user_plan, 0)
        required_level = plan_levels.get(required_plan, 0)
        
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

        user_plan = request.user.subscription_plan
        plan_config = settings.SUBSCRIPTION_PLANS.get(user_plan, settings.SUBSCRIPTION_PLANS['BASIC'])
        
        user_features = plan_config.get('features', [])
        
        # The PRO plan inherits all features from the STARTER plan.
        if plan_config.get('inherits') == 'STARTER':
            starter_config = settings.SUBSCRIPTION_PLANS.get('STARTER', {})
            user_features.extend(starter_config.get('features', []))

        if required_feature in user_features:
            return True
            
        self.message = f"Your '{user_plan}' plan does not include the '{required_feature}' feature. Please upgrade your plan."
        return False
