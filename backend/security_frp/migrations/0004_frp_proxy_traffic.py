from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_frp', '0003_remove_unavailable_agent_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='frpproxy',
            name='traffic_in_bytes',
            field=models.PositiveBigIntegerField(default=0, help_text='frp proxy的入站流量字节数字段。', verbose_name='入站流量字节数'),
        ),
        migrations.AddField(
            model_name='frpproxy',
            name='traffic_out_bytes',
            field=models.PositiveBigIntegerField(default=0, help_text='frp proxy的出站流量字节数字段。', verbose_name='出站流量字节数'),
        ),
        migrations.AddField(
            model_name='frpproxy',
            name='traffic_updated_at',
            field=models.DateTimeField(blank=True, help_text='frp proxy的流量更新时间字段。', null=True, verbose_name='流量更新时间'),
        ),
    ]
