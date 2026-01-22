from billing.models import AuditLog

def log_action(user, action, model_name, object_id, description):
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        description=description
    )