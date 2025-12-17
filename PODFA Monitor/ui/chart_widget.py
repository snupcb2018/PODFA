"""
PBS 2.0 Chart Widget
================

Real-time chart display widget based on matplotlib
"""

import io
import time
import logging
from collections import deque
from typing import List, Optional
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel,
    QSplitter, QPushButton, QScrollBar, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
import qtawesome as qta

# matplotlib imports
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib import animation
import numpy as np

from core.data_processor import DataPoint


class DynamicYAxisManager:
    """진정한 동적 Y축 스케일링 - 데이터 최대값에 따라 실시간 적응"""
    
    def __init__(self, enable_dynamic_scaling: bool = True):
        """
        초기화
        
        Args:
            enable_dynamic_scaling: 동적 스케일링 활성화 여부
        """
        self.enable_dynamic_scaling = enable_dynamic_scaling
        self.margin = 1.5           # 상단 여유분 (그램)
        self.min_y_max = 3.5        # 최소 Y축 최대값
        self.y_min = -0.5           # Y축 최소값 (고정)
    
    def get_y_range(self, window_data: list, current_y_max: float = None) -> tuple:
        """
        데이터 윈도우에 기반한 동적 Y축 범위 계산
        
        Args:
            window_data: 현재 표시되는 데이터 값들
            current_y_max: 현재 Y축 최대값 (부드러운 전환용, 선택사항)
            
        Returns:
            tuple: (y_min, y_max) Y축 범위
        """
        if not self.enable_dynamic_scaling or not window_data:
            return (self.y_min, self.min_y_max)
        
        # 데이터 최대값 기반 동적 계산
        window_max = max(window_data)
        target_y_max = window_max + self.margin
        
        # 최소 범위 보장
        target_y_max = max(target_y_max, self.min_y_max)
        
        # 부드러운 전환 (선택사항)
        if current_y_max is not None:
            # 급격한 변화 완화 (0.3g 이상 차이날 때)
            if abs(target_y_max - current_y_max) > 0.3:
                if target_y_max > current_y_max:
                    # 확장시: 점진적 확장 (더 빠르게)
                    y_max = min(current_y_max + 2.0, target_y_max)
                else:
                    # 축소시: 점진적 축소 (더 빠르게)
                    y_max = max(current_y_max - 0.8, target_y_max)
            else:
                y_max = target_y_max
        else:
            y_max = target_y_max
            
        return (self.y_min, y_max)
    
    def set_margin(self, margin: float):
        """여유분 설정"""
        self.margin = max(0.5, margin)  # 최소 0.5g 여유분
    
    def set_min_y_max(self, min_y_max: float):
        """최소 Y축 최대값 설정"""
        self.min_y_max = max(2.0, min_y_max)  # 최소 2.0g
        
    def is_enabled(self) -> bool:
        """동적 스케일링 활성화 상태"""
        return self.enable_dynamic_scaling
        
    def set_enabled(self, enabled: bool):
        """동적 스케일링 활성화/비활성화"""
        self.enable_dynamic_scaling = enabled


@dataclass
class ChartConfig:
    """Chart configuration"""
    time_window: int = 30  # Time window (seconds)
    update_interval: int = 100  # Update interval (ms)
    line_color: str = '#2196F3'
    line_width: float = 1.2  # 더 세련된 선 굵기
    background_color: str = 'white'
    grid_alpha: float = 0.3
    max_points: int = 10000  # Maximum data points


