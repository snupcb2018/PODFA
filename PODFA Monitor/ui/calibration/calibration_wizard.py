"""
PBS 2.0 Calibration Wizard
===========================

캘리브레이션 마법사 - QWizard 기반 단계별 인터페이스
"""

import logging
import time
from typing import List, Optional, Dict
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar,
    QTextEdit, QGroupBox, QComboBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QRadioButton, QButtonGroup, QCheckBox,
    QFormLayout, QGridLayout, QMessageBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QThread
from PyQt6.QtGui import QFont, QPixmap, QIcon
import qtawesome as qta

from core.calibration import (
    CalibrationEngine, CalibrationMethod, CalibrationState,
    CalibrationPoint, CalibrationResult, CollectionConfig
)


@dataclass
class CalibrationSettings:
    """캘리브레이션 설정"""
    reference_weights: List[float]  # 기준 무게 리스트 (누적)
    individual_weights: List[float]  # 개별 무게 리스트 (단일)
    collection_duration: float = 5.0  # 각 포인트 수집 시간
    min_samples: int = 100  # 최소 샘플 수
    method: CalibrationMethod = CalibrationMethod.LINEAR  # 회귀 방법
    save_profile: bool = True  # 프로파일 저장


class IntroductionPage(QWizardPage):
    """Introduction Page"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Calibration Wizard")
        self.setSubTitle("Start calibration process for accurate measurements")
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Welcome message
        welcome_label = QLabel(
            "<h2>🎯 PODFA Calibration Wizard</h2>"
            "<p>This wizard will guide you through the sensor calibration process.</p>"
        )
        welcome_label.setWordWrap(True)
        layout.addWidget(welcome_label)
        
        # Preparation
        prep_group = QGroupBox("Preparation")
        prep_layout = QVBoxLayout()
        
        prep_text = QTextEdit()
        prep_text.setReadOnly(True)
        prep_text.setMaximumHeight(150)
        prep_text.setHtml("""
            <ul>
                <li>✅ Prepare five 1g standard weights</li>
                <li>✅ Ensure sensor is in stable condition</li>
                <li>✅ Install on flat surface without vibration</li>
                <li>✅ Verify serial port connection</li>
            </ul>
        """)
        prep_layout.addWidget(prep_text)
        prep_group.setLayout(prep_layout)
        layout.addWidget(prep_group)
        
        # Process description
        process_group = QGroupBox("Calibration Process")
        process_layout = QVBoxLayout()
        
        process_text = QLabel(
            "1️⃣ Set reference weights\n"
            "2️⃣ Collect data for each weight\n"
            "3️⃣ Perform regression analysis\n"
            "4️⃣ Verify and save results"
        )
        process_text.setStyleSheet("QLabel { padding: 10px; }")
        process_layout.addWidget(process_text)
        process_group.setLayout(process_layout)
        layout.addWidget(process_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def validatePage(self):
        """Page validation"""
        wizard = self.wizard()
        if wizard and hasattr(wizard, 'serial_manager') and wizard.serial_manager:
            # Check COM port settings, but not connection status
            if not hasattr(wizard.serial_manager, 'config') or not wizard.serial_manager.config:
                QMessageBox.warning(
                    self, 
                    "Configuration Required",
                    "Please select COM port first."
                )
                return False
            
            # Try to connect if not connected
            if not wizard.serial_manager.is_connected():
                reply = QMessageBox.question(
                    self,
                    "Connection Confirmation",
                    f"Connect to COM port {wizard.serial_manager.config.port}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # Try to connect
                    wizard.serial_manager.connect()
                    # Wait briefly
                    import time
                    time.sleep(0.5)
                    
                    if not wizard.serial_manager.is_connected():
                        QMessageBox.warning(
                            self,
                            "Connection Failed",
                            "Failed to connect to serial port. Continue calibration anyway?\n\n"
                            "※ Will proceed in simulation mode."
                        )
        return True


class WeightSettingsPage(QWizardPage):
    """Weight Settings Page"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Reference Weight Settings")
        self.setSubTitle("Set reference weights for calibration")
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Weight input method description
        info_label = QLabel(
            "<h3>📏 Cumulative Weight Calibration Settings</h3>"
            "<p><b>Cumulative Method:</b> Add weights one by one from the first step.<br>"
            "Enter the weight of each added weight, and the cumulative weight will be calculated automatically.</p>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Weight input table
        weight_group = QGroupBox("Step-wise Weight Settings")
        weight_layout = QVBoxLayout()
        
        # Description
        desc_label = QLabel(
            "💡 <b>Usage:</b><br>"
            "• Step 1: 0g (No load)<br>"
            "• Step 2: Add first weight (e.g., 1.07g)<br>"
            "• Step 3: Add second weight (e.g., +1.14g → Total 2.21g)<br>"
            "• Step 4: Add third weight (e.g., +1.00g → Total 3.21g)<br>"
            "• And so on..."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("QLabel { background-color: #e8f5e8; padding: 8px; border-radius: 4px; }")
        weight_layout.addWidget(desc_label)
        
        # 무게 입력 테이블
        self.weight_table = QTableWidget(5, 4)
        self.weight_table.setHorizontalHeaderLabels(["Use", "Weight (g)", "Total Weight (g)", "Description"])
        self.weight_table.horizontalHeader().setStretchLastSection(True)
        self.weight_table.setAlternatingRowColors(True)
        
        # Default weight data (cumulative method) - All 5 steps checked by default
        default_steps = [
            (True, 0.00, "Step 1: Zero point (No load)"),
            (True, 1.07, "Step 2: First weight"),
            (True, 1.14, "Step 3: Add second weight"),
            (True, 1.00, "Step 4: Add third weight"),
            (True, 1.08, "Step 5: Add fourth weight")
        ]
        
        for row, (use, weight, desc) in enumerate(default_steps):
            # 체크박스
            check = QCheckBox()
            check.setChecked(use)
            self.weight_table.setCellWidget(row, 0, check)
            
            # 추가할 무게 (편집 가능한 SpinBox)
            weight_spin = QDoubleSpinBox()
            weight_spin.setRange(0.0, 1000.0)
            weight_spin.setValue(weight)
            weight_spin.setDecimals(2)  # 소수 2자리
            weight_spin.setSuffix(" g")
            weight_spin.setMinimumWidth(120)
            if row == 0:  # 첫 번째 행은 0으로 고정
                weight_spin.setEnabled(False)
                weight_spin.setStyleSheet("background-color: #f0f0f0;")
            else:
                weight_spin.valueChanged.connect(self._update_cumulative_weights)
            self.weight_table.setCellWidget(row, 1, weight_spin)
            
            # 누적 무게 (읽기 전용)
            cumulative_label = QLabel("0.00 g")
            cumulative_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cumulative_label.setStyleSheet("background-color: #f8f8f8; padding: 4px; border-radius: 2px;")
            self.weight_table.setCellWidget(row, 2, cumulative_label)
            
            # 설명 (편집 가능한 텍스트)
            desc_item = QTableWidgetItem(desc)
            desc_item.setFlags(desc_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.weight_table.setItem(row, 3, desc_item)
        
        # 초기 누적 무게 계산
        self._update_cumulative_weights()
        
        weight_layout.addWidget(self.weight_table)
        
        # Weight management buttons
        button_layout = QHBoxLayout()
        
        add_button = QPushButton("Add Weight")
        add_button.setIcon(qta.icon('fa5s.plus'))
        add_button.clicked.connect(self._add_weight_row)
        button_layout.addWidget(add_button)
        
        remove_button = QPushButton("Remove Selected")
        remove_button.setIcon(qta.icon('fa5s.minus'))
        remove_button.clicked.connect(self._remove_selected_rows)
        button_layout.addWidget(remove_button)
        
        button_layout.addStretch()
        weight_layout.addLayout(button_layout)
        
        weight_group.setLayout(weight_layout)
        layout.addWidget(weight_group)
        
        # Collection settings
        settings_group = QGroupBox("Collection Settings")
        settings_layout = QFormLayout()
        
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 60)
        self.duration_spin.setValue(10)  # Default 10 seconds
        self.duration_spin.setSuffix(" sec")
        settings_layout.addRow("Collection time per weight:", self.duration_spin)
        
        self.min_samples_spin = QSpinBox()
        self.min_samples_spin.setRange(50, 500)
        self.min_samples_spin.setValue(150)  # Default 150 samples
        self.min_samples_spin.setSuffix(" samples")
        settings_layout.addRow("Minimum samples:", self.min_samples_spin)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        self.setLayout(layout)
    
    def _update_cumulative_weights(self):
        """누적 무게 업데이트"""
        cumulative = 0.0
        
        for row in range(self.weight_table.rowCount()):
            # 추가할 무게 가져오기
            weight_spin = self.weight_table.cellWidget(row, 1)
            if weight_spin:
                if row == 0:
                    # 첫 번째 행은 항상 0
                    cumulative = 0.0
                else:
                    # 누적 계산
                    cumulative += weight_spin.value()
                
                # 누적 무게 레이블 업데이트
                cumulative_label = self.weight_table.cellWidget(row, 2)
                if cumulative_label:
                    cumulative_label.setText(f"{cumulative:.2f} g")
                    
                    # 색상 구분 (무게에 따라)
                    if cumulative == 0.0:
                        cumulative_label.setStyleSheet(
                            "background-color: #f0f0f0; padding: 4px; border-radius: 2px; color: #666;"
                        )
                    else:
                        cumulative_label.setStyleSheet(
                            "background-color: #e8f5e8; padding: 4px; border-radius: 2px; color: #2c5f2d; font-weight: bold;"
                        )
    
    def _add_weight_row(self):
        """무게 행 추가"""
        row = self.weight_table.rowCount()
        self.weight_table.insertRow(row)
        
        # 체크박스
        check = QCheckBox()
        check.setChecked(True)
        self.weight_table.setCellWidget(row, 0, check)
        
        # 추가할 무게 SpinBox
        weight_spin = QDoubleSpinBox()
        weight_spin.setRange(0.0, 1000.0)
        weight_spin.setValue(1.00)
        weight_spin.setDecimals(2)  # 소수 2자리
        weight_spin.setSuffix(" g")
        weight_spin.setMinimumWidth(120)
        weight_spin.valueChanged.connect(self._update_cumulative_weights)
        self.weight_table.setCellWidget(row, 1, weight_spin)
        
        # 누적 무게 레이블
        cumulative_label = QLabel("0.00 g")
        cumulative_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cumulative_label.setStyleSheet("background-color: #f8f8f8; padding: 4px; border-radius: 2px;")
        self.weight_table.setCellWidget(row, 2, cumulative_label)
        
        # 설명
        desc_item = QTableWidgetItem(f"{row + 1}단계: 추가 무게추")
        desc_item.setFlags(desc_item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.weight_table.setItem(row, 3, desc_item)
        
        # 누적 무게 업데이트
        self._update_cumulative_weights()
        
        # 새 행으로 스크롤
        self.weight_table.scrollToItem(desc_item)
    
    def _remove_selected_rows(self):
        """선택된 행 삭제"""
        selected_rows = set()
        for item in self.weight_table.selectedItems():
            selected_rows.add(item.row())
        
        # 첫 번째 행(영점)은 삭제 불가
        selected_rows.discard(0)
        
        if not selected_rows:
            QMessageBox.information(
                self,
                "삭제 불가",
                "영점(첫 번째 행)은 삭제할 수 없습니다.\n다른 행을 선택해주세요."
            )
            return
        
        # 역순으로 삭제 (인덱스 변경 방지)
        for row in sorted(selected_rows, reverse=True):
            self.weight_table.removeRow(row)
        
        # 최소 2행은 유지 (영점 + 1개 이상)
        if self.weight_table.rowCount() < 2:
            self._add_weight_row()
        
        # 누적 무게 재계산
        self._update_cumulative_weights()
    
    def get_weights(self) -> List[float]:
        """선택된 누적 무게 목록 반환"""
        weights = []
        cumulative = 0.0
        
        for row in range(self.weight_table.rowCount()):
            check = self.weight_table.cellWidget(row, 0)
            if check and check.isChecked():
                weight_spin = self.weight_table.cellWidget(row, 1)
                if weight_spin:
                    if row == 0:
                        cumulative = 0.0
                    else:
                        cumulative += weight_spin.value()
                    weights.append(round(cumulative, 2))
        
        return weights  # 이미 순서대로 되어 있음
    
    def get_individual_weights(self) -> List[float]:
        """선택된 개별 무게 목록 반환 (단일 무게)"""
        individual_weights = []
        
        for row in range(self.weight_table.rowCount()):
            check = self.weight_table.cellWidget(row, 0)
            if check and check.isChecked():
                weight_spin = self.weight_table.cellWidget(row, 1)
                if weight_spin:
                    if row == 0:
                        individual_weights.append(0.0)  # 영점
                    else:
                        individual_weights.append(round(weight_spin.value(), 2))
        
        return individual_weights
    
    def validatePage(self):
        """페이지 검증"""
        weights = self.get_weights()
        
        # Check minimum count
        if len(weights) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Weights",
                "Please select at least 2 weights.\n\n"
                "3 or more weights are recommended for accurate calibration."
            )
            return False
        
        # Check for duplicate weights
        if len(weights) != len(set(weights)):
            QMessageBox.warning(
                self,
                "Duplicate Weights",
                "Multiple identical weights have been selected.\n"
                "Please use different weights for each step."
            )
            return False
        
        # Check weight range
        if max(weights) - min(weights) < 10.0:
            reply = QMessageBox.question(
                self,
                "Weight Range Warning",
                f"The selected weight range is narrow ({max(weights) - min(weights):.1f}g).\n"
                "A wider range will improve calibration accuracy.\n\n"
                "Do you want to continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        
        # Save settings
        wizard = self.wizard()
        if wizard:
            individual_weights = self.get_individual_weights()
            wizard.settings = CalibrationSettings(
                reference_weights=weights,
                individual_weights=individual_weights,
                collection_duration=self.duration_spin.value(),
                min_samples=self.min_samples_spin.value()
            )
            
            # Log selected weight information
            wizard.logger.info(f"Calibration weight settings: {weights}")
        
        return True


class CollectionPage(QWizardPage):
    """Data Collection Page"""
    
    collection_completed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Data Collection")
        self.setSubTitle("Collect sensor data for each weight")
        
        self.current_weight = 0.0
        self.current_step = 0
        self.total_steps = 0
        self.is_collecting = False
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # 현재 단계 표시
        self.step_label = QLabel()
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.step_label.setFont(font)
        layout.addWidget(self.step_label)
        
        # Weight instruction
        instruction_group = QGroupBox("Instructions")
        instruction_layout = QVBoxLayout()
        
        self.instruction_label = QLabel()
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instruction_layout.addWidget(self.instruction_label)
        
        instruction_group.setLayout(instruction_layout)
        layout.addWidget(instruction_group)
        
        # Real-time data display
        data_group = QGroupBox("Real-time Sensor Data")
        data_layout = QGridLayout()
        
        # Current value
        data_layout.addWidget(QLabel("Current Value:"), 0, 0)
        self.current_value_label = QLabel("0.0")
        self.current_value_label.setStyleSheet("QLabel { font-size: 18px; font-weight: bold; }")
        data_layout.addWidget(self.current_value_label, 0, 1)
        
        # Average value
        data_layout.addWidget(QLabel("Average:"), 1, 0)
        self.average_label = QLabel("0.0")
        data_layout.addWidget(self.average_label, 1, 1)
        
        # Standard deviation
        data_layout.addWidget(QLabel("Std Dev:"), 2, 0)
        self.std_label = QLabel("0.0")
        data_layout.addWidget(self.std_label, 2, 1)
        
        # Sample count
        data_layout.addWidget(QLabel("Samples:"), 3, 0)
        self.sample_count_label = QLabel("0")
        data_layout.addWidget(self.sample_count_label, 3, 1)
        
        # Quality indicator
        data_layout.addWidget(QLabel("Quality:"), 4, 0)
        self.quality_label = QLabel("Waiting")
        data_layout.addWidget(self.quality_label, 4, 1)
        
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)
        
        # 진행률
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Collection")
        self.start_button.setIcon(qta.icon('fa5s.play'))
        self.start_button.clicked.connect(self.start_collection)
        button_layout.addWidget(self.start_button)
        
        self.skip_button = QPushButton("Skip")
        self.skip_button.setIcon(qta.icon('fa5s.forward', color='red'))
        self.skip_button.clicked.connect(self.skip_weight)
        self.skip_button.setEnabled(False)
        button_layout.addWidget(self.skip_button)
        
        layout.addLayout(button_layout)
        
        # Status message
        self.status_label = QLabel("Waiting...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def initializePage(self):
        """페이지 초기화"""
        wizard = self.wizard()
        if wizard and hasattr(wizard, 'settings'):
            self.weights = wizard.settings.reference_weights  # 누적 무게 (캘리브레이션용)
            self.individual_weights = wizard.settings.individual_weights  # 개별 무게 (안내용)
            self.total_steps = len(self.weights)
            self.current_step = 0
            
            # 캘리브레이션 엔진 연결
            if hasattr(wizard, 'calibration_engine'):
                engine = wizard.calibration_engine
                
                # 시그널 연결
                engine.data_point_added.connect(self.update_sensor_value)
                engine.progress_updated.connect(self.update_progress)
                engine.point_collected.connect(self.on_point_collected)
                engine.error_occurred.connect(self.on_error)
                
                # 캘리브레이션 시작
                config = CollectionConfig(
                    collection_duration=wizard.settings.collection_duration,
                    min_samples=wizard.settings.min_samples,
                    auto_advance=False  # 항상 수동 진행
                )
                engine.config = config
                engine.start_calibration(self.weights)
            
            self.update_display()
    
    def update_display(self):
        """Update display"""
        if self.current_step < self.total_steps:
            self.current_weight = self.weights[self.current_step]  # For calibration (cumulative)
            current_individual_weight = self.individual_weights[self.current_step]  # For guidance (individual)
            
            self.step_label.setText(f"Step {self.current_step + 1} / {self.total_steps}")
            
            # Display guidance message with individual weight
            if self.current_step == 0:
                # First step (zero point)
                self.instruction_label.setText(
                    f"<h3>Zero Point Setting</h3>"
                    f"<p>Click 'Start Collection' button without any weight.</p>"
                )
                self.status_label.setText("Waiting for zero point collection...")
            else:
                # Subsequent steps - guidance with individual weight
                self.instruction_label.setText(
                    f"<h3>Place {current_individual_weight}g weight</h3>"
                    f"<p>After placing the weight, click 'Start Collection' button.</p>"
                )
                self.status_label.setText(f"Waiting to collect {current_individual_weight}g weight...")
            
            self.progress_bar.setValue(0)
    
    def start_collection(self):
        """Start collection"""
        if self.is_collecting:
            return
        
        self.is_collecting = True
        self.start_button.setEnabled(False)
        self.skip_button.setEnabled(True)
        
        wizard = self.wizard()
        if wizard and hasattr(wizard, 'calibration_engine'):
            # Start collecting current weight (pass cumulative weight to calibration engine)
            wizard.calibration_engine.start_point_collection(self.current_weight)
            
            # Display status message with individual weight
            if self.current_step == 0:
                self.status_label.setText("Collecting zero point...")
            else:
                current_individual_weight = self.individual_weights[self.current_step]
                self.status_label.setText(f"Collecting {current_individual_weight}g weight...")
    
    def skip_weight(self):
        """현재 무게 건너뛰기"""
        self.current_step += 1
        self.is_collecting = False
        self.start_button.setEnabled(True)
        self.skip_button.setEnabled(False)
        
        if self.current_step >= self.total_steps:
            self.collection_completed.emit()
            wizard = self.wizard()
            if wizard:
                wizard.next()
        else:
            self.update_display()
    
    @pyqtSlot(float)
    def update_sensor_value(self, value):
        """센서 값 업데이트"""
        self.current_value_label.setText(f"{value:.2f}")
    
    @pyqtSlot(int, str)
    def update_progress(self, progress, status):
        """Update progress"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(status)
    
    @pyqtSlot(CalibrationPoint)
    def on_point_collected(self, point):
        """Point collection completed"""
        # Display statistics
        self.average_label.setText(f"{point.average_reading:.2f}")
        self.std_label.setText(f"{point.std_reading:.4f}")
        self.sample_count_label.setText(f"{len(point.sensor_readings)}")
        
        # Quality evaluation
        quality_score = point.quality_score
        if quality_score >= 0.9:
            quality_text = "✅ Excellent"
            color = "green"
        elif quality_score >= 0.7:
            quality_text = "⚠️ Good"
            color = "orange"
        else:
            quality_text = "❌ Poor"
            color = "red"
        
        self.quality_label.setText(quality_text)
        self.quality_label.setStyleSheet(f"color: {color};")
        
        # Reset UI state
        self.is_collecting = False
        self.start_button.setEnabled(True)
        self.skip_button.setEnabled(False)
        
        # Move to next step
        self.current_step += 1
        
        if self.current_step >= self.total_steps:
            self.status_label.setText("All data collection completed!")
            self.collection_completed.emit()
            # Only send signal without auto-advancing to next page
        else:
            # Update next step display - user starts manually
            self.update_display()
    
    @pyqtSlot(str)
    def on_error(self, error_msg):
        """Error handling"""
        QMessageBox.critical(self, "Error", error_msg)
        self.is_collecting = False
        self.start_button.setEnabled(True)
    
    def isComplete(self):
        """Check if page is complete"""
        return self.current_step >= self.total_steps


class AnalysisPage(QWizardPage):
    """Analysis page"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Calibration Analysis")
        self.setSubTitle("Analyze collected data and generate optimal calibration")
        
        self.result = None
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()

        # Analysis method info (fixed to Linear Regression)
        method_group = QGroupBox("Analysis Method")
        method_layout = QVBoxLayout()

        method_info = QLabel(
            "<b>Regression Method:</b> Linear Regression<br>"
            "<i>Using simple linear regression (y = ax + b) for calibration</i>"
        )
        method_info.setWordWrap(True)
        method_info.setStyleSheet("QLabel { padding: 8px; }")
        method_layout.addWidget(method_info)

        method_group.setLayout(method_layout)
        layout.addWidget(method_group)

        # Analysis results
        result_group = QGroupBox("Analysis Results")
        result_layout = QGridLayout()
        
        # R²
        result_layout.addWidget(QLabel("Coefficient of Determination (R²):"), 0, 0)
        self.r_squared_label = QLabel("-")
        self.r_squared_label.setStyleSheet("font-weight: bold;")
        result_layout.addWidget(self.r_squared_label, 0, 1)
        
        # RMSE
        result_layout.addWidget(QLabel("RMSE:"), 1, 0)
        self.rmse_label = QLabel("-")
        self.rmse_label.setStyleSheet("font-weight: bold;")
        result_layout.addWidget(self.rmse_label, 1, 1)
        
        # Quality grade
        result_layout.addWidget(QLabel("Quality Grade:"), 2, 0)
        self.quality_grade_label = QLabel("-")
        self.quality_grade_label.setStyleSheet("font-weight: bold;")
        result_layout.addWidget(self.quality_grade_label, 2, 1)
        
        # Validation results
        result_layout.addWidget(QLabel("Validation:"), 3, 0)
        self.validation_label = QLabel("-")
        self.validation_label.setStyleSheet("font-weight: bold;")
        result_layout.addWidget(self.validation_label, 3, 1)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        # Coefficient display
        coeff_group = QGroupBox("Regression Coefficients")
        coeff_layout = QVBoxLayout()
        
        self.coeff_text = QTextEdit()
        self.coeff_text.setReadOnly(True)
        self.coeff_text.setMaximumHeight(100)
        coeff_layout.addWidget(self.coeff_text)
        
        coeff_group.setLayout(coeff_layout)
        layout.addWidget(coeff_group)

        layout.addStretch()
        self.setLayout(layout)
    
    def initializePage(self):
        """Initialize page"""
        # Run automatic analysis
        QTimer.singleShot(500, self.run_analysis)
    
    def run_analysis(self):
        """Run analysis (fixed to Linear Regression)"""
        wizard = self.wizard()
        if not wizard or not hasattr(wizard, 'calibration_engine'):
            return

        engine = wizard.calibration_engine

        # Always use Linear Regression
        method = CalibrationMethod.LINEAR

        # Run analysis
        self.result = engine.calculate_calibration(method)
        
        if self.result:
            # Display results
            self.r_squared_label.setText(f"{self.result.r_squared:.6f}")
            self.rmse_label.setText(f"{self.result.rmse:.6f}")
            self.quality_grade_label.setText(self.result.quality_grade)
            
            # Color by quality
            if self.result.quality_grade == "Excellent":
                color = "green"
            elif self.result.quality_grade == "Good":
                color = "blue"
            elif self.result.quality_grade == "Fair":
                color = "orange"
            else:
                color = "red"
            self.quality_grade_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            
            # Validation results
            if self.result.validation_passed:
                self.validation_label.setText("✅ Passed")
                self.validation_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.validation_label.setText("⚠️ Needs Attention")
                self.validation_label.setStyleSheet("color: orange; font-weight: bold;")
            
            # Display coefficients
            coeff_text = f"Method: {self.result.method.value}\n"
            if self.result.method == CalibrationMethod.LINEAR:
                slope, intercept = self.result.coefficients
                coeff_text += f"y = {slope:.6f} * x + {intercept:.6f}"
            elif self.result.method == CalibrationMethod.POLYNOMIAL_2:
                a, b, c = self.result.coefficients
                coeff_text += f"y = {a:.6f}x² + {b:.6f}x + {c:.6f}"
            elif self.result.method == CalibrationMethod.POLYNOMIAL_3:
                a, b, c, d = self.result.coefficients
                coeff_text += f"y = {a:.6f}x³ + {b:.6f}x² + {c:.6f}x + {d:.6f}"
            
            self.coeff_text.setText(coeff_text)
            
            # Save result to wizard
            wizard.calibration_result = self.result
    
    def validatePage(self):
        """Validate page"""
        if not self.result:
            QMessageBox.warning(
                self,
                "Analysis Required",
                "Please run analysis first."
            )
            return False
        
        if not self.result.validation_passed:
            reply = QMessageBox.question(
                self,
                "Validation Warning",
                "Calibration quality does not meet standards.\nDo you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        
        return True


class CompletionPage(QWizardPage):
    """Completion page"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Calibration Complete")
        self.setSubTitle("Calibration has been successfully completed")
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Completion message
        complete_label = QLabel(
            "<h2>✅ Calibration Complete!</h2>"
            "<p>Sensor calibration has been successfully completed.</p>"
        )
        complete_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(complete_label)
        
        # Summary information
        summary_group = QGroupBox("Calibration Summary")
        summary_layout = QFormLayout()
        
        self.method_label = QLabel()
        summary_layout.addRow("Method:", self.method_label)
        
        self.quality_label = QLabel()
        summary_layout.addRow("Quality:", self.quality_label)
        
        self.points_label = QLabel()
        summary_layout.addRow("Collection Points:", self.points_label)
        
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        # Next steps
        next_steps = QLabel(
            "<b>Next Steps:</b><br>"
            "• Calibration will be applied automatically<br>"
            "• When you start measuring, converted values will be displayed<br>"
            "• If needed, you can re-run from Tools → Calibration"
        )
        next_steps.setWordWrap(True)
        layout.addWidget(next_steps)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def initializePage(self):
        """Initialize page"""
        wizard = self.wizard()
        if wizard and hasattr(wizard, 'calibration_result'):
            result = wizard.calibration_result
            
            # Display summary information
            self.method_label.setText(result.method.value)
            self.quality_label.setText(f"{result.quality_grade} (R² = {result.r_squared:.4f})")
            self.points_label.setText(f"{len(result.points)} points")
            
            # Color by quality
            if result.quality_grade == "Excellent":
                color = "green"
            elif result.quality_grade == "Good":
                color = "blue"
            else:
                color = "orange"
            self.quality_label.setStyleSheet(f"color: {color}; font-weight: bold;")
    
    def validatePage(self):
        """Validate page (save processing)"""
        wizard = self.wizard()
        if not wizard or not hasattr(wizard, 'calibration_result'):
            return True

        result = wizard.calibration_result

        # Always apply calibration to DataProcessor
        if hasattr(wizard, 'data_processor'):
            wizard.data_processor.set_calibration(result)

        return True


class CalibrationWizard(QWizard):
    """
    Calibration Wizard
    
    Wizard that guides through step-by-step calibration process
    """
    
    calibration_completed = pyqtSignal(CalibrationResult)
    
    def __init__(self, serial_manager=None, data_processor=None, parent=None):
        super().__init__(parent)
        
        self.serial_manager = serial_manager
        self.data_processor = data_processor
        self.calibration_engine = CalibrationEngine()
        self.calibration_result = None
        self.settings = None
        
        self.setWindowTitle("PODFA Calibration Wizard")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(1000, 800)  # Increased size
        self.resize(1200, 900)  # Default size also increased
        
        # Add pages
        self.addPage(IntroductionPage())
        self.addPage(WeightSettingsPage())
        
        # Add CollectionPage and connect signals
        self.collection_page = CollectionPage()
        self.collection_page.collection_completed.connect(self._on_collection_completed)
        self.addPage(self.collection_page)
        
        self.addPage(AnalysisPage())
        self.addPage(CompletionPage())
        
        # Serial connection
        if self.serial_manager:
            self.serial_manager.data_received.connect(self._on_serial_data)
        
        # Completion signal
        self.finished.connect(self._on_finished)
        
        # Logger
        self.logger = logging.getLogger(__name__)
        
        # Set data processor to calibration mode when starting calibration
        if self.data_processor:
            self.data_processor.set_calibration_mode(True)
            self.logger.info("Data processor calibration mode activated")
    
    @pyqtSlot(str)
    def _on_serial_data(self, data):
        """Serial data received"""
        if self.calibration_engine.state == CalibrationState.COLLECTING:
            try:
                # Parse data (needs adjustment for format)
                value = float(data.strip())
                self.calibration_engine.add_sensor_reading(value)
            except ValueError:
                pass  # Ignore invalid data
    
    @pyqtSlot()
    def _on_collection_completed(self):
        """Data collection completed"""
        self.logger.info("Data collection completed, proceeding to next step")
        self.next()  # Move to next page
    
    def _on_finished(self, result):
        """Wizard completed"""
        # Disable calibration mode
        if self.data_processor:
            self.data_processor.set_calibration_mode(False)
            self.logger.info("Data processor calibration mode deactivated")
        
        if result == QWizard.DialogCode.Accepted and self.calibration_result:
            self.calibration_completed.emit(self.calibration_result)
            self.logger.info("Calibration wizard completed")
        else:
            self.logger.info("Calibration wizard cancelled")