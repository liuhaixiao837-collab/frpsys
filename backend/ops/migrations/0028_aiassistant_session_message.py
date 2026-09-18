from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ops', '0027_llmcallrecord_token_counts'),
    ]

    operations = [
        migrations.CreateModel(
            name='AiAssistantSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=160)),
                ('context', models.JSONField(blank=True, default=dict)),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_assistant_sessions', to='ops.organization')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_assistant_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='AiAssistantMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=32)),
                ('content', models.TextField()),
                ('status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed')], default='success', max_length=32)),
                ('provider', models.CharField(blank=True, max_length=120)),
                ('model', models.CharField(blank=True, max_length=120)),
                ('latency_ms', models.FloatField(default=0)),
                ('input_tokens', models.PositiveIntegerField(default=0)),
                ('output_tokens', models.PositiveIntegerField(default=0)),
                ('request_id', models.CharField(blank=True, max_length=80)),
                ('error', models.TextField(blank=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='ops.aiassistantsession')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='aiassistantsession',
            index=models.Index(fields=['user', 'updated_at'], name='ops_ai_chat_user_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='aiassistantsession',
            index=models.Index(fields=['organization', 'updated_at'], name='ops_ai_chat_org_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='aiassistantmessage',
            index=models.Index(fields=['session', 'created_at'], name='ops_ai_msg_session_created_idx'),
        ),
        migrations.AddIndex(
            model_name='aiassistantmessage',
            index=models.Index(fields=['request_id'], name='ops_ai_msg_request_idx'),
        ),
    ]
