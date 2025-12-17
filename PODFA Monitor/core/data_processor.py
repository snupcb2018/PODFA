"""
PBS 2.0 Data Processing Engine
===============================

실시간 데이터 처리 및 분석 엔진
- 고성능 데이터 스트리밍
- 통계 분석 및 필터링
- 메모리 효율적 관리
- 캘리브레이션 적용
"""

import time
import logging
import numpy as np
import polars as pl
from collections import deque
from typing import Optional, List, Tuple, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
from queue import Queue, Empty

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

try:
    from scipy import signal
except ImportError:
    signal = None

# 캘리브레이션 임포트 (옵션)
try:
    from core.calibration import CalibrationResult
except ImportError:
    CalibrationResult = None


class FilterType(Enum):
    """필터 타입 열거형"""
    NONE = "none"
    MOVING_AVERAGE = "moving_average"  
    MEDIAN = "median"
    KALMAN = "kalman"
    BUTTERWORTH = "butterworth"


@dataclass
class DataPoint:
    """데이터 포인트"""
    timestamp: float
    raw_value: float
    filtered_value: Optional[float] = None
    calibrated_value: Optional[float] = None
    quality_score: float = 1.0  # 0.0 ~ 1.0
    
    @property
    def value(self) -> float:
        """최종 값 반환 (캘리브레이션 > 필터링 > 원시값 순서)"""
        if self.calibrated_value is not None:
            return self.calibrated_value
        elif self.filtered_value is not None:
            return self.filtered_value
        else:
            return self.raw_value


@dataclass
class StatisticsSnapshot:
    """통계 스냅샷"""
    count: int = 0
    mean: float = 0.0
    std: float = 0.0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    median: float = 0.0
    percentile_25: float = 0.0
    percentile_75: float = 0.0
    trend: str = "stable"  # "increasing", "decreasing", "stable"
    
    def __post_init__(self):
        """후처리"""
        if self.count == 0:
            self.min_value = 0.0
            self.max_value = 0.0


@dataclass 
class ProcessingConfig:
    """데이터 처리 설정"""
    max_buffer_size: int = 50000  # 최대 버퍼 크기
    filter_type: FilterType = FilterType.MOVING_AVERAGE
    filter_window: int = 5  # 필터 윈도우 크기
    outlier_threshold: float = 3.0  # 이상치 임계값 (표준편차 배수)
    enable_auto_scaling: bool = True  # 자동 스케일링
    statistics_window: int = 1000  # 통계 계산 윈도우
    quality_threshold: float = 0.5  # 품질 임계값
    # Butterworth 필터 설정
    butterworth_cutoff: float = 1.0  # cutoff 주파수 (Hz)
    butterworth_order: int = 2  # 필터 차수 (1차, 2차, 3차 등)
    sampling_rate: float = 10.0  # 샘플링 레이트 (Hz) - 일반적으로 10Hz


class CircularBuffer:
    """메모리 효율적인 순환 버퍼"""
    
    def __init__(self, max_size: int):
        self.max_size = max_size
        self._buffer = deque(maxlen=max_size)
        self._lock = threading.Lock()
    
    def append(self, item: DataPoint):
        """항목 추가"""
        with self._lock:
            self._buffer.append(item)
    
    def get_latest(self, count: int) -> List[DataPoint]:
        """최신 N개 항목 반환"""
        with self._lock:
            if count >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-count:]
    
    def get_range(self, start_idx: int, end_idx: int) -> List[DataPoint]:
        """범위 데이터 반환"""
        with self._lock:
            buffer_list = list(self._buffer)
            return buffer_list[start_idx:end_idx]
    
    def get_all(self) -> List[DataPoint]:
        """모든 데이터 반환"""
        with self._lock:
            return list(self._buffer)
    
    def clear(self):
        """버퍼 초기화"""
        with self._lock:
            self._buffer.clear()
    
    def __len__(self) -> int:
        """버퍼 크기"""
        return len(self._buffer)


