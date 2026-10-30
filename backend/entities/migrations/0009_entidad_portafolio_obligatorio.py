"""Toda entidad pertenece a un portafolio (D-29): ya con los datos migrados, el campo es obligatorio."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("entities", "0008_datos_portafolios"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entidad",
            name="portafolio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entidades",
                to="entities.portafolio",
            ),
        ),
    ]
