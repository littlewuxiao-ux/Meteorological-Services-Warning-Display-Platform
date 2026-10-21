from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('config_db', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='MapStyleConfig',
            new_name='StyleConfig',
        ),
        migrations.AlterModelTable(
            name='StyleConfig',
            table='style_config',
        ),
        migrations.AlterModelOptions(
            name='StyleConfig',
            options={
                'verbose_name': '样式配置',
                'verbose_name_plural': '样式配置',
            },
        ),
    ]
