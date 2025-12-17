"""
PBS 2.0 필터 설정 다이얼로그
============================

사용자가 필터 타입과 설정값을 조정할 수 있는 다이얼로그
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QDoubleSpinBox, QSpinBox, 
    QPushButton, QGroupBox, QCheckBox, QSlider,
    QFrame, QMessageBox, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QPalette, QColor
import qtawesome as qta

from core.data_processor import ProcessingConfig, FilterType


class FilterSettingsDialog(QDialog):
    """필터 설정 다이얼로그"""
    
    # 설정 변경 시그널
    filter_settings_changed = pyqtSignal(ProcessingConfig)
    
    def __init__(self, current_config: ProcessingConfig, parent=None):
        super().__init__(parent)
        self.current_config = current_config
        self.settings = QSettings()
        
        self._init_ui()
        self._load_settings()
        self._connect_signals()
        
    def _init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("📊 Filter Settings")
        self.setWindowIcon(qta.icon('fa5s.filter'))
        self.setFixedSize(500, 650)
        self.setModal(True)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # 제목
        title_label = QLabel("필터 설정")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 필터 타입 그룹
        self._create_filter_type_group(main_layout)
        
        # 필터별 설정 그룹들
        self._create_moving_average_group(main_layout)
        self._create_median_group(main_layout)
        self._create_butterworth_group(main_layout)
        
        # 미리보기 그룹
        self._create_preview_group(main_layout)
        
        # 버튼 그룹
        self._create_button_group(main_layout)
        
        # 스타일 적용
        self._apply_styles()
        
    def _create_filter_type_group(self, main_layout):
        """필터 타입 선택 그룹 생성"""
        group = QGroupBox("🎛️ 필터 타입")
        group_layout = QVBoxLayout(group)
        
        # 라디오 버튼 그룹
        self.filter_type_group = QButtonGroup(self)
        
        # 필터 옵션들
        filter_options = [
            (FilterType.NONE, "없음", "필터링 없이 원시 데이터 사용"),
            (FilterType.MOVING_AVERAGE, "이동평균", "부드러운 평균 필터 (일반적)"),
            (FilterType.MEDIAN, "중앙값", "돌출값 제거에 효과적"),
            (FilterType.BUTTERWORTH, "Butterworth", "전문적인 주파수 필터")
        ]
        
        for filter_type, name, description in filter_options:
            radio = QRadioButton(f"{name}")
            radio.setProperty("filter_type", filter_type)
            
            # 설명 라벨
            desc_label = QLabel(f"   {description}")
            desc_label.setStyleSheet("color: #666; font-size: 11px; margin-left: 20px;")
            
            group_layout.addWidget(radio)
            group_layout.addWidget(desc_label)
            group_layout.addSpacing(5)
            
            self.filter_type_group.addButton(radio)
        
        main_layout.addWidget(group)
        
    def _create_moving_average_group(self, main_layout):
        """이동평균 필터 설정 그룹"""
        self.ma_group = QGroupBox("📈 이동평균 필터 설정")
        layout = QGridLayout(self.ma_group)
        
        # 윈도우 크기
        layout.addWidget(QLabel("윈도우 크기:"), 0, 0)
        self.ma_window = QSpinBox()
        self.ma_window.setRange(2, 50)
        self.ma_window.setValue(5)
        self.ma_window.setSuffix(" 샘플")
        layout.addWidget(self.ma_window, 0, 1)
        
        # 설명
        desc = QLabel("작을수록 빠른 응답, 클수록 부드러운 결과")
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc, 1, 0, 1, 2)
        
        main_layout.addWidget(self.ma_group)
        
    def _create_median_group(self, main_layout):
        """중앙값 필터 설정 그룹"""
        self.median_group = QGroupBox("📊 중앙값 필터 설정")
        layout = QGridLayout(self.median_group)
        
        # 윈도우 크기
        layout.addWidget(QLabel("윈도우 크기:"), 0, 0)
        self.median_window = QSpinBox()
        self.median_window.setRange(3, 21)  # 홀수만 권장
        self.median_window.setValue(5)
        self.median_window.setSuffix(" 샘플")
        layout.addWidget(self.median_window, 0, 1)
        
        # 설명
        desc = QLabel("돌출값(spike) 제거에 매우 효과적")
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc, 1, 0, 1, 2)
        
        main_layout.addWidget(self.median_group)
        
    def _create_butterworth_group(self, main_layout):
        """Butterworth 필터 설정 그룹"""
        self.butterworth_group = QGroupBox("🔧 Butterworth 필터 설정")
        layout = QGridLayout(self.butterworth_group)
        
        # Cutoff 주파수
        layout.addWidget(QLabel("Cutoff 주파수:"), 0, 0)
        self.butterworth_cutoff = QDoubleSpinBox()
        self.butterworth_cutoff.setRange(0.1, 10.0)
        self.butterworth_cutoff.setValue(1.0)
        self.butterworth_cutoff.setSingleStep(0.1)
        self.butterworth_cutoff.setDecimals(1)
        self.butterworth_cutoff.setSuffix(" Hz")
        layout.addWidget(self.butterworth_cutoff, 0, 1)
        
        # 필터 차수
        layout.addWidget(QLabel("필터 차수:"), 1, 0)
        self.butterworth_order = QSpinBox()
        self.butterworth_order.setRange(1, 5)
        self.butterworth_order.setValue(2)
        self.butterworth_order.setSuffix(" 차")
        layout.addWidget(self.butterworth_order, 1, 1)
        
        # 샘플링 레이트
        layout.addWidget(QLabel("샘플링 레이트:"), 2, 0)
        self.sampling_rate = QDoubleSpinBox()
        self.sampling_rate.setRange(1.0, 100.0)
        self.sampling_rate.setValue(10.0)
        self.sampling_rate.setSingleStep(1.0)
        self.sampling_rate.setDecimals(1)
        self.sampling_rate.setSuffix(" Hz")
        layout.addWidget(self.sampling_rate, 2, 1)
        
        # 추천 설정 버튼들
        preset_layout = QHBoxLayout()
        presets = [
            ("일반", 1.0, 2, "균형잡힌 필터링"),
            ("강함", 0.5, 3, "강한 노이즈 제거"),
            ("약함", 3.0, 1, "빠른 응답")
        ]
        
        for name, cutoff, order, tooltip in presets:
            btn = QPushButton(name)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked, c=cutoff, o=order: self._apply_preset(c, o))
            preset_layout.addWidget(btn)
        
        layout.addLayout(preset_layout, 3, 0, 1, 2)
        
        # 설명
        desc = QLabel("Cutoff 주파수 이상의 신호를 차단합니다")
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc, 4, 0, 1, 2)
        
        main_layout.addWidget(self.butterworth_group)
        
    def _create_preview_group(self, main_layout):
        """미리보기 그룹"""
        self.preview_group = QGroupBox("👁️ 필터 효과 미리보기")
        layout = QVBoxLayout(self.preview_group)
        
        # 효과 설명 라벨
        self.effect_label = QLabel("필터를 선택하면 효과를 보여드립니다")
        self.effect_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                font-family: monospace;
            }
        """)
        layout.addWidget(self.effect_label)
        
        main_layout.addWidget(self.preview_group)
        
    def _create_button_group(self, main_layout):
        """버튼 그룹"""
        button_layout = QHBoxLayout()
        
        # 초기화 버튼
        reset_btn = QPushButton("🔄 초기화")
        reset_btn.clicked.connect(self._reset_settings)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        # 취소 버튼
        cancel_btn = QPushButton("❌ 취소")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        # 적용 버튼
        apply_btn = QPushButton("✅ 적용")
        apply_btn.clicked.connect(self._apply_settings)
        apply_btn.setDefault(True)
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        button_layout.addWidget(apply_btn)
        
        main_layout.addLayout(button_layout)
        
    def _apply_styles(self):
        """스타일 적용"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QSpinBox, QDoubleSpinBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton {
                padding: 5px 10px;
                border-radius: 3px;
                border: 1px solid #ccc;
                background-color: #f8f8f8;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
        """)
        
    def _connect_signals(self):
        """시그널 연결"""
        # 필터 타입 변경 시 그룹 표시/숨김
        for button in self.filter_type_group.buttons():
            button.toggled.connect(self._on_filter_type_changed)
            
        # 설정값 변경 시 미리보기 업데이트
        self.ma_window.valueChanged.connect(self._update_preview)
        self.median_window.valueChanged.connect(self._update_preview)
        self.butterworth_cutoff.valueChanged.connect(self._update_preview)
        self.butterworth_order.valueChanged.connect(self._update_preview)
        self.sampling_rate.valueChanged.connect(self._update_preview)
        
    def _on_filter_type_changed(self):
        """필터 타입 변경 핸들러"""
        # 모든 설정 그룹 숨기기
        self.ma_group.setVisible(False)
        self.median_group.setVisible(False)
        self.butterworth_group.setVisible(False)
        
        # 선택된 필터 그룹만 보이기
        selected_filter = self._get_selected_filter_type()
        
        if selected_filter == FilterType.MOVING_AVERAGE:
            self.ma_group.setVisible(True)
        elif selected_filter == FilterType.MEDIAN:
            self.median_group.setVisible(True)
        elif selected_filter == FilterType.BUTTERWORTH:
            self.butterworth_group.setVisible(True)
            
        self._update_preview()
        
        # 다이얼로그 크기 조정
        self.adjustSize()
        
    def _get_selected_filter_type(self) -> FilterType:
        """선택된 필터 타입 반환"""
        for button in self.filter_type_group.buttons():
            if button.isChecked():
                return button.property("filter_type")
        return FilterType.NONE
        
    def _apply_preset(self, cutoff: float, order: int):
        """Butterworth 프리셋 적용"""
        self.butterworth_cutoff.setValue(cutoff)
        self.butterworth_order.setValue(order)
        self._update_preview()
        
    def _update_preview(self):
        """미리보기 업데이트"""
        filter_type = self._get_selected_filter_type()
        
        preview_texts = {
            FilterType.NONE: "원시 데이터를 그대로 사용합니다.\n노이즈가 그대로 남아있을 수 있습니다.",
            
            FilterType.MOVING_AVERAGE: f"지난 {self.ma_window.value()}개 데이터의 평균을 계산합니다.\n"
                                     f"{'빠른 응답' if self.ma_window.value() < 5 else '부드러운 결과'}을 제공합니다.",
            
            FilterType.MEDIAN: f"지난 {self.median_window.value()}개 데이터의 중앙값을 사용합니다.\n"
                              f"돌출값(spike)을 효과적으로 제거합니다.",
            
            FilterType.BUTTERWORTH: f"{self.butterworth_cutoff.value()}Hz 이상의 주파수를 차단합니다.\n"
                                  f"{self.butterworth_order.value()}차 필터로 "
                                  f"{'급격한' if self.butterworth_order.value() >= 3 else '부드러운'} 필터링을 적용합니다.\n"
                                  f"샘플링: {self.sampling_rate.value()}Hz"
        }
        
        self.effect_label.setText(preview_texts.get(filter_type, "Unknown filter type."))
        
    def _load_settings(self):
        """설정 불러오기"""
        # 현재 설정값으로 UI 업데이트
        for button in self.filter_type_group.buttons():
            if button.property("filter_type") == self.current_config.filter_type:
                button.setChecked(True)
                break
        
        self.ma_window.setValue(self.current_config.filter_window)
        self.median_window.setValue(self.current_config.filter_window)
        self.butterworth_cutoff.setValue(self.current_config.butterworth_cutoff)
        self.butterworth_order.setValue(self.current_config.butterworth_order)
        self.sampling_rate.setValue(self.current_config.sampling_rate)
        
        # 필터 타입에 따라 그룹 표시
        self._on_filter_type_changed()
        
    def _reset_settings(self):
        """설정 초기화"""
        reply = QMessageBox.question(
            self, "설정 초기화", 
            "필터 설정을 기본값으로 초기화하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 기본 설정으로 초기화
            default_config = ProcessingConfig()
            
            for button in self.filter_type_group.buttons():
                if button.property("filter_type") == default_config.filter_type:
                    button.setChecked(True)
                    break
            
            self.ma_window.setValue(default_config.filter_window)
            self.median_window.setValue(default_config.filter_window)
            self.butterworth_cutoff.setValue(default_config.butterworth_cutoff)
            self.butterworth_order.setValue(default_config.butterworth_order)
            self.sampling_rate.setValue(default_config.sampling_rate)
            
            self._on_filter_type_changed()
            
    def _apply_settings(self):
        """설정 적용"""
        try:
            # 새 설정 생성
            new_config = ProcessingConfig(
                filter_type=self._get_selected_filter_type(),
                max_buffer_size=self.current_config.max_buffer_size,
                outlier_threshold=self.current_config.outlier_threshold,
                enable_auto_scaling=self.current_config.enable_auto_scaling,
                statistics_window=self.current_config.statistics_window,
                quality_threshold=self.current_config.quality_threshold
            )
            
            # 필터별 설정
            if new_config.filter_type == FilterType.MOVING_AVERAGE:
                new_config.filter_window = self.ma_window.value()
            elif new_config.filter_type == FilterType.MEDIAN:
                new_config.filter_window = self.median_window.value()
            elif new_config.filter_type == FilterType.BUTTERWORTH:
                new_config.butterworth_cutoff = self.butterworth_cutoff.value()
                new_config.butterworth_order = self.butterworth_order.value()
                new_config.sampling_rate = self.sampling_rate.value()
            
            # 설정 저장
            self._save_settings(new_config)
            
            # 시그널 발송
            self.filter_settings_changed.emit(new_config)
            
            # 성공 메시지
            QMessageBox.information(self, "Settings Applied", "Filter settings have been applied!")
            
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Settings Error", f"An error occurred while applying settings:\n{str(e)}")
            
    def _save_settings(self, config: ProcessingConfig):
        """설정 저장"""
        self.settings.setValue("filter/type", config.filter_type.value)
        self.settings.setValue("filter/window", config.filter_window)
        self.settings.setValue("filter/butterworth_cutoff", config.butterworth_cutoff)
        self.settings.setValue("filter/butterworth_order", config.butterworth_order)
        self.settings.setValue("filter/sampling_rate", config.sampling_rate)
        
