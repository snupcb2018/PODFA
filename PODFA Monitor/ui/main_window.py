"""
PBS 2.0 Main Window
====================

PBS 계측기 2.0 메인 윈도우
- 현대적인 UI/UX
- 인터랙티브 차트 위젯 통합
- 시리얼 통신 관리
- 향상된 저장 기능
"""

import os
import logging
import time
from typing import List, Optional, Dict
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QToolBar, QStatusBar,
    QComboBox, QLabel, QPushButton, QTabWidget,
    QFileDialog, QMessageBox, QDialog, QLineEdit,
    QProgressBar, QSplitter, QWizard
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QAction
import qtawesome as qta

from core.serial_manager import SerialManager, SerialConfig, ConnectionState
from core.data_processor import DataProcessor, DataPoint
from core.calibration import CalibrationEngine
from utils.excel_exporter import ExcelExporter, ExportOptions
from ui.chart_widget import ChartWidget
from ui.filter_settings_dialog import FilterSettingsDialog
from ui.statistics_table_widget import StatisticsTableWidget
from ui.calibration.calibration_wizard import CalibrationWizard


class WorkbenchWidget(QWidget):
    """워크벤치 위젯 - 차트들과 통계 테이블을 관리"""
    
    chart_tab_changed = pyqtSignal(int)  # 차트 탭 변경 시그널
    modified_changed = pyqtSignal(bool)  # 수정 상태 변경 시그널
    
    def __init__(self, name: str, path: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.path = path
        self.chart_widgets: List[ChartWidget] = []
        self.is_modified = False  # 수정 상태 추적
        
        self._init_ui()
    
    def _init_ui(self):
        """UI 초기화"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 수직 스플리터 (위: 차트, 아래: 통계 테이블)
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 상단: 차트 영역
        self.chart_tabs = QTabWidget()
        self.chart_tabs.setTabsClosable(True)
        self.chart_tabs.tabCloseRequested.connect(self._close_chart_tab)
        self.chart_tabs.currentChanged.connect(self._on_chart_tab_changed)
        self.main_splitter.addWidget(self.chart_tabs)
        
        # 하단: 통계 테이블 영역
        self.statistics_table = StatisticsTableWidget()
        self.statistics_table.chart_selected.connect(self._on_chart_selected_from_table)
        self.main_splitter.addWidget(self.statistics_table)
        
        # 스플리터 초기 비율 설정 (차트:테이블 = 70:30)
        self.main_splitter.setSizes([700, 300])
        self.main_splitter.setChildrenCollapsible(False)  # 영역 완전 접기 방지
        
        layout.addWidget(self.main_splitter)
        self.setLayout(layout)
    
    def add_chart(self, name: str) -> ChartWidget:
        """새 차트 추가"""
        chart_widget = ChartWidget(name)
        self.chart_widgets.append(chart_widget)
        
        # 메인 윈도우의 data_processor에서 캘리브레이션 상태 확인 및 적용
        main_window = self.window()  # 메인 윈도우 가져오기
        if hasattr(main_window, 'data_processor'):
            is_calibrated = main_window.data_processor.is_calibrated()
            if is_calibrated:
                chart_widget.set_calibration_status(True)
        
        # 탭에 추가
        index = self.chart_tabs.addTab(chart_widget, name)
        self.chart_tabs.setCurrentIndex(index)
        
        # 통계 테이블에 차트 추가
        self.statistics_table.add_chart(chart_widget)
        
        # 수정 상태 설정
        self.set_modified(True)
        
        return chart_widget
    
    def get_current_chart(self) -> Optional[ChartWidget]:
        """현재 활성 차트 반환"""
        current_widget = self.chart_tabs.currentWidget()
        if isinstance(current_widget, ChartWidget):
            return current_widget
        return None
    
    def _close_chart_tab(self, index: int):
        """차트 탭 닫기"""
        widget = self.chart_tabs.widget(index)
        if isinstance(widget, ChartWidget):
            # 저장되지 않은 상태라면 경고
            parent_window = self.window()
            if self.is_modified and isinstance(parent_window, MainWindow):
                reply = QMessageBox.warning(
                    self,
                    "Delete Chart Confirmation",
                    f"The workbench is not saved.\nAre you sure you want to delete '{widget.name}' chart?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # 통계 테이블에서 차트 제거
            self.statistics_table.remove_chart(widget.name)
            
            # 정리
            widget.cleanup()
            self.chart_widgets.remove(widget)
            
            # 수정 상태 설정
            self.set_modified(True)
        
        self.chart_tabs.removeTab(index)
    
    def _on_chart_tab_changed(self, index: int):
        """차트 탭 변경 시 통계 업데이트"""
        # MainWindow에 차트 탭 변경 알림
        self.chart_tab_changed.emit(index)
        
        current_chart = self.get_current_chart()
        if current_chart and hasattr(self, 'statistics_table'):
            # 현재 차트의 통계 업데이트
            self.statistics_table.update_chart_focus(current_chart.name)
    
    def _on_chart_selected_from_table(self, chart_name: str):
        """통계 테이블에서 차트 선택 시 해당 차트 탭으로 이동"""
        for i in range(self.chart_tabs.count()):
            widget = self.chart_tabs.widget(i)
            if isinstance(widget, ChartWidget) and widget.name == chart_name:
                self.chart_tabs.setCurrentIndex(i)
                break
    
    def _update_chart_statistics(self, chart_widget: ChartWidget):
        """차트 통계 업데이트"""
        if hasattr(chart_widget, 'data_points'):
            # ChartWidget의 데이터 포인트를 통계 테이블에 업데이트
            self.statistics_table.update_chart_statistics(
                chart_widget.name, 
                list(chart_widget.data_points)
            )
    
    def update_all_statistics(self):
        """모든 차트의 통계 업데이트"""
        for chart_widget in self.chart_widgets:
            self._update_chart_statistics(chart_widget)
    
    def set_modified(self, modified: bool):
        """수정 상태 설정"""
        if self.is_modified != modified:
            self.is_modified = modified
            self.modified_changed.emit(modified)
    
    def save(self):
        """워크벤치 저장 (구현 필요)"""
        # TODO: 실제 저장 로직 구현
        self.set_modified(False)
        return True



class MainWindow(QMainWindow):
    """
    🏠 PBS 2.0 메인 윈도우
    
    Features:
    - 현대적인 UI/UX
    - 시리얼 통신 관리
    - 인터랙티브 차트
    - 향상된 저장 기능
    """
    
    def __init__(self):
        super().__init__()
        
        # 로깅
        self.logger = logging.getLogger(__name__)
        
        # 설정 - INI 파일로 저장
        settings_path = Path(__file__).parent.parent / "settings" / "pbs_settings.ini"
        settings_path.parent.mkdir(exist_ok=True)  # settings 폴더 생성
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        
        # 시스템 컴포넌트
        self.serial_manager = SerialManager()
        self.data_processor = DataProcessor()
        self.calibration_engine = CalibrationEngine()
        self.excel_exporter = ExcelExporter()
        
        # UI 상태
        self.workbenches: List[WorkbenchWidget] = []
        self.is_measuring = False
        
        # 타이머
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)  # 1초마다 상태 업데이트
        
        # UI 초기화
        self._init_ui()
        self._connect_signals()
        self._restore_settings()
        
        # 환영 메시지
        self.statusBar().showMessage("PODFA Ready! 🚀", 3000)
        
        self.logger.info("메인 윈도우 초기화 완료")
        
        # 현재 캘리브레이션 상태 확인 (초기화 완료 후)
        QTimer.singleShot(1000, self._check_initial_calibration_status)
    
    def _init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("PODFA")
        self.setGeometry(100, 100, 1400, 900)
        
        # 아이콘 설정 (기본 아이콘 사용)
        self.setWindowIcon(qta.icon('fa5s.chart-line'))
        
        # 중앙 위젯
        self.workbench_tabs = QTabWidget()
        self.workbench_tabs.setTabsClosable(True)
        self.workbench_tabs.tabCloseRequested.connect(self._close_workbench)
        self.setCentralWidget(self.workbench_tabs)
        
        # 메뉴 바 생성
        self._create_menu_bar()
        
        # 툴 바 생성
        self._create_tool_bar()
        
        # 상태 바 생성
        self._create_status_bar()
        
        # 스타일 적용
        self._apply_modern_style()
    
    def _create_menu_bar(self):
        """메뉴 바 생성"""
        menubar = self.menuBar()
        
        # File 메뉴
        file_menu = menubar.addMenu("File")
        
        new_workbench_action = QAction(qta.icon('fa5s.plus'), "New Workbench", self)
        new_workbench_action.setShortcut("Ctrl+N")
        new_workbench_action.triggered.connect(self._new_workbench)
        file_menu.addAction(new_workbench_action)
        
        file_menu.addSeparator()
        
        save_action = QAction(qta.icon('fa5s.save'), "Save Workbench", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_current_workbench)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction(qta.icon('fa5s.times'), "Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools 메뉴
        tools_menu = menubar.addMenu("Tools")
        
        calibration_action = QAction(qta.icon('fa5s.cogs'), "Calibration", self)
        calibration_action.triggered.connect(self._open_calibration)
        tools_menu.addAction(calibration_action)
        
        # Help 메뉴
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction(qta.icon('fa5s.info'), "About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _create_tool_bar(self):
        """툴 바 생성"""
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        # 워크벤치 관련
        new_workbench_action = QAction(qta.icon('fa5s.plus'), "New Workbench", self)
        new_workbench_action.triggered.connect(self._new_workbench)
        toolbar.addAction(new_workbench_action)
        
        add_chart_action = QAction(qta.icon('fa5s.chart-line'), "Add Chart", self)
        add_chart_action.triggered.connect(self._add_chart)
        toolbar.addAction(add_chart_action)
        self.add_chart_action = add_chart_action  # 참조 저장
        
        toolbar.addSeparator()
        
        # 측정 컨트롤
        self.start_stop_action = QAction(qta.icon('fa5s.play'), "Start", self)
        self.start_stop_action.triggered.connect(self._toggle_measurement)
        toolbar.addAction(self.start_stop_action)
        
        toolbar.addSeparator()
        
        # COM 포트 선택
        toolbar.addWidget(QLabel("COM Port:"))
        self.com_port_combo = QComboBox()
        self.com_port_combo.setMinimumWidth(100)
        self.com_port_combo.currentTextChanged.connect(self._on_com_port_changed)
        toolbar.addWidget(self.com_port_combo)
        
        # 포트 새로고침
        refresh_action = QAction(qta.icon('fa5s.sync'), "Refresh Ports", self)
        refresh_action.triggered.connect(self._refresh_ports)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        # 필터 설정
        filter_action = QAction(qta.icon('fa5s.filter'), "Filter Settings", self)
        filter_action.triggered.connect(self._open_filter_settings)
        filter_action.setToolTip("Data filter settings")
        toolbar.addAction(filter_action)
        
        toolbar.addSeparator()
        
        # 저장
        save_action = QAction(qta.icon('fa5s.save'), "Save", self)
        save_action.triggered.connect(self._save_current_workbench)
        toolbar.addAction(save_action)
        
        # 초기 상태 설정
        self._update_toolbar_state()
    
    def _create_status_bar(self):
        """상태 바 생성"""
        statusbar = self.statusBar()
        
        # 연결 상태
        self.connection_label = QLabel("🔴 Disconnected")
        statusbar.addWidget(self.connection_label)
        
        statusbar.addWidget(QLabel("|"))
        
        # 데이터 통계
        self.data_stats_label = QLabel("Data: 0 points")
        statusbar.addWidget(self.data_stats_label)
        
        statusbar.addWidget(QLabel("|"))
        
        # 진행률 바 (필요 시 사용)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        statusbar.addWidget(self.progress_bar)
        
        # 오른쪽 정렬
        statusbar.addPermanentWidget(QLabel("PODFA Ready"))
    
    def _apply_modern_style(self):
        """현대적인 스타일 적용"""
        # 폰트 설정
        font = QFont("Segoe UI", 9)
        self.setFont(font)
        
        # 툴바 스타일
        for toolbar in self.findChildren(QToolBar):
            toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    
    def _connect_signals(self):
        """시그널 연결"""
        # 시리얼 매니저 시그널
        self.serial_manager.data_received.connect(self._on_serial_data)
        self.serial_manager.connection_changed.connect(self._on_connection_changed)
        self.serial_manager.port_list_updated.connect(self._on_ports_updated)
        self.serial_manager.error_occurred.connect(self._on_serial_error)
        
        # 데이터 프로세서 시그널
        self.data_processor.data_processed.connect(self._on_data_processed)
        self.data_processor.calibration_status_changed.connect(self._on_calibration_status_changed)
    
    def _restore_settings(self):
        """설정 복원"""
        # 윈도우 위치 복원
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        # 포트 목록 먼저 초기화 (저장된 포트 복원은 _refresh_ports에서 처리)
        self._refresh_ports()
        
        # 저장된 COM 포트 정보 로그 출력
        saved_port = self.settings.value("com_port", "")
        if saved_port:
            self.logger.info(f"마지막 사용 COM 포트: {saved_port}")
        else:
            self.logger.info("저장된 COM 포트 없음")
        
        # 필터 설정 복원
        self._restore_filter_settings()
        
        # 캘리브레이션 설정 복원
        self._restore_calibration_settings()
    
    def _restore_filter_settings(self):
        """필터 설정 복원"""
        try:
            from core.data_processor import ProcessingConfig, FilterType
            
            # 저장된 필터 설정 불러오기
            filter_type_str = self.settings.value("filter/type", "moving_average")
            filter_window = int(self.settings.value("filter/window", 5))
            butterworth_cutoff = float(self.settings.value("filter/butterworth_cutoff", 1.0))
            butterworth_order = int(self.settings.value("filter/butterworth_order", 2))
            sampling_rate = float(self.settings.value("filter/sampling_rate", 10.0))
            
            # FilterType 변환
            filter_type_map = {
                'none': FilterType.NONE,
                'moving_average': FilterType.MOVING_AVERAGE,
                'median': FilterType.MEDIAN,
                'butterworth': FilterType.BUTTERWORTH
            }
            filter_type = filter_type_map.get(filter_type_str, FilterType.MOVING_AVERAGE)
            
            # 새 설정 생성
            new_config = ProcessingConfig(
                filter_type=filter_type,
                filter_window=filter_window,
                butterworth_cutoff=butterworth_cutoff,
                butterworth_order=butterworth_order,
                sampling_rate=sampling_rate,
                # 기존 설정 유지
                max_buffer_size=self.data_processor.config.max_buffer_size,
                outlier_threshold=self.data_processor.config.outlier_threshold,
                enable_auto_scaling=self.data_processor.config.enable_auto_scaling,
                statistics_window=self.data_processor.config.statistics_window,
                quality_threshold=self.data_processor.config.quality_threshold
            )
            
            # DataProcessor에 적용
            self.data_processor.update_config(new_config)
            
            # 로그 출력
            filter_names = {
                FilterType.NONE: '없음',
                FilterType.MOVING_AVERAGE: '이동평균',
                FilterType.MEDIAN: '중앙값',
                FilterType.BUTTERWORTH: 'Butterworth'
            }
            filter_name = filter_names.get(filter_type, '알 수 없음')
            
            if filter_type == FilterType.BUTTERWORTH:
                self.logger.info(
                    f"필터 설정 복원: {filter_name} (cutoff: {butterworth_cutoff}Hz, "
                    f"order: {butterworth_order}, sampling: {sampling_rate}Hz)"
                )
            elif filter_type in [FilterType.MOVING_AVERAGE, FilterType.MEDIAN]:
                self.logger.info(f"필터 설정 복원: {filter_name} (window: {filter_window})")
            else:
                self.logger.info(f"필터 설정 복원: {filter_name}")
                
        except Exception as e:
            self.logger.warning(f"필터 설정 복원 실패, 기본값 사용: {e}")
            # 기본값으로 진행
    
    def _save_calibration_settings(self):
        """캘리브레이션 설정 저장"""
        try:
            if self.data_processor and self.data_processor.calibration_result:
                result = self.data_processor.calibration_result
                
                # 캘리브레이션 데이터 저장
                self.settings.setValue("calibration/method", result.method.value)
                self.settings.setValue("calibration/coefficients", result.coefficients)
                self.settings.setValue("calibration/r_squared", result.r_squared)
                self.settings.setValue("calibration/rmse", result.rmse)
                self.settings.setValue("calibration/quality_grade", result.quality_grade)
                self.settings.setValue("calibration/validation_passed", result.validation_passed)
                
                # 캘리브레이션 포인트들 저장 (간단화)
                points_data = []
                for point in result.points:
                    points_data.append({
                        'weight': point.reference_weight,  # reference_weight 사용
                        'average_reading': point.average_reading,
                        'std_reading': point.std_reading,
                        'quality_score': point.quality_score
                    })
                
                import json
                self.settings.setValue("calibration/points", json.dumps(points_data))
                self.settings.setValue("calibration/enabled", True)
                
                self.logger.info("캘리브레이션 설정 저장됨")
            else:
                # 캘리브레이션이 없는 경우 - 기존 enabled 값을 유지
                self.logger.info("캘리브레이션 없음 - 기존 설정 유지")
        except Exception as e:
            self.logger.error(f"캘리브레이션 설정 저장 실패: {e}")
    
    def _restore_calibration_settings(self):
        """캘리브레이션 설정 복원"""
        try:
            self.logger.info("🔄 캘리브레이션 설정 복원 시작...")
            
            calibration_enabled = self.settings.value("calibration/enabled", False, type=bool)
            self.logger.info(f"📋 calibration/enabled: {calibration_enabled}")
            
            if not calibration_enabled:
                self.logger.info("❌ 저장된 캘리브레이션 없음 (enabled=false)")
                return
            
            # CalibrationResult 임포트
            from core.calibration import CalibrationResult, CalibrationMethod, CalibrationPoint
            
            # 저장된 데이터 불러오기
            method_str = self.settings.value("calibration/method", "")
            coefficients_raw = self.settings.value("calibration/coefficients", [])
            
            # coefficients 처리 (문자열인 경우 파싱)
            if isinstance(coefficients_raw, str):
                # "2.5, 0.1" 형태의 문자열을 리스트로 변환
                coefficients = [float(x.strip()) for x in coefficients_raw.split(',')]
            elif isinstance(coefficients_raw, (list, tuple)):
                # 리스트/튜플인 경우 각 요소를 float로 변환
                coefficients = [float(x) for x in coefficients_raw]
            else:
                coefficients = []
            
            r_squared = float(self.settings.value("calibration/r_squared", 0.0))
            rmse = float(self.settings.value("calibration/rmse", 0.0))
            quality_grade = self.settings.value("calibration/quality_grade", "")
            validation_passed = self.settings.value("calibration/validation_passed", False, type=bool)
            
            # 메소드 변환
            method_map = {
                'linear': CalibrationMethod.LINEAR,
                'polynomial_2': CalibrationMethod.POLYNOMIAL_2,
                'polynomial_3': CalibrationMethod.POLYNOMIAL_3
            }
            method = method_map.get(method_str, CalibrationMethod.LINEAR)
            
            # 포인트 데이터 복원
            import json
            points_raw = self.settings.value("calibration/points", "[]")
            
            try:
                # 문자열인 경우 JSON 파싱
                if isinstance(points_raw, str):
                    points_data = json.loads(points_raw)
                else:
                    points_data = points_raw
                
                self.logger.info(f"📍 Points raw type: {type(points_raw)}")
                self.logger.info(f"📍 Points data: {points_data}")
                
                points = []
                for point_data in points_data:
                    self.logger.info(f"📍 Processing point: {point_data}")
                    
                    # CalibrationPoint는 reference_weight를 사용함
                    point = CalibrationPoint(
                        reference_weight=point_data['weight'],
                        sensor_readings=[point_data['average_reading']],  # 평균값으로 센서 데이터 시뮬레이션
                        collection_time=time.time(),  # 현재 시간
                        quality_score=point_data['quality_score']
                    )
                    points.append(point)
                    
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self.logger.warning(f"포인트 데이터 파싱 실패: {e}")
                points = []
            
            # CalibrationResult 생성 (quality_grade는 property이므로 제외)
            calibration_result = CalibrationResult(
                method=method,
                coefficients=tuple(coefficients),  # tuple로 변환
                r_squared=r_squared,
                rmse=rmse,
                points=points,
                created_time=time.time(),  # 현재 시간
                validation_passed=validation_passed
            )
            
            self.logger.info(f"✅ CalibrationResult 생성됨: coefficients={coefficients}")
            self.logger.info(f"✅ Quality grade (computed): {calibration_result.quality_grade}")
            
            # DataProcessor에 적용
            self.data_processor.set_calibration(calibration_result)
            
            self.logger.info(f"캘리브레이션 설정 복원됨: {method_str}, R²={r_squared:.4f}")
            
            # 상세 캘리브레이션 정보 로그 출력
            self._log_calibration_details(calibration_result)
            
        except Exception as e:
            self.logger.warning(f"캘리브레이션 설정 복원 실패: {e}")
            # 실패 시 캘리브레이션 없이 진행
    
    def _log_calibration_details(self, calibration_result):
        """캘리브레이션 상세 정보 로그 출력"""
        try:
            self.logger.info("=" * 50)
            self.logger.info("🎯 CALIBRATION DETAILS")
            self.logger.info("=" * 50)
            self.logger.info(f"📊 Method: {calibration_result.method.value}")
            self.logger.info(f"📈 Quality Grade: {calibration_result.quality_grade}")
            self.logger.info(f"🎯 R-squared: {calibration_result.r_squared:.6f}")
            self.logger.info(f"📏 RMSE: {calibration_result.rmse:.6f}")
            self.logger.info(f"✅ Validation: {'PASSED' if calibration_result.validation_passed else 'FAILED'}")
            
            # 계수 출력
            self.logger.info(f"🔢 Coefficients: {calibration_result.coefficients}")
            
            # 회귀 방정식 출력
            if calibration_result.method.value == "linear":
                if len(calibration_result.coefficients) >= 2:
                    slope, intercept = calibration_result.coefficients[0], calibration_result.coefficients[1]
                    self.logger.info(f"📐 Equation: y = {slope:.6f} * x + {intercept:.6f}")
                    
                    # 테스트 값 변환 예시
                    test_values = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]  # voltage 값들
                    self.logger.info("🧪 TEST CONVERSIONS (Voltage → Gram):")
                    for voltage in test_values:
                        gram = calibration_result.apply(voltage)
                        self.logger.info(f"   {voltage:.2f}V → {gram:.3f}g")
            
            # 포인트 데이터 출력
            self.logger.info(f"📍 Calibration Points: {len(calibration_result.points)}")
            for i, point in enumerate(calibration_result.points):
                self.logger.info(f"   Point {i+1}: {point.reference_weight:.2f}g @ {point.average_reading:.3f}V (σ={point.std_reading:.4f})")
            
            # 현재 DataProcessor 상태 확인
            is_calibrated = self.data_processor.is_calibrated()
            self.logger.info(f"🔧 DataProcessor Calibrated: {is_calibrated}")
            
            self.logger.info("=" * 50)
            
        except Exception as e:
            self.logger.error(f"캘리브레이션 로그 출력 오류: {e}")
    
    def _check_initial_calibration_status(self):
        """초기 캘리브레이션 상태 확인"""
        try:
            is_calibrated = self.data_processor.is_calibrated()
            self.logger.info("=" * 50)
            self.logger.info("🔍 INITIAL CALIBRATION STATUS CHECK")
            self.logger.info("=" * 50)
            self.logger.info(f"📊 DataProcessor is_calibrated: {is_calibrated}")
            
            if is_calibrated and self.data_processor.calibration_result:
                result = self.data_processor.calibration_result
                self.logger.info(f"✅ Calibration found: {result.method.value}")
                self.logger.info(f"📈 Quality: {result.quality_grade}, R²={result.r_squared:.4f}")
                
                # 차트 위젯들의 단위 상태 확인
                for i, workbench in enumerate(self.workbenches):
                    for j, chart in enumerate(workbench.chart_widgets):
                        unit = chart.get_current_unit()
                        calibrated = chart.is_calibrated
                        self.logger.info(f"📊 Chart[{i}][{j}] unit: {unit}, is_calibrated: {calibrated}")
            else:
                self.logger.info("❌ No calibration found")
            
            self.logger.info("=" * 50)
            
        except Exception as e:
            self.logger.error(f"캘리브레이션 상태 확인 오류: {e}")
    
    def _new_workbench(self):
        """새 워크벤치 생성"""
        dialog = QDialog(self)
        dialog.setWindowTitle("New Workbench")
        dialog.setModal(True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)  # 애플리케이션 전체에 대해 모달
        dialog.resize(500, 200)  # 다이얼로그 크기 설정
        
        # 컨테이너 위젯 생성
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(15)  # 항목 간 간격 증가
        layout.setContentsMargins(20, 20, 20, 20)  # 여백 추가
        
        # 이름 입력
        name_layout = QHBoxLayout()
        name_label = QLabel("Name:")
        name_label.setMinimumWidth(80)  # 레이블 최소 너비
        name_layout.addWidget(name_label)
        name_edit = QLineEdit()
        name_edit.setText(f"Workbench_{len(self.workbenches) + 1}")
        name_edit.setMinimumHeight(30)  # 입력 필드 높이 증가
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)
        
        # 경로 입력
        path_layout = QHBoxLayout()
        path_label = QLabel("Path:")
        path_label.setMinimumWidth(80)  # 레이블 최소 너비
        path_layout.addWidget(path_label)
        path_edit = QLineEdit()
        
        # 이전 경로를 QSettings에서 불러오기, 없으면 홈 디렉터리 사용
        last_path = self.settings.value("workbench/last_path", str(Path.home()))
        path_edit.setText(last_path)
        path_edit.setMinimumHeight(30)  # 입력 필드 높이 증가
        
        def browse_directory():
            """디렉터리 선택 및 경로 저장"""
            current_path = path_edit.text() if os.path.exists(path_edit.text()) else str(Path.home())
            selected_path = QFileDialog.getExistingDirectory(
                dialog, 
                "Select Directory", 
                current_path
            )
            if selected_path:
                path_edit.setText(selected_path)
                # 선택한 경로를 QSettings에 저장
                self.settings.setValue("workbench/last_path", selected_path)
        
        browse_btn = QPushButton("Browse")
        browse_btn.setMinimumHeight(30)  # 버튼 높이 증가
        browse_btn.setMinimumWidth(80)  # 버튼 너비 설정
        browse_btn.clicked.connect(browse_directory)
        path_layout.addWidget(path_edit)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)
        
        # 여백 추가
        layout.addStretch()
        
        # 버튼
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 버튼을 오른쪽 정렬
        button_layout.addStretch()
        
        create_btn = QPushButton("Create")
        create_btn.setIcon(qta.icon('fa5s.check'))
        create_btn.setMinimumHeight(35)  # 버튼 높이 증가
        create_btn.setMinimumWidth(100)  # 버튼 너비 설정
        create_btn.clicked.connect(dialog.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setIcon(qta.icon('fa5s.times'))
        cancel_btn.setMinimumHeight(35)  # 버튼 높이 증가
        cancel_btn.setMinimumWidth(100)  # 버튼 너비 설정
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(create_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        # 다이얼로그에 컨테이너 설정
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.addWidget(container)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        
        # 다이얼로그 실행
        try:
            result = dialog.exec()
            
            # 다이얼로그가 수락되었을 때 처리
            if result == QDialog.DialogCode.Accepted:
                try:
                    # 값들을 추출 (위젯 유효성은 예외 처리로 확인)
                    name = name_edit.text().strip()
                    path = path_edit.text().strip()
                except RuntimeError as e:
                    self.logger.warning(f"Dialog widgets are not accessible: {e}")
                    return
                
                if name and path and os.path.isdir(path):
                    # 워크벤치 생성 완료 시 경로 저장
                    self.settings.setValue("workbench/last_path", path)
                    
                    workbench = WorkbenchWidget(name, path)
                    
                    # 차트 탭 변경 시그널 연결
                    workbench.chart_tab_changed.connect(self._on_chart_tab_changed)
                    # 수정 상태 변경 시그널 연결
                    workbench.modified_changed.connect(lambda modified, idx=len(self.workbenches): 
                                                      self._update_tab_title(idx, modified))
                    
                    self.workbenches.append(workbench)
                    
                    index = self.workbench_tabs.addTab(workbench, name)
                    self.workbench_tabs.setCurrentIndex(index)
                    
                    self._update_toolbar_state()
                    self.logger.info(f"새 워크벤치 생성: {name} (경로: {path})")
                else:
                    QMessageBox.warning(self, "Error", "Please enter valid name and path.")
                    
        except Exception as e:
            self.logger.error(f"워크벤치 생성 오류: {e}")
            QMessageBox.critical(self, "Error", f"Workbench creation error: {e}")
        
        finally:
            # 다이얼로그 정리
            if dialog:
                dialog.close()
                dialog.deleteLater()
    
    def _add_chart(self):
        """차트 추가"""
        current_workbench = self._get_current_workbench()
        if not current_workbench:
            QMessageBox.information(self, "No Workbench", "Please create a workbench first.")
            return
        
        chart_name = f"Chart_{len(current_workbench.chart_widgets) + 1}"
        chart_widget = current_workbench.add_chart(chart_name)
        
        self.logger.info(f"새 차트 추가: {chart_name}")
    
    def _toggle_measurement(self):
        """측정 시작/중지"""
        if not self.is_measuring:
            # 측정 시작
            current_chart = self._get_current_chart()
            if not current_chart:
                QMessageBox.information(self, "No Chart", "Please add a chart first.")
                return
            
            com_port = self.com_port_combo.currentText()
            if not com_port:
                QMessageBox.warning(self, "No COM Port", "Please select a COM port.")
                return
            
            # 기존 데이터가 있는지 확인
            if current_chart.data_points and len(current_chart.data_points) > 0:
                reply = QMessageBox.question(
                    self,
                    "Data Reset Confirmation",
                    f"'{current_chart.name}' contains existing data.\n\n"
                    f"Current data points: {len(current_chart.data_points)} points\n\n"
                    "Starting a new measurement will reset all data and charts.\n"
                    "Do you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.No:
                    return
                
                # 데이터 리셋
                current_chart.clear_data()
                
                # 통계 테이블 리셋
                current_workbench = self._get_current_workbench()
                if current_workbench:
                    current_workbench.statistics_table.reset_chart_statistics(current_chart.name)
                
                self.logger.info(f"Chart '{current_chart.name}' data reset")
            
            # 시리얼 연결 시도
            if self.serial_manager.connect(com_port):
                current_chart.start_updates()
                
                # 현재 워크벤치의 통계에 측정 시작 기록
                current_workbench = self._get_current_workbench()
                if current_workbench:
                    current_workbench.statistics_table.start_measurement_for_chart(current_chart.name)
                
                self.is_measuring = True
                self.start_stop_action.setIcon(qta.icon('fa5s.stop'))
                self.start_stop_action.setText("Stop")
                self.logger.info("Measurement started")
            else:
                QMessageBox.warning(self, "Connection Failed", "Failed to connect to COM port.")
        else:
            # 측정 중지
            self._stop_measurement()
    
    def _stop_measurement(self):
        """측정 중지"""
        if not self.is_measuring:
            return
        
        current_chart = self._get_current_chart()
        if current_chart:
            current_chart.stop_updates()
            
            # 현재 워크벤치의 통계 테이블에 측정 중지 알림
            current_workbench = self._get_current_workbench()
            if current_workbench:
                current_workbench.statistics_table.stop_measurement_for_chart(current_chart.name)
        
        # 모든 차트의 애니메이션도 중지
        for workbench in self.workbenches:
            for chart_widget in workbench.chart_widgets:
                if chart_widget.is_updating:
                    chart_widget.stop_updates()
        
        self.serial_manager.disconnect()
        self.is_measuring = False
        self.start_stop_action.setIcon(qta.icon('fa5s.play'))
        self.start_stop_action.setText("Start")
        self.logger.info("Measurement stopped")
    
    def _save_current_workbench(self):
        """현재 워크벤치 저장"""
        workbench = self._get_current_workbench()
        if not workbench or not workbench.chart_widgets:
            QMessageBox.information(self, "Nothing to Save", "No data to save.")
            return
        
        # 파일 경로 선택
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Workbench",
            f"{workbench.path}/{workbench.name}.xlsx",
            "Excel files (*.xlsx);;All files (*.*)"
        )
        
        if filename:
            try:
                # 엑셀 내보내기 옵션
                options = ExportOptions(
                    export_type="viewport",  # 현재 보이는 영역만
                    include_chart_image=True,  # 차트 이미지 포함
                    include_excel_chart=False,  # 엑셀 네이티브 차트 제외
                    include_metadata=True,     # 메타데이터 포함
                    freeze_header=False,        # 헤더 고정 해제
                    image_width=2000,
                    image_height=1000,
                    image_dpi=600
                )
                
                # 내보내기 실행
                result = self.excel_exporter.export_workbench(
                    workbench.name,
                    workbench.chart_widgets,
                    filename,
                    options
                )
                
                if result.success:
                    QMessageBox.information(
                        self,
                        "Save Successful",
                        f"Workbench saved successfully!\n\n"
                        f"File: {filename}\n"
                        f"Data points: {result.data_points:,}\n"
                        f"File size: {result.file_size:,} bytes\n"
                        f"Export time: {result.export_time:.1f}s"
                    )
                    # 워크벤치 저장 상태 업데이트
                    workbench.save()
                    self.logger.info(f"워크벤치 저장 완료: {filename}")
                else:
                    QMessageBox.warning(self, "Save Failed", f"Failed to save: {result.error_message}")
                    
            except Exception as e:
                self.logger.error(f"워크벤치 저장 실패: {e}")
                QMessageBox.warning(self, "Save Error", f"Failed to save workbench:\n{str(e)}")
    
    def _open_calibration(self):
        """캘리브레이션 열기"""
        # COM 포트 설정 확인 (연결 상태는 확인하지 않음)
        if not hasattr(self.serial_manager, 'config') or not self.serial_manager.config:
            QMessageBox.warning(
                self,
                "설정 필요",
                "먼저 COM 포트를 선택해주세요."
            )
            return
        
        # 캘리브레이션 마법사 실행
        wizard = CalibrationWizard(
            serial_manager=self.serial_manager,
            data_processor=self.data_processor,
            parent=self
        )
        
        # 완료 시그널 연결
        wizard.calibration_completed.connect(self._on_calibration_completed)
        
        if wizard.exec() == QWizard.DialogCode.Accepted:
            self.logger.info("캘리브레이션 완료")
    
    def _on_calibration_completed(self, result):
        """캘리브레이션 완료 처리"""
        self.logger.info(f"캘리브레이션 결과: {result.quality_grade}, R²={result.r_squared:.4f}")
        
        # 데이터 프로세서에 캘리브레이션 적용
        self.data_processor.set_calibration(result)
        
        # 캘리브레이션 설정 자동 저장
        self._save_calibration_settings()
        
        # 상세 캘리브레이션 정보 로그 출력
        self._log_calibration_details(result)
        
        # 상태바에 표시
        self.statusBar().showMessage("🎯 Calibration applied and saved", 5000)  # 5초간 표시
    
    def _show_about(self):
        """About 다이얼로그"""
        QMessageBox.about(
            self,
            "About PODFA",
            "<h3>PODFA</h3>"
            "<p><b>Petal Breaking Strength Meter</b></p>"
            "<p>Version: 2.0.0</p>"
            "<p>Built with ❤️ using PyQt6 and Matplotlib</p>"
            "<hr>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>✨ Beautiful line charts</li>"
            "<li>🖱️ Mouse hover value display</li>"
            "<li>📊 Window scrolling</li>"
            "<li>💾 Enhanced Excel export</li>"
            "<li>🎨 Sophisticated UI/UX</li>"
            "</ul>"
        )
    
    def _close_workbench(self, index: int):
        """워크벤치 닫기"""
        workbench = self.workbench_tabs.widget(index)
        if isinstance(workbench, WorkbenchWidget):
            # 저장되지 않은 변경사항이 있는지 확인
            if workbench.is_modified:
                reply = QMessageBox.question(
                    self,
                    "Close Workbench",
                    f"'{workbench.name}' workbench has unsaved changes.\nDo you want to continue closing?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.No:
                    return
            
            # 정리
            for widget in workbench.chart_widgets:
                widget.cleanup()
            
            self.workbenches.remove(workbench)
        
        self.workbench_tabs.removeTab(index)
        self._update_toolbar_state()
    
    def _refresh_ports(self):
        """COM 포트 목록 새로고침"""
        # 시그널 차단으로 불필요한 로그 방지
        self.com_port_combo.blockSignals(True)
        
        try:
            # 현재 선택된 포트 또는 저장된 포트 확인
            current_text = self.com_port_combo.currentText()
            saved_port = self.settings.value("com_port", "")
            target_port = current_text or saved_port
            
            self.com_port_combo.clear()
            
            ports = self.serial_manager.get_available_ports()
            if not ports:
                self.com_port_combo.addItem("No ports found")
                self.com_port_combo.setEnabled(False)
                return
            
            self.com_port_combo.setEnabled(True)
            
            # 포트 목록 추가
            for port in ports:
                self.com_port_combo.addItem(port['device'])
            
            # 저장된 포트 또는 이전 선택 복원
            if target_port:
                index = self.com_port_combo.findText(target_port)
                if index != -1:
                    self.com_port_combo.setCurrentIndex(index)
                    # 복원 시에만 로그 출력
                    if target_port == saved_port:
                        self.logger.info(f"COM 포트 복원: {target_port}")
                else:
                    # 저장된 포트가 없으면 첫 번째 포트를 기본 선택
                    if self.com_port_combo.count() > 0:
                        self.com_port_combo.setCurrentIndex(0)
                        if not current_text:  # 처음 실행시에만 로그 출력
                            self.logger.info(f"기본 COM 포트 선택: {self.com_port_combo.currentText()}")
            else:
                # 아무것도 저장되지 않았으면 첫 번째 포트를 기본 선택
                if self.com_port_combo.count() > 0:
                    self.com_port_combo.setCurrentIndex(0)
                    
        finally:
            # 시그널 차단 해제
            self.com_port_combo.blockSignals(False)
    
    def _get_current_workbench(self) -> Optional[WorkbenchWidget]:
        """현재 워크벤치 반환"""
        widget = self.workbench_tabs.currentWidget()
        if isinstance(widget, WorkbenchWidget):
            return widget
        return None
    
    def _get_current_chart(self) -> Optional[ChartWidget]:
        """현재 차트 반환"""
        workbench = self._get_current_workbench()
        if workbench:
            return workbench.get_current_chart()
        return None
    
    def _update_toolbar_state(self):
        """툴바 상태 업데이트"""
        has_workbench = len(self.workbenches) > 0
        self.add_chart_action.setEnabled(has_workbench)
    
    def _update_status(self):
        """상태 업데이트"""
        # 연결 상태
        if self.serial_manager.is_connected():
            self.connection_label.setText("🟢 Connected")
        else:
            self.connection_label.setText("🔴 Disconnected")
        
        # 데이터 통계
        chart = self._get_current_chart()
        if chart and chart.data_points:
            count = len(chart.data_points)
            self.data_stats_label.setText(f"Data: {count:,} points")
        else:
            self.data_stats_label.setText("Data: 0 points")
    
    # 이벤트 핸들러
    def _on_serial_data(self, data: str):
        """시리얼 데이터 수신"""
        # 데이터 처리
        data_point = self.data_processor.process_raw_data(data)
        
        if data_point:
            # 현재 차트에 데이터 추가
            chart = self._get_current_chart()
            
            if chart:
                chart.add_data_point(data_point)
                
                # 통계 업데이트
                workbench = self._get_current_workbench()
                if workbench:
                    workbench._update_chart_statistics(chart)
    
    def _on_data_processed(self, data_point: DataPoint):
        """데이터 처리 완료"""
        pass  # 추가 처리 필요 시 구현
    
    def _on_calibration_status_changed(self, is_calibrated: bool):
        """캘리브레이션 상태 변경"""
        self.logger.info(f"캘리브레이션 상태 변경: {'gram 단위' if is_calibrated else 'voltage 단위'}")
        
        # 모든 워크벤치의 모든 차트에 캘리브레이션 상태 전파
        for i in range(self.workbench_tabs.count()):
            workbench = self.workbench_tabs.widget(i)
            if isinstance(workbench, WorkbenchWidget):
                # 워크벤치의 모든 차트에 상태 전파
                for chart_widget in workbench.chart_widgets:
                    chart_widget.set_calibration_status(is_calibrated)
                
                # 워크벤치의 통계 테이블에도 상태 전파
                if hasattr(workbench, 'statistics_table'):
                    workbench.statistics_table.set_calibration_status(is_calibrated)
    
    def _on_connection_changed(self, state: ConnectionState):
        """연결 상태 변경"""
        self.logger.info(f"연결 상태 변경: {state.value}")
    
    def _on_ports_updated(self, ports: List[Dict]):
        """포트 목록 업데이트 (실제 변경이 있을 때만)"""
        # 현재 포트 목록과 비교
        current_ports = [self.com_port_combo.itemText(i) for i in range(self.com_port_combo.count())]
        new_ports = [port['device'] for port in ports]
        
        # 포트 목록에 변경이 있을 때만 새로고침
        if set(current_ports) != set(new_ports):
            self.logger.debug(f"포트 목록 변경 감지: {new_ports}")
            self._refresh_ports()
        # 변경이 없으면 아무것도 하지 않음 (로그도 출력하지 않음)
    
    def _on_serial_error(self, error_msg: str):
        """시리얼 오류"""
        self.logger.error(f"시리얼 오류: {error_msg}")
        QMessageBox.warning(self, "Serial Error", error_msg)
    
    def _on_com_port_changed(self, port: str):
        """COM 포트 선택 변경"""
        if port:
            self.settings.setValue("com_port", port)
            self.logger.info(f"COM 포트 선택: {port}")
    
    def _on_chart_tab_changed(self, index: int):
        """차트 탭 변경 시 측정 중지 및 모든 차트 애니메이션 중지"""
        if self.is_measuring:
            self._stop_measurement()
            self.logger.info("Chart tab changed - measurement stopped")
        
        # 모든 워크벤치의 모든 차트 애니메이션 중지
        for workbench in self.workbenches:
            for chart_widget in workbench.chart_widgets:
                if chart_widget.is_updating:
                    chart_widget.stop_updates()
                    self.logger.debug(f"Stopped animation for chart '{chart_widget.name}'")
    
    def _update_tab_title(self, index: int, is_modified: bool):
        """탭 제목 업데이트 (수정 상태 표시)"""
        if index < self.workbench_tabs.count():
            workbench = self.workbench_tabs.widget(index)
            if isinstance(workbench, WorkbenchWidget):
                title = workbench.name
                if is_modified:
                    title = f"*{title}"
                self.workbench_tabs.setTabText(index, title)
    
    def _open_filter_settings(self):
        """필터 설정 다이얼로그 열기"""
        try:
            # 현재 설정 가져오기
            current_config = self.data_processor.config
            
            # 다이얼로그 생성 및 표시
            dialog = FilterSettingsDialog(current_config, self)
            dialog.filter_settings_changed.connect(self._on_filter_settings_changed)
            
            # 다이얼로그 실행
            dialog.exec()
            
        except Exception as e:
            self.logger.error(f"필터 설정 다이얼로그 오류: {e}")
            QMessageBox.critical(self, "Filter Settings Error", f"Cannot open filter settings:\n{str(e)}")
    
    def _on_filter_settings_changed(self, new_config):
        """필터 설정 변경 핸들러"""
        try:
            # DataProcessor 설정 업데이트
            self.data_processor.update_config(new_config)
            
            # 로그 메시지
            filter_name = {
                'none': '없음',
                'moving_average': '이동평균',
                'median': '중앙값',
                'butterworth': 'Butterworth'
            }.get(new_config.filter_type.value, '알 수 없음')
            
            self.logger.info(f"필터 설정 변경: {filter_name}")
            
            # 상태바에 메시지 표시
            if new_config.filter_type.value == 'butterworth':
                self.statusBar().showMessage(
                    f"📊 {filter_name} 필터 적용됨 (cutoff: {new_config.butterworth_cutoff}Hz, "
                    f"order: {new_config.butterworth_order})", 5000
                )
            elif new_config.filter_type.value in ['moving_average', 'median']:
                self.statusBar().showMessage(
                    f"📊 {filter_name} 필터 적용됨 (window: {new_config.filter_window})", 5000
                )
            else:
                self.statusBar().showMessage("📊 필터 해제됨", 3000)
                
        except Exception as e:
            self.logger.error(f"필터 설정 적용 오류: {e}")
            QMessageBox.critical(self, "Filter Settings Error", f"Cannot apply filter settings:\n{str(e)}")
    
    def closeEvent(self, event):
        """종료 이벤트"""
        # 저장되지 않은 워크벤치 확인
        unsaved_workbenches = [w for w in self.workbenches if w.is_modified]
        
        if unsaved_workbenches:
            reply = QMessageBox.warning(
                self,
                "Program Exit",
                f"There are {len(unsaved_workbenches)} unsaved workbenches.\n"
                "Do you want to save them?",
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Save:
                # 모든 수정된 워크벤치 저장
                for workbench in unsaved_workbenches:
                    # 현재 탭으로 전환
                    for i in range(self.workbench_tabs.count()):
                        if self.workbench_tabs.widget(i) == workbench:
                            self.workbench_tabs.setCurrentIndex(i)
                            self._save_current_workbench()
                            break
        
        # 측정 중인 경우 중지
        if self.is_measuring:
            self._toggle_measurement()
        
        # 설정 저장
        self.settings.setValue("geometry", self.saveGeometry())
        
        # COM 포트 저장
        if self.com_port_combo.currentText() and self.com_port_combo.currentText() != "포트를 찾을 수 없습니다":
            self.settings.setValue("com_port", self.com_port_combo.currentText())
        
        # 캘리브레이션 설정 저장
        self._save_calibration_settings()
        
        # 리소스 정리
        try:
            self.serial_manager.cleanup()
        except Exception as e:
            self.logger.warning(f"SerialManager cleanup 오류: {e}")
        
        try:
            self.data_processor.cleanup()
        except Exception as e:
            self.logger.warning(f"DataProcessor cleanup 오류: {e}")
        
        try:
            self.calibration_engine.cleanup()
        except Exception as e:
            self.logger.warning(f"CalibrationEngine cleanup 오류: {e}")
        
        try:
            for workbench in self.workbenches:
                for widget in workbench.chart_widgets:
                    widget.cleanup()
        except Exception as e:
            self.logger.warning(f"Chart widget cleanup 오류: {e}")
        
        self.logger.info("메인 윈도우 종료")
        event.accept()