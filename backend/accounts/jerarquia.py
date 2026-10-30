from .models import PerfilRol


def puede_asignar(nivel_actor: int, perfil: PerfilRol) -> bool:
    """¿Quien tiene `nivel_actor` puede crear, asignar o quitar el rol de `perfil`? (D-18)

    Hace falta un nivel estrictamente mayor al del rol y, además, alcanzar el nivel mínimo
    para asignarlo (esa es la excepción del Auditor). No incluye el permiso de gestionar
    miembros ni el caso del Admin y el superusuario, que salta esta regla: lo decide quien llama.
    """
    return nivel_actor > perfil.nivel and nivel_actor >= perfil.nivel_minimo_para_asignar


def puede_asignar_en_portafolio(nivel_actor: int, perfil: PerfilRol) -> bool:
    """En un portafolio se puede asignar un rol de nivel igual o menor al propio (D-29).

    A diferencia de las entidades, los pares pueden nombrarse entre sí: es lo que permite que
    varios Gestores colaboren. El permiso de gestionar miembros del portafolio lo decide quien llama.
    """
    return nivel_actor >= perfil.nivel
