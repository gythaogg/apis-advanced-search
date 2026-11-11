from django.conf import settings

from apis_core.generic.helpers import permission_fullname


def can_view_model(request, model) -> bool:
    if getattr(settings, "APIS_ANON_VIEWS_ALLOWED", False):
        return True
    return request.user.has_perm(permission_fullname("view", model))
