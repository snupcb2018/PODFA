"""
PBS 2.0 Calibration Engine
===========================

고급 캘리브레이션 시스템
- 다양한 캘리브레이션 방법
- 품질 평가 및 검증
- 자동 데이터 수집
- 실시간 모니터링
"""

import time
import logging
import numpy as np
from typing import List, Tuple, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime
from scipy.optimize import curve_fit
from scipy import stats
import threading

from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class CalibrationMethod(Enum):
    """캘리브레이션 방법 열거형"""
    LINEAR = "linear"              # 선형 회귀
    POLYNOMIAL_2 = "polynomial_2"  # 2차 다항식
    POLYNOMIAL_3 = "polynomial_3"  # 3차 다항식
    CUBIC_SPLINE = "cubic_spline"  # 큐빅 스플라인


class CalibrationState(Enum):
    """캘리브레이션 상태"""
    IDLE = "idle"
    COLLECTING = "collecting"      # 데이터 수집 중
    PROCESSING = "processing"      # 계산 중
    COMPLETED = "completed"        # 완료
    ERROR = "error"               # 오류


@dataclass
class CalibrationPoint:
    """캘리브레이션 포인트"""
    reference_weight: float        # 기준 무게 (g)
    sensor_readings: List[float]   # 센서 측정값들
    collection_time: float         # 수집 시간
    quality_score: float = 1.0     # 품질 점수
    
    @property
    def average_reading(self) -> float:
        """평균 센서 값"""
        return np.mean(self.sensor_readings) if self.sensor_readings else 0.0
    
    @property
    def std_reading(self) -> float:
        """표준편차"""
        return np.std(self.sensor_readings) if len(self.sensor_readings) > 1 else 0.0
    
    @property
    def cv_percentage(self) -> float:
        """변동계수 (%)"""
        avg = self.average_reading
        return (self.std_reading / avg * 100) if avg != 0 else 0.0


@dataclass
class CalibrationResult:
    """캘리브레이션 결과"""
    method: CalibrationMethod
    coefficients: Tuple[float, ...]    # 회귀 계수
    r_squared: float                   # 결정계수
    rmse: float                        # 제곱근 평균 제곱 오차
    points: List[CalibrationPoint]     # 캘리브레이션 포인트들
    created_time: float                # 생성 시간
    validation_passed: bool = False    # 검증 통과 여부
    
    @property
    def quality_grade(self) -> str:
        """품질 등급"""
        if self.r_squared >= 0.99:
            return "Excellent"
        elif self.r_squared >= 0.95:
            return "Good" 
        elif self.r_squared >= 0.90:
            return "Fair"
        else:
            return "Poor"
    
    def apply(self, sensor_value: float) -> float:
        """센서 값을 무게로 변환"""
        if self.method == CalibrationMethod.LINEAR:
            slope, intercept = self.coefficients
            return slope * sensor_value + intercept
        elif self.method == CalibrationMethod.POLYNOMIAL_2:
            a, b, c = self.coefficients
            return a * sensor_value**2 + b * sensor_value + c
        elif self.method == CalibrationMethod.POLYNOMIAL_3:
            a, b, c, d = self.coefficients
            return a * sensor_value**3 + b * sensor_value**2 + c * sensor_value + d
        else:
            # 기본적으로 선형 변환
            if len(self.coefficients) >= 2:
                return self.coefficients[0] * sensor_value + self.coefficients[1]
            return sensor_value


@dataclass
class CollectionConfig:
    """데이터 수집 설정"""
    collection_duration: float = 10.0  # 수집 시간 (초) - 무게 안정화를 위해 증가
    min_samples: int = 150             # 최소 샘플 수 - 안정적인 수집을 위해 증가
    max_cv_percentage: float = 5.0     # 최대 변동계수 (%) - 캘리브레이션 모드에서 완화
    outlier_threshold: float = 3.0     # 이상치 임계값 (표준편차 배수) - 완화
    auto_advance: bool = True          # 자동 다음 단계
    stabilization_time: float = 3.0    # 무게 안정화 대기 시간 (초)


