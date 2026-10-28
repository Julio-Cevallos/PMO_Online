from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import EntidadViewSet, MiembroDetalleView, MiembrosView, TipoEntidadViewSet

router = SimpleRouter()
router.register("entity-types", TipoEntidadViewSet, basename="entity-types")
router.register("entities", EntidadViewSet, basename="entities")

urlpatterns = [
    *router.urls,
    path("entities/<int:entidad_id>/members/", MiembrosView.as_view(), name="entity-members"),
    path(
        "entities/<int:entidad_id>/members/<int:pk>/",
        MiembroDetalleView.as_view(),
        name="entity-member-detail",
    ),
]