class ChartWidget(QWidget):
    """📊 Matplotlib-based real-time chart widget"""
    
    # Signals
    data_exported = pyqtSignal(str)  # Data export completed
    
    def __init__(self, name: str = "Chart", config: Optional[ChartConfig] = None, parent=None):
        super().__init__(parent)
        
        # Configuration
        self.name = name
        self.config = config or ChartConfig()
        
        # Data management
        self.data_points: List[DataPoint] = []
        self.time_buffer = deque(maxlen=10000)  # Time buffer (current view)
        self.value_buffer = deque(maxlen=10000)  # Value buffer (current view)
        
        # Full history (for scroll functionality)
        self.full_time_history = deque(maxlen=50000)  # Full time history
        self.full_value_history = deque(maxlen=50000)  # Full value history
        
        self.max_sensor_value = float('-inf')
        
        # Scroll state
        self.is_scrolling = False  # Whether user is scrolling
        self.scroll_position = 1.0  # 0.0(oldest data) ~ 1.0(latest data)
        
        # State
        self.is_updating = False
        self.is_calibrated = False  # 캘리브레이션 상태 추적
        self.is_measuring = False   # 측정 중 상태 추적 (저장 시 데이터 필터링용)
        
        # 진정한 동적 Y축 스케일링 (캘리브레이션된 경우에만 활성화)
        self.y_axis_manager = DynamicYAxisManager(enable_dynamic_scaling=self.is_calibrated)
        self.current_y_max = 3.5  # 현재 Y축 최대값 (부드러운 전환용)
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
        # Initialize UI
        self._init_ui()
        self._init_chart()
        
        self.logger.info(f"Matplotlib chart widget '{self.name}' created")
    
    def _init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 툴바
        self.toolbar = self._create_toolbar()
        layout.addWidget(self.toolbar)
        
        # 메인 영역
        main_widget = QSplitter(Qt.Orientation.Vertical)
        
        # 차트 영역
        chart_area = QWidget()
        chart_layout = QVBoxLayout(chart_area)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        
        # matplotlib 캔버스 with high-quality settings
        self.figure = Figure(
            figsize=(10, 6), 
            facecolor=self.config.background_color,
            dpi=120,  # 화면 표시용 DPI
            tight_layout=True
        )
        self.canvas = FigureCanvas(self.figure)
        
        # 고품질 렌더링을 위한 설정
        self.figure.patch.set_antialiased(True)
        chart_layout.addWidget(self.canvas)
        
        # 스크롤바
        self.scrollbar = self._create_scrollbar()
        chart_layout.addWidget(self.scrollbar)
        
        main_widget.addWidget(chart_area)
        
        # 상태바
        status_widget = self._create_status_widget()
        main_widget.addWidget(status_widget)
        
        # 분할 비율 설정
        main_widget.setSizes([900, 100])  # 차트:상태 = 9:1
        
        layout.addWidget(main_widget)
        self.setLayout(layout)
    
    def _create_toolbar(self):
        """Create toolbar"""
        toolbar = QToolBar()
        toolbar.setIconSize(qta.icon('fa5s.play').actualSize(toolbar.iconSize()))
        
        # 재생/일시정지 버튼
        self.play_action = toolbar.addAction(qta.icon('fa5s.play'), "Start")
        self.play_action.setCheckable(True)
        self.play_action.triggered.connect(self._toggle_updates)
        
        toolbar.addSeparator()
        
        # 데이터 지우기
        clear_action = toolbar.addAction(qta.icon('fa5s.trash'), "Clear")
        clear_action.triggered.connect(self._confirm_clear_data)
        clear_action.setToolTip("Clear all data")
        
        toolbar.addSeparator()
        
        # 최신 데이터로 이동
        home_action = toolbar.addAction(qta.icon('fa5s.fast-forward'), "Latest")
        home_action.triggered.connect(self._go_to_latest)
        home_action.setToolTip("Go to latest data (End)")
        
        return toolbar
    
    def _create_scrollbar(self):
        """Create scrollbar"""
        scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        scrollbar.setMinimum(0)
        scrollbar.setMaximum(100)
        scrollbar.setValue(100)
        scrollbar.setPageStep(10)
        scrollbar.valueChanged.connect(self._on_scroll_changed)
        return scrollbar
    
    def _create_status_widget(self):
        """Create status widget"""
        status_widget = QFrame()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(5, 2, 5, 2)
        
        # 통계 라벨
        self.stats_label = QLabel("Data: 0 points | Max: 0.000g")
        self.stats_label.setFont(QFont("Consolas", 9))
        status_layout.addWidget(self.stats_label)
        
        status_layout.addStretch()
        
        # 차트 이름
        name_label = QLabel(f"📊 {self.name}")
        name_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        status_layout.addWidget(name_label)
        
        return status_widget
    
    def _init_chart(self):
        """Initialize chart"""
        self.ax = self.figure.add_subplot(111)
        
        # 빈 선 그래프 생성
        label = 'Equivalent Gram (g)' if self.is_calibrated else 'Voltage (mV)'
        self.line, = self.ax.plot([], [], 
                                  color=self.config.line_color, 
                                  linewidth=self.config.line_width,
                                  label=label)
        
        # Axis settings
        self.ax.set_xlabel('Time (sec)')
        self._update_y_axis_label()  # 캘리브레이션 상태에 따른 y축 라벨
        self.ax.set_title(f'{self.name}')
        self.ax.grid(True, alpha=self.config.grid_alpha)
        self.ax.legend()
        
        # 초기 범위 설정
        self.ax.set_xlim(0, self.config.time_window)
        
        # 캘리브레이션 상태에 따른 y축 범위 설정
        if self.is_calibrated:
            # 그램 단위일 때: 동적 스케일링 사용
            y_range = self.y_axis_manager.get_y_range([])  # 빈 데이터로 기본 범위
            self.ax.set_ylim(y_range[0], y_range[1])
            self.current_y_max = y_range[1]
            # Y축 틱을 자동으로 설정하도록 함
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        else:
            # 전압 단위일 때: 0 ~ 15V
            self.ax.set_ylim(0, 15)
            # Y축 틱을 자동으로 설정하도록 함
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        
        # X축 tick을 역순으로 설정 (30, 25, 20, 15, 10, 5, 0)
        import numpy as np
        tick_positions = np.arange(0, self.config.time_window + 1, 5)  # 5초 간격
        tick_labels = [str(int(self.config.time_window - pos)) for pos in tick_positions]  # 역순 라벨
        self.ax.set_xticks(tick_positions)
        self.ax.set_xticklabels(tick_labels)
        
        # tight layout
        self.figure.tight_layout()
        
        # 애니메이션 시작 (처음에는 정지 상태)
        self.anim = animation.FuncAnimation(
            self.figure, 
            self._update_animation, 
            interval=self.config.update_interval,
            blit=False,  # Y축 라벨 동적 업데이트를 위해 blit 비활성화
            cache_frame_data=False
        )
        self.anim.pause()  # 처음에는 정지
    
    def add_data_point(self, data_point: DataPoint):
        """Add data point"""
        current_time = time.time()
        
        # 데이터 추가
        self.data_points.append(data_point)
        
        # 값 추출
        # 캘리브레이션된 값이 있으면 우선 사용 (0이나 음수도 유효함)
        if data_point.calibrated_value is not None:
            value = data_point.calibrated_value
        elif data_point.filtered_value is not None:
            value = data_point.filtered_value
        else:
            value = data_point.raw_value
        
        # 전체 히스토리에 추가 (삭제하지 않음)
        self.full_time_history.append(current_time)
        self.full_value_history.append(value)
        
        # 스크롤 중이 아니면 최신 데이터로 뷰 업데이트
        if not self.is_scrolling:
            self.scroll_position = 1.0  # 최신 위치
            self._update_view_buffers()
            
        # 스크롤바 범위 업데이트
        self._update_scrollbar_range()
        
        # 최대값 추적
        if value > self.max_sensor_value:
            self.max_sensor_value = value
        
        # 첫 번째 데이터일 때 자동 시작
        if len(self.data_points) == 1 and not self.is_updating:
            self.start_updates()
        
        self._update_statistics()
    
    def _update_animation(self, frame):
        """Animation update (FuncAnimation callback)"""
        if not self.time_buffer:
            return self.line,
        
        # 스크롤 중일 때와 실시간일 때 다르게 처리
        if self.is_scrolling:
            # 스크롤 중 - 버퍼의 데이터를 그대로 표시
            if self.time_buffer:
                # 버퍼의 시간을 상대 시간으로 변환
                times = list(self.time_buffer)
                if times:
                    start_time = times[0]
                    relative_times = [(t - start_time) for t in times]
                    
                    self.line.set_data(relative_times, list(self.value_buffer))
                    
                    # Y축 범위 재계산
                    if self.value_buffer:
                        if self.is_calibrated:
                            # 그램 단위: 진정한 동적 스케일링
                            current_data = list(self.value_buffer)
                            y_range = self.y_axis_manager.get_y_range(current_data, self.current_y_max)
                            old_y_max = self.current_y_max
                            self.ax.set_ylim(y_range[0], y_range[1])
                            self.current_y_max = y_range[1]
                            # Y축 틱을 자동으로 업데이트
                            old_ticks = self.ax.get_yticks()
                            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
                            new_ticks = self.ax.get_yticks()
                            # Y축 범위가 변경된 경우에만 처리 (향후 로그 등 추가 가능)
                            if abs(y_range[1] - old_y_max) > 0.1:
                                pass  # 필요시 추가 처리
                        else:
                            # 전압 단위: 기존 자동 스케일
                            y_min = min(self.value_buffer) * 0.95
                            y_max = max(self.value_buffer) * 1.05
                            if y_max - y_min < 10:
                                y_center = (y_max + y_min) / 2
                                y_min = y_center - 5
                                y_max = y_center + 5
                            self.ax.set_ylim(y_min, y_max)
                            # Y축 틱을 자동으로 업데이트
                            old_ticks = self.ax.get_yticks()
                            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
                            new_ticks = self.ax.get_yticks()
        else:
            # 실시간 모드 - 현재 시간 기준 상대 시간 (오른쪽이 최신)
            current_time = time.time()
            relative_times = [current_time - t for t in self.time_buffer]
            relative_times = [self.config.time_window - rt for rt in relative_times]  # 뒤집기
            
            self.line.set_data(relative_times, list(self.value_buffer))
        
        # X축 범위 (항상 윈도우 크기 고정)
        self.ax.set_xlim(0, self.config.time_window)
        
        # Y축 범위 설정 (캘리브레이션 상태에 따라)
        if self.is_calibrated and self.value_buffer:
            # 그램 단위: 진정한 동적 스케일링
            current_data = list(self.value_buffer)
            y_range = self.y_axis_manager.get_y_range(current_data, self.current_y_max)
            old_y_max = self.current_y_max
            self.ax.set_ylim(y_range[0], y_range[1])
            self.current_y_max = y_range[1]
            # Y축 틱을 자동으로 업데이트
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
            # Y축 범위가 변경된 경우에만 처리 (향후 로그 등 추가 가능)
            if abs(y_range[1] - old_y_max) > 0.1:
                pass  # 필요시 추가 처리
        elif not self.is_calibrated and self.value_buffer:
            # 전압 단위: 기존 자동 스케일
            y_min = min(self.value_buffer) * 0.95
            y_max = max(self.value_buffer) * 1.05
            if y_max - y_min < 10:  # 최소 범위 보장
                y_center = (y_max + y_min) / 2
                y_min = y_center - 5
                y_max = y_center + 5
            self.ax.set_ylim(y_min, y_max)
            # Y축 틱을 자동으로 업데이트
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        
        return self.line,
    
    def start_updates(self):
        """Start updates and animation"""
        self.is_updating = True
        self.is_measuring = True  # 측정 시작
        
        # 애니메이션 시작/재시작
        if hasattr(self, 'anim') and self.anim is not None:
            try:
                if hasattr(self.anim, 'event_source') and not self.anim.event_source:
                    # 이벤트 소스가 중지된 경우 재시작
                    self.anim.event_source.start()
                else:
                    self.anim.resume()
            except Exception as e:
                self.logger.debug(f"Animation start error (ignored): {e}")
        
        if hasattr(self, 'play_action'):
            self.play_action.setChecked(True)
            self.play_action.setIcon(qta.icon('fa5s.pause'))
            self.play_action.setText("Stop")
        
        self.logger.info(f"Chart '{self.name}' updates started")
    
    def stop_updates(self):
        """Stop updates and animation completely"""
        self.is_updating = False
        self.is_measuring = False  # 측정 중단
        
        # 애니메이션 완전 중지
        if hasattr(self, 'anim') and self.anim is not None:
            try:
                self.anim.pause()  # 먼저 일시 정지
                self.anim.event_source.stop()  # 이벤트 소스 중지
            except Exception as e:
                self.logger.debug(f"Animation stop error (ignored): {e}")
        
        if hasattr(self, 'play_action'):
            self.play_action.setChecked(False)
            self.play_action.setIcon(qta.icon('fa5s.play'))
            self.play_action.setText("Start")
        
        self.logger.info(f"Chart '{self.name}' updates and animation stopped")
    
    def _confirm_clear_data(self):
        """Confirm before clearing data"""
        # 데이터가 있는 경우에만 확인
        if self.data_points and len(self.data_points) > 0:
            from PyQt6.QtWidgets import QMessageBox
            
            reply = QMessageBox.question(
                self,
                "Clear Data Confirmation",
                f"Are you sure you want to clear all data?\n\n"
                f"Chart: {self.name}\n"
                f"Data points: {len(self.data_points)} points\n\n"
                "This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.clear_data()
        else:
            # 데이터가 없으면 바로 초기화
            self.clear_data()
    
    def clear_data(self):
        """Clear data"""
        self.data_points.clear()
        self.time_buffer.clear()
        self.value_buffer.clear()
        
        # 히스토리도 초기화
        self.full_time_history.clear()
        self.full_value_history.clear()
        
        self.max_sensor_value = float('-inf')
        self.scroll_position = 1.0
        self.is_scrolling = False
        
        # 스크롤바 초기화
        self.scrollbar.setValue(100)
        
        # Y축 범위 초기화 (캘리브레이션 상태에 따라)
        if self.is_calibrated:
            # 그램 단위: 기본 범위로 초기화
            y_range = self.y_axis_manager.get_y_range([])  # 빈 데이터로 기본 범위
            self.ax.set_ylim(y_range[0], y_range[1])
            self.current_y_max = y_range[1]
            # Y축 틱을 자동으로 설정
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        else:
            self.ax.set_ylim(0, 15)
            # Y축 틱을 자동으로 설정
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        
        # 빈 라인 설정
        self.line.set_data([], [])
        self.canvas.draw()
        
        # 통계 테이블도 초기화
        self._clear_statistics_table()
        
        self.logger.info(f"Chart '{self.name}' data cleared")
        self._update_statistics()
    
    def _clear_statistics_table(self):
        """Clear statistics table for this chart"""
        try:
            # 부모 워크벤치 위젯 찾기
            parent_widget = self.parent()
            while parent_widget:
                if hasattr(parent_widget, 'statistics_table'):
                    # 통계 테이블의 이 차트 데이터 리셋
                    parent_widget.statistics_table.reset_chart_statistics(self.name)
                    self.logger.debug(f"Statistics table cleared for chart '{self.name}'")
                    break
                parent_widget = parent_widget.parent()
        except Exception as e:
            self.logger.debug(f"Could not clear statistics table: {e}")
    
    def _toggle_updates(self):
        """Toggle updates"""
        if self.is_updating:
            self.stop_updates()
        else:
            self.start_updates()
    
    def _on_scroll_changed(self, value):
        """Scroll change event"""
        self.scroll_position = value / 100.0  # 0.0 ~ 1.0
        
        # 스크롤 중인지 확인 (최신 위치가 아니면 스크롤 중)
        self.is_scrolling = (self.scroll_position < 1.0)
        
        # 뷰 버퍼 업데이트
        self._update_view_buffers()
        
        # 스크롤 시 즉시 차트 업데이트
        if self.time_buffer:
            self._update_chart_immediately()
    
    def _go_to_latest(self):
        """Go to latest data"""
        self.is_scrolling = False
        self.scroll_position = 1.0
        self._update_view_buffers()
        self.scrollbar.setValue(100)
        
        self.logger.info("Automatically returned to latest data")
    
    def _update_chart_immediately(self):
        """Update chart immediately during scroll"""
        if not self.time_buffer:
            return
        
        try:
            # 시간을 상대 시간으로 변환
            times = list(self.time_buffer)
            start_time = times[0]
            relative_times = [(t - start_time) for t in times]
            
            # 라인 데이터 설정
            self.line.set_data(relative_times, list(self.value_buffer))
            
            # Y축 범위 재계산 - 캘리브레이션 상태에 따라 분기
            if self.value_buffer:
                if self.is_calibrated:
                    # 그램 모드: 동적 스케일링 사용
                    current_data = list(self.value_buffer)
                    y_range = self.y_axis_manager.get_y_range(current_data, self.current_y_max)
                    self.ax.set_ylim(y_range[0], y_range[1])
                    self.current_y_max = y_range[1]
                    # Y축 틱을 자동으로 업데이트
                    self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
                else:
                    # 전압 모드: 기존 로직 유지
                    y_min = min(self.value_buffer) * 0.95
                    y_max = max(self.value_buffer) * 1.05
                    if y_max - y_min < 10:
                        y_center = (y_max + y_min) / 2
                        y_min = y_center - 5
                        y_max = y_center + 5
                    self.ax.set_ylim(y_min, y_max)
            
            # X축 범위 설정
            if relative_times:
                self.ax.set_xlim(0, self.config.time_window)
            
            # 캔버스 다시 그리기
            self.canvas.draw()
            
        except Exception as e:
            self.logger.error(f"Chart update error during scroll: {e}")
    
    def _update_statistics(self):
        """Update statistics"""
        count = len(self.data_points)
        max_val = self.max_sensor_value if self.max_sensor_value != float('-inf') else 0
        
        text = f"Data: {count} points | Max: {max_val:.3f}g"
        if hasattr(self, 'stats_label'):
            self.stats_label.setText(text)
    
    def get_visible_data(self) -> List[DataPoint]:
        """Return visible DataPoint objects for export"""
        if not self.data_points:
            return []
        
        # 측정 중일 때만 시간 윈도우 적용, 측정 완료 후에는 모든 데이터 반환
        if self.is_measuring:
            # 실시간 측정 중: 현재 보이는 시간 범위의 데이터만 반환
            current_time = time.time()
            visible_data = []
            
            for dp in self.data_points:
                time_diff = current_time - dp.timestamp
                if time_diff <= self.config.time_window:
                    visible_data.append(dp)
            
            return visible_data
        else:
            # 측정 완료: 모든 데이터 반환 (시간에 관계없이)
            return list(self.data_points)
    
    def cleanup(self):
        """Clean up resources"""
        # 애니메이션 정지
        if hasattr(self, 'anim'):
            self.anim.event_source.stop()
        
        # 데이터 초기화
        self.clear_data()
        
        self.logger.info(f"Chart widget '{self.name}' resources cleaned up")

    def generate_image(self, format='png', width=1800, height=800, dpi=120):
        """Generate chart image for export"""
        try:
            # 현재 figure의 크기, DPI, 축 설정 저장
            original_size = self.figure.get_size_inches()
            original_dpi = self.figure.get_dpi()
            original_ylim = self.ax.get_ylim()
            original_yticks = self.ax.get_yticks()
            original_yticklabels = [t.get_text() for t in self.ax.get_yticklabels()]
            original_xlim = self.ax.get_xlim()
            original_xticks = self.ax.get_xticks()
            original_xticklabels = [t.get_text() for t in self.ax.get_xticklabels()]
            
            # 더 높은 DPI로 고품질 이미지 생성 (최종 크기는 스케일링으로 조정)
            export_dpi = max(dpi, 450)  # 최소 450 DPI로 생성
            
            # 출력용 크기와 DPI 설정
            fig_width = width / export_dpi
            fig_height = height / export_dpi
            self.figure.set_size_inches(fig_width, fig_height)
            self.figure.set_dpi(export_dpi)
            
            # matplotlib 품질 설정 임시 변경
            import matplotlib
            original_rcParams = matplotlib.rcParams.copy()
            matplotlib.rcParams.update({
                'figure.dpi': export_dpi,
                'savefig.dpi': export_dpi,
                'font.size': 2,                # 폰트 크기를 매우 작게 (4 → 2)
                'axes.titlesize': 3,           # 제목 폰트 크기
                'axes.labelsize': 2.5,         # 축 라벨 폰트 크기
                'xtick.labelsize': 2,          # X축 틱 라벨 폰트 크기
                'ytick.labelsize': 2,          # Y축 틱 라벨 폰트 크기
                'legend.fontsize': 2,          # 범례 폰트 크기
                'axes.linewidth': 0.5,        # 축 선 굵기 감소 (더 깔끔하게)
                'axes.grid.axis': 'both',      # x, y축 모두 그리드 표시
                'grid.linewidth': 1.0,        # 그리드 선 굵기 증가
                'grid.alpha': 0.4,            # 그리드 투명도 약간 증가
                'lines.linewidth': 0.5,       # 데이터 선 굵기 감소 (더 세련되게)
                'lines.markersize': 1,        # 마커 크기 약간 감소
                'text.antialiased': True,
                'figure.autolayout': False,
                'savefig.facecolor': 'white',
                'savefig.edgecolor': 'none',
                'savefig.bbox': 'tight',
                'savefig.pad_inches': 0.1
            })
            
            # y축 범위와 틱 설정 (UI 차트와 동일한 범위 사용)
            import numpy as np
            
            # X축 범위와 틱을 UI 차트와 동일하게 설정
            self.ax.set_xlim(original_xlim)
            self.ax.set_xticks(original_xticks)
            self.ax.set_xticklabels(original_xticklabels)
            
            if self.is_calibrated:
                # 캘리브레이션 모드: 현재 UI 차트의 Y축 범위와 틱을 그대로 사용
                self.ax.set_ylim(original_ylim)
                self.ax.set_yticks(original_yticks)
                self.ax.set_yticklabels(original_yticklabels)
            else:
                # 전압 모드: 기존 고정 범위 사용
                self.ax.set_ylim(510, 580)
                yticks = np.arange(510, 581, 10)  # 510부터 580까지 10씩 증가
                self.ax.set_yticks(yticks)
                self.ax.set_yticklabels([f"{int(y)}" for y in yticks])
            
            # 그리드를 모든 틱 위치에 표시 (10 간격으로 모든 라벨에 그리드 선)
            self.ax.grid(True, axis='both', alpha=0.4, linewidth=1.0)
            
            # 이미지 생성
            buffer = io.BytesIO()
            self.figure.savefig(
                buffer, 
                format=format.lower(),
                dpi=export_dpi,
                bbox_inches='tight',
                facecolor='white',
                edgecolor='none',
                pad_inches=0.1,
                metadata={'Title': f'Chart: {self.name}'}
            )
            buffer.seek(0)
            
            # matplotlib 설정 복원
            matplotlib.rcParams.update(original_rcParams)
            
            # 원래 크기, DPI, 축 설정 복원
            self.figure.set_size_inches(original_size)
            self.figure.set_dpi(original_dpi)
            self.ax.set_xlim(original_xlim)
            self.ax.set_xticks(original_xticks)
            self.ax.set_xticklabels(original_xticklabels)
            self.ax.set_ylim(original_ylim)
            self.ax.set_yticks(original_yticks)
            self.ax.set_yticklabels(original_yticklabels)
            self.canvas.draw()
            
            return buffer.getvalue()
            
        except Exception as e:
            self.logger.error(f"Failed to generate chart image: {e}")
            return None

    def _update_view_buffers(self):
        """Update view buffers based on current scroll position"""
        if not self.full_time_history:
            return
        
        # 전체 데이터를 리스트로 변환
        full_times = list(self.full_time_history)
        full_values = list(self.full_value_history)
        
        if not full_times:
            return
        
        # 전체 시간 범위
        total_duration = full_times[-1] - full_times[0] if len(full_times) > 1 else self.config.time_window
        
        # 스크롤 위치에 따른 종료 시점 계산
        if self.scroll_position >= 1.0:
            # 최신 데이터
            end_time = full_times[-1]
        else:
            # 스크롤 위치를 전체 데이터 범위에 매핑
            available_scroll_range = total_duration - self.config.time_window
            if available_scroll_range > 0:
                # 스크롤 가능한 범위가 있는 경우
                end_time = full_times[0] + self.config.time_window + (available_scroll_range * self.scroll_position)
            else:
                # 전체 데이터가 윈도우보다 작은 경우
                end_time = full_times[-1]
        
        # 윈도우 시작 시점
        start_time = end_time - self.config.time_window
        
        # 해당 범위의 데이터 추출
        self.time_buffer.clear()
        self.value_buffer.clear()
        
        for t, v in zip(full_times, full_values):
            if start_time <= t <= end_time:
                self.time_buffer.append(t)
                self.value_buffer.append(v)

    def _update_scrollbar_range(self):
        """Update scrollbar range and page size"""
        if not self.full_time_history or len(self.full_time_history) < 2:
            # 데이터가 부족할 때는 전체 크기로 설정
            self.scrollbar.setEnabled(False)
            self.scrollbar.setPageStep(100)  # 전체 크기
            self.scrollbar.setValue(100)
            return
        
        # 전체 데이터 기간 계산
        full_times = list(self.full_time_history)
        total_duration = full_times[-1] - full_times[0]
        
        if total_duration <= self.config.time_window:
            # 윈도우보다 작거나 같으면 스크롤 불필요
            self.scrollbar.setEnabled(False)
            self.scrollbar.setPageStep(100)
            self.scrollbar.setValue(100)
        else:
            # 스크롤 필요
            self.scrollbar.setEnabled(True)
            # 페이지 크기 = (윈도우 크기 / 전체 기간) * 100
            page_step = int((self.config.time_window / total_duration) * 100)
            self.scrollbar.setPageStep(max(page_step, 1))
            
            # 현재 스크롤 위치 유지 (단, 최신 데이터가 추가되었으면 자동으로 최신으로)
            if not self.is_scrolling:
                self.scrollbar.setValue(100)
    
    def _update_y_axis_label(self):
        """캘리브레이션 상태에 따른 y축 라벨 업데이트"""
        if self.is_calibrated:
            self.ax.set_ylabel('Equivalent Gram (g)')
        else:
            self.ax.set_ylabel('Voltage (V)')
        
        # 캔버스 다시 그리기 (차트가 이미 초기화된 경우에만)
        if hasattr(self, 'canvas'):
            self.canvas.draw()
    
    def _update_line_label(self):
        """캘리브레이션 상태에 따른 라인 라벨 업데이트"""
        if hasattr(self, 'line'):
            label = 'Equivalent Gram (g)' if self.is_calibrated else 'Voltage (mV)'
            self.line.set_label(label)
            self.ax.legend()
            
            # 캔버스 다시 그리기 (차트가 이미 초기화된 경우에만)
            if hasattr(self, 'canvas'):
                self.canvas.draw()
    
    def set_calibration_status(self, is_calibrated: bool):
        """
        캘리브레이션 상태 설정
        
        Args:
            is_calibrated: True = gram 단위, False = voltage 단위
        """
        if self.is_calibrated != is_calibrated:
            self.is_calibrated = is_calibrated
            self._update_y_axis_label()
            self._update_line_label()
            
            # 동적 스케일링 활성화/비활성화
            self.y_axis_manager.set_enabled(is_calibrated)
        
        # Y축 범위 업데이트 (상태 변경 여부와 관계없이 항상 실행)
        if is_calibrated:
            # 그램 단위: 동적 스케일링 사용
            current_data = list(self.value_buffer) if self.value_buffer else []
            y_range = self.y_axis_manager.get_y_range(current_data)
            self.ax.set_ylim(y_range[0], y_range[1])
            self.current_y_max = y_range[1]
            # Y축 틱을 자동으로 설정
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        else:
            # 전압 단위: 0 ~ 15V
            self.ax.set_ylim(0, 15)
            # Y축 틱을 자동으로 설정
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
        
        # 차트 다시 그리기
        if hasattr(self, 'canvas'):
            self.canvas.draw_idle()
            
            self.logger.info(f"Chart units changed to {'gram' if is_calibrated else 'voltage'} (Dynamic scaling: {'enabled' if is_calibrated else 'disabled'})")
    
    def get_current_unit(self) -> str:
        """현재 단위 반환"""
        return "g" if self.is_calibrated else "V"
    
    # === 진정한 동적 Y축 스케일링 관련 메서드들 ===
    
    def set_dynamic_scaling_enabled(self, enabled: bool):
        """동적 스케일링 활성화/비활성화"""
        self.y_axis_manager.set_enabled(enabled)
        
        if self.is_calibrated:
            # 현재 데이터에 맞는 Y축 범위 적용
            current_data = list(self.value_buffer) if self.value_buffer else []
            y_range = self.y_axis_manager.get_y_range(current_data)
            self.ax.set_ylim(y_range[0], y_range[1])
            self.current_y_max = y_range[1]
            # Y축 틱을 자동으로 설정
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
            self.canvas.draw_idle()
        
        self.logger.info(f"Dynamic Y-axis scaling {'enabled' if enabled else 'disabled'}")
    
    def is_dynamic_scaling_enabled(self) -> bool:
        """동적 스케일링 활성화 상태 확인"""
        return self.y_axis_manager.is_enabled()
    
    def get_current_y_range(self) -> tuple:
        """현재 Y축 범위 반환"""
        return self.ax.get_ylim()
    
    def set_y_margin(self, margin: float):
        """Y축 상단 여유분 설정 (그램)"""
        self.y_axis_manager.set_margin(margin)
        
        # 현재 데이터에 새 여유분 적용
        if self.is_calibrated and self.value_buffer:
            current_data = list(self.value_buffer)
            y_range = self.y_axis_manager.get_y_range(current_data, self.current_y_max)
            self.ax.set_ylim(y_range[0], y_range[1])
            self.current_y_max = y_range[1]
            # Y축 틱을 자동으로 설정
            old_ticks = self.ax.get_yticks()
            self.ax.yaxis.set_major_locator(plt.MaxNLocator(nbins='auto'))
            new_ticks = self.ax.get_yticks()
            self.canvas.draw_idle()
    
    def get_y_margin(self) -> float:
        """현재 Y축 여유분 반환"""
        return self.y_axis_manager.margin