"""
解析数据模型
包括航班、METAR、TAF报文解析后的数据表
"""

from django.db import models
from django.utils import timezone


class Flight(models.Model):
    """航班数据表 - 根据项目规划.md 3.1节要求"""
    
    # 机场标识
    airport_4code = models.CharField(max_length=4, verbose_name='机场四字代码')
    
    # 是否有航班
    has_flight = models.BooleanField(default=False, verbose_name='是否有航班')

    # 三段式 48 时段与 marks 事件各占一列
    time_slots = models.JSONField(blank=True, null=True, verbose_name='航班时段明细')
    events = models.JSONField(blank=True, null=True, verbose_name='航班时刻事件')
    metar_highest_alert = models.JSONField(blank=True, null=True, verbose_name='机场实况最高告警五档')
    taf_highest_alert = models.JSONField(blank=True, null=True, verbose_name='机场预报最高告警五档')
    airport_highest_alert = models.JSONField(blank=True, null=True, verbose_name='机场综合最高告警五档')
    
    # 新增字段
    en_route = models.IntegerField(blank=True, null=True, verbose_name='是否在航线上')
    closest_departure_time_of_arriving_flight = models.BigIntegerField(blank=True, null=True, verbose_name='到达航班的最早起飞时间')
    closest_departure_time_at_this_airport = models.BigIntegerField(blank=True, null=True, verbose_name='本机场的最早起飞时间')
    closest_landing_time_of_arriving_flight = models.BigIntegerField(blank=True, null=True, verbose_name='到达航班的最近落地时间')
    
    # 系统字段
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'flight'
        verbose_name = '航班数据'
        verbose_name_plural = '航班数据'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['airport_4code']),
            models.Index(fields=['has_flight']),
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        return f"Flight {self.airport_4code} - Has: {self.has_flight}"

    def as_time_slots(self):
        """返回前端使用的 time_slots 数组。"""
        slots = self.time_slots
        if isinstance(slots, list):
            return slots
        return [''] * 48

    def as_events(self):
        """返回 marks 模式用的 events 列表。"""
        events = self.events
        if isinstance(events, list):
            return events
        return []

    def as_alert_levels(self, attr: str):
        """返回长度 5 的告警数组（裕度 0–4）。"""
        raw = getattr(self, attr, None)
        if isinstance(raw, list) and len(raw) >= 5:
            return [raw[i] if raw[i] in ('R', 'Y', 'G', 'N') else 'N' for i in range(5)]
        return ['N', 'N', 'N', 'N', 'N']



