"""
运行解析器的Django管理命令
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from parsers.parsing_manager import ParsingManager


class Command(BaseCommand):
    help = '运行数据解析器'

    def add_arguments(self, parser):
        parser.add_argument(
            '--parser',
            type=str,
            choices=['all', 'flight', 'metar', 'taf'],
            default='all',
            help='指定运行的解析器类型',
        )
        parser.add_argument(
            '--time-mode',
            type=str,
            choices=['current', 'test'],
            default='current',
            help='时间模式：current（当前时间）或 test（测试时间）',
        )

    def handle(self, *args, **options):
        parser_type = options['parser']
        time_mode = options['time_mode']
        
        self.stdout.write(f'开始运行解析器，类型: {parser_type}，时间模式: {time_mode}')
        
        # 创建解析管理器
        manager = ParsingManager(time_mode=time_mode, token=None, user_code='system')
        
        try:
            if parser_type == 'all':
                # 运行所有解析器
                results = manager.run_all_parsers()
                self._display_all_results(results)
            else:
                # 运行单个解析器
                result = manager.run_single_parser(parser_type)
                self._display_single_result(parser_type, result)
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'解析器运行失败: {str(e)}')
            )
    
    def _display_all_results(self, results):
        """显示所有解析器的结果"""
        total_time = results.get('total_execution_time', 0)
        total_records = results.get('total_records', 0)
        
        self.stdout.write(
            self.style.SUCCESS(f'所有解析器运行完成！')
        )
        self.stdout.write(f'总耗时: {total_time:.2f} 秒')
        self.stdout.write(f'总处理记录数: {total_records}')
        
        # 显示各个解析器的结果
        for parser_name, result in results.get('parsers', {}).items():
            status = '成功' if result.get('success', False) else '失败'
            record_count = result.get('record_count', 0)
            error_count = result.get('error_count', 0)
            execution_time = result.get('execution_time', 0)
            
            self.stdout.write(f'\n{parser_name.upper()}解析器:')
            self.stdout.write(f'  状态: {status}')
            self.stdout.write(f'  处理记录数: {record_count}')
            if error_count > 0:
                self.stdout.write(f'  错误记录数: {error_count}')
            self.stdout.write(f'  执行时间: {execution_time:.2f} 秒')
            
            if not result.get('success', False):
                self.stdout.write(
                    self.style.WARNING(f'  错误信息: {result.get("message", "")}')
                )
    
    def _display_single_result(self, parser_type, result):
        """显示单个解析器的结果"""
        if result.get('success', False):
            self.stdout.write(
                self.style.SUCCESS(f'{parser_type.upper()}解析器运行成功！')
            )
            self.stdout.write(f'处理记录数: {result.get("record_count", 0)}')
            if result.get('error_count', 0) > 0:
                self.stdout.write(f'错误记录数: {result.get("error_count", 0)}')
            self.stdout.write(f'执行时间: {result.get("execution_time", 0):.2f} 秒')
        else:
            self.stdout.write(
                self.style.ERROR(f'{parser_type.upper()}解析器运行失败！')
            )
            self.stdout.write(f'错误信息: {result.get("message", "")}') 