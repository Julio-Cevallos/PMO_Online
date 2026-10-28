from rest_framework.routers import DefaultRouter

from .views_roles import RolViewSet

router = DefaultRouter()
router.register("", RolViewSet, basename="roles")

urlpatterns = router.urls