class Metar(models.Model):
    """METAR数据表 - 根据项目规划.md 3.2节要求"""
    
    # 机场标识
    airport_4code = models.CharField(max_length=4, verbose_name='机场四字代码')
    
    # SQC字段作为主键（全局唯一）
    sqc = models.CharField(max_length=50, primary_key=True, verbose_name='SQC标识')
    
    # METAR报文解析结果 - 按照项目规划.md 3.2节严格定义
    metar_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='metar报文类型')
    metar_auto_flag = models.CharField(max_length=10, blank=True, null=True, verbose_name='自动报标签')
    metar_wind_direction = models.CharField(max_length=10, blank=True, null=True, verbose_name='风向')
    metar_wind_speed_original = models.CharField(max_length=20, blank=True, null=True, verbose_name='原始报文的风速')
    metar_wind_speed_val = models.FloatField(blank=True, null=True, verbose_name='平均风速值')
    metar_gust_val = models.FloatField(blank=True, null=True, verbose_name='阵风值')
    metar_wind_warning = models.CharField(max_length=1, blank=True, null=True, 
                                         choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                         verbose_name='风速告警')
    metar_visibility_original = models.CharField(max_length=20, blank=True, null=True, verbose_name='原始报文能见度')
    metar_visibility_val = models.IntegerField(blank=True, null=True, verbose_name='能见度值')
    metar_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='能见度告警级别')
    metar_weather = models.CharField(max_length=50, blank=True, null=True, verbose_name='天气现象')
    metar_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='天气现象告警级别')
    metar_weather_pre = models.CharField(max_length=50, blank=True, null=True, verbose_name='近时天气')
    metar_cloud = models.CharField(max_length=50, blank=True, null=True, verbose_name='云组')
    metar_min_cloud_height = models.IntegerField(blank=True, null=True, verbose_name='最低云层高度')
    metar_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                          choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                          verbose_name='云组告警级别')
    metar_temperature = models.CharField(max_length=10, blank=True, null=True, verbose_name='温度')
    metar_temp_val = models.FloatField(blank=True, null=True, verbose_name='温度值')
    metar_temperature_warning = models.CharField(max_length=1, blank=True, null=True,
                                                choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                verbose_name='温度告警级别')
    metar_dew_point = models.CharField(max_length=10, blank=True, null=True, verbose_name='露点温度')
    metar_ws_dsc = models.CharField(max_length=50, blank=True, null=True, verbose_name='风切变')
    metar_change_trend = models.CharField(max_length=100, blank=True, null=True, verbose_name='变化组')
    metar_change_trend_warning = models.CharField(max_length=1, blank=True, null=True,
                                                choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                verbose_name='变化组告警级别')
    metar_rvr_dsc = models.CharField(max_length=50, blank=True, null=True, verbose_name='跑道视程')
    metar_rvr_warning = models.CharField(max_length=1, blank=True, null=True,
                                        choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                        verbose_name='跑道视程告警')
    metar_ws_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='风切变告警')
    metar_content = models.TextField(blank=True, null=True, verbose_name='metar原文')
    metar_observation_time = models.BigIntegerField(blank=True, null=True, verbose_name='发布时间')
    metar_elements = models.JSONField(blank=True, null=True, verbose_name='METAR最小单元要素')
    metar_ice_flag = models.CharField(max_length=10, blank=True, null=True, verbose_name='积冰条件标签')
    metar_warning = models.CharField(max_length=1, blank=True, null=True, default='N',
                                   choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                   verbose_name='实况综合告警级别')
    
    # 上一份METAR的SQC标识
    last_metar_sqc = models.BigIntegerField(blank=True, null=True, verbose_name='上一份METAR的SQC标识')
    
    # 系统字段
    created_at = models.BigIntegerField(verbose_name='创建时间戳')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    # 弹窗相关字段
    user_code = models.CharField(max_length=12, blank=True, null=True, verbose_name='用户代码')
    operation_popup = models.CharField(max_length=1, blank=True, null=True, verbose_name='运行类弹窗标记')
    parking_popup = models.CharField(max_length=1, blank=True, null=True, verbose_name='停场类弹窗标记')
    popup_time = models.BigIntegerField(blank=True, null=True, verbose_name='弹窗时间')
    popup_handle_records = models.JSONField(blank=True, null=True, default=dict, verbose_name='弹窗处理记录')
    metar_weather_type = models.TextField(blank=True, null=True, verbose_name='天气类型字典')
    data_status = models.CharField(
        max_length=1, blank=True, null=True,
        choices=[('N', '当前'), ('H', '历史'), ('C', '系统创建')],
        verbose_name='数据状态'
    )
    rvr_min_org = models.IntegerField(blank=True, null=True, verbose_name='RVR最小值原始')
    rvr_min_val = models.IntegerField(blank=True, null=True, verbose_name='RVR最小值')
    operation_metar_popup_leeway = models.IntegerField(blank=True, null=True, verbose_name='运行区METAR弹窗余量')
    operation_metar_popup_level = models.CharField(max_length=1, blank=True, null=True, verbose_name='运行区METAR弹窗级别')
    parking_metar_popup_level = models.CharField(max_length=1, blank=True, null=True, verbose_name='停场METAR弹窗级别')

    # 入库告警字段
    import_alert = models.CharField(max_length=1, blank=True, null=True, verbose_name='入库告警标记')
    import_alert_time = models.BigIntegerField(blank=True, null=True, verbose_name='入库告警时间戳')
    handle_status = models.CharField(max_length=100, blank=True, null=True, verbose_name='告警处理状态')
    import_alert_handle_time = models.BigIntegerField(blank=True, null=True, verbose_name='告警处理时间戳')

    class Meta:
        db_table = 'metar'
        verbose_name = 'METAR数据'
        verbose_name_plural = 'METAR数据'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['airport_4code', '-created_at']),
            models.Index(fields=['metar_observation_time']),
            models.Index(fields=['metar_content']),
        ]
        
    def __str__(self):
        return f"METAR {self.airport_4code} - {self.metar_observation_time}"


