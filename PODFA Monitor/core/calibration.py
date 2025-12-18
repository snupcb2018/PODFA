"""
PBS 2.0 Calibration Engine
===========================

Advanced calibration system
- Multiple calibration methods
- Quality assessment and validation
- Automatic data collection
- Real-time monitoring
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
    """Calibration method enumeration"""
    LINEAR = "linear"              # Linear regression
    POLYNOMIAL_2 = "polynomial_2"  # 2nd order polynomial
    POLYNOMIAL_3 = "polynomial_3"  # 3rd order polynomial
    CUBIC_SPLINE = "cubic_spline"  # Cubic spline


class CalibrationState(Enum):
    """Calibration state"""
    IDLE = "idle"
    COLLECTING = "collecting"      # Data collection in progress
    PROCESSING = "processing"      # Processing
    COMPLETED = "completed"        # Completed
    ERROR = "error"               # Error


@dataclass
class CalibrationPoint:
    """Calibration point"""
    reference_weight: float        # Reference weight (g)
    sensor_readings: List[float]   # Sensor readings
    collection_time: float         # Collection time
    quality_score: float = 1.0     # Quality score

    @property
    def average_reading(self) -> float:
        """Average sensor reading"""
        return np.mean(self.sensor_readings) if self.sensor_readings else 0.0

    @property
    def std_reading(self) -> float:
        """Standard deviation"""
        return np.std(self.sensor_readings) if len(self.sensor_readings) > 1 else 0.0

    @property
    def cv_percentage(self) -> float:
        """Coefficient of variation (%)"""
        avg = self.average_reading
        return (self.std_reading / avg * 100) if avg != 0 else 0.0


@dataclass
class CalibrationResult:
    """Calibration result"""
    method: CalibrationMethod
    coefficients: Tuple[float, ...]    # Regression coefficients
    r_squared: float                   # Coefficient of determination
    rmse: float                        # Root mean square error
    points: List[CalibrationPoint]     # Calibration points
    created_time: float                # Creation time
    validation_passed: bool = False    # Validation passed flag

    @property
    def quality_grade(self) -> str:
        """Quality grade"""
        if self.r_squared >= 0.99:
            return "Excellent"
        elif self.r_squared >= 0.95:
            return "Good"
        elif self.r_squared >= 0.90:
            return "Fair"
        else:
            return "Poor"
    
    def apply(self, sensor_value: float) -> float:
        """Convert sensor value to weight"""
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
            # Default linear conversion
            if len(self.coefficients) >= 2:
                return self.coefficients[0] * sensor_value + self.coefficients[1]
            return sensor_value


@dataclass
class CollectionConfig:
    """Data collection configuration"""
    collection_duration: float = 10.0  # Collection time (seconds)
    min_samples: int = 150             # Minimum number of samples
    max_cv_percentage: float = 5.0     # Maximum coefficient of variation (%)
    outlier_threshold: float = 3.0     # Outlier threshold (standard deviation multiplier)
    auto_advance: bool = True          # Auto-advance to next step
    stabilization_time: float = 3.0    # Weight stabilization wait time (seconds)


class CalibrationEngine(QObject):
    """
    🎯 Advanced calibration engine

    Features:
    - Multiple regression methods
    - Automatic quality assessment
    - Real-time data collection
    - Validation system
    """

    # Signal definitions
    state_changed = pyqtSignal(CalibrationState)            # State changed
    point_collected = pyqtSignal(CalibrationPoint)          # Point collection completed
    progress_updated = pyqtSignal(int, str)                 # Progress updated
    calibration_completed = pyqtSignal(CalibrationResult)   # Calibration completed
    data_point_added = pyqtSignal(float)                    # Data point added
    error_occurred = pyqtSignal(str)                        # Error occurred
    
    def __init__(self, config: Optional[CollectionConfig] = None):
        super().__init__()
        
        # Configuration
        self.config = config or CollectionConfig()

        # State management
        self.state = CalibrationState.IDLE
        self.current_step = 0
        self.total_steps = 5  # Default 5 steps

        # Data storage
        self.calibration_points: List[CalibrationPoint] = []
        self.current_point: Optional[CalibrationPoint] = None
        self.current_readings: List[float] = []

        # Collection management
        self.collection_start_time: Optional[float] = None
        self.target_weight: Optional[float] = None

        # Timer
        self.collection_timer = QTimer()
        self.collection_timer.timeout.connect(self._check_collection_progress)
        
        # Logging
        self.logger = logging.getLogger(__name__)

    def start_calibration(self, reference_weights: List[float]):
        """
        Start calibration

        Args:
            reference_weights: List of reference weights (g)
        """
        if self.state != CalibrationState.IDLE:
            self.logger.warning("Calibration is already in progress")
            return False

        # Initialize
        self.calibration_points.clear()
        self.current_step = 0
        self.total_steps = len(reference_weights)
        self.reference_weights = reference_weights

        # Keep state as IDLE - wizard will start each step manually
        self.logger.info(f"Calibration started: {len(reference_weights)} steps")

        # Do not auto-start first step - wizard will control manually
        # self._start_next_point()

        return True
    
    def start_point_collection(self, reference_weight: float):
        """
        Start point collection

        Args:
            reference_weight: Reference weight (g)
        """
        if self.state == CalibrationState.COLLECTING and self.current_point:
            self.logger.warning("Collection is already in progress")
            return False

        # Change state to COLLECTING
        self._set_state(CalibrationState.COLLECTING)

        # Start new point
        self.target_weight = reference_weight
        self.current_readings.clear()
        self.collection_start_time = time.time()
        self.stabilization_start_time = time.time()  # Stabilization start time
        self.is_stabilizing = True  # Stabilization phase flag

        self.current_point = CalibrationPoint(
            reference_weight=reference_weight,
            sensor_readings=[],
            collection_time=time.time()
        )

        # Start timer
        self.collection_timer.start(100)  # Check every 100ms

        self.logger.info(f"Point collection started: {reference_weight}g (waiting for stabilization...)")
        self.progress_updated.emit(0, f"Stabilizing... {reference_weight}g")

        return True
    
    def add_sensor_reading(self, sensor_value: float):
        """
        Add sensor reading

        Args:
            sensor_value: Sensor value
        """
        if self.state != CalibrationState.COLLECTING or not self.current_point:
            return

        # During stabilization phase, only buffer data, don't actually collect
        if hasattr(self, 'is_stabilizing') and self.is_stabilizing:
            # Perform outlier check even during stabilization, but relaxed
            if len(self.current_readings) >= 20:  # Only when sufficient data exists
                if self._is_outlier(sensor_value):
                    self.logger.debug(f"Outlier removed during stabilization: {sensor_value}")
                    return

            # Add stabilization data (keep max 50)
            self.current_readings.append(sensor_value)
            if len(self.current_readings) > 50:
                self.current_readings.pop(0)

            self.data_point_added.emit(sensor_value)
            return

        # Outlier check during actual collection phase (relaxed)
        if self._is_outlier(sensor_value):
            self.logger.debug(f"Outlier removed: {sensor_value}")
            return

        # Add data
        self.current_readings.append(sensor_value)
        self.current_point.sensor_readings.append(sensor_value)

        # Emit signal
        self.data_point_added.emit(sensor_value)
    
    def complete_current_point(self) -> bool:
        """Complete current point collection"""
        if not self.current_point or not self.current_readings:
            self.logger.error("No data to collect")
            return False

        # Quality assessment
        self.current_point.quality_score = self._evaluate_point_quality(
            self.current_point
        )

        # Collection completed
        self.collection_timer.stop()
        self.calibration_points.append(self.current_point)

        # Restore state to IDLE (wizard controls next step)
        self._set_state(CalibrationState.IDLE)

        # Emit signal
        self.point_collected.emit(self.current_point)

        self.logger.info(
            f"Point collection completed: {self.current_point.reference_weight}g, "
            f"Quality: {self.current_point.quality_score:.3f}"
        )

        # Wizard manages step, so don't increment here
        # self.current_step += 1

        # Wizard controls next step, so don't auto-advance
        # if self.current_step < self.total_steps:
        #     if self.config.auto_advance:
        #         self._start_next_point()
        # else:
        #     # All steps completed
        #     self._process_calibration()

        return True
    
    def calculate_calibration(self, method: CalibrationMethod = CalibrationMethod.LINEAR) -> Optional[CalibrationResult]:
        """
        Calculate calibration

        Args:
            method: Calibration method

        Returns:
            Calibration result
        """
        if len(self.calibration_points) < 2:
            self.logger.error("Minimum 2 points required")
            return None

        self._set_state(CalibrationState.PROCESSING)
        
        try:
            # Prepare data
            x_data = np.array([point.average_reading for point in self.calibration_points])
            y_data = np.array([point.reference_weight for point in self.calibration_points])

            # Regression analysis
            if method == CalibrationMethod.LINEAR:
                coeffs, r_squared, rmse = self._linear_regression(x_data, y_data)
            elif method == CalibrationMethod.POLYNOMIAL_2:
                coeffs, r_squared, rmse = self._polynomial_regression(x_data, y_data, 2)
            elif method == CalibrationMethod.POLYNOMIAL_3:
                coeffs, r_squared, rmse = self._polynomial_regression(x_data, y_data, 3)
            else:
                coeffs, r_squared, rmse = self._linear_regression(x_data, y_data)

            # Create result
            result = CalibrationResult(
                method=method,
                coefficients=coeffs,
                r_squared=r_squared,
                rmse=rmse,
                points=self.calibration_points.copy(),
                created_time=time.time()
            )

            # Perform validation
            result.validation_passed = self._validate_calibration(result)

            self._set_state(CalibrationState.COMPLETED)
            self.calibration_completed.emit(result)

            self.logger.info(
                f"Calibration completed - Method: {method.value}, "
                f"R²: {r_squared:.6f}, RMSE: {rmse:.6f}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Calibration calculation error: {e}")
            self.error_occurred.emit(f"Calculation error: {str(e)}")
            self._set_state(CalibrationState.ERROR)
            return None
    
    def save_calibration(self, result: CalibrationResult, filename: str):
        """
        Save calibration result

        Args:
            result: Calibration result
            filename: Filename to save
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

            self.logger.info(f"Calibration saved: {filename}")

        except Exception as e:
            self.logger.error(f"Calibration save failed: {e}")
            self.error_occurred.emit(f"Save failed: {str(e)}")
    
    def load_calibration(self, filename: str) -> Optional[CalibrationResult]:
        """
        Load calibration result

        Args:
            filename: Filename

        Returns:
            Calibration result
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore points
            points = []
            for point_data in data['points']:
                point = CalibrationPoint(
                    reference_weight=point_data['reference_weight'],
                    sensor_readings=point_data['sensor_readings'],
                    collection_time=point_data['collection_time'],
                    quality_score=point_data.get('quality_score', 1.0)
                )
                points.append(point)

            # Restore result
            result = CalibrationResult(
                method=CalibrationMethod(data['method']),
                coefficients=tuple(data['coefficients']),
                r_squared=data['r_squared'],
                rmse=data['rmse'],
                points=points,
                created_time=data['created_time'],
                validation_passed=data.get('validation_passed', False)
            )

            self.logger.info(f"Calibration loaded: {filename}")
            return result

        except Exception as e:
            self.logger.error(f"Calibration load failed: {e}")
            self.error_occurred.emit(f"Load failed: {str(e)}")
            return None
    
    def cancel_calibration(self):
        """Cancel calibration"""
        self.collection_timer.stop()
        self.calibration_points.clear()
        self.current_point = None
        self.current_readings.clear()
        self.current_step = 0

        self._set_state(CalibrationState.IDLE)
        self.logger.info("Calibration cancelled")
    
    def _start_next_point(self):
        """Start next point collection"""
        if self.current_step < len(self.reference_weights):
            next_weight = self.reference_weights[self.current_step]
            self.start_point_collection(next_weight)

    def _check_collection_progress(self):
        """Check collection progress"""
        if not self.current_point or not self.collection_start_time:
            return

        current_time = time.time()

        # Handle stabilization phase
        if hasattr(self, 'is_stabilizing') and self.is_stabilizing:
            stabilization_elapsed = current_time - self.stabilization_start_time
            stabilization_progress = min(int((stabilization_elapsed / self.config.stabilization_time) * 100), 100)

            sample_count = len(self.current_readings)
            status = f"Stabilizing... {self.target_weight}g ({sample_count} samples, {stabilization_elapsed:.1f}s)"
            self.progress_updated.emit(stabilization_progress, status)

            # Check stabilization completion
            if stabilization_elapsed >= self.config.stabilization_time:
                self.is_stabilizing = False
                self.collection_start_time = current_time  # Reset actual collection start time
                self.current_point.sensor_readings.clear()  # Clear stabilization data
                self.logger.info(f"Stabilization completed, starting actual collection: {self.target_weight}g")
                self.progress_updated.emit(0, f"Collecting... {self.target_weight}g")
            return

        # Actual collection phase
        elapsed = current_time - self.collection_start_time
        progress = min(int((elapsed / self.config.collection_duration) * 100), 100)

        # Update progress
        sample_count = len(self.current_point.sensor_readings)  # Only actual collected data
        total_samples = len(self.current_readings)  # All including stabilization

        status = f"Collecting... {self.target_weight}g ({sample_count}/{self.config.min_samples} samples)"
        self.progress_updated.emit(progress, status)

        # Check collection completion
        if (elapsed >= self.config.collection_duration and
            sample_count >= self.config.min_samples):

            # Quality check
            if sample_count > 0:  # Complete only if data exists
                self.complete_current_point()
            else:
                # Wait longer if no data
                self.logger.warning(f"Insufficient collected data: {sample_count}")
        elif elapsed >= self.config.collection_duration * 2:  # Wait max 2x
            # Timeout, force completion
            self.logger.warning(f"Timeout, force completion: {sample_count} samples")
            if sample_count > 10:  # Complete if minimum data exists
                self.complete_current_point()
    
    def _is_outlier(self, value: float) -> bool:
        """Outlier detection (relaxed in calibration mode)"""
        if len(self.current_readings) < 10:
            return False

        # Increase outlier threshold in calibration mode (more lenient)
        outlier_threshold = self.config.outlier_threshold * 3.0

        recent = self.current_readings[-10:]
        mean_val = np.mean(recent)
        std_val = np.std(recent)

        if std_val == 0:
            return False

        z_score = abs((value - mean_val) / std_val)

        # Allow large variations during calibration
        return z_score > outlier_threshold
    
    def _evaluate_point_quality(self, point: CalibrationPoint) -> float:
        """Evaluate point quality"""
        quality = 1.0

        # Coefficient of variation criteria
        cv = point.cv_percentage
        if cv > self.config.max_cv_percentage:
            quality *= 0.5

        # Sample count criteria
        if len(point.sensor_readings) < self.config.min_samples:
            quality *= 0.7

        return max(0.0, min(1.0, quality))
    
    def _linear_regression(self, x_data: np.ndarray, y_data: np.ndarray) -> Tuple[Tuple[float, float], float, float]:
        """Linear regression"""
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)

        # Calculate predictions
        y_pred = slope * x_data + intercept

        # Calculate RMSE
        rmse = np.sqrt(np.mean((y_data - y_pred) ** 2))

        return (slope, intercept), r_value ** 2, rmse

    def _polynomial_regression(self, x_data: np.ndarray, y_data: np.ndarray, degree: int) -> Tuple[Tuple[float, ...], float, float]:
        """Polynomial regression"""
        coeffs = np.polyfit(x_data, y_data, degree)

        # Calculate predictions
        y_pred = np.polyval(coeffs, x_data)

        # Calculate R²
        ss_res = np.sum((y_data - y_pred) ** 2)
        ss_tot = np.sum((y_data - np.mean(y_data)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)

        # Calculate RMSE
        rmse = np.sqrt(np.mean((y_data - y_pred) ** 2))

        return tuple(coeffs), r_squared, rmse
    
    def _validate_calibration(self, result: CalibrationResult) -> bool:
        """Validate calibration"""
        # Basic quality criteria
        min_r_squared = 0.95
        max_rmse = 0.1

        # R² check
        if result.r_squared < min_r_squared:
            self.logger.warning(f"R² too low: {result.r_squared:.6f}")
            return False

        # RMSE check
        if result.rmse > max_rmse:
            self.logger.warning(f"RMSE too high: {result.rmse:.6f}")
            return False

        # Coefficient validity check
        if result.method == CalibrationMethod.LINEAR:
            slope, intercept = result.coefficients
            if slope <= 0:
                self.logger.warning("Slope is zero or negative")
                return False

        return True

    def _process_calibration(self):
        """Process calibration"""
        # Automatically select optimal method
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
                # Calculate score (R² priority, RMSE consideration)
                score = result.r_squared - (result.rmse * 0.1)
                if score > best_score:
                    best_score = score
                    best_result = result

        if best_result:
            self.logger.info(f"Optimal method selected: {best_result.method.value}")
        else:
            # Provide linear regression result even if validation fails
            best_result = self.calculate_calibration(CalibrationMethod.LINEAR)

    def _set_state(self, new_state: CalibrationState):
        """Change state"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.logger.debug(f"State change: {old_state.value} -> {new_state.value}")
            self.state_changed.emit(new_state)

    def cleanup(self):
        """Clean up resources"""
        self.collection_timer.stop()
        self.calibration_points.clear()
        self.current_point = None
        self.current_readings.clear()
        self._set_state(CalibrationState.IDLE)


# Compatibility alias
CalibrationManager = CalibrationEngine