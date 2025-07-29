from django.core.exceptions import PermissionDenied

class RoleRequiredMixin:
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("User not authenticated")

        if request.user.role not in self.allowed_roles:
            raise PermissionDenied("User not allowed")

        return super().dispatch(request, *args, **kwargs)