class Taf(models.Model):
    """TAF数据表 - 根据项目规划.md 3.3节要求"""
    
    # 机场标识
    airport_4code = models.CharField(max_length=4, verbose_name='机场四字代码')
    
    # SQC字段用于去重
    sqc = models.CharField(max_length=50, verbose_name='SQC标识', db_index=True)
    
    # TAF报文解析结果 - 按照项目规划.md 3.3节严格定义
    whole_validity_period = models.CharField(max_length=20, blank=True, null=True, verbose_name='整体预报有效期')
    taf_observation_time = models.BigIntegerField(blank=True, null=True, verbose_name='发布时间')
    taf_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='taf报文类型')
    taf_content = models.TextField(blank=True, null=True, verbose_name='taf原文')
    taf_elements = models.JSONField(blank=True, null=True, verbose_name='TAF最小单元要素')
    
    # 主预报字段
    subject_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='主预报起始时间')
    subject_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='主预报截至时间')
    subject_content = models.TextField(blank=True, null=True, verbose_name='主预报原文')
    subject_warning = models.CharField(max_length=1, blank=True, null=True,
                                      choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                      verbose_name='主预报告警等级')
    
    # 主预报详细字段（按原始程序添加）
    subject_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='主预报风速(m/s)')
    subject_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='主预报阵风(m/s)')
    subject_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                           choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                           verbose_name='主预报风组告警')
    subject_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='主预报能见度(m)')
    subject_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                 choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                 verbose_name='主预报能见度告警')
    subject_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='主预报天气现象1')
    subject_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='主预报天气现象2')
    subject_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='主预报天气现象3')
    subject_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='主预报天气现象4')
    subject_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='主预报天气现象5')
    subject_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                              choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                              verbose_name='主预报天气现象告警')
    subject_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='主预报最低云高')
    subject_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='主预报云组告警')
    
    # 主预报温度字段
    subject_max_temp1 = models.CharField(max_length=10, blank=True, null=True, verbose_name='第1个最高温度')
    subject_max_temp1_time = models.CharField(max_length=10, blank=True, null=True, verbose_name='第1个最高温度所在时间')
    subject_max_temp1_warning = models.CharField(max_length=1, blank=True, null=True,
                                                choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                verbose_name='第1个最高温度告警等级')
    subject_max_temp2 = models.CharField(max_length=10, blank=True, null=True, verbose_name='第2个最高温度')
    subject_max_temp2_time = models.CharField(max_length=10, blank=True, null=True, verbose_name='第2个最高温度所在时间')
    subject_max_temp2_warning = models.CharField(max_length=1, blank=True, null=True,
                                                choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                verbose_name='第2个最高温度告警等级')
    subject_min_temp1 = models.CharField(max_length=10, blank=True, null=True, verbose_name='第1个最低温度')
    subject_min_temp1_time = models.CharField(max_length=10, blank=True, null=True, verbose_name='第1个最低温度所在时间')
    subject_min_temp1_warning = models.CharField(max_length=1, blank=True, null=True,
                                                choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                verbose_name='第1个最低温度告警等级')
    subject_min_temp2 = models.CharField(max_length=10, blank=True, null=True, verbose_name='第2个最低温度')
    subject_min_temp2_time = models.CharField(max_length=10, blank=True, null=True, verbose_name='第2个最低温度所在时间')
    subject_min_temp2_warning = models.CharField(max_length=1, blank=True, null=True,
                                                choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                verbose_name='第2个最低温度告警等级')
    
    # 变化组字段 - change_[i]_* 其中[i]为1-8
    change_1_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组1的类型')
    change_1_content_all = models.TextField(blank=True, null=True, verbose_name='变化组1的原文')
    change_1_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组1的告警等级')
    change_1_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组1的起始时间')
    change_1_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组1的截止时间')
    
    # 变化组1详细字段
    change_1_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组1风速(m/s)')
    change_1_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组1阵风(m/s)')
    change_1_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组1风组告警')
    change_1_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组1能见度(m)')
    change_1_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组1能见度告警')
    change_1_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组1天气现象1')
    change_1_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组1天气现象2')
    change_1_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组1天气现象3')
    change_1_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组1天气现象4')
    change_1_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组1天气现象5')
    change_1_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组1天气现象告警')
    change_1_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组1最低云高')
    change_1_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组1云组告警')
    
    change_2_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组2的类型')
    change_2_content_all = models.TextField(blank=True, null=True, verbose_name='变化组2的原文')
    change_2_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组2的告警等级')
    change_2_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组2的起始时间')
    change_2_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组2的截止时间')
    
    # 变化组2详细字段
    change_2_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组2风速(m/s)')
    change_2_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组2阵风(m/s)')
    change_2_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组2风组告警')
    change_2_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组2能见度(m)')
    change_2_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组2能见度告警')
    change_2_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组2天气现象1')
    change_2_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组2天气现象2')
    change_2_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组2天气现象3')
    change_2_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组2天气现象4')
    change_2_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组2天气现象5')
    change_2_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组2天气现象告警')
    change_2_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组2最低云高')
    change_2_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组2云组告警')
    
    change_3_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组3的类型')
    change_3_content_all = models.TextField(blank=True, null=True, verbose_name='变化组3的原文')
    change_3_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组3的告警等级')
    change_3_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组3的起始时间')
    change_3_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组3的截止时间')
    
    # 变化组3详细字段
    change_3_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组3风速(m/s)')
    change_3_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组3阵风(m/s)')
    change_3_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组3风组告警')
    change_3_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组3能见度(m)')
    change_3_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组3能见度告警')
    change_3_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组3天气现象1')
    change_3_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组3天气现象2')
    change_3_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组3天气现象3')
    change_3_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组3天气现象4')
    change_3_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组3天气现象5')
    change_3_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组3天气现象告警')
    change_3_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组3最低云高')
    change_3_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组3云组告警')
    
    change_4_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组4的类型')
    change_4_content_all = models.TextField(blank=True, null=True, verbose_name='变化组4的原文')
    change_4_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组4的告警等级')
    change_4_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组4的起始时间')
    change_4_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组4的截止时间')
    
    # 变化组4详细字段
    change_4_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组4风速(m/s)')
    change_4_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组4阵风(m/s)')
    change_4_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组4风组告警')
    change_4_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组4能见度(m)')
    change_4_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组4能见度告警')
    change_4_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组4天气现象1')
    change_4_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组4天气现象2')
    change_4_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组4天气现象3')
    change_4_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组4天气现象4')
    change_4_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组4天气现象5')
    change_4_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组4天气现象告警')
    change_4_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组4最低云高')
    change_4_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组4云组告警')
    
    change_5_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组5的类型')
    change_5_content_all = models.TextField(blank=True, null=True, verbose_name='变化组5的原文')
    change_5_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组5的告警等级')
    change_5_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组5的起始时间')
    change_5_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组5的截止时间')
    
    # 变化组5详细字段
    change_5_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组5风速(m/s)')
    change_5_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组5阵风(m/s)')
    change_5_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组5风组告警')
    change_5_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组5能见度(m)')
    change_5_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组5能见度告警')
    change_5_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组5天气现象1')
    change_5_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组5天气现象2')
    change_5_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组5天气现象3')
    change_5_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组5天气现象4')
    change_5_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组5天气现象5')
    change_5_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组5天气现象告警')
    change_5_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组5最低云高')
    change_5_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组5云组告警')
    
    change_6_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组6的类型')
    change_6_content_all = models.TextField(blank=True, null=True, verbose_name='变化组6的原文')
    change_6_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组6的告警等级')
    change_6_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组6的起始时间')
    change_6_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组6的截止时间')
    
    # 变化组6详细字段
    change_6_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组6风速(m/s)')
    change_6_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组6阵风(m/s)')
    change_6_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组6风组告警')
    change_6_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组6能见度(m)')
    change_6_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组6能见度告警')
    change_6_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组6天气现象1')
    change_6_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组6天气现象2')
    change_6_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组6天气现象3')
    change_6_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组6天气现象4')
    change_6_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组6天气现象5')
    change_6_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组6天气现象告警')
    change_6_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组6最低云高')
    change_6_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组6云组告警')
    
    change_7_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组7的类型')
    change_7_content_all = models.TextField(blank=True, null=True, verbose_name='变化组7的原文')
    change_7_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组7的告警等级')
    change_7_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组7的起始时间')
    change_7_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组7的截止时间')
    
    # 变化组7详细字段
    change_7_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组7风速(m/s)')
    change_7_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组7阵风(m/s)')
    change_7_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组7风组告警')
    change_7_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组7能见度(m)')
    change_7_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组7能见度告警')
    change_7_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组7天气现象1')
    change_7_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组7天气现象2')
    change_7_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组7天气现象3')
    change_7_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组7天气现象4')
    change_7_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组7天气现象5')
    change_7_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组7天气现象告警')
    change_7_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组7最低云高')
    change_7_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组7云组告警')
    
    change_8_type = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组8的类型')
    change_8_content_all = models.TextField(blank=True, null=True, verbose_name='变化组8的原文')
    change_8_warning = models.CharField(max_length=1, blank=True, null=True,
                                       choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                       verbose_name='变化组8的告警等级')
    change_8_validity_period_start = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组8的起始时间')
    change_8_validity_period_end = models.CharField(max_length=10, blank=True, null=True, verbose_name='变化组8的截止时间')
    
    # 变化组8详细字段
    change_8_wind_speed_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组8风速(m/s)')
    change_8_gust_mps = models.IntegerField(blank=True, null=True, verbose_name='变化组8阵风(m/s)')
    change_8_wind_warning = models.CharField(max_length=1, blank=True, null=True,
                                            choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                            verbose_name='变化组8风组告警')
    change_8_visibility_m = models.IntegerField(blank=True, null=True, verbose_name='变化组8能见度(m)')
    change_8_visibility_warning = models.CharField(max_length=1, blank=True, null=True,
                                                  choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                                  verbose_name='变化组8能见度告警')
    change_8_weather1 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组8天气现象1')
    change_8_weather2 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组8天气现象2')
    change_8_weather3 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组8天气现象3')
    change_8_weather4 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组8天气现象4')
    change_8_weather5 = models.CharField(max_length=20, blank=True, null=True, verbose_name='变化组8天气现象5')
    change_8_weather_warning = models.CharField(max_length=1, blank=True, null=True,
                                               choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                               verbose_name='变化组8天气现象告警')
    change_8_cloud_min = models.IntegerField(blank=True, null=True, verbose_name='变化组8最低云高')
    change_8_cloud_warning = models.CharField(max_length=1, blank=True, null=True,
                                             choices=[('R', '红色'), ('Y', '黄色'), ('G', '绿色'), ('N', '无告警')],
                                             verbose_name='变化组8云组告警')
    
    # 修正/更正标识
    amd_or_cor = models.CharField(max_length=3, blank=True, null=True, verbose_name='修正或更正标识')
    
    # 其他字段
    error_report = models.TextField(blank=True, null=True, verbose_name='错误报告')
    abnormal_label = models.CharField(max_length=20, blank=True, null=True, verbose_name='异常标签')

    # 数据状态与入库告警字段
    data_status = models.CharField(max_length=1, blank=True, null=True, verbose_name='数据状态')
    import_alert = models.CharField(max_length=1, blank=True, null=True, verbose_name='入库告警标记')
    import_alert_time = models.BigIntegerField(blank=True, null=True, verbose_name='入库告警时间戳')
    handle_status = models.CharField(max_length=100, blank=True, null=True, verbose_name='告警处理状态')
    import_alert_handle_time = models.BigIntegerField(blank=True, null=True, verbose_name='告警处理时间戳')

    # 系统字段
    created_at = models.BigIntegerField(verbose_name='创建时间戳（毫秒）')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'taf'
        verbose_name = 'TAF数据'
        verbose_name_plural = 'TAF数据'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['airport_4code', '-created_at']),
            models.Index(fields=['taf_observation_time']),
            models.Index(fields=['taf_content']),
            models.Index(fields=['whole_validity_period']),
        ]
        
    def __str__(self):
        return f"TAF {self.airport_4code} - {self.taf_observation_time}"


class UserAirportAlert(models.Model):
    """每个用户、每个机场、实况或预报只留最新一条告警结果。"""

    user_code = models.CharField(max_length=12, verbose_name='用户代码')
    airport_4code = models.CharField(max_length=4, verbose_name='机场四字代码')
    kind = models.CharField(max_length=8, verbose_name='metar或taf')
    source_key = models.CharField(max_length=50, verbose_name='来源报文标识')
    warnings = models.JSONField(default=dict, verbose_name='告警字段')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'user_airport_alert'
        verbose_name = '用户机场告警'
        unique_together = [['user_code', 'airport_4code', 'kind']]

    def __str__(self):
        return f'{self.user_code} {self.airport_4code} {self.kind}'