class MovingAverageFilter:
    """이동 평균 필터"""
    
    def __init__(self, window_size: int):
        self.window_size = window_size
        self.values = deque(maxlen=window_size)
    
    def filter(self, value: float) -> float:
        """필터 적용"""
        self.values.append(value)
        return sum(self.values) / len(self.values)
    
    def reset(self):
        """필터 초기화"""
        self.values.clear()


class MedianFilter:
    """중앙값 필터"""
    
    def __init__(self, window_size: int):
        self.window_size = window_size
        self.values = deque(maxlen=window_size)
    
    def filter(self, value: float) -> float:
        """필터 적용"""
        self.values.append(value)
        return float(np.median(self.values))
    
    def reset(self):
        """필터 초기화"""
        self.values.clear()


class ButterworthFilter:
    """Butterworth Low-Pass 필터"""
    
    def __init__(self, cutoff_freq: float, sampling_rate: float, order: int = 2):
        """
        Butterworth Low-Pass 필터 초기화
        
        Args:
            cutoff_freq: cutoff 주파수 (Hz)
            sampling_rate: 샘플링 레이트 (Hz)
            order: 필터 차수 (기본값: 2)
        """
        self.cutoff_freq = cutoff_freq
        self.sampling_rate = sampling_rate
        self.order = order
        
        # scipy가 없으면 간단한 RC 필터로 대체
        if signal is None:
            # RC 필터의 시간 상수 계산
            self.alpha = self._calculate_alpha(cutoff_freq, sampling_rate)
            self.filtered_value = None
            self.use_scipy = False
            self.logger = logging.getLogger(__name__)
            self.logger.warning("scipy 패키지가 없어 간단한 RC 필터를 사용합니다. scipy 설치를 권장합니다.")
        else:
            # Butterworth 필터 계수 계산
            self.use_scipy = True
            nyquist = sampling_rate * 0.5
            normalized_cutoff = cutoff_freq / nyquist
            
            # cutoff 주파수가 nyquist 주파수보다 클 경우 보정
            if normalized_cutoff >= 1.0:
                normalized_cutoff = 0.99
                self.logger = logging.getLogger(__name__)
                self.logger.warning(f"cutoff 주파수가 너무 높습니다. {nyquist * 0.99:.2f}Hz로 조정됩니다.")
            
            self.b, self.a = signal.butter(order, normalized_cutoff, btype='low')
            self.z = signal.lfilter_zi(self.b, self.a)
            self.initialized = False
    
    def _calculate_alpha(self, cutoff_freq: float, sampling_rate: float) -> float:
        """RC 필터의 alpha 값 계산"""
        dt = 1.0 / sampling_rate
        tau = 1.0 / (2 * np.pi * cutoff_freq)
        return dt / (tau + dt)
    
    def filter(self, value: float) -> float:
        """필터 적용"""
        if self.use_scipy:
            # scipy의 Butterworth 필터 사용
            if not self.initialized:
                # 첫 번째 값으로 초기 조건 설정
                self.z = self.z * value
                self.initialized = True
            
            # 필터 적용
            filtered_value, self.z = signal.lfilter(
                self.b, self.a, [value], zi=self.z
            )
            return float(filtered_value[0])
        else:
            # 간단한 RC 필터 사용 (1차 low-pass)
            if self.filtered_value is None:
                self.filtered_value = value
            else:
                self.filtered_value = (
                    self.alpha * value + 
                    (1.0 - self.alpha) * self.filtered_value
                )
            return self.filtered_value
    
    def update_parameters(self, cutoff_freq: float, sampling_rate: float, order: int = None):
        """필터 파라미터 업데이트"""
        self.cutoff_freq = cutoff_freq
        self.sampling_rate = sampling_rate
        if order is not None:
            self.order = order
        
        if self.use_scipy:
            # 새로운 계수 계산
            nyquist = sampling_rate * 0.5
            normalized_cutoff = cutoff_freq / nyquist
            
            if normalized_cutoff >= 1.0:
                normalized_cutoff = 0.99
            
            self.b, self.a = signal.butter(self.order, normalized_cutoff, btype='low')
            self.z = signal.lfilter_zi(self.b, self.a)
            self.initialized = False
        else:
            # RC 필터 alpha 재계산
            self.alpha = self._calculate_alpha(cutoff_freq, sampling_rate)
            self.filtered_value = None
    
    def reset(self):
        """필터 상태 초기화"""
        if self.use_scipy:
            # scipy 필터 초기화
            self.z = signal.lfilter_zi(self.b, self.a)
            self.initialized = False
        else:
            # RC 필터 초기화
            self.filtered_value = None


