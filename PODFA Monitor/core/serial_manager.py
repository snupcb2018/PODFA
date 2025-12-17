"""
PBS 2.0 Serial Communication Manager
=====================================

고급 시리얼 통신 관리자
- 비동기 데이터 수집
- 자동 포트 감지 및 재연결
- 안전한 리소스 관리
- 성능 모니터링
"""

import asyncio
import logging
import time
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import threading
from queue import Queue, Empty

import serial
import serial.tools.list_ports as list_ports
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class ConnectionState(Enum):
    """연결 상태 열거형"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class SerialConfig:
    """시리얼 포트 설정"""
    port: str = "COM3"
    baudrate: int = 921600
    timeout: float = 1.0
    rtscts: bool = True
    parity: str = 'N'
    stopbits: int = 1
    bytesize: int = 8
    
    def __post_init__(self):
        """설정 검증"""
        if self.baudrate <= 0:
            raise ValueError("Baudrate must be positive")
        if self.timeout < 0:
            raise ValueError("Timeout cannot be negative")


@dataclass
class PerformanceMetrics:
    """성능 메트릭"""
    bytes_received: int = 0
    packets_received: int = 0
    errors_count: int = 0
    connection_uptime: float = 0.0
    last_data_time: Optional[float] = None
    
    @property
    def data_rate(self) -> float:
        """데이터 수신율 (bytes/sec)"""
        if self.connection_uptime > 0:
            return self.bytes_received / self.connection_uptime
        return 0.0
    
    @property
    def packet_rate(self) -> float:
        """패킷 수신율 (packets/sec)"""
        if self.connection_uptime > 0:
            return self.packets_received / self.connection_uptime
        return 0.0


class SerialManager(QObject):
    """
    🔌 고급 시리얼 통신 관리자
    
    Features:
    - 비동기 데이터 처리
    - 자동 재연결
    - 성능 모니터링
    - 안전한 리소스 관리
    """
    
    # 시그널 정의
    data_received = pyqtSignal(str)  # 데이터 수신
    connection_changed = pyqtSignal(ConnectionState)  # 연결 상태 변경
    port_list_updated = pyqtSignal(list)  # 포트 목록 업데이트
    performance_updated = pyqtSignal(PerformanceMetrics)  # 성능 메트릭 업데이트
    error_occurred = pyqtSignal(str)  # 에러 발생
    
    def __init__(self, config: Optional[SerialConfig] = None):
        super().__init__()
        
        # 설정 및 상태
        self.config = config or SerialConfig()
        self.state = ConnectionState.DISCONNECTED
        self.serial_port: Optional[serial.Serial] = None
        
        # 성능 메트릭
        self.metrics = PerformanceMetrics()
        self._connection_start_time: Optional[float] = None
        
        # 스레딩 및 큐
        self._running = False
        self._read_thread: Optional[threading.Thread] = None
        self._data_queue = Queue(maxsize=10000)  # 대용량 버퍼
        
        # 타이머 설정
        self._port_scanner = QTimer()
        self._port_scanner.timeout.connect(self._scan_ports)
        self._port_scanner.start(2000)  # 2초마다 스캔
        
        self._metrics_timer = QTimer()
        self._metrics_timer.timeout.connect(self._update_metrics)
        self._metrics_timer.start(1000)  # 1초마다 메트릭 업데이트
        
        # 로깅
        self.logger = logging.getLogger(__name__)
        
        # 초기 포트 스캔
        self._scan_ports()
    
    def get_available_ports(self) -> List[Dict[str, str]]:
        """사용 가능한 포트 목록 반환"""
        ports = []
        try:
            for port in sorted(list_ports.comports()):
                ports.append({
                    'device': port.device,
                    'description': port.description,
                    'hwid': port.hwid
                })
        except Exception as e:
            self.logger.error(f"포트 스캔 실패: {e}")
        
        return ports
    
    def connect(self, port: Optional[str] = None) -> bool:
        """
        시리얼 포트 연결
        
        Args:
            port: 연결할 포트. None이면 config의 포트 사용
            
        Returns:
            연결 성공 여부
        """
        if self.state == ConnectionState.CONNECTED:
            self.logger.warning("이미 연결되어 있습니다")
            return True
            
        if port:
            self.config.port = port
            
        self._set_state(ConnectionState.CONNECTING)
        
        try:
            # 시리얼 포트 열기
            self.serial_port = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                timeout=self.config.timeout,
                rtscts=self.config.rtscts,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
                bytesize=self.config.bytesize
            )
            
            # 입력 버퍼 초기화
            self.serial_port.reset_input_buffer()
            
            # 읽기 스레드 시작
            self._running = True
            self._read_thread = threading.Thread(
                target=self._read_loop, 
                daemon=True,
                name=f"SerialReader-{self.config.port}"
            )
            self._read_thread.start()
            
            # 연결 시간 기록
            self._connection_start_time = time.time()
            self.metrics = PerformanceMetrics()  # 메트릭 초기화
            
            self._set_state(ConnectionState.CONNECTED)
            self.logger.info(f"포트 {self.config.port} 연결 성공")
            
            return True
            
        except Exception as e:
            self.logger.error(f"포트 연결 실패: {e}")
            self.error_occurred.emit(f"연결 실패: {str(e)}")
            self._set_state(ConnectionState.ERROR)
            return False
    
    def disconnect(self):
        """시리얼 포트 연결 해제"""
        if self.state == ConnectionState.DISCONNECTED:
            return
            
        self.logger.info("연결 해제 중...")
        self._running = False
        
        # 읽기 스레드 종료 대기
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
            
        # 시리얼 포트 닫기
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception as e:
                self.logger.error(f"포트 닫기 실패: {e}")
                
        self.serial_port = None
        self._connection_start_time = None
        self._set_state(ConnectionState.DISCONNECTED)
        self.logger.info("연결 해제 완료")
    
    def send_data(self, data: str) -> bool:
        """
        데이터 전송
        
        Args:
            data: 전송할 데이터
            
        Returns:
            전송 성공 여부
        """
        if not self.is_connected():
            self.logger.warning("연결되지 않은 상태에서 데이터 전송 시도")
            return False
            
        try:
            self.serial_port.write(data.encode())
            return True
        except Exception as e:
            self.logger.error(f"데이터 전송 실패: {e}")
            self.error_occurred.emit(f"전송 실패: {str(e)}")
            return False
    
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return (self.state == ConnectionState.CONNECTED and 
                self.serial_port and 
                self.serial_port.is_open)
    
    def get_metrics(self) -> PerformanceMetrics:
        """현재 성능 메트릭 반환"""
        return self.metrics
    
    def _read_loop(self):
        """데이터 읽기 루프 (별도 스레드에서 실행)"""
        self.logger.info("데이터 읽기 시작")
        
        while self._running and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    # 데이터 읽기
                    raw_data = self.serial_port.readline()
                    
                    if raw_data:
                        try:
                            # 디코딩 및 정리
                            data = raw_data.decode('utf-8', errors='ignore').strip()
                            
                            if data:
                                # 메트릭 업데이트
                                self.metrics.bytes_received += len(raw_data)
                                self.metrics.packets_received += 1
                                self.metrics.last_data_time = time.time()
                                
                                # 데이터 큐에 추가 (논블로킹)
                                try:
                                    self._data_queue.put_nowait(data)
                                except:
                                    # 큐가 가득 찬 경우 오래된 데이터 제거
                                    try:
                                        self._data_queue.get_nowait()
                                        self._data_queue.put_nowait(data)
                                    except Empty:
                                        pass
                                
                                # 시그널 발송 (UI 스레드에서 처리)
                                self.data_received.emit(data)
                                
                        except UnicodeDecodeError:
                            self.metrics.errors_count += 1
                            self.logger.debug("디코딩 오류")
                            
                else:
                    # CPU 사용량 감소를 위한 작은 대기
                    time.sleep(0.005)  # 5ms 대기
                    
            except serial.SerialException as e:
                self.logger.error(f"시리얼 읽기 오류: {e}")
                self.metrics.errors_count += 1
                self.error_occurred.emit(f"읽기 오류: {str(e)}")
                break
            except Exception as e:
                self.logger.error(f"예상치 못한 오류: {e}")
                self.metrics.errors_count += 1
                break
        
        self.logger.info("데이터 읽기 종료")
    
    def _scan_ports(self):
        """포트 목록 스캔 및 업데이트"""
        try:
            ports = self.get_available_ports()
            self.port_list_updated.emit(ports)
        except Exception as e:
            self.logger.error(f"포트 스캔 오류: {e}")
    
    def _update_metrics(self):
        """성능 메트릭 업데이트"""
        if self._connection_start_time:
            self.metrics.connection_uptime = time.time() - self._connection_start_time
            
        self.performance_updated.emit(self.metrics)
    
    def _set_state(self, new_state: ConnectionState):
        """연결 상태 변경"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.logger.info(f"상태 변경: {old_state.value} -> {new_state.value}")
            self.connection_changed.emit(new_state)
    
    def cleanup(self):
        """리소스 정리"""
        self.disconnect()
        
        # QTimer 객체들 안전하게 정리
        try:
            if hasattr(self, '_port_scanner') and self._port_scanner:
                self._port_scanner.stop()
        except RuntimeError:
            # QTimer가 이미 삭제된 경우 무시
            pass
        
        try:
            if hasattr(self, '_metrics_timer') and self._metrics_timer:
                self._metrics_timer.stop()
        except RuntimeError:
            # QTimer가 이미 삭제된 경우 무시
            pass
        
        # 큐 정리
        try:
            while not self._data_queue.empty():
                try:
                    self._data_queue.get_nowait()
                except Empty:
                    break
        except AttributeError:
            # 큐가 이미 삭제된 경우 무시
            pass
    
    def __del__(self):
        """소멸자"""
        try:
            self.cleanup()
        except Exception:
            # 종료 과정에서 발생하는 모든 예외 무시
            pass