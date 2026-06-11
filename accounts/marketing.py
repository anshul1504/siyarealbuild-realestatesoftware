from .policies import role_matrix_allows


MARKETING_MODULE = "marketing"


def can_perform_marketing(profile, permission):
    return role_matrix_allows(profile, permission, module=MARKETING_MODULE)
