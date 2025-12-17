"""
PBS 2.0 Core Module
===================

핵심 비즈니스 로직 및 데이터 처리 모듈
- 시리얼 통신 관리
- 데이터 처리 엔진
- 캘리브레이션 시스템
"""

__version__ = "2.0.0"
__author__ = "PBS Team"

# 핵심 컴포넌트 임포트
from .serial_manager import SerialManager
from .data_processor import DataProcessor
from .calibration import CalibrationEngine

__all__ = [
    'SerialManager',
    'DataProcessor', 
    'CalibrationEngine'
]