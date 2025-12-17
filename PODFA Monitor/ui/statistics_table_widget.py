"""
PBS 2.0 Statistics Table Widget
===============================

각 차트별 통계 정보를 표시하는 테이블 위젯
- 차트별 최대값, 최소값, 평균값 등 통계 정보 표시
- 실시간 업데이트
- 스프레드시트 형태의 직관적인 인터페이스
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QToolBar, QCheckBox, QSpinBox,
    QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush
import qtawesome as qta

from core.data_processor import DataPoint
from ui.chart_widget import ChartWidget


@dataclass
class ChartStatistics:
    """차트 통계 정보"""
    chart_name: str
    data_count: int = 0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    avg_value: float = 0.0
    std_value: float = 0.0
    last_value: float = 0.0
    last_update_time: Optional[datetime] = None
    measurement_start_time: Optional[datetime] = None
    measurement_stop_time: Optional[datetime] = None  # 측정 종료 시간 추가
    measurement_duration: float = 0.0  # seconds
    is_measuring: bool = False  # 측정 상태 플래그 추가
    
    def reset(self):
        """통계 초기화"""
        self.data_count = 0
        self.min_value = float('inf')
        self.max_value = float('-inf')
        self.avg_value = 0.0
        self.std_value = 0.0
        self.last_value = 0.0
        self.last_update_time = None
        self.measurement_start_time = None
        self.measurement_stop_time = None
        self.measurement_duration = 0.0
        self.is_measuring = False
    
    def start_measurement(self):
        """측정 시작"""
        self.measurement_start_time = datetime.now()
        self.measurement_stop_time = None
        self.measurement_duration = 0.0
        self.is_measuring = True
    
    def stop_measurement(self):
        """측정 종료"""
        if self.is_measuring and self.measurement_start_time:
            self.measurement_stop_time = datetime.now()
            self.measurement_duration = (self.measurement_stop_time - self.measurement_start_time).total_seconds()
            self.is_measuring = False
    
    def update_duration(self):
        """측정 지속 시간 업데이트"""
        if self.is_measuring and self.measurement_start_time:
            # 측정 중일 때만 시간 업데이트
            self.measurement_duration = (datetime.now() - self.measurement_start_time).total_seconds()
        # 측정이 중지되면 마지막 duration 값을 유지


class StatisticsTableWidget(QWidget):
    """📊 차트별 통계 정보 테이블 위젯"""
    
    # 시그널 정의
    export_requested = pyqtSignal(str)  # 내보내기 요청
    chart_selected = pyqtSignal(str)    # 차트 선택
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 데이터
        self.chart_statistics: Dict[str, ChartStatistics] = {}
        self.auto_update_enabled = True
        self.update_interval = 1000  # 1초
        self.is_calibrated = False  # 캘리브레이션 상태 추적
        
        # UI 초기화
        self._init_ui()
        
        # 타이머 설정
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(self.update_interval)
        
        # 로깅
        self.logger = logging.getLogger(__name__)
        self.logger.info("Statistics Table Widget 초기화 완료")
    
    def _init_ui(self):
        """UI 초기화"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 제목 및 툴바
        header_layout = self._create_header()
        layout.addLayout(header_layout)
        
        # 통계 테이블
        self.table = self._create_table()
        layout.addWidget(self.table)
        
        # 하단 컨트롤
        bottom_layout = self._create_bottom_controls()
        layout.addLayout(bottom_layout)
        
        # 스타일 적용
        self._apply_styles()
    
    def _create_header(self) -> QHBoxLayout:
        """헤더 영역 생성 - 향상된 디자인"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        
        # 제목 - 더 세련된 스타일
        title_label = QLabel("📊 Statistics Dashboard")
        title_font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                padding: 5px;
            }
        """)
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        # 자동 업데이트 체크박스
        self.auto_update_check = QCheckBox("Auto Update")
        self.auto_update_check.setChecked(True)
        self.auto_update_check.toggled.connect(self._toggle_auto_update)
        self.auto_update_check.setStyleSheet("""
            QCheckBox {
                font-weight: 500;
            }
        """)
        layout.addWidget(self.auto_update_check)
        
        # 새로고침 버튼 - qtawesome 아이콘 사용
        refresh_btn = QPushButton()
        refresh_btn.setIcon(qta.icon('fa5s.sync-alt', color='#4a90e2'))
        refresh_btn.setToolTip("Manual refresh (F5)")
        refresh_btn.clicked.connect(self._manual_refresh)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 2px solid #4a90e2;
            }
            QPushButton:hover {
                background-color: #e8f4fd;
            }
        """)
        layout.addWidget(refresh_btn)
        
        # 내보내기 버튼 - qtawesome 아이콘 사용
        export_btn = QPushButton()
        export_btn.setIcon(qta.icon('fa5s.file-export', color='#27ae60'))
        export_btn.setToolTip("Export to CSV (Ctrl+E)")
        export_btn.clicked.connect(self._export_to_csv)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 2px solid #27ae60;
            }
            QPushButton:hover {
                background-color: #e8f7ed;
            }
        """)
        layout.addWidget(export_btn)
        
        return layout
    
    def _create_table(self) -> QTableWidget:
        """통계 테이블 생성 - 향상된 가독성"""
        table = QTableWidget()
        
        # 컬럼 설정 - 영어로 변경하여 국제화
        columns = [
            "📈 Chart Name", "📊 Data Count", "⬇️ Min Value", "⬆️ Max Value", 
            "📉 Average", "📐 Std Dev", "🎯 Current Value", "⏱️ Duration", "🕐 Last Update"
        ]
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        
        # 테이블 설정
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)  # 그리드 라인 제거로 깔끔한 느낌
        
        # 폰트 설정
        table_font = QFont("Segoe UI", 11)
        table.setFont(table_font)
        
        # 헤더 스타일 및 크기 조정
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 차트 이름
        
        # 각 컬럼 너비 최적화
        column_widths = [200, 100, 100, 100, 100, 100, 100, 120, 150]
        for i, width in enumerate(column_widths):
            if i > 0:  # 첫 번째 컬럼은 Stretch
                table.setColumnWidth(i, width)
        
        # 행 높이 설정
        table.verticalHeader().setDefaultSectionSize(45)
        
        # 시그널 연결
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        return table
    
    def _create_bottom_controls(self) -> QHBoxLayout:
        """하단 컨트롤 생성 - 향상된 디자인"""
        layout = QHBoxLayout()
        layout.setSpacing(15)
        
        # 업데이트 간격 설정 - 아이콘 추가
        interval_icon = QLabel()
        interval_icon.setPixmap(qta.icon('fa5s.clock', color='#7f8c8d').pixmap(16, 16))
        layout.addWidget(interval_icon)
        
        interval_label = QLabel("Update Interval:")
        interval_label.setStyleSheet("font-weight: 500; color: #34495e;")
        layout.addWidget(interval_label)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(500, 10000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setStyleSheet("""
            QSpinBox {
                font-size: 12px;
                font-weight: 500;
            }
        """)
        self.interval_spin.valueChanged.connect(self._update_interval_changed)
        layout.addWidget(self.interval_spin)
        
        layout.addStretch()
        
        # 통계 요약 - 더 상세한 정보와 스타일
        self.summary_label = QLabel("📌 Active Charts: 0 | Total Data: 0")
        self.summary_label.setStyleSheet("""
            QLabel {
                background-color: #f0f7ff;
                border: 1px solid #d4e9ff;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 500;
                color: #2c3e50;
            }
        """)
        layout.addWidget(self.summary_label)
        
        return layout
    
    def _apply_styles(self):
        """스타일 적용 - 모던하고 가독성 높은 디자인"""
        self.setStyleSheet("""
            /* 메인 테이블 스타일 */
            QTableWidget {
                gridline-color: transparent;
                background-color: #ffffff;
                alternate-background-color: #f8fafb;
                selection-background-color: #e8f4fd;
                border: 1px solid #e1e8ed;
                border-radius: 8px;
                font-size: 13px;
            }
            
            /* 테이블 아이템 스타일 */
            QTableWidget::item {
                padding: 12px 8px;
                border: none;
                color: #2c3e50;
            }
            
            QTableWidget::item:selected {
                background-color: #d4e9ff;
                color: #1a73e8;
                font-weight: 500;
            }
            
            QTableWidget::item:hover {
                background-color: #f0f7ff;
            }
            
            /* 헤더 스타일 - 더 모던하게 */
            QHeaderView::section {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                           stop: 0 #4a90e2, stop: 1 #357abd);
                color: white;
                border: none;
                padding: 12px 8px;
                font-weight: 600;
                font-size: 13px;
                text-align: left;
            }
            
            QHeaderView::section:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                           stop: 0 #5ba0f2, stop: 1 #4080cd);
            }
            
            /* 체크박스 스타일 */
            QCheckBox {
                font-size: 13px;
                color: #34495e;
                spacing: 8px;
            }
            
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #cbd5e0;
                background-color: white;
            }
            
            QCheckBox::indicator:checked {
                background-color: #4a90e2;
                border: 2px solid #4a90e2;
                image: url(checkmark.png);
            }
            
            QCheckBox::indicator:hover {
                border: 2px solid #4a90e2;
            }
            
            /* 버튼 스타일 - 더 모던하게 */
            QPushButton {
                border: none;
                border-radius: 6px;
                background-color: #f7f9fb;
                padding: 8px;
                font-size: 14px;
                min-width: 32px;
                min-height: 32px;
            }
            
            QPushButton:hover {
                background-color: #e8f4fd;
                border: 1px solid #4a90e2;
            }
            
            QPushButton:pressed {
                background-color: #d4e9ff;
            }
            
            /* 스핀박스 스타일 */
            QSpinBox {
                border: 2px solid #e1e8ed;
                border-radius: 6px;
                padding: 6px;
                background-color: white;
                font-size: 13px;
                min-width: 100px;
            }
            
            QSpinBox:focus {
                border: 2px solid #4a90e2;
            }
            
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                border: none;
                background-color: #f0f4f8;
            }
            
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #e1e8ed;
            }
            
            /* 레이블 스타일 */
            QLabel {
                color: #34495e;
                font-size: 13px;
            }
        """)
    
    def add_chart(self, chart_widget: ChartWidget):
        """차트 추가 및 모니터링 시작"""
        chart_name = chart_widget.name
        
        # 통계 객체 생성
        self.chart_statistics[chart_name] = ChartStatistics(chart_name=chart_name)
        
        # 차트의 데이터 업데이트 시그널 연결
        # chart_widget에 데이터 추가 시그널이 있다면 연결
        # (ChartWidget에 data_updated 시그널 추가 필요)
        
        # 테이블에 행 추가
        new_row = self._add_table_row(chart_name)
        
        # 새로 추가된 행에 포커스 설정
        self._set_row_focus(new_row)
        
        self.logger.info(f"Chart '{chart_name}' statistics monitoring started")
    
    def remove_chart(self, chart_name: str):
        """차트 제거"""
        if chart_name in self.chart_statistics:
            del self.chart_statistics[chart_name]
            
            # 테이블에서 행 제거
            self._remove_table_row(chart_name)
            
            self.logger.info(f"Chart '{chart_name}' statistics monitoring stopped")
    
    def start_measurement_for_chart(self, chart_name: str):
        """특정 차트의 측정 시작"""
        if chart_name in self.chart_statistics:
            self.chart_statistics[chart_name].start_measurement()
            self.logger.info(f"Measurement started for chart '{chart_name}'")
    
    def stop_measurement_for_chart(self, chart_name: str):
        """특정 차트의 측정 중지"""
        if chart_name in self.chart_statistics:
            self.chart_statistics[chart_name].stop_measurement()
            self.logger.info(f"Measurement stopped for chart '{chart_name}'")
    
    def stop_all_measurements(self):
        """모든 차트의 측정 중지"""
        for stats in self.chart_statistics.values():
            stats.stop_measurement()
        self.logger.info("All measurements stopped")
    
    def reset_chart_statistics(self, chart_name: str):
        """특정 차트의 통계 리셋"""
        if chart_name in self.chart_statistics:
            self.chart_statistics[chart_name].reset()
            self.logger.info(f"Statistics reset for chart '{chart_name}'")
    
    def _add_table_row(self, chart_name: str) -> int:
        """테이블에 행 추가 - 향상된 스타일"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Chart Name (편집 불가) - 차트 아이콘 추가
        name_item = QTableWidgetItem(f"  {chart_name}")
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        name_item.setData(Qt.ItemDataRole.UserRole, chart_name)  # 차트 이름 저장
        name_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.table.setItem(row, 0, name_item)
        
        # 나머지 컬럼들 (모두 편집 불가)
        for col in range(1, self.table.columnCount()):
            item = QTableWidgetItem("-")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 가운데 정렬로 변경
            item.setFont(QFont("Consolas", 10))  # 숫자는 고정폭 폰트 사용
            self.table.setItem(row, col, item)
        
        return row
    
    def _set_row_focus(self, row: int):
        """특정 행에 포커스 설정 및 하이라이트"""
        # 해당 행의 첫 번째 셀 선택
        self.table.setCurrentCell(row, 0)
        
        # 행 전체 선택
        self.table.selectRow(row)
        
        # 테이블에 포커스 설정
        self.table.setFocus()
        
        # 선택된 행으로 스크롤
        self.table.scrollToItem(self.table.item(row, 0))
    
    def update_chart_focus(self, chart_name: str):
        """차트 이름으로 해당 행에 포커스 설정"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == chart_name:
                self._set_row_focus(row)
                break
    
    def _remove_table_row(self, chart_name: str):
        """테이블에서 행 제거"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == chart_name:
                self.table.removeRow(row)
                break
    
    def update_chart_statistics(self, chart_name: str, data_points: List[DataPoint]):
        """차트 통계 업데이트"""
        if chart_name not in self.chart_statistics:
            return
            
        stats = self.chart_statistics[chart_name]
        
        if not data_points:
            # 데이터가 없는 경우 초기화
            stats.reset()
        else:
            # 통계 계산
            values = [dp.value for dp in data_points]
            
            stats.data_count = len(values)
            stats.min_value = min(values)
            stats.max_value = max(values)
            stats.avg_value = sum(values) / len(values)
            
            # 표준편차 계산
            if len(values) > 1:
                variance = sum((x - stats.avg_value) ** 2 for x in values) / (len(values) - 1)
                stats.std_value = variance ** 0.5
            else:
                stats.std_value = 0.0
            
            stats.last_value = values[-1]
            stats.last_update_time = datetime.now()
    
    def _update_display(self):
        """디스플레이 업데이트 - 향상된 표시"""
        if not self.auto_update_enabled:
            return
            
        total_data_points = 0
        
        for row in range(self.table.rowCount()):
            chart_name_item = self.table.item(row, 0)
            if not chart_name_item:
                continue
                
            chart_name = chart_name_item.data(Qt.ItemDataRole.UserRole)
            if chart_name not in self.chart_statistics:
                continue
                
            stats = self.chart_statistics[chart_name]
            
            # 각 컬럼 업데이트 - 숫자 형식 개선
            if stats.data_count > 0:
                # 데이터 수 - 천 단위 구분 기호
                self._update_cell_with_style(row, 1, f"{stats.data_count:,}", "#2ecc71")
                total_data_points += stats.data_count
                
                # 최소값 - 파란색
                self._update_cell_with_style(row, 2, f"{stats.min_value:.2f}", "#3498db")
                
                # 최대값 - 빨간색
                self._update_cell_with_style(row, 3, f"{stats.max_value:.2f}", "#e74c3c")
                
                # 평균값 - 기본색
                self._update_cell_with_style(row, 4, f"{stats.avg_value:.2f}", "#34495e")
                
                # 표준편차 - 회색
                self._update_cell_with_style(row, 5, f"{stats.std_value:.2f}", "#7f8c8d")
                
                # 현재값 - 주황색 강조
                self._update_cell_with_style(row, 6, f"{stats.last_value:.2f}", "#f39c12", bold=True)
                
                # Duration 업데이트 - 시간 형식
                stats.update_duration()
                duration_str = self._format_duration(stats.measurement_duration)
                self._update_cell_with_style(row, 7, duration_str, "#9b59b6")
                
                # 마지막 업데이트 시간
                if stats.last_update_time:
                    time_str = stats.last_update_time.strftime("%H:%M:%S")
                    self._update_cell_with_style(row, 8, time_str, "#95a5a6")
                else:
                    self._update_cell(row, 8, "-")
            else:
                # 데이터가 없는 경우
                self._update_cell_with_style(row, 1, "0", "#95a5a6")
                for col in range(2, self.table.columnCount()):
                    self._update_cell(row, col, "-")
        
        # 요약 업데이트 - 더 상세한 정보
        total_charts = len(self.chart_statistics)
        active_charts = sum(1 for stats in self.chart_statistics.values() if stats.data_count > 0)
        self.summary_label.setText(
            f"📌 Active Charts: {active_charts}/{total_charts} | "
            f"📊 Total Data: {total_data_points:,} points"
        )
    
    def _update_cell(self, row: int, col: int, value: str):
        """셀 업데이트"""
        item = self.table.item(row, col)
        if item:
            item.setText(value)
    
    def _update_cell_with_style(self, row: int, col: int, value: str, color: str, bold: bool = False):
        """스타일과 함께 셀 업데이트"""
        item = self.table.item(row, col)
        if item:
            item.setText(value)
            
            # 폰트 설정
            font = QFont("Consolas", 10)
            if bold:
                font.setBold(True)
            item.setFont(font)
            
            # 색상 설정
            from PyQt6.QtGui import QColor, QBrush
            item.setForeground(QBrush(QColor(color)))
    
    def _format_duration(self, duration_seconds: float) -> str:
        """지속 시간을 더 가독성 있게 포맷"""
        if duration_seconds <= 0:
            return "00:00"
        
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def _toggle_auto_update(self, enabled: bool):
        """자동 업데이트 토글"""
        self.auto_update_enabled = enabled
        if enabled:
            self.update_timer.start()
            self.logger.info("Auto update enabled")
        else:
            self.update_timer.stop()
            self.logger.info("Auto update disabled")
    
    def _manual_refresh(self):
        """수동 새로고침"""
        self._update_display()
        self.logger.info("수동 새로고침 실행")
    
    def _update_interval_changed(self, interval: int):
        """업데이트 간격 변경"""
        self.update_interval = interval
        if self.auto_update_enabled:
            self.update_timer.stop()
            self.update_timer.start(interval)
        self.logger.info(f"Update interval changed: {interval}ms")
    
    def _export_to_csv(self):
        """CSV로 내보내기"""
        if not self.chart_statistics:
            QMessageBox.information(self, "Export", "No data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "CSV 파일로 저장", 
            f"chart_statistics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        
        if filename:
            try:
                self._save_to_csv(filename)
                QMessageBox.information(self, "Export Complete", f"Statistics data saved successfully:\n{filename}")
                self.logger.info(f"Statistics data saved to CSV: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"An error occurred while saving the file:\n{str(e)}")
                self.logger.error(f"CSV save failed: {e}")
    
    def _save_to_csv(self, filename: str):
        """CSV 파일로 저장"""
        import csv
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # 헤더 쓰기
            headers = []
            for col in range(self.table.columnCount()):
                headers.append(self.table.horizontalHeaderItem(col).text())
            writer.writerow(headers)
            
            # 데이터 쓰기
            for row in range(self.table.rowCount()):
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item else "")
                writer.writerow(row_data)
    
    def _on_cell_clicked(self, row: int, col: int):
        """셀 클릭 이벤트"""
        chart_name_item = self.table.item(row, 0)
        if chart_name_item:
            chart_name = chart_name_item.data(Qt.ItemDataRole.UserRole)
            self.chart_selected.emit(chart_name)
    
    def _on_cell_double_clicked(self, row: int, col: int):
        """셀 더블클릭 이벤트"""
        # 더블클릭 시 추가 동작 (예: 차트로 이동)
        chart_name_item = self.table.item(row, 0)
        if chart_name_item:
            chart_name = chart_name_item.data(Qt.ItemDataRole.UserRole)
            self.logger.info(f"Chart '{chart_name}' double clicked")
    
    def clear_all_statistics(self):
        """모든 통계 초기화"""
        for stats in self.chart_statistics.values():
            stats.reset()
        self._update_display()
        self.logger.info("All statistics cleared")
        self.logger.info("모든 통계 초기화됨")
    
    def set_calibration_status(self, is_calibrated: bool):
        """
        캘리브레이션 상태 설정
        
        Args:
            is_calibrated: True = gram 단위, False = voltage 단위
        """
        if self.is_calibrated != is_calibrated:
            self.is_calibrated = is_calibrated
            self._update_table_headers()
            self.logger.info(f"Statistics table units changed to {'gram' if is_calibrated else 'voltage'}")
    
    def _update_table_headers(self):
        """캘리브레이션 상태에 따른 테이블 헤더 업데이트"""
        unit = "g" if self.is_calibrated else "V"
        
        # 컬럼 설정 - 캘리브레이션 상태에 따른 단위 표시
        columns = [
            "📈 Chart Name", 
            "📊 Data Count", 
            f"⬇️ Min ({unit})", 
            f"⬆️ Max ({unit})", 
            f"📉 Avg ({unit})", 
            f"📐 Std ({unit})", 
            f"🎯 Current ({unit})", 
            "⏱️ Duration", 
            "🕐 Last Update"
        ]
        
        for i, column_name in enumerate(columns):
            if i < self.table.columnCount():
                self.table.setHorizontalHeaderItem(i, QTableWidgetItem(column_name))
    
    def get_current_unit(self) -> str:
        """현재 단위 반환"""
        return "g" if self.is_calibrated else "V"

    def cleanup(self):
        """리소스 정리"""
        self.update_timer.stop()
        self.chart_statistics.clear()
        self.logger.info("Statistics Table Widget 정리 완료")