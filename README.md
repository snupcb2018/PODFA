# PODFA - Plant Organ Detachment Force Analyzer

A Raspberry Pi-based, user-friendly system for measuring petal detachment force in flower abscission studies.

**Authors**: Minsoo Han*, Hoon Jung*, Yuree Lee‡
*Equal contribution | ‡Correspondence

## License

**GNU General Public License v3 (GPL v3)** - See [LICENSE](./LICENSE) file

This software is designed for **research and educational purposes**. You are free to use, modify, and share your improvements, but modifications must be kept open-source under the same GPL v3 license. Commercial use is permitted only if source code modifications are shared publicly.

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Hardware Requirements](#hardware-requirements)
4. [Software Installation](#software-installation)
5. [Hardware Assembly](#hardware-assembly)
6. [Calibration & Usage](#calibration--usage)
7. [Troubleshooting](#troubleshooting)
8. [Technical Specifications](#technical-specifications)
9. [Support & Contact](#support--contact)

---

## Overview

**PODFA** (Plant Organ Detachment Force Analyzer) is a precision instrument designed to quantify the force required to detach plant organs, particularly flower petals. This system addresses critical limitations in floral abscission research by:

- **Automating measurement**: Motorized Z-stage eliminates operator-dependent variability
- **Improving precision**: High-resolution 12-bit ADC with signal conditioning achieves consistent, reproducible results
- **Providing accessibility**: Raspberry Pi-based platform is user-friendly compared to traditional microcontroller setups
- **Enabling reproducibility**: Complete open-source design for easy replication

### Key Features

- ✅ Real-time data visualization with PyQt6
- ✅ Automated vertical Z-stage for consistent measurement
- ✅ Multi-stage data filtering (Moving Average, Median, Butterworth)
- ✅ Automatic calibration system with correlation verification
- ✅ High-quality Excel export with embedded charts
- ✅ Joystick-based manual/automated control
- ✅ Auto-homing with limit switch
- ✅ Modular, reproducible hardware design

### System Components

PODFA consists of six main components:

1. **Petal Gripper** - Precision tweezers for secure petal handling
2. **Force Transducer** - MLT050 (0-50g) for accurate force measurement
3. **Signal Processing Circuit** - Amplification, filtering, and ADC conversion
4. **Raspberry Pi 5** - Data acquisition and processing
5. **Vertical Z-Stage** - Motorized stage with joystick control
6. **PC Software** - Real-time monitoring and data management

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PODFA System Architecture                 │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Sensor                    Signal Processing    PC Software  │
│  ┌──────────┐         ┌──────────────────┐   ┌────────────┐ │
│  │ Gripper+ │         │ Raspberry Pi 5   │   │  PODFA     │ │
│  │Transducer├────────►│ + MCP3208 ADC    │──►│  Monitor   │ │
│  │ (0-50g)  │         │ + Signal Cond.   │   │            │ │
│  └──────────┘         └──────────────────┘   └────────────┘ │
│                              ▲                                │
│                              │                                │
│                       ┌──────┴────────┐                       │
│                       │  Arduino UNO  │                       │
│                       │ + TMC2209     │                       │
│                       └───────┬────────┘                       │
│                               ▼                                │
│                       ┌──────────────────┐                    │
│                       │  Vertical        │                    │
│                       │  Z-Stage Motor   │                    │
│                       │ + Joystick       │                    │
│                       └──────────────────┘                    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Force Acquisition**: Gripper holds petal → Force transducer converts mechanical force to voltage
2. **Signal Conditioning**: AD620 amplifier (2.5× gain) → RC low-pass filter (7.24 Hz cutoff)
3. **Digitization**: MCP3208 ADC (12-bit) samples at high resolution
4. **Transmission**: Raspberry Pi sends data via USB UART to PC
5. **Processing**: PODFA Monitor applies filtering, calibration, and visualization
6. **Storage**: Peak force recorded and data exported to Excel

---

## Hardware Requirements

### 6.1 Bill of Materials (BOM)

All components are listed below with specific part numbers for reproducibility.

#### Mechanical Components
| Component | Part Number | Supplier | Notes |
|-----------|------------|----------|-------|
| Tripod Support | SciLab SL.St8101 | SciLab | Stable base |
| Bosshead Clamp | NAVIMRO K11180351 | NAVIMRO | Height adjustment |
| Nylon Fishing Line | 0.5 mm | Generic | Force transmission |
| SMD IC Test Hook Clip | Cleqee P5003 | Cleqee | Gripper base |
| Stainless Blade | Dorco ST300 | Dorco | Cutting edge |

#### Electronics - Force Measurement
| Component | Part Number | Supplier | Rating |
|-----------|------------|----------|--------|
| Force Transducer | MLT050/ST | AD Instruments | 0-50g |
| Instrumentation Amplifier | AD620 | Analog Devices | Gain 2.5× |
| Resistor | PR9372 | Precision Resistive | 1.2 kΩ |
| Capacitor | KAISEI | Audio Note | 10 µF |
| ADC | MCP3208-CI/P | Microchip | 12-bit, SPI |
| Raspberry Pi | SC1112 | Raspberry Pi Foundation | Single board computer |
| USB-UART Module | DIP232RL | NEROMART | USB serial adapter |
| Voltage Reference | LM4040 | Adafruit | 4.096V |

#### Electronics - Z-Stage Control
| Component | Part Number | Supplier | Specifications |
|-----------|------------|----------|-----------------|
| Stepper Motor | 17HS3430 | Oukeda | 200 steps/rev |
| Motor Driver | MKS TMC2209 | Makerbase | UART controlled |
| Microcontroller | Arduino UNO R3 | Arduino | Firmware upload |
| Joystick Module | Generic | - | XY + button |

#### Vertical Z-Stage
| Component | Notes |
|-----------|-------|
| Custom Pantograph Linkage | Based on Standa 8MVT188-20 design |
| Stepper Motor Integration | 200 steps per revolution |

### 6.2 PCB Fabrication

PODFA requires two custom PCBs:

#### PCB 1: Signal Processing Board (Raspberry Pi Mainboard)
- **Circuit Diagram**: See `RaspberryPi/hardware/schematic.svg`
- **Gerber Files**: `RaspberryPi/hardware/gerber/`
- **Key Components**: AD620, MCP3208, RC filter, LM4040
- **Fabrication File**: `Gerber_PBS-Device_PCB_PBS-Device_4_2025-12-17.zip`

#### PCB 2: Z-Stage Control Board (Arduino Mainboard)
- **Circuit Diagram**: See `Vertical Z-Stage/hardware/schematic.svg`
- **Gerber Files**: `Vertical Z-Stage/hardware/gerber/`
- **Key Components**: Arduino, TMC2209 driver, motor connectors
- **Fabrication File**: `Gerber_Vertical-Z-Stage_PCB_Vertical-Z-Stage_2_2025-12-17.zip`

### Manufacturing with JLCPCB

**Step-by-step guide**:

1. **Download Gerber Files**
   ```
   Extract the .zip file from the respective hardware/gerber/ folder
   ```

2. **Upload to JLCPCB**
   - Go to https://jlcpcb.com
   - Click "Add Gerber file" and upload the .zip
   - JLCPCB will auto-detect layer stack and dimensions

3. **PCB Specifications**
   - **Layers**: 2 (signal + ground)
   - **PCB Thickness**: 1.6 mm
   - **Surface Finish**: HASL (lead-free)
   - **Copper Weight**: 1 oz
   - **Track Width/Spacing**: 0.254 mm (10 mil)

4. **Assembly Options** (Optional)
   - Use "SMT Assembly" service for precise component placement
   - Or assemble manually using the schematic as reference

5. **Estimated Cost**
   - Signal Processing PCB: ~$15-25 (10 pieces)
   - Z-Stage Control PCB: ~$15-25 (10 pieces)
   - Typical 2-week delivery

---

## Software Installation

### 7.1 PODFA Monitor (PC Software)

The main data acquisition and analysis application.

**System Requirements**:
- Windows 10/11 or Linux/macOS
- Python 3.13 or higher
- USB port for serial communication
- ~500 MB free disk space

**Installation Steps**:

```bash
# 1. Clone the repository
git clone https://github.com/snupcb2018/PODFA.git
cd PODFA

# 2. Navigate to PODFA Monitor directory
cd "PODFA Monitor"

# 3. Create Python virtual environment (recommended)
python -m venv venv

# Windows: Activate virtual environment
venv\Scripts\activate

# Linux/macOS: Activate virtual environment
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run the application
python main.py
```

**Dependencies**:
- PyQt6 (6.6.0+) - GUI framework
- matplotlib (3.8.0+) - Real-time charting
- polars (0.20.0+) - High-performance data processing
- numpy (1.26.0+) - Numerical computing
- pandas (2.1.0+) - Data analysis
- scipy (1.11.0+) - Statistical analysis
- pyserial (3.5+) - Serial communication
- openpyxl (3.1.0+) - Excel file writing
- qtawesome (1.3.0+) - Icon library
- Pillow (10.0.0+) - Image processing

**First Launch**:
1. Open PODFA Monitor
2. Check Device Manager for COM port (Windows: `devmgmt.msc`)
3. Select the correct COM port in the application
4. Proceed to calibration

### 7.2 Raspberry Pi Setup

Data acquisition unit that reads sensor signals and transmits to PC.

**Hardware Requirements**:
- Raspberry Pi 5 (or Pi 4B as minimum)
- MicroSD card (16GB minimum, Class 10 recommended)
- Power supply (5V 3A USB-C)
- Signal processing PCB (see Hardware section)
- Internet connection for initial setup

**OS Installation**:

```bash
# Download and flash Raspberry Pi OS (64-bit)
# https://www.raspberrypi.com/software/
#
# Flash to MicroSD using Raspberry Pi Imager
# Boot the Raspberry Pi and complete initial setup
```

**Configuration**:

```bash
# 1. Enable SPI interface (required for MCP3208)
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable

# 2. Update system
sudo apt update
sudo apt upgrade

# 3. Install Python and libraries
sudo apt install python3-pip python3-serial

# 4. Install Adafruit GPIO library
pip3 install Adafruit-GPIO

# 5. Copy RaspberryPi software to Raspberry Pi
# On your PC:
scp RaspberryPi/main.py pi@<your-raspberry-pi-ip>:~/

# 6. Test the connection
ssh pi@<your-raspberry-pi-ip>
python3 main.py
# Press Ctrl+C to stop
```

**Auto-start on Boot** (Optional):

```bash
# Create systemd service for automatic startup
sudo nano /etc/systemd/system/podfa-adc.service

# Paste the following:
[Unit]
Description=PODFA ADC Data Acquisition
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=pi
ExecStart=/usr/bin/python3 /home/pi/main.py

[Install]
WantedBy=multi-user.target

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable podfa-adc.service
sudo systemctl start podfa-adc.service

# Check status
sudo systemctl status podfa-adc.service
```

**Wiring Connections**:

| Component | Raspberry Pi GPIO |
|-----------|------------------|
| MCP3208 CLK | GPIO 11 (SPI_SCLK) |
| MCP3208 MOSI | GPIO 10 (SPI_MOSI) |
| MCP3208 MISO | GPIO 9 (SPI_MISO) |
| MCP3208 CS | GPIO 8 (SPI_CE0) |
| UART TX | Via DIP232RL module to PC |
| Power | 5V USB |
| Ground | GND |

### 7.3 Arduino (Z-Stage Motor Control)

Controls the motorized vertical Z-stage.

**Hardware Requirements**:
- Arduino UNO R3
- TMC2209 stepper motor driver
- Z-Stage control PCB
- Stepper motor (200 steps/rev)
- Joystick module
- 18V DC power supply

**Software Installation**:

```bash
# 1. Download Arduino IDE
# https://www.arduino.cc/en/software

# 2. Install Arduino IDE following official instructions

# 3. Install required libraries in Arduino IDE:
# Tools → Manage Libraries
# Search and install:
#   - TMCStepper (by teemuatlut)
#   - Streaming (by Mikal Hart)
```

**Upload Firmware**:

```
1. Connect Arduino to PC via USB cable
2. Open Arduino IDE
3. File → Open → "Vertical Z-Stage/main.ino"
4. Select Board: Tools → Board → Arduino AVR Boards → Arduino Uno
5. Select Port: Tools → Port → COM# (or /dev/ttyACM#)
6. Click Upload button (right arrow icon)
7. Wait for upload to complete (LED will flash)
8. Check Serial Monitor (115200 baud) for startup messages
```

**Pin Configuration** (verify in main.ino):

```cpp
#define EN_PIN           2      // Motor Enable
#define DIR_PIN          3      // Motor Direction
#define STEP_PIN         4      // Motor Step
#define SW_SCK           5      // SPI Clock
#define SW_TX            6      // Serial TX
#define SW_RX            7      // Serial RX
#define JOYSTICK_PIN    A1      // Joystick Y-axis (analog)
#define JOYSTICK_BUTTON  8      // Joystick button (digital)
#define LIMIT_SWITCH     9      // Home position switch
```

**Testing Arduino**:

```
1. Open Serial Monitor: Tools → Serial Monitor
2. Set baud rate: 115200
3. Power on the system
4. Watch for "Set to zero position..." and "Finished" messages
5. Test joystick:
   - Push up: Motor should move up
   - Push down: Motor should move down
   - Press button: Fixed speed mode toggle
6. Test limit switch by gently pushing mechanism to home position
```

---

## Hardware Assembly

### 8.1 Gripper Assembly

The gripper securely holds petals without damaging them.

**Steps**:
1. Use SMD IC test hook clip as the base body
2. Attach thin stainless steel blade using instant adhesive
3. Reinforce the attachment point with stripped wire insulation
4. Connect to force transducer using 0.5 mm nylon fishing line
5. Test grip: Should hold petal firmly without cutting

### 8.2 Force Transducer Mounting

**Steps**:
1. Mount MLT050 force transducer on tripod support stand
2. Secure with bosshead clamp holder for height adjustment
3. Connect transducer output to signal processing PCB
4. Place heavy steel platform underneath to minimize vibration
5. Test: Verify transducer reads ~0g at rest

### 8.3 Z-Stage Assembly

**Steps**:
1. Assemble pantograph-style linkage (based on Standa 8MVT188-20)
2. Install stepper motor with coupling
3. Mount joystick on control panel
4. Connect motor driver (TMC2209) to Arduino board
5. Attach limit switch at home position
6. Test: Manual movement up/down with joystick

### 8.4 System Integration

**Final Assembly**:

1. **Place all components** on flat, stable surface
2. **Connect signal chain**:
   - Gripper → Nylon line → Force transducer → Signal PCB
   - Signal PCB → USB cable → PC (PODFA Monitor)
3. **Connect Z-stage control**:
   - Joystick → Arduino control board → Motor driver
   - Motor driver → Stepper motor → Z-stage
4. **Power connections**:
   - Raspberry Pi: 5V USB
   - Arduino: USB or 5V power
   - Z-stage motor: 18V DC power supply
5. **Verification checklist**:
   - [ ] All USB connections secure
   - [ ] Power supplies connected properly
   - [ ] Signal cable not damaged
   - [ ] Mechanical parts move freely
   - [ ] Limit switch functional
   - [ ] Force transducer reads correctly

---

## Calibration & Usage

### 9.1 Device Setup

**Initial Setup Procedure**:

1. Place PODFA on flat, vibration-free surface
2. Mount MLT050 transducer on tripod with bosshead clamp
3. Attach gripper to transducer with nylon line
4. Connect all USB cables to PC
5. Connect 18V DC power to Z-stage motor
6. Boot Raspberry Pi and Arduino
7. Launch PODFA Monitor software
8. Allow 30 seconds for system initialization

### 9.2 Calibration Procedure

**Important**: Calibration must be performed before first measurements.

**In PODFA Monitor**:

1. Click **Tools** → **Calibration**
2. **Reference Weight Settings** tab:
   - Enter reference weight values (e.g., 5g, 10g, 20g)
   - Note: Use any objects with known mass (coins, standard weights)
   - Total mass should not exceed 50g
3. **Data Collection** tab:
   - Click "Start collection" button
   - Place first reference weight on gripper
   - Click "Start collection" again
   - Repeat for each weight
4. **Verification**:
   - Calibration graph should show linear relationship
   - R² value should be > 0.95
   - If not, check connections and repeat

**Calibration Validation**:

| R² Value | Quality | Action |
|----------|---------|--------|
| > 0.99 | Excellent | Proceed with measurements |
| 0.95-0.99 | Good | Acceptable |
| < 0.95 | Poor | Redo calibration |

### 9.3 pBS Measurement Protocol

**Pre-measurement**:
- Prepare Arabidopsis plants (6-7 weeks old recommended)
- Allow plants to acclimate to room temperature (30 min)
- Ensure gripper is clean and dry

**Measurement Steps**:

1. Create new workbench:
   - Click "New Workbench"
   - Enter workbench name (e.g., "WT_2025-12-17")
   - Select data save directory

2. Position specimen:
   - Place Arabidopsis flower on vertical Z-stage
   - Adjust transducer height using bosshead clamp
   - Gently grasp single petal with gripper

3. Data collection:
   - Click "Start" button
   - Joystick down to initiate automated downward movement
   - Force value increases on screen in real-time
   - Petal detaches when force peaks
   - Click "Stop" button immediately after detachment

4. Data verification:
   - Confirm only single petal was detached
   - Check force curve shape (smooth rise to peak)
   - Record peak force value

5. Data storage:
   - Automatically saves as XLSX file
   - Includes chart image (1800×1800 pixels)
   - Metadata with timestamp and parameters

**Quality Control**:

✅ Valid measurements:
- Single petal detached only
- Smooth force curve
- Peak force 0.5-4.5g (typical range)

❌ Invalid measurements (discard):
- Multiple organs detached
- Irregular force curve
- Peak force outside expected range
- Gripper slip detected

### 9.4 Data Output

**Excel File Contents**:

Each measurement generates an XLSX file containing:
- **Data Sheet**: Raw force vs. time data
- **Chart Sheet**: High-resolution force curve plot
- **Statistics Sheet**: Mean, median, std dev, min, max
- **Metadata Sheet**: Timestamp, genotype, measurements

**File Organization**:

```
Workbench_Name/
├── Sample_001.xlsx
├── Sample_002.xlsx
├── Sample_003.xlsx
└── ...
```

---

## Validation Results

PODFA has been validated using *Arabidopsis thaliana* genotypes with known abscission phenotypes:

### Petal Break Strength (pBS) Measurements

| Genotype | P1-P3 | P4-P6 | P7-P9 | P10-P11 | Notes |
|----------|-------|-------|-------|---------|-------|
| WT (Col-0) | ~2g | ~1g | <0.5g | - | Normal: abscission at P5 |
| etr1-1 | ~2g | ~1.8g | ~0.8g | ~0.5g | Delayed: abscission at P9 |
| hae/hsl2 | ~2g | ~1.5g | ~0.8g | ~1.2g | Defective: no abscission |

**Key Results**:
- ✅ Low measurement variability across replicates
- ✅ High reproducibility between different plants
- ✅ Genotype-specific phenotypes clearly distinguished
- ✅ Measurement precision enables statistical analysis

---

## Troubleshooting

### Serial Communication Issues

**Problem**: "Port not available" or "Cannot connect"

**Solutions**:
1. Check Device Manager (Windows: `devmgmt.msc`)
2. Verify USB cable is functional
3. Reinstall CH340 driver (for UART modules)
4. Try different USB port
5. Check baud rate: Raspberry Pi (115200) vs PC (check settings)

### Z-Stage Not Moving

**Problem**: Joystick unresponsive or motor not turning

**Solutions**:
1. Verify 18V DC power supply is connected and ON
2. Check Arduino serial connection
3. Open Arduino Serial Monitor (115200 baud)
4. Check for error messages
5. Test joystick with multimeter (0-1023 range)
6. Verify TMC2209 connections

### Calibration Issues

**Problem**: Calibration fails or R² < 0.95

**Solutions**:
1. Ensure reference weights are accurate
2. Check force transducer connections
3. Verify stable, vibration-free surface
4. Clean gripper and transducer
5. Check for mechanical looseness
6. Repeat calibration 2-3 times

### Data Not Saving

**Problem**: Measurements don't save to Excel

**Solutions**:
1. Check write permissions in save directory
2. Verify sufficient disk space
3. Try alternate save location
4. Check application logs: `pbs_2.0.log`
5. Restart PODFA Monitor
6. Verify file format is XLSX

### Force Readings Unstable

**Problem**: Noisy or fluctuating force values

**Solutions**:
1. Verify proper grounding of all components
2. Check cable shielding and connections
3. Move away from electromagnetic interference
4. Ensure gripper is not vibrating
5. Verify Z-stage base is level and stable
6. Increase filter cutoff frequency in settings

---

## Technical Specifications

### Signal Processing

| Parameter | Value | Notes |
|-----------|-------|-------|
| Force Range | 0-50 g | MLT050 transducer rating |
| Amplification | 2.5× | AD620 instrumentation amp |
| Low-pass Filter | 7.24 Hz | RC filter: fc = 1/(2πRC) |
| ADC Resolution | 12-bit (0-4096) | MCP3208 SPI ADC |
| Voltage Reference | 4.096V | LM4040 precision reference |
| Serial Baud Rate | Up to 921600 | USB UART interface |
| Sampling Rate | ~100 Hz | Real-time monitoring |

### Z-Stage Motor Control

| Parameter | Value |
|-----------|-------|
| Motor Type | Stepper motor (NEMA 17) |
| Steps per Revolution | 200 |
| Microsteps | 256 (set via TMC2209) |
| Driver | TMC2209 (UART controlled) |
| Operating Mode | StealthChop (quiet, smooth) |
| RMS Current | 400 mA |
| Max Speed | ~150,000 steps/sec |
| Movement Resolution | 0.0176 mm/microstep |

### System Performance

| Metric | Value | Comment |
|--------|-------|---------|
| Measurement Precision | ±0.05 g | Typical repeatability |
| Measurement Accuracy | ±0.1 g | Post-calibration |
| Data Acquisition Rate | ~100 samples/sec | Real-time streaming |
| Storage Requirements | ~5 MB per 100 measurements | Excel format with embedded charts |
| Power Consumption | ~15W total | PC: separate; Raspberry Pi: 5W; Arduino: <1W |

### Software Requirements

| Component | Requirement | Tested |
|-----------|-------------|--------|
| Python | 3.13+ | ✅ 3.13.0 |
| PyQt6 | 6.6.0+ | ✅ 6.6.0 |
| matplotlib | 3.8.0+ | ✅ 3.8.2 |
| Arduino IDE | 2.0+ | ✅ 2.3.0 |
| Raspberry Pi OS | Bullseye or later | ✅ Latest |

---

## Project Structure

```
PODFA/
├── PODFA Monitor/              # PC data acquisition software
│   ├── main.py                 # Application entry point
│   ├── requirements.txt        # Python dependencies
│   ├── core/                   # Core processing modules
│   │   ├── serial_manager.py   # Serial communication
│   │   ├── data_processor.py   # Data filtering & analysis
│   │   └── calibration.py      # Calibration engine
│   ├── ui/                     # User interface
│   │   ├── main_window.py      # Main application window
│   │   ├── chart_widget.py     # Real-time plotting
│   │   └── calibration/        # Calibration wizard
│   ├── utils/                  # Utility functions
│   │   └── excel_exporter.py   # Excel file generation
│   └── settings/               # Configuration files
│       └── pbs_settings.ini    # User settings
│
├── RaspberryPi/                # Raspberry Pi data acquisition
│   ├── main.py                 # ADC reading and transmission
│   └── hardware/               # Hardware design files
│       ├── schematic.svg       # Circuit diagram
│       └── gerber/             # PCB fabrication files
│           └── Gerber_PBS-Device_PCB_*.zip
│
├── Vertical Z-Stage/           # Arduino Z-stage control
│   ├── main.ino                # Motor control firmware
│   └── hardware/               # Hardware design files
│       ├── schematic.svg       # Circuit diagram
│       └── gerber/             # PCB fabrication files
│           └── Gerber_Vertical-Z-Stage_*.zip
│
└── README.md                   # This file
```

---

## Support & Contact

### Reporting Issues

Found a bug or have a suggestion?

1. Check existing [GitHub Issues](https://github.com/snupcb2018/PODFA/issues)
2. Provide detailed description including:
   - Error message and screenshots
   - Operating system and hardware
   - Steps to reproduce
   - Expected vs. actual behavior

### Contact Information

For questions or collaboration:

**Correspondence**: Yuree Lee
**Email**: yuree.lee@snu.ac.kr
**Affiliation**: Seoul National University, Plant Genomics and Breeding Institute

---

## Acknowledgments

This work was supported by:
- Suh Kyungbae Foundation
- National Research Foundation of Korea (MSIT)
- Stadelmann-Lee Scholarship Fund, Seoul National University

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-17 | Initial release with complete hardware and software |

---

**Last Updated**: December 17, 2025

For the latest updates, visit: https://github.com/snupcb2018/PODFA
