from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0022_model_strategy_config'),
    ]

    operations = [
        migrations.DeleteModel(name='ModelRoutePolicy'),
    ]