class DataProcessor(QObject):
    """
    📊 고성능 데이터 처리 엔진
    
    Features:
    - 실시간 데이터 스트리밍
    - 다양한 필터링 옵션
    - 통계 분석
    - 메모리 효율적 관리
    - 캘리브레이션 적용
    """
    
    # 시그널 정의
    data_processed = pyqtSignal(DataPoint)  # 처리된 데이터
    statistics_updated = pyqtSignal(StatisticsSnapshot)  # 통계 업데이트
    outlier_detected = pyqtSignal(DataPoint)  # 이상치 감지
    buffer_overflow = pyqtSignal()  # 버퍼 오버플로우
    processing_error = pyqtSignal(str)  # 처리 오류
    calibration_status_changed = pyqtSignal(bool)  # 캘리브레이션 상태 변경 (True = gram 단위, False = voltage 단위)
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        super().__init__()
        
        # 설정
        self.config = config or ProcessingConfig()
        
        # 데이터 저장소
        self.buffer = CircularBuffer(self.config.max_buffer_size)
        self.calibration_result: Optional[CalibrationResult] = None
        self.calibration_mode = False  # 캘리브레이션 모드 플래그
        
        # 필터 초기화
        self._init_filter()
        
        # 통계 및 상태
        self._statistics = StatisticsSnapshot()
        self._last_statistics_update = time.time()
        
        # 타이머
        self._statistics_timer = QTimer()
        self._statistics_timer.timeout.connect(self._update_statistics)
        self._statistics_timer.start(1000)  # 1초마다 통계 업데이트
        
        # 로깅
        self.logger = logging.getLogger(__name__)
    
    def _init_filter(self):
        """필터 초기화"""
        if self.config.filter_type == FilterType.MOVING_AVERAGE:
            self._filter = MovingAverageFilter(self.config.filter_window)
        elif self.config.filter_type == FilterType.MEDIAN:
            self._filter = MedianFilter(self.config.filter_window)
        elif self.config.filter_type == FilterType.BUTTERWORTH:
            self._filter = ButterworthFilter(
                cutoff_freq=self.config.butterworth_cutoff,
                sampling_rate=self.config.sampling_rate,
                order=self.config.butterworth_order
            )
        else:
            self._filter = None
    
    def process_raw_data(self, raw_value_str: str) -> Optional[DataPoint]:
        """
        원시 데이터 처리
        
        Args:
            raw_value_str: 원시 데이터 문자열
            
        Returns:
            처리된 데이터 포인트
        """
        try:
            # 문자열을 숫자로 변환
            raw_value = float(raw_value_str.strip())
            
            # 데이터 포인트 생성
            data_point = DataPoint(
                timestamp=time.time(),
                raw_value=raw_value
            )
            
            # 품질 점수 계산
            data_point.quality_score = self._calculate_quality_score(raw_value)
            
            # 필터링 적용
            if self._filter and data_point.quality_score >= self.config.quality_threshold:
                data_point.filtered_value = self._filter.filter(raw_value)
            else:
                data_point.filtered_value = raw_value
            
            # 캘리브레이션 적용
            if self.calibration_result:
                data_point.calibrated_value = self.calibration_result.apply(
                    data_point.filtered_value
                )
            else:
                data_point.calibrated_value = data_point.filtered_value
            
            # 이상치 검사
            if self._is_outlier(data_point):
                self.outlier_detected.emit(data_point)
            
            # 버퍼에 저장
            self.buffer.append(data_point)
            
            # 처리 완료 시그널
            self.data_processed.emit(data_point)
            
            return data_point
            
        except ValueError as e:
            self.logger.error(f"데이터 변환 오류: {raw_value_str} - {e}")
            self.processing_error.emit(f"데이터 변환 실패: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"데이터 처리 오류: {e}")
            self.processing_error.emit(f"처리 오류: {str(e)}")
            return None
    
    def get_all_data(self) -> List[DataPoint]:
        """모든 데이터 반환"""
        return self.buffer.get_all()
    
    def get_statistics(self) -> StatisticsSnapshot:
        """현재 통계 반환"""
        return self._statistics
    
    def clear_buffer(self):
        """버퍼 초기화"""
        self.buffer.clear()
        if self._filter:
            self._filter.reset()
        self.logger.info("데이터 버퍼 초기화됨")
    
    def _calculate_quality_score(self, value: float) -> float:
        """
        데이터 품질 점수 계산
        
        Args:
            value: 측정값
            
        Returns:
            품질 점수 (0.0 ~ 1.0)
        """
        # 기본 품질 점수
        quality = 1.0
        
        # 범위 체크 (센서 특성에 따라 조정 필요)
        if value < 0 or value > 10000:
            quality *= 0.5
        
        # 급격한 변화 체크
        recent_data = self.buffer.get_latest(5)
        if len(recent_data) >= 3:
            recent_values = [dp.raw_value for dp in recent_data[-3:]]
            mean_recent = np.mean(recent_values)
            
            if abs(value - mean_recent) > 3 * np.std(recent_values):
                quality *= 0.7
        
        return max(0.0, min(1.0, quality))
    
    def _is_outlier(self, data_point: DataPoint) -> bool:
        """
        이상치 검사
        
        Args:
            data_point: 데이터 포인트
            
        Returns:
            이상치 여부
        """
        # 캘리브레이션 모드에서는 이상치 감지 비활성화
        if self.calibration_mode:
            return False
            
        if len(self.buffer) < 10:  # 충분한 데이터가 없으면 이상치로 판단하지 않음
            return False
        
        recent_data = self.buffer.get_latest(self.config.statistics_window)
        values = [dp.filtered_value or dp.raw_value for dp in recent_data]
        
        mean_val = np.mean(values)
        std_val = np.std(values)
        
        if std_val == 0:
            return False
        
        z_score = abs((data_point.filtered_value - mean_val) / std_val)
        return z_score > self.config.outlier_threshold
    
    def _update_statistics(self):
        """통계 업데이트"""
        data = self.buffer.get_latest(self.config.statistics_window)
        
        if not data:
            return
        
        # 값 추출 (캘리브레이션된 값 우선)
        values = []
        for dp in data:
            if dp.calibrated_value is not None:
                values.append(dp.calibrated_value)
            elif dp.filtered_value is not None:
                values.append(dp.filtered_value)
            else:
                values.append(dp.raw_value)
        
        # 통계 계산
        try:
            self._statistics = StatisticsSnapshot(
                count=len(values),
                mean=float(np.mean(values)),
                std=float(np.std(values)),
                min_value=float(np.min(values)),
                max_value=float(np.max(values)),
                median=float(np.median(values)),
                percentile_25=float(np.percentile(values, 25)),
                percentile_75=float(np.percentile(values, 75))
            )
            
            # 트렌드 계산
            if len(values) >= 10:
                first_half = values[:len(values)//2]
                second_half = values[len(values)//2:]
                
                mean_first = np.mean(first_half)
                mean_second = np.mean(second_half)
                
                diff_ratio = (mean_second - mean_first) / mean_first if mean_first != 0 else 0
                
                if diff_ratio > 0.05:
                    self._statistics.trend = "increasing"
                elif diff_ratio < -0.05:
                    self._statistics.trend = "decreasing"
                else:
                    self._statistics.trend = "stable"
            
            # 시그널 발송
            self.statistics_updated.emit(self._statistics)
            
        except Exception as e:
            self.logger.error(f"통계 계산 오류: {e}")
    
    def update_config(self, new_config: ProcessingConfig):
        """
        설정 업데이트
        
        Args:
            new_config: 새로운 설정
        """
        self.config = new_config
        self._init_filter()  # 필터 재초기화
        self.logger.info("데이터 처리 설정 업데이트됨")
    
    def update_butterworth_filter(self, cutoff_freq: float = None, 
                                 sampling_rate: float = None, 
                                 order: int = None):
        """
        Butterworth 필터 파라미터를 실시간으로 업데이트
        
        Args:
            cutoff_freq: cutoff 주파수 (Hz)
            sampling_rate: 샘플링 레이트 (Hz) 
            order: 필터 차수
        """
        if self.config.filter_type != FilterType.BUTTERWORTH:
            self.logger.warning("현재 필터가 Butterworth가 아닙니다.")
            return
            
        # 설정 업데이트
        if cutoff_freq is not None:
            self.config.butterworth_cutoff = cutoff_freq
        if sampling_rate is not None:
            self.config.sampling_rate = sampling_rate
        if order is not None:
            self.config.butterworth_order = order
            
        # 필터가 ButterworthFilter이고 업데이트 메서드가 있으면 실시간 업데이트
        if (hasattr(self, '_filter') and 
            isinstance(self._filter, ButterworthFilter)):
            self._filter.update_parameters(
                cutoff_freq=self.config.butterworth_cutoff,
                sampling_rate=self.config.sampling_rate,
                order=self.config.butterworth_order
            )
            self.logger.info(
                f"Butterworth 필터 파라미터 업데이트: "
                f"cutoff={self.config.butterworth_cutoff}Hz, "
                f"sampling_rate={self.config.sampling_rate}Hz, "
                f"order={self.config.butterworth_order}"
            )
        else:
            # 필터 재초기화
            self._init_filter()
            self.logger.info("Butterworth 필터 재초기화됨")
    
    def set_calibration(self, calibration_result):
        """
        캘리브레이션 결과 설정
        
        Args:
            calibration_result: CalibrationResult 객체 또는 None
        """
        if CalibrationResult is None:
            self.logger.warning("CalibrationResult 클래스를 임포트할 수 없습니다")
            return
        
        if calibration_result is None:
            self.calibration_result = None
            self.logger.info("캘리브레이션 제거됨")
            # 캘리브레이션 해제: voltage 단위로 돌아감
            self.calibration_status_changed.emit(False)
        else:
            if not isinstance(calibration_result, CalibrationResult):
                self.logger.error("올바르지 않은 캘리브레이션 객체")
                return
            
            self.calibration_result = calibration_result
            self.logger.info(
                f"캘리브레이션 적용됨: "
                f"방법={calibration_result.method.value}, "
                f"R²={calibration_result.r_squared:.4f}, "
                f"RMSE={calibration_result.rmse:.4f}"
            )
            # 캘리브레이션 적용: gram 단위로 변경
            self.calibration_status_changed.emit(True)
    
    def get_calibration_info(self) -> Optional[dict]:
        """
        현재 캘리브레이션 정보 반환
        
        Returns:
            캘리브레이션 정보 딕셔너리 또는 None
        """
        if self.calibration_result is None:
            return None
        
        return {
            'method': self.calibration_result.method.value,
            'quality_grade': self.calibration_result.quality_grade,
            'r_squared': self.calibration_result.r_squared,
            'rmse': self.calibration_result.rmse,
            'validation_passed': self.calibration_result.validation_passed,
            'created_time': self.calibration_result.created_time
        }
    
    def is_calibrated(self) -> bool:
        """캘리브레이션 여부 반환"""
        return self.calibration_result is not None
    
    def set_calibration_mode(self, enabled: bool):
        """
        캘리브레이션 모드 설정
        
        Args:
            enabled: 캘리브레이션 모드 활성화 여부
        """
        self.calibration_mode = enabled
        self.logger.info(f"캘리브레이션 모드: {'활성화' if enabled else '비활성화'}")
    
    def cleanup(self):
        """리소스 정리"""
        self._statistics_timer.stop()
        self.calibration_result = None
        self.clear_buffer()
        self.logger.info("데이터 프로세서 정리 완료")