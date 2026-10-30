from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CandidatosView,
    EntidadViewSet,
    MiembroDetalleView,
    MiembrosView,
    RolesAsignablesView,
    TipoEntidadViewSet,
)
from .views_invitaciones import (
    AceptarInvitacionView,
    InvitacionEntidadDetalleView,
    InvitacionesEntidadView,
    MisInvitacionesView,
    RechazarInvitacionView,
)
from .views_portafolios import (
    AceptarInvitacionPortafolioView,
    InvitacionesPortafolioView,
    InvitacionPortafolioDetalleView,
    MiembroPortafolioDetalleView,
    MiembrosPortafolioView,
    MisInvitacionesPortafolioView,
    PortafolioViewSet,
    RechazarInvitacionPortafolioView,
    RolesAsignablesPortafolioView,
)

router = SimpleRouter()
router.register("entity-types", TipoEntidadViewSet, basename="entity-types")
router.register("entities", EntidadViewSet, basename="entities")
router.register("portfolios", PortafolioViewSet, basename="portfolios")

urlpatterns = [
    *router.urls,
    path("entities/<int:entidad_id>/members/", MiembrosView.as_view(), name="entity-members"),
    path(
        "entities/<int:entidad_id>/assignable-roles/",
        RolesAsignablesView.as_view(),
        name="entity-assignable-roles",
    ),
    path(
        "entities/<int:entidad_id>/candidates/",
        CandidatosView.as_view(),
        name="entity-candidates",
    ),
    path(
        "entities/<int:entidad_id>/invitations/",
        InvitacionesEntidadView.as_view(),
        name="entity-invitations",
    ),
    path(
        "entities/<int:entidad_id>/invitations/<int:pk>/",
        InvitacionEntidadDetalleView.as_view(),
        name="entity-invitation-detail",
    ),
    path(
        "portfolios/<int:portafolio_id>/members/",
        MiembrosPortafolioView.as_view(),
        name="portfolio-members",
    ),
    path(
        "portfolios/<int:portafolio_id>/members/<int:pk>/",
        MiembroPortafolioDetalleView.as_view(),
        name="portfolio-member-detail",
    ),
    path(
        "portfolios/<int:portafolio_id>/assignable-roles/",
        RolesAsignablesPortafolioView.as_view(),
        name="portfolio-assignable-roles",
    ),
    path(
        "portfolios/<int:portafolio_id>/invitations/",
        InvitacionesPortafolioView.as_view(),
        name="portfolio-invitations",
    ),
    path(
        "portfolios/<int:portafolio_id>/invitations/<int:pk>/",
        InvitacionPortafolioDetalleView.as_view(),
        name="portfolio-invitation-detail",
    ),
    path(
        "portfolio-invitations/",
        MisInvitacionesPortafolioView.as_view(),
        name="my-portfolio-invitations",
    ),
    path(
        "portfolio-invitations/<int:pk>/accept/",
        AceptarInvitacionPortafolioView.as_view(),
        name="portfolio-invitation-accept",
    ),
    path(
        "portfolio-invitations/<int:pk>/reject/",
        RechazarInvitacionPortafolioView.as_view(),
        name="portfolio-invitation-reject",
    ),
    path("invitations/", MisInvitacionesView.as_view(), name="my-invitations"),
    path(
        "invitations/<int:pk>/accept/",
        AceptarInvitacionView.as_view(),
        name="invitation-accept",
    ),
    path(
        "invitations/<int:pk>/reject/",
        RechazarInvitacionView.as_view(),
        name="invitation-reject",
    ),
    path(
        "entities/<int:entidad_id>/members/<int:pk>/",
        MiembroDetalleView.as_view(),
        name="entity-member-detail",
    ),
]