class CalibrationEngine(QObject):
    """
    🎯 고급 캘리브레이션 엔진
    
    Features:
    - 다양한 회귀 방법
    - 자동 품질 평가
    - 실시간 데이터 수집
    - 검증 시스템
    """
    
    # 시그널 정의
    state_changed = pyqtSignal(CalibrationState)            # 상태 변경
    point_collected = pyqtSignal(CalibrationPoint)          # 포인트 수집 완료
    progress_updated = pyqtSignal(int, str)                 # 진행률 업데이트
    calibration_completed = pyqtSignal(CalibrationResult)   # 캘리브레이션 완료
    data_point_added = pyqtSignal(float)                    # 데이터 포인트 추가
    error_occurred = pyqtSignal(str)                        # 오류 발생
    
    def __init__(self, config: Optional[CollectionConfig] = None):
        super().__init__()
        
        # 설정
        self.config = config or CollectionConfig()
        
        # 상태 관리
        self.state = CalibrationState.IDLE
        self.current_step = 0
        self.total_steps = 5  # 기본 5단계
        
        # 데이터 저장
        self.calibration_points: List[CalibrationPoint] = []
        self.current_point: Optional[CalibrationPoint] = None
        self.current_readings: List[float] = []
        
        # 수집 관리
        self.collection_start_time: Optional[float] = None
        self.target_weight: Optional[float] = None
        
        # 타이머
        self.collection_timer = QTimer()
        self.collection_timer.timeout.connect(self._check_collection_progress)
        
        # 로깅
        self.logger = logging.getLogger(__name__)
    
    def start_calibration(self, reference_weights: List[float]):
        """
        캘리브레이션 시작
        
        Args:
            reference_weights: 기준 무게 리스트 (g)
        """
        if self.state != CalibrationState.IDLE:
            self.logger.warning("캘리브레이션이 이미 진행 중입니다")
            return False
        
        # 초기화
        self.calibration_points.clear()
        self.current_step = 0
        self.total_steps = len(reference_weights)
        self.reference_weights = reference_weights
        
        # 상태는 IDLE 유지 - 위저드에서 각 단계를 수동으로 시작
        self.logger.info(f"캘리브레이션 시작: {len(reference_weights)}단계")
        
        # 첫 번째 단계 자동 시작하지 않음 - 위저드에서 수동으로 제어
        # self._start_next_point()
        
        return True
    
    def start_point_collection(self, reference_weight: float):
        """
        포인트 수집 시작
        
        Args:
            reference_weight: 기준 무게 (g)
        """
        if self.state == CalibrationState.COLLECTING and self.current_point:
            self.logger.warning("이미 수집 중입니다")
            return False
        
        # 상태를 COLLECTING으로 변경
        self._set_state(CalibrationState.COLLECTING)
        
        # 새 포인트 시작
        self.target_weight = reference_weight
        self.current_readings.clear()
        self.collection_start_time = time.time()
        self.stabilization_start_time = time.time()  # 안정화 시작 시간
        self.is_stabilizing = True  # 안정화 단계 플래그
        
        self.current_point = CalibrationPoint(
            reference_weight=reference_weight,
            sensor_readings=[],
            collection_time=time.time()
        )
        
        # 타이머 시작
        self.collection_timer.start(100)  # 100ms마다 체크
        
        self.logger.info(f"포인트 수집 시작: {reference_weight}g (안정화 대기 중...)")
        self.progress_updated.emit(0, f"안정화 대기 중... {reference_weight}g")
        
        return True
    
    def add_sensor_reading(self, sensor_value: float):
        """
        센서 측정값 추가
        
        Args:
            sensor_value: 센서 값
        """
        if self.state != CalibrationState.COLLECTING or not self.current_point:
            return
        
        # 안정화 단계에서는 데이터만 버퍼링하고 실제 수집은 하지 않음
        if hasattr(self, 'is_stabilizing') and self.is_stabilizing:
            # 안정화 중에도 이상치 검사는 완화해서 수행
            if len(self.current_readings) >= 20:  # 충분한 데이터가 있을 때만
                if self._is_outlier(sensor_value):
                    self.logger.debug(f"안정화 중 이상치 제거: {sensor_value}")
                    return
            
            # 안정화 데이터 추가 (최대 50개만 유지)
            self.current_readings.append(sensor_value)
            if len(self.current_readings) > 50:
                self.current_readings.pop(0)
            
            self.data_point_added.emit(sensor_value)
            return
        
        # 정식 수집 단계에서의 이상치 검사 (완화됨)
        if self._is_outlier(sensor_value):
            self.logger.debug(f"이상치 제거: {sensor_value}")
            return
        
        # 데이터 추가
        self.current_readings.append(sensor_value)
        self.current_point.sensor_readings.append(sensor_value)
        
        # 시그널 발송
        self.data_point_added.emit(sensor_value)
    
    def complete_current_point(self) -> bool:
        """현재 포인트 수집 완료"""
        if not self.current_point or not self.current_readings:
            self.logger.error("수집할 데이터가 없습니다")
            return False
        
        # 품질 평가
        self.current_point.quality_score = self._evaluate_point_quality(
            self.current_point
        )
        
        # 수집 완료
        self.collection_timer.stop()
        self.calibration_points.append(self.current_point)
        
        # 상태를 IDLE로 복구 (위저드에서 다음 단계를 제어)
        self._set_state(CalibrationState.IDLE)
        
        # 시그널 발송
        self.point_collected.emit(self.current_point)
        
        self.logger.info(
            f"포인트 수집 완료: {self.current_point.reference_weight}g, "
            f"품질: {self.current_point.quality_score:.3f}"
        )
        
        # 위저드에서 step 관리하므로 여기서는 step 증가하지 않음
        # self.current_step += 1
        
        # 위저드에서 다음 단계 제어하므로 자동 진행하지 않음
        # if self.current_step < self.total_steps:
        #     if self.config.auto_advance:
        #         self._start_next_point()
        # else:
        #     # 모든 단계 완료
        #     self._process_calibration()
        
        return True
    
    def calculate_calibration(self, method: CalibrationMethod = CalibrationMethod.LINEAR) -> Optional[CalibrationResult]:
        """
        캘리브레이션 계산
        
        Args:
            method: 캘리브레이션 방법
            
        Returns:
            캘리브레이션 결과
        """
        if len(self.calibration_points) < 2:
            self.logger.error("최소 2개의 포인트가 필요합니다")
            return None
        
        self._set_state(CalibrationState.PROCESSING)
        
        try:
            # 데이터 준비
            x_data = np.array([point.average_reading for point in self.calibration_points])
            y_data = np.array([point.reference_weight for point in self.calibration_points])
            
            # 회귀 분석
            if method == CalibrationMethod.LINEAR:
                coeffs, r_squared, rmse = self._linear_regression(x_data, y_data)
            elif method == CalibrationMethod.POLYNOMIAL_2:
                coeffs, r_squared, rmse = self._polynomial_regression(x_data, y_data, 2)
            elif method == CalibrationMethod.POLYNOMIAL_3:
                coeffs, r_squared, rmse = self._polynomial_regression(x_data, y_data, 3)
            else:
                coeffs, r_squared, rmse = self._linear_regression(x_data, y_data)
            
            # 결과 생성
            result = CalibrationResult(
                method=method,
                coefficients=coeffs,
                r_squared=r_squared,
                rmse=rmse,
                points=self.calibration_points.copy(),
                created_time=time.time()
            )
            
            # 검증 수행
            result.validation_passed = self._validate_calibration(result)
            
            self._set_state(CalibrationState.COMPLETED)
            self.calibration_completed.emit(result)
            
            self.logger.info(
                f"캘리브레이션 완료 - 방법: {method.value}, "
                f"R²: {r_squared:.6f}, RMSE: {rmse:.6f}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"캘리브레이션 계산 오류: {e}")
            self.error_occurred.emit(f"계산 오류: {str(e)}")
            self._set_state(CalibrationState.ERROR)
            return None
    
    def save_calibration(self, result: CalibrationResult, filename: str):
        """
        캘리브레이션 결과 저장
        
        Args:
            result: 캘리브레이션 결과
            filename: 저장할 파일명
        """
        try:
            data = {
                'method': result.method.value,
                'coefficients': result.coefficients,
                'r_squared': result.r_squared,
                'rmse': result.rmse,
                'created_time': result.created_time,
                'validation_passed': result.validation_passed,
                'points': [
                    {
                        'reference_weight': point.reference_weight,
                        'sensor_readings': point.sensor_readings,
                        'collection_time': point.collection_time,
                        'quality_score': point.quality_score
                    }
                    for point in result.points
                ]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            self.logger.info(f"캘리브레이션 저장 완료: {filename}")
            
        except Exception as e:
            self.logger.error(f"캘리브레이션 저장 실패: {e}")
            self.error_occurred.emit(f"저장 실패: {str(e)}")
    
    def load_calibration(self, filename: str) -> Optional[CalibrationResult]:
        """
        캘리브레이션 결과 로드
        
        Args:
            filename: 파일명
            
        Returns:
            캘리브레이션 결과
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 포인트 복원
            points = []
            for point_data in data['points']:
                point = CalibrationPoint(
                    reference_weight=point_data['reference_weight'],
                    sensor_readings=point_data['sensor_readings'],
                    collection_time=point_data['collection_time'],
                    quality_score=point_data.get('quality_score', 1.0)
                )
                points.append(point)
            
            # 결과 복원
            result = CalibrationResult(
                method=CalibrationMethod(data['method']),
                coefficients=tuple(data['coefficients']),
                r_squared=data['r_squared'],
                rmse=data['rmse'],
                points=points,
                created_time=data['created_time'],
                validation_passed=data.get('validation_passed', False)
            )
            
            self.logger.info(f"캘리브레이션 로드 완료: {filename}")
            return result
            
        except Exception as e:
            self.logger.error(f"캘리브레이션 로드 실패: {e}")
            self.error_occurred.emit(f"로드 실패: {str(e)}")
            return None
    
    def cancel_calibration(self):
        """캘리브레이션 취소"""
        self.collection_timer.stop()
        self.calibration_points.clear()
        self.current_point = None
        self.current_readings.clear()
        self.current_step = 0
        
        self._set_state(CalibrationState.IDLE)
        self.logger.info("캘리브레이션 취소됨")
    
    def _start_next_point(self):
        """다음 포인트 수집 시작"""
        if self.current_step < len(self.reference_weights):
            next_weight = self.reference_weights[self.current_step]
            self.start_point_collection(next_weight)
        
    def _check_collection_progress(self):
        """수집 진행률 체크"""
        if not self.current_point or not self.collection_start_time:
            return
        
        current_time = time.time()
        
        # 안정화 단계 처리
        if hasattr(self, 'is_stabilizing') and self.is_stabilizing:
            stabilization_elapsed = current_time - self.stabilization_start_time
            stabilization_progress = min(int((stabilization_elapsed / self.config.stabilization_time) * 100), 100)
            
            sample_count = len(self.current_readings)
            status = f"안정화 중... {self.target_weight}g ({sample_count} samples, {stabilization_elapsed:.1f}s)"
            self.progress_updated.emit(stabilization_progress, status)
            
            # 안정화 완료 체크
            if stabilization_elapsed >= self.config.stabilization_time:
                self.is_stabilizing = False
                self.collection_start_time = current_time  # 실제 수집 시작 시간 재설정
                self.current_point.sensor_readings.clear()  # 실제 수집 데이터 초기화
                self.logger.info(f"안정화 완료, 실제 수집 시작: {self.target_weight}g")
                self.progress_updated.emit(0, f"수집 시작... {self.target_weight}g")
            return
        
        # 실제 수집 단계
        elapsed = current_time - self.collection_start_time
        progress = min(int((elapsed / self.config.collection_duration) * 100), 100)
        
        # 진행률 업데이트
        sample_count = len(self.current_point.sensor_readings)  # 실제 수집된 데이터만
        total_samples = len(self.current_readings)  # 안정화 포함 전체
        
        status = f"수집 중... {self.target_weight}g ({sample_count}/{self.config.min_samples} samples)"
        self.progress_updated.emit(progress, status)
        
        # 수집 완료 조건 체크
        if (elapsed >= self.config.collection_duration and 
            sample_count >= self.config.min_samples):
            
            # 품질 체크
            if sample_count > 0:  # 데이터가 있을 때만 완료
                self.complete_current_point()
            else:
                # 데이터가 없으면 더 기다림
                self.logger.warning(f"수집된 데이터 부족: {sample_count}개")
        elif elapsed >= self.config.collection_duration * 2:  # 최대 2배까지 대기
            # 시간 초과, 강제 완료
            self.logger.warning(f"시간 초과, 강제 완료: {sample_count}개 샘플")
            if sample_count > 10:  # 최소한의 데이터가 있으면 완료
                self.complete_current_point()
    
    def _is_outlier(self, value: float) -> bool:
        """이상치 검사 (캘리브레이션 모드에서는 완화됨)"""
        if len(self.current_readings) < 10:  # 더 많은 데이터 필요
            return False
        
        # 캘리브레이션 모드에서는 이상치 임계값을 높임 (더 관대함)
        outlier_threshold = self.config.outlier_threshold * 3.0  # 3배 완화
        
        recent = self.current_readings[-10:]  # 더 많은 최근 데이터 사용
        mean_val = np.mean(recent)
        std_val = np.std(recent)
        
        if std_val == 0:
            return False
        
        z_score = abs((value - mean_val) / std_val)
        
        # 캘리브레이션 중에는 큰 변화도 허용
        return z_score > outlier_threshold
    
    def _evaluate_point_quality(self, point: CalibrationPoint) -> float:
        """포인트 품질 평가"""
        quality = 1.0
        
        # 변동계수 기준
        cv = point.cv_percentage
        if cv > self.config.max_cv_percentage:
            quality *= 0.5
        
        # 샘플 수 기준
        if len(point.sensor_readings) < self.config.min_samples:
            quality *= 0.7
        
        return max(0.0, min(1.0, quality))
    
    def _linear_regression(self, x_data: np.ndarray, y_data: np.ndarray) -> Tuple[Tuple[float, float], float, float]:
        """선형 회귀"""
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)
        
        # 예측값 계산
        y_pred = slope * x_data + intercept
        
        # RMSE 계산
        rmse = np.sqrt(np.mean((y_data - y_pred) ** 2))
        
        return (slope, intercept), r_value ** 2, rmse
    
    def _polynomial_regression(self, x_data: np.ndarray, y_data: np.ndarray, degree: int) -> Tuple[Tuple[float, ...], float, float]:
        """다항식 회귀"""
        coeffs = np.polyfit(x_data, y_data, degree)
        
        # 예측값 계산
        y_pred = np.polyval(coeffs, x_data)
        
        # R² 계산
        ss_res = np.sum((y_data - y_pred) ** 2)
        ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)
        
        # RMSE 계산
        rmse = np.sqrt(np.mean((y_data - y_pred) ** 2))
        
        return tuple(coeffs), r_squared, rmse
    
    def _validate_calibration(self, result: CalibrationResult) -> bool:
        """캘리브레이션 검증"""
        # 기본 품질 기준
        min_r_squared = 0.95
        max_rmse = 0.1  # 0.1g 이내
        
        # R² 검사
        if result.r_squared < min_r_squared:
            self.logger.warning(f"R² 너무 낮음: {result.r_squared:.6f}")
            return False
        
        # RMSE 검사
        if result.rmse > max_rmse:
            self.logger.warning(f"RMSE 너무 높음: {result.rmse:.6f}")
            return False
        
        # 계수 유효성 검사
        if result.method == CalibrationMethod.LINEAR:
            slope, intercept = result.coefficients
            if slope <= 0:
                self.logger.warning("기울기가 0 이하입니다")
                return False
        
        return True
    
    def _process_calibration(self):
        """캘리브레이션 처리"""
        # 자동으로 최적의 방법 선택하여 계산
        methods = [
            CalibrationMethod.LINEAR,
            CalibrationMethod.POLYNOMIAL_2,
            CalibrationMethod.POLYNOMIAL_3
        ]
        
        best_result = None
        best_score = -1
        
        for method in methods:
            result = self.calculate_calibration(method)
            if result and result.validation_passed:
                # 점수 계산 (R² 우선, RMSE 고려)
                score = result.r_squared - (result.rmse * 0.1)
                if score > best_score:
                    best_score = score
                    best_result = result
        
        if best_result:
            self.logger.info(f"최적 방법 선택: {best_result.method.value}")
        else:
            # 검증 실패해도 선형 회귀 결과는 제공
            best_result = self.calculate_calibration(CalibrationMethod.LINEAR)
    
    def _set_state(self, new_state: CalibrationState):
        """상태 변경"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.logger.debug(f"상태 변경: {old_state.value} -> {new_state.value}")
            self.state_changed.emit(new_state)
    
    def cleanup(self):
        """리소스 정리"""
        self.collection_timer.stop()
        self.calibration_points.clear()
        self.current_point = None
        self.current_readings.clear()
        self._set_state(CalibrationState.IDLE)


# 호환성을 위한 별명
CalibrationManager = CalibrationEngine