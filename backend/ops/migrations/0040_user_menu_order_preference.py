from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ops', '0039_platform_security_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserMenuOrderPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, help_text='数据库主键。', primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, help_text='记录创建时间。')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最后更新时间。')),
                ('order_data', models.JSONField(blank=True, default=dict, help_text='按父级菜单权限代码保存的完整同级菜单代码顺序。')),
                ('user', models.OneToOneField(help_text='使用这套个人菜单顺序的平台用户。', on_delete=django.db.models.deletion.CASCADE, related_name='menu_order_preference', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
