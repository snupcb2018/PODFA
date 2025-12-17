"""
PBS 2.0 Calibration Monitor Widget
===================================

실시간 캘리브레이션 모니터링 위젯
- 실시간 센서 값 그래프
- 수집 진행률 표시
- 품질 지표 시각화
"""

import numpy as np
from collections import deque
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QGroupBox,
    QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


class RealtimeGraph(FigureCanvas):
    """실시간 그래프 위젯"""
    
    def __init__(self, parent=None, max_points=500):
        self.figure = Figure(figsize=(8, 4))
        super().__init__(self.figure)
        self.setParent(parent)
        
        self.max_points = max_points
        self.data_buffer = deque(maxlen=max_points)
        self.time_buffer = deque(maxlen=max_points)
        self.time_counter = 0
        
        self._init_plot()
    
    def _init_plot(self):
        """플롯 초기화"""
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel('Time (samples)')
        self.ax.set_ylabel('Sensor Value')
        self.ax.set_title('Real-time Sensor Data')
        self.ax.grid(True, alpha=0.3)
        
        # 라인 객체 생성
        self.line, = self.ax.plot([], [], 'b-', linewidth=1.5)
        self.avg_line = self.ax.axhline(y=0, color='r', linestyle='--', alpha=0.5, label='Average')
        
        # 범위 설정
        self.ax.set_xlim(0, self.max_points)
        self.ax.set_ylim(0, 100)  # 초기 범위
        
        self.ax.legend(loc='upper right')
        self.figure.tight_layout()
    
    def add_data_point(self, value: float):
        """데이터 포인트 추가"""
        self.data_buffer.append(value)
        self.time_buffer.append(self.time_counter)
        self.time_counter += 1
        
        # 그래프 업데이트
        if len(self.data_buffer) > 0:
            self.line.set_data(list(self.time_buffer), list(self.data_buffer))
            
            # 평균선 업데이트
            avg_value = np.mean(self.data_buffer)
            self.avg_line.set_ydata([avg_value, avg_value])
            
            # 축 범위 자동 조정
            if len(self.data_buffer) > 1:
                y_min = min(self.data_buffer) * 0.9
                y_max = max(self.data_buffer) * 1.1
                self.ax.set_ylim(y_min, y_max)
                
                if self.time_counter > self.max_points:
                    self.ax.set_xlim(self.time_counter - self.max_points, self.time_counter)
            
            self.draw()
    
    def clear_data(self):
        """데이터 초기화"""
        self.data_buffer.clear()
        self.time_buffer.clear()
        self.time_counter = 0
        self.line.set_data([], [])
        self.avg_line.set_ydata([0, 0])
        self.ax.set_xlim(0, self.max_points)
        self.draw()
    
    def set_reference_line(self, value: float, label: str = "Reference"):
        """기준선 설정"""
        # 기존 기준선 제거
        for line in self.ax.lines:
            if line.get_label() == label:
                line.remove()
        
        # 새 기준선 추가
        self.ax.axhline(y=value, color='g', linestyle=':', alpha=0.7, label=label)
        self.ax.legend(loc='upper right')
        self.draw()


class QualityIndicator(QWidget):
    """품질 지표 위젯"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.quality_score = 0.0
        self.setMinimumSize(100, 100)
    
    def set_quality(self, score: float):
        """품질 점수 설정 (0.0 ~ 1.0)"""
        self.quality_score = max(0.0, min(1.0, score))
        self.update()
    
    def paintEvent(self, event):
        """페인트 이벤트"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 배경
        painter.fillRect(self.rect(), QColor(240, 240, 240))
        
        # 원형 인디케이터
        center_x = self.width() // 2
        center_y = self.height() // 2
        radius = min(self.width(), self.height()) // 3
        
        # 품질에 따른 색상
        if self.quality_score >= 0.9:
            color = QColor(0, 200, 0)  # 녹색
        elif self.quality_score >= 0.7:
            color = QColor(255, 165, 0)  # 주황색
        else:
            color = QColor(255, 0, 0)  # 빨간색
        
        # 원 그리기
        painter.setPen(QPen(color, 3))
        painter.setBrush(QBrush(color, Qt.BrushStyle.Dense6Pattern))
        
        # 품질 점수에 따른 각도
        angle = int(360 * self.quality_score)
        painter.drawPie(
            center_x - radius, center_y - radius,
            radius * 2, radius * 2,
            90 * 16, -angle * 16  # Qt는 1/16도 단위 사용
        )
        
        # 텍스트
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            f"{self.quality_score * 100:.0f}%"
        )


