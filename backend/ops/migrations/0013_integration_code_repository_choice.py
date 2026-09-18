from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0012_clear_role_permissions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='integration',
            name='integration_type',
            field=models.CharField(choices=[('llm', 'LLM'), ('prometheus', 'Prometheus'), ('loki', 'Loki'), ('tempo', 'Tempo'), ('grafana', 'Grafana'), ('notification', 'Notification'), ('code_repository', 'Code Repository')], max_length=40),
        ),
    ]
