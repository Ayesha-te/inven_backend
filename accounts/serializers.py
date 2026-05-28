from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User, UserProfile, UserSession
from .plan_limits import normalize_subscription_plan


from supermarkets.models import Supermarket, SupermarketSettings

class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration with optional supermarket auto-creation"""
    
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    subscription_plan = serializers.CharField(required=False, default='STARTER')
    supermarket_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    supermarket_address = serializers.CharField(required=False, allow_blank=True, write_only=True)
    supermarket_phone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 
            'password', 'password_confirm', 'phone', 'company_name', 'address', 'subscription_plan',
            'supermarket_name', 'supermarket_address', 'supermarket_phone'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")

        submitted_plan = str(attrs.get('subscription_plan', 'STARTER')).upper()
        normalized_plan = normalize_subscription_plan(submitted_plan)
        valid_plans = {choice[0] for choice in User.SUBSCRIPTION_CHOICES}
        if normalized_plan not in valid_plans:
            raise serializers.ValidationError({
                'subscription_plan': f"Invalid plan '{submitted_plan}'. Choose STARTER, BASIC, STANDARD, or PREMIUM."
            })
        attrs['subscription_plan'] = normalized_plan
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Extract supermarket fields (optional)
        supermarket_name = validated_data.pop('supermarket_name', '').strip()
        supermarket_address = validated_data.pop('supermarket_address', '').strip()
        supermarket_phone = validated_data.pop('supermarket_phone', '').strip()
        
        # Map supermarket_name to company_name if company_name not provided
        if supermarket_name and not validated_data.get('company_name'):
            validated_data['company_name'] = supermarket_name

        validated_data['approval_status'] = 'PENDING'
        validated_data['is_active'] = False
        
        # Create user
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        
        # Auto-create a primary supermarket for this user
        try:
            name = supermarket_name or validated_data.get('company_name') or (
                f"{(user.first_name or user.email.split('@')[0]).strip()}'s Supermarket"
            )
            address = supermarket_address or 'Not provided'
            # Must satisfy regex '^[+]?1?\d{9,15}$'
            phone = supermarket_phone or '+10000000000'
            Supermarket_obj = Supermarket.objects.create(
                owner=user,
                name=name,
                address=address,
                phone=phone,
                email=user.email,
                description='Automatically created on user registration',
            )
            # Create default settings (optional)
            try:
                SupermarketSettings.objects.create(supermarket=Supermarket_obj)
            except Exception:
                pass
        except Exception:
            # Do not fail user registration if supermarket creation fails
            pass
        
        # UserProfile is automatically created by signal, no need to create manually
        
        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            try:
                requested_user = User.objects.get(email=email)
            except User.DoesNotExist:
                requested_user = None

            if requested_user:
                if requested_user.approval_status == 'PENDING':
                    raise serializers.ValidationError('Your registration request is still pending admin approval.')
                if requested_user.approval_status == 'REJECTED':
                    raise serializers.ValidationError('Your registration request was rejected. Please contact the administrator.')
                if not requested_user.is_active:
                    raise serializers.ValidationError('Your account is inactive. Please contact the administrator.')

            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials')
            
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must include email and password')


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile"""
    
    subscription_days_remaining = serializers.ReadOnlyField(source='get_subscription_days_remaining')
    is_subscription_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name',
            'phone', 'company_name', 'address', 'profile_picture',
            'subscription_plan', 'subscription_start_date', 'subscription_end_date',
            'is_subscription_active', 'subscription_days_remaining', 'is_subscription_expired',
            'timezone', 'language', 'email_notifications', 'is_verified',
            'approval_status', 'approved_at', 'is_staff', 'is_superuser', 'is_active',
            'registration_date', 'last_login'
        ]
        read_only_fields = [
            'id', 'email', 'registration_date', 'last_login',
            'subscription_plan', 'subscription_start_date', 'subscription_end_date',
            'is_subscription_active', 'is_verified', 'approval_status', 'approved_at',
            'is_staff', 'is_superuser', 'is_active'
        ]


class UserProfileDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for user profile with extended info"""
    
    profile = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name',
            'phone', 'company_name', 'address', 'profile_picture',
            'subscription_plan', 'subscription_start_date', 'subscription_end_date',
            'is_subscription_active', 'timezone', 'language', 'email_notifications',
            'is_verified', 'approval_status', 'approved_at', 'is_staff', 'is_superuser',
            'is_active', 'registration_date', 'last_login', 'profile'
        ]
    
    def get_profile(self, obj):
        try:
            profile = obj.profile
            return {
                'bio': profile.bio,
                'birth_date': profile.birth_date,
                'website': profile.website,
                'business_type': profile.business_type,
                'tax_id': profile.tax_id,
                'low_stock_alerts': profile.low_stock_alerts,
                'expiry_alerts': profile.expiry_alerts,
                'pos_sync_alerts': profile.pos_sync_alerts,
                'weekly_reports': profile.weekly_reports,
            }
        except UserProfile.DoesNotExist:
            return None


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password"""
    
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match")
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value


class UserSessionSerializer(serializers.ModelSerializer):
    """Serializer for user sessions"""
    
    class Meta:
        model = UserSession
        fields = [
            'id', 'session_key', 'ip_address', 'user_agent',
            'device_info', 'location', 'created_at', 'last_activity', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'last_activity']


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request"""
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No user found with this email address")
        return value


class AdminManagedStoreSerializer(serializers.ModelSerializer):
    sub_stores = serializers.SerializerMethodField()
    staff_members = serializers.SerializerMethodField()

    class Meta:
        model = Supermarket
        fields = [
            'id', 'name', 'address', 'email', 'phone', 'is_verified',
            'is_sub_store', 'registration_date', 'sub_stores', 'staff_members'
        ]

    def get_sub_stores(self, obj):
        return [
            {
                'id': str(sub_store.id),
                'name': sub_store.name,
                'is_verified': sub_store.is_verified,
                'registration_date': sub_store.registration_date,
            }
            for sub_store in obj.sub_stores.filter(is_active=True)
        ]

    def get_staff_members(self, obj):
        return [
            {
                'id': staff.user.id,
                'name': staff.user.get_full_name() or staff.user.email,
                'email': staff.user.email,
                'role': staff.role,
                'is_active': staff.is_active,
            }
            for staff in obj.staff.select_related('user').filter(is_active=True)
        ]


class AdminManagedUserSerializer(serializers.ModelSerializer):
    stores = serializers.SerializerMethodField()
    total_stores = serializers.SerializerMethodField()
    total_sub_stores = serializers.SerializerMethodField()
    total_staff_members = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    subscription_days_remaining = serializers.ReadOnlyField(source='get_subscription_days_remaining')
    subscription_status_text = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'email', 'phone', 'company_name', 'subscription_plan',
            'subscription_start_date', 'subscription_end_date', 'subscription_days_remaining',
            'approval_status', 'approved_at', 'approved_by_name', 'is_active', 'is_verified',
            'registration_date', 'stores', 'total_stores', 'total_sub_stores',
            'total_staff_members', 'subscription_status_text'
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email

    def get_stores(self, obj):
        stores = obj.owned_supermarkets.filter(is_active=True, is_sub_store=False).prefetch_related('sub_stores', 'staff__user')
        return AdminManagedStoreSerializer(stores, many=True).data

    def get_total_stores(self, obj):
        return obj.owned_supermarkets.filter(is_active=True, is_sub_store=False).count()

    def get_total_sub_stores(self, obj):
        return obj.owned_supermarkets.filter(is_active=True, is_sub_store=True).count()

    def get_total_staff_members(self, obj):
        return sum(store.staff.filter(is_active=True).count() for store in obj.owned_supermarkets.filter(is_active=True))

    def get_subscription_status_text(self, obj):
        if obj.subscription_end_date:
            remaining = obj.get_subscription_days_remaining()
            if remaining is not None:
                if remaining == 0:
                    return 'Subscription period completed'
                return f'{remaining} day(s) remaining'

        if obj.subscription_start_date:
            elapsed = timezone.now() - obj.subscription_start_date
            months = max(1, elapsed.days // 30) if elapsed.days > 0 else 0
            return f'{months} month(s) completed'

        return 'Subscription dates not set'

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return None
        return obj.approved_by.get_full_name() or obj.approved_by.email


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation"""
    
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
