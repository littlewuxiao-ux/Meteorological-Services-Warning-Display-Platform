"""配置库模型：用户设置、机场资料、告警规则。"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator



class AirportInfo(models.Model):
    """机场信息表"""
    
    airport_4code = models.CharField(max_length=4, primary_key=True, verbose_name='机场四字代码')
    airport_3code = models.CharField(max_length=3, blank=True, null=True, verbose_name='机场三字代码')
    airport_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='机场名称')
    classification = models.CharField(max_length=50, blank=True, null=True, verbose_name='性质')
    
    # 区域信息
    area = models.CharField(max_length=20, blank=True, null=True, verbose_name='区域')
    area_code = models.CharField(max_length=10, blank=True, null=True, verbose_name='区号')
    
    # 联系方式
    forecast_phone = models.CharField(max_length=100, blank=True, null=True, verbose_name='预报电话')
    observation_phone = models.CharField(max_length=100, blank=True, null=True, verbose_name='观测电话')
    other_phone = models.CharField(max_length=100, blank=True, null=True, verbose_name='其他电话')

    latitude = models.FloatField(blank=True, null=True, verbose_name='纬度（十进制度）')
    longitude = models.FloatField(blank=True, null=True, verbose_name='经度（十进制度）')
    catalog_only = models.BooleanField(default=False, verbose_name='仅坐标目录')
    taf_infer_attempted = models.BooleanField(default=False, verbose_name='已尝试推断预报入库配置')
    
    # 预留字段
    extraInfo4 = models.TextField(blank=True, null=True, verbose_name='预留字段4')
    extraInfo5 = models.TextField(blank=True, null=True, verbose_name='预留字段5')
    extraInfo6 = models.TextField(blank=True, null=True, verbose_name='预留字段6')
    
    # 修订历史
    revision_history = models.TextField(blank=True, null=True, verbose_name='修订历史')
    
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'airport_info'
        verbose_name = '机场信息'
        verbose_name_plural = '机场信息'
        
    def __str__(self):
        return f"{self.airport_4code} - {self.airport_name or '未知机场'}"


class AirportAlertThresholds(models.Model):
    """机场告警阈值。每个用户只存改过的机场；机场代码 default 是通用行。"""

    id = models.AutoField(primary_key=True)
    user_code = models.CharField(max_length=12, verbose_name='用户代码')
    airport_4code = models.CharField(max_length=4, verbose_name='机场四字代码')
    
    # 能见度告警阈值（单位：米）
    visibility_m_red = models.PositiveIntegerField(default=800, verbose_name='能见度红色告警值')
    visibility_m_yellow = models.PositiveIntegerField(default=1600, verbose_name='能见度黄色告警值')
    visibility_m_green = models.PositiveIntegerField(default=2000, verbose_name='能见度绿色告警值')
    
    # RVR告警阈值（单位：米）
    rvr_m_red = models.PositiveIntegerField(blank=True, null=True, verbose_name='RVR红色告警值')
    rvr_m_yellow = models.PositiveIntegerField(blank=True, null=True, verbose_name='RVR黄色告警值')
    rvr_m_green = models.PositiveIntegerField(blank=True, null=True, verbose_name='RVR绿色告警值')
    
    # 云高告警阈值（单位：百英尺）
    cloud_min_red = models.PositiveIntegerField(default=2, verbose_name='云高红色告警值')
    cloud_min_yellow = models.PositiveIntegerField(default=5, verbose_name='云高黄色告警值')
    cloud_min_green = models.PositiveIntegerField(default=10, verbose_name='云高绿色告警值')
    # 计入最低云底高的最低云量（含）。低于该云量的云组不参与取最低云底高。
    min_cloud_amt = models.CharField(
        max_length=3,
        choices=[('FEW', 'FEW'), ('SCT', 'SCT'), ('BKN', 'BKN'), ('OVC', 'OVC')],
        default='SCT',
        verbose_name='计入云底高的最低云量',
    )
    
    # 平均风速告警阈值（单位：米/秒）
    average_wind_speed_mps_red = models.PositiveIntegerField(default=12, verbose_name='平均风红色告警值')
    average_wind_speed_mps_yellow = models.PositiveIntegerField(default=8, verbose_name='平均风黄色告警值')
    average_wind_speed_mps_green = models.PositiveIntegerField(default=5, verbose_name='平均风绿色告警值')
    
    # 阵风告警阈值（单位：米/秒）
    gust_mps_red = models.PositiveIntegerField(default=17, verbose_name='阵风红色告警值')
    gust_mps_yellow = models.PositiveIntegerField(default=13, verbose_name='阵风黄色告警值')
    gust_mps_green = models.PositiveIntegerField(default=10, verbose_name='阵风绿色告警值')
    
    # 温度告警阈值（单位：摄氏度）
    temperature_cold_red = models.IntegerField(default=-30, verbose_name='低温红色告警值')
    temperature_cold_yellow = models.IntegerField(default=-27, verbose_name='低温黄色告警值')
    temperature_cold_green = models.IntegerField(default=-25, verbose_name='低温绿色告警值')
    temperature_hot_red = models.PositiveIntegerField(default=40, verbose_name='高温红色告警值')
    temperature_hot_yellow = models.PositiveIntegerField(default=37, verbose_name='高温黄色告警值')
    temperature_hot_green = models.PositiveIntegerField(default=35, verbose_name='高温绿色告警值')
    
    # 跑道视程告警阈值（单位：米）
    rvr_m_red = models.PositiveIntegerField(blank=True, null=True, verbose_name='RVR红色告警值')
    rvr_m_yellow = models.PositiveIntegerField(blank=True, null=True, verbose_name='RVR黄色告警值')
    rvr_m_green = models.PositiveIntegerField(blank=True, null=True, verbose_name='RVR绿色告警值')
    
    # 修订历史
    revision_history = models.TextField(blank=True, null=True, verbose_name='修订历史')
    
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'airport_alert_thresholds'
        verbose_name = '机场告警阈值'
        verbose_name_plural = '机场告警阈值'
        unique_together = [['user_code', 'airport_4code']]

    def __str__(self):
        return f"{self.user_code}:{self.airport_4code} - 告警阈值"


class WeatherAlertLevels(models.Model):
    """天气现象告警等级表"""
    
    ALERT_LEVEL_CHOICES = [
        ('R', '红色告警'),
        ('Y', '黄色告警'),
        ('G', '绿色告警'),
    ]
    
    user_code = models.CharField(max_length=12, verbose_name='用户代码')
    weather = models.CharField(max_length=20, verbose_name='天气现象代码')
    alert_level = models.CharField(max_length=1, choices=ALERT_LEVEL_CHOICES, verbose_name='告警等级')
    type1 = models.CharField(max_length=1, blank=True, null=True, verbose_name='天气类型1')
    type2 = models.CharField(max_length=1, blank=True, null=True, verbose_name='天气类型2')
    type3 = models.CharField(max_length=1, blank=True, null=True, verbose_name='天气类型3')
    description = models.CharField(max_length=100, blank=True, null=True, verbose_name='描述')
    
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'weather_alert_levels'
        verbose_name = '天气现象告警等级'
        verbose_name_plural = '天气现象告警等级'
        unique_together = [['user_code', 'weather', 'alert_level']]
        
    def __str__(self):
        return f"{self.weather} - {self.get_alert_level_display()}"


class Carrier(models.Model):
    """每个用户一行已选承运人。没改过则不建行，读取用 default。"""

    user_code = models.CharField(max_length=12, unique=True, verbose_name='用户代码')
    codes = models.JSONField(default=list, verbose_name='二字代码列表')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'carrier'
        verbose_name = '航空公司'
        verbose_name_plural = '航空公司'

    def __str__(self):
        return f"{self.user_code} - 承运人"


class SystemConfig(models.Model):
    """系统配置表"""
    
    CONFIG_TYPE_CHOICES = [
        ('data_retention', '数据保留配置'),
        ('auto_refresh', '自动刷新配置'),
        ('data_source', '数据源配置'),
    ]
    
    config_type = models.CharField(max_length=20, choices=CONFIG_TYPE_CHOICES, verbose_name='配置类型')
    config_key = models.CharField(max_length=50, verbose_name='配置键')
    config_value = models.TextField(verbose_name='配置值')
    description = models.CharField(max_length=200, blank=True, null=True, verbose_name='描述')
    
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'system_config'
        verbose_name = '系统配置'
        verbose_name_plural = '系统配置'
        unique_together = [['config_type', 'config_key']]
        
    def __str__(self):
        return f"{self.get_config_type_display()} - {self.config_key}"


class DataRefreshTimer(models.Model):
    """每个用户一份刷新间隔。config 的键是 metar / taf / flight / aircraft_parking。"""

    user_code = models.CharField(max_length=12, unique=True, verbose_name='用户代码')
    config = models.JSONField(default=dict, verbose_name='刷新配置')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'data_refresh_timer'
        verbose_name = '数据刷新定时器配置'
        verbose_name_plural = '数据刷新定时器配置'

    def __str__(self):
        return f"{self.user_code} - 刷新间隔"


class PopupSettings(models.Model):
    """弹窗规则与开关。按用户分存，没有个人行时用 default。"""

    user_code = models.CharField(max_length=12, unique=True, verbose_name='用户代码')
    operation_metar_popup_leeway = models.IntegerField(blank=True, null=True, verbose_name='运行区METAR弹窗余量')
    operation_metar_popup_level = models.CharField(max_length=1, blank=True, null=True, verbose_name='运行区METAR弹窗级别')
    parking_metar_popup_level = models.CharField(max_length=1, blank=True, null=True, verbose_name='停场METAR弹窗级别')
    trace_time = models.PositiveSmallIntegerField(default=6, verbose_name='弹窗追溯时间（小时）')
    operation_enabled = models.BooleanField(default=True, verbose_name='运行类弹窗')
    parking_enabled = models.BooleanField(default=True, verbose_name='停场类弹窗')
    intercept_enabled = models.BooleanField(default=True, verbose_name='降级免打扰')

    class Meta:
        db_table = 'popup_settings'
        verbose_name = '弹窗设置'
        verbose_name_plural = '弹窗设置'

    def __str__(self):
        return f"{self.user_code} - 弹窗设置"


class WeatherTypeInfo(models.Model):
    """天气类型信息表"""
    
    weather_type_code = models.CharField(max_length=1, verbose_name='天气类型代码')
    description_cn = models.CharField(max_length=10, blank=True, null=True, verbose_name='中文说明')
    description_en = models.CharField(max_length=20, blank=True, null=True, verbose_name='英文说明')
    
    class Meta:
        db_table = 'weather_type_info'
        verbose_name = '天气类型信息'
        verbose_name_plural = '天气类型信息'
    
    def __str__(self):
        return f"{self.weather_type_code} - {self.description_cn or self.description_en or ''}"


class AirportTafImportConfig(models.Model):
    """预报入库配置。主键为机场四字代码，与机场资料分开维护。"""

    airport_4code = models.CharField(max_length=4, primary_key=True, verbose_name='机场四字代码')
    taf_init_time = models.SmallIntegerField(blank=True, null=True, verbose_name='首份预报发布整点')
    import_check_interval = models.SmallIntegerField(blank=True, null=True, verbose_name='发布间隔小时')
    taf_max_delay = models.SmallIntegerField(blank=True, null=True, verbose_name='接收延迟分钟')

    class Meta:
        db_table = 'airport_taf_import_config'
        verbose_name = '预报入库配置'
        verbose_name_plural = '预报入库配置'

    def __str__(self):
        return self.airport_4code


class AirportPrefixArea(models.Model):
    """一行一个前缀。同一序号、区域名称、性质在设置页合并显示。"""

    prefix = models.CharField(max_length=4, primary_key=True, verbose_name='前缀')
    sequence = models.PositiveIntegerField(default=1, verbose_name='序号')
    classification = models.CharField(max_length=10, verbose_name='性质')
    area = models.CharField(max_length=20, verbose_name='区域')
    remark = models.TextField(blank=True, default='', verbose_name='备注')

    class Meta:
        db_table = 'airport_prefix_area'
        verbose_name = '前缀区域'
        verbose_name_plural = '前缀区域'
        ordering = ['sequence', 'area', 'prefix']

    def __str__(self):
        return f'{self.prefix} {self.classification}/{self.area}'


class RadarAlertConfig(models.Model):
    """雷达告警可配置参数。每个用户一行 JSON，没改过则读 default。"""

    user_code = models.CharField(max_length=12, unique=True, verbose_name='用户代码')
    config = models.JSONField(default=dict, verbose_name='配置JSON')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'radar_alert_config'
        verbose_name = '雷达告警配置'
        verbose_name_plural = '雷达告警配置'

    def __str__(self):
        return f'RadarAlertConfig#{self.pk}'


class StyleConfig(models.Model):
    """界面样式等配置（单行有效，JSON 存整表）。雷达地图样式与机场详细信息主题写在同一份 JSON 里，按登录用户覆盖。"""

    config = models.JSONField(default=dict, verbose_name='配置JSON')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'style_config'
        verbose_name = '样式配置'
        verbose_name_plural = '样式配置'

    def __str__(self):
        return f'StyleConfig#{self.pk}'


class TrendAlertConfig(models.Model):
    """实况趋势告警规则。每个用户一行 JSON，没改过则读 default。"""

    user_code = models.CharField(max_length=12, unique=True, verbose_name='用户代码')
    config = models.JSONField(default=dict, verbose_name='配置JSON')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'trend_alert_config'
        verbose_name = '实况趋势告警配置'
        verbose_name_plural = '实况趋势告警配置'

    def __str__(self):
        return f'TrendAlertConfig#{self.pk}'
