import django_filters
from rest_framework import serializers, viewsets
from rest_framework.routers import SimpleRouter

from .models import EventoAuditoria
from .visibilidad import PuedeVerAuditoria, eventos_visibles


class EventoAuditoriaSerializer(serializers.ModelSerializer):
    """Un evento del historial. Todo es de solo lectura."""

    categoria_nombre = serializers.CharField(source="get_categoria_display", read_only=True)

    class Meta:
        model = EventoAuditoria
        fields = (
            "id",
            "ocurrido_en",
            "categoria",
            "categoria_nombre",
            "accion",
            "usuario_id",
            "usuario_nombre",
            "ip",
            "entidad_id",
            "entidad_nombre",
            "portafolio_id",
            "portafolio_nombre",
            "objeto_tipo",
            "objeto_id",
            "objeto_nombre",
            "cambios",
            "detalle",
        )
        read_only_fields = fields


class EventoFilter(django_filters.FilterSet):
    """Filtros del historial. `accion` acepta un prefijo (`usuario.` trae todas las de usuarios)."""

    usuario = django_filters.NumberFilter(field_name="usuario_id")
    entidad = django_filters.NumberFilter(field_name="entidad_id")
    portafolio = django_filters.NumberFilter(field_name="portafolio_id")
    accion = django_filters.CharFilter(lookup_expr="startswith")
    desde = django_filters.DateFilter(field_name="ocurrido_en", lookup_expr="date__gte")
    hasta = django_filters.DateFilter(field_name="ocurrido_en", lookup_expr="date__lte")

    class Meta:
        model = EventoAuditoria
        fields = ("categoria", "objeto_tipo", "objeto_id")


class AuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """Historial de auditoría: solo lectura, del más reciente al más antiguo, paginado.

    Cada persona ve solo lo que le corresponde (ver `audit/visibilidad.py`). Un evento fuera de
    su alcance responde 404.
    """

    serializer_class = EventoAuditoriaSerializer
    permission_classes = (PuedeVerAuditoria,)
    filterset_class = EventoFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # generación del esquema OpenAPI
            return EventoAuditoria.objects.none()
        return eventos_visibles(self.request.user)


router = SimpleRouter()
router.register("", AuditoriaViewSet, basename="audit")
urlpatterns = router.urls
