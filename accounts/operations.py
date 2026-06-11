OPERATIONS_MODULE = "operations"


def can_perform_operations(profile, permission):
    from .policies import role_matrix_allows

    return role_matrix_allows(profile, permission, module=OPERATIONS_MODULE, default=False)
