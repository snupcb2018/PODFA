"""
PBS 2.0 UI Module
==================

사용자 인터페이스 컴포넌트들
- 메인 윈도우
- 차트 위젯
- 워크벤치
- 다이얼로그들
"""

from .main_window import MainWindow, WorkbenchWidget
from .chart_widget import ChartWidget
# from .workbench import WorkbenchWidget  # WorkbenchWidget은 main_window에서 정의됨
# from .dialogs import CalibrationDialog, SaveOptionsDialog  # TODO: 구현 예정

__all__ = [
    'MainWindow',
    'ChartWidget',
    'WorkbenchWidget', 
    # 'CalibrationDialog',  # TODO: 구현 예정
    # 'SaveOptionsDialog'  # TODO: 구현 예정
]