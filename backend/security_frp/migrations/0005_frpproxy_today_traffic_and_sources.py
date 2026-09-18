from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_frp', '0004_frp_proxy_traffic'),
    ]

    operations = [
        migrations.AddField(
            model_name='frpproxy',
            name='today_traffic_in_bytes',
            field=models.PositiveBigIntegerField(default=0, help_text='frp proxy的今日入站流量字节数字段。', verbose_name='今日入站流量字节数'),
        ),
        migrations.AddField(
            model_name='frpproxy',
            name='today_traffic_out_bytes',
            field=models.PositiveBigIntegerField(default=0, help_text='frp proxy的今日出站流量字节数字段。', verbose_name='今日出站流量字节数'),
        ),
        migrations.AddField(
            model_name='frpproxy',
            name='traffic_date',
            field=models.DateField(blank=True, help_text='frp proxy的流量统计日期字段。', null=True, verbose_name='流量统计日期'),
        ),
        migrations.AddField(
            model_name='frpproxy',
            name='traffic_source_in_bytes',
            field=models.PositiveBigIntegerField(default=0, help_text='frp proxy的最近源入站流量字节数字段。', verbose_name='最近源入站流量字节数'),
        ),
        migrations.AddField(
            model_name='frpproxy',
            name='traffic_source_out_bytes',
            field=models.PositiveBigIntegerField(default=0, help_text='frp proxy的最近源出站流量字节数字段。', verbose_name='最近源出站流量字节数'),
        ),
    ]
