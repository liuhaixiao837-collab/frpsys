from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0026_llmcallconfig_unavailable_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='llmcallrecord',
            name='input_tokens',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='llmcallrecord',
            name='output_tokens',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
