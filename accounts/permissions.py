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
        
        # Plan hierarchy: BASIC < STANDARD < OTHER
        plan_levels = {
            'BASIC': 0,
            'STANDARD': 1,
            'OTHER': 2
        }
        
        user_level = plan_levels.get(user_plan, 0)
        required_level = plan_levels.get(required_plan, 0)
        
        return user_level >= required_level