class CalibrationMonitor(QWidget):
    """
    캘리브레이션 실시간 모니터링 위젯
    
    실시간 센서 데이터와 품질 지표를 시각화
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_weight = 0.0
        self.sample_count = 0
        self.readings = []
        
        self._init_ui()
    
    def _init_ui(self):
        """UI 초기화"""
        layout = QVBoxLayout()
        
        # 상단 정보 패널
        info_layout = QHBoxLayout()
        
        # 현재 무게 표시
        weight_group = QGroupBox("현재 무게")
        weight_layout = QVBoxLayout()
        self.weight_label = QLabel("0.0 g")
        self.weight_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weight_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #2196F3;
            }
        """)
        weight_layout.addWidget(self.weight_label)
        weight_group.setLayout(weight_layout)
        info_layout.addWidget(weight_group)
        
        # 샘플 수 표시
        sample_group = QGroupBox("샘플 수")
        sample_layout = QVBoxLayout()
        self.sample_label = QLabel("0")
        self.sample_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sample_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #4CAF50;
            }
        """)
        sample_layout.addWidget(self.sample_label)
        sample_group.setLayout(sample_layout)
        info_layout.addWidget(sample_group)
        
        # 품질 지표
        quality_group = QGroupBox("품질")
        quality_layout = QVBoxLayout()
        self.quality_indicator = QualityIndicator()
        quality_layout.addWidget(self.quality_indicator)
        quality_group.setLayout(quality_layout)
        info_layout.addWidget(quality_group)
        
        layout.addLayout(info_layout)
        
        # 실시간 그래프
        graph_group = QGroupBox("실시간 센서 데이터")
        graph_layout = QVBoxLayout()
        self.graph = RealtimeGraph()
        graph_layout.addWidget(self.graph)
        graph_group.setLayout(graph_layout)
        layout.addWidget(graph_group)
        
        # 통계 정보
        stats_group = QGroupBox("통계")
        stats_layout = QGridLayout()
        
        # 평균
        stats_layout.addWidget(QLabel("평균:"), 0, 0)
        self.avg_label = QLabel("0.0")
        stats_layout.addWidget(self.avg_label, 0, 1)
        
        # 표준편차
        stats_layout.addWidget(QLabel("표준편차:"), 0, 2)
        self.std_label = QLabel("0.0")
        stats_layout.addWidget(self.std_label, 0, 3)
        
        # 최소/최대
        stats_layout.addWidget(QLabel("최소:"), 1, 0)
        self.min_label = QLabel("0.0")
        stats_layout.addWidget(self.min_label, 1, 1)
        
        stats_layout.addWidget(QLabel("최대:"), 1, 2)
        self.max_label = QLabel("0.0")
        stats_layout.addWidget(self.max_label, 1, 3)
        
        # CV%
        stats_layout.addWidget(QLabel("CV%:"), 2, 0)
        self.cv_label = QLabel("0.0")
        stats_layout.addWidget(self.cv_label, 2, 1)
        
        # 안정성
        stats_layout.addWidget(QLabel("안정성:"), 2, 2)
        self.stability_label = QLabel("대기 중")
        stats_layout.addWidget(self.stability_label, 2, 3)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        self.setLayout(layout)
    
    def set_reference_weight(self, weight: float):
        """기준 무게 설정"""
        self.current_weight = weight
        self.weight_label.setText(f"{weight:.1f} g")
        self.graph.set_reference_line(weight, f"Target: {weight}g")
    
    def add_sensor_reading(self, value: float):
        """센서 읽기 값 추가"""
        self.readings.append(value)
        self.sample_count += 1
        
        # UI 업데이트
        self.sample_label.setText(str(self.sample_count))
        self.graph.add_data_point(value)
        
        # 통계 업데이트
        self._update_statistics()
    
    def _update_statistics(self):
        """통계 정보 업데이트"""
        if not self.readings:
            return
        
        # 최근 100개 샘플만 사용
        recent_readings = self.readings[-100:]
        
        avg = np.mean(recent_readings)
        std = np.std(recent_readings)
        min_val = np.min(recent_readings)
        max_val = np.max(recent_readings)
        
        # CV% 계산
        cv = (std / avg * 100) if avg != 0 else 0
        
        # UI 업데이트
        self.avg_label.setText(f"{avg:.2f}")
        self.std_label.setText(f"{std:.4f}")
        self.min_label.setText(f"{min_val:.2f}")
        self.max_label.setText(f"{max_val:.2f}")
        self.cv_label.setText(f"{cv:.2f}%")
        
        # 안정성 평가
        if cv < 1.0:
            stability = "매우 안정"
            color = "green"
        elif cv < 2.0:
            stability = "안정"
            color = "blue"
        elif cv < 5.0:
            stability = "보통"
            color = "orange"
        else:
            stability = "불안정"
            color = "red"
        
        self.stability_label.setText(stability)
        self.stability_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        
        # 품질 점수 계산 (CV 기반)
        quality_score = max(0, 1 - cv / 10)  # CV 10% 이상이면 품질 0
        self.quality_indicator.set_quality(quality_score)
    
    def clear_data(self):
        """데이터 초기화"""
        self.readings.clear()
        self.sample_count = 0
        self.sample_label.setText("0")
        self.graph.clear_data()
        
        # 통계 초기화
        self.avg_label.setText("0.0")
        self.std_label.setText("0.0")
        self.min_label.setText("0.0")
        self.max_label.setText("0.0")
        self.cv_label.setText("0.0")
        self.stability_label.setText("Waiting")
        self.quality_indicator.set_quality(0.0)
    
    def get_statistics(self) -> dict:
        """현재 통계 정보 반환"""
        if not self.readings:
            return {}
        
        recent_readings = self.readings[-100:]
        avg = np.mean(recent_readings)
        std = np.std(recent_readings)
        
        return {
            'average': avg,
            'std': std,
            'min': np.min(recent_readings),
            'max': np.max(recent_readings),
            'cv_percentage': (std / avg * 100) if avg != 0 else 0,
            'sample_count': self.sample_count,
            'readings': recent_readings
        }