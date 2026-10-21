"""口令库模型。"""

from django.db import models


class AccessSetting(models.Model):
    """超级用户口令哈希。"""

    key = models.CharField(max_length=64, unique=True, verbose_name='键')
    value = models.TextField(verbose_name='值')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'access_setting'
        verbose_name = '口令配置'
        verbose_name_plural = '口令配置'

    def __str__(self):
        return self.key
