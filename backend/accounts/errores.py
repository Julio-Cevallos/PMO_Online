from rest_framework import status
from rest_framework.exceptions import APIException


class Conflicto(APIException):
    """409: la acción choca con el estado actual (algo en uso, ya existe, archivado…)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "La acción no se puede realizar en el estado actual."
    default_code = "conflict"
