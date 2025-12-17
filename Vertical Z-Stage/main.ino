#include <TMCStepper.h>         // TMCstepper - https://github.com/teemuatlut/TMCStepper
#include <SoftwareSerial.h>     // Software serial for the UART to TMC2209 - https://www.arduino.cc/en/Reference/softwareSerial
#include <Streaming.h>          // For serial debugging output - https://www.arduino.cc/reference/en/libraries/streaming/

#define EN_PIN           2      // Enable - PURPLE
#define DIR_PIN          3      // Direction - WHITE
#define STEP_PIN         4      // Step - ORANGE
#define SW_SCK           5      // Software Slave Clock (SCK) - BLUE
#define SW_TX            6      // SoftwareSerial receive pin - BROWN
#define SW_RX            7      // SoftwareSerial transmit pin - YELLOW
#define DRIVER_ADDRESS   0b00   // TMC2209 Driver address according to MS1 and MS2
#define R_SENSE 0.11f           // SilentStepStick series use 0.11 ...and so does my fysetc TMC2209 (?)
#define JOYSTICK_PIN A1         // Joystick y-axis analog input pin
#define JOYSTICK_BUTTON_PIN 8   // Joystick button digital input pin
#define LIMIT_SWITCH_PIN 9      // Limit switch digital input pin

SoftwareSerial SoftSerial(SW_RX, SW_TX);                          // Be sure to connect RX to TX and TX to RX between both devices
TMC2209Stepper TMCdriver(&SoftSerial, R_SENSE, DRIVER_ADDRESS);   // Create TMC driver

int joystickValue = 0;
long speed = 0;
bool dir = false;
long stepCount = 0;           // Total steps taken
bool fixedSpeedMoving = false;    // Track motor state based on button press
unsigned long lastInteractionTime = 0; // Track last interaction time
const unsigned long inactivityTimeout = 5000; // 10 seconds timeout
bool b = false;
unsigned long limitSwitchEventStartTime = 0;
bool setTozero = false;

//== Setup ===============================================================================

void setup() {
  Serial.begin(115200);               // initialize hardware serial for debugging
  SoftSerial.begin(11520);           // initialize software serial for UART motor control
  TMCdriver.beginSerial(115200);      // Initialize UART

  pinMode(EN_PIN, OUTPUT);           // Set pinmodes
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(LIMIT_SWITCH_PIN, INPUT_PULLUP); // Limit switch input with pull-up resistor
  pinMode(JOYSTICK_BUTTON_PIN, INPUT_PULLUP); // Joystick button input with pull-up resistor
  digitalWrite(EN_PIN, LOW);         // Enable TMC2209 board

  TMCdriver.begin();                 // UART: Init SW UART with default 115200 baudrate
  TMCdriver.toff(5);                 // Enables driver in software
  TMCdriver.rms_current(400);        // Set motor RMS current
  TMCdriver.microsteps(256);         // Set microsteps

  TMCdriver.en_spreadCycle(false);
  TMCdriver.pwm_autoscale(true);     // Needed for stealthChop
  
  Serial.print("Set to zero position ... ");

  // Initialize motor to zero position using limit switch
  if (digitalRead(LIMIT_SWITCH_PIN) == HIGH) {
    speed = 100000;
    dir = false;
    TMCdriver.shaft(dir);
    TMCdriver.VACTUAL(speed);

    limitSwitchEventStartTime = 0;
    while (true) {
      if (digitalRead(LIMIT_SWITCH_PIN) == LOW) {
        if (limitSwitchEventStartTime == 0) {
          limitSwitchEventStartTime = millis(); // Start timing when switch is detected
        } else if (millis() - limitSwitchEventStartTime >= 400) { // Check if 0.5 seconds have passed
          // Serial.println("Switch pressed!!");
          break; // Exit loop if signal is stable for 0.5 seconds
        }
      } else {
        limitSwitchEventStartTime = 0; // Reset timing if signal is not stable
      }

      // Serial.print("Limit switch: ");
      // Serial.println(digitalRead(LIMIT_SWITCH_PIN));

      delay(50);
    }
  }

  if (digitalRead(LIMIT_SWITCH_PIN) == LOW) {
    speed = 20000;
    dir = true;
    // Set motor direction
    TMCdriver.shaft(dir);
    // Set motor speed
    TMCdriver.VACTUAL(speed);

    limitSwitchEventStartTime = 0;
    while (true) {
      if (digitalRead(LIMIT_SWITCH_PIN) == HIGH) {
        if (limitSwitchEventStartTime == 0) {
          limitSwitchEventStartTime = millis(); // Start timing when switch is detected
        } else if (millis() - limitSwitchEventStartTime >= 400) { // Check if 0.5 seconds have passed
          // Serial.println("Switch released!!");
          break; // Exit loop if signal is stable for 0.5 seconds
        }
      } else {
        limitSwitchEventStartTime = 0; // Reset timing if signal is not stable
      }

      delay(50);
    }
    stepCount = 0;
    limitSwitchEventStartTime = 0;
    setTozero = false;
  }

  Serial.println("Finished");
}

//== Loop =================================================================================

void loop() {
  // Read joystick y-axis value (0 to 1023)
  joystickValue = analogRead(JOYSTICK_PIN);

  // Check for joystick interaction
  bool joystickMoved = (joystickValue > 650 || joystickValue < 510);
  bool buttonPressed = (digitalRead(JOYSTICK_BUTTON_PIN) == LOW);

  //  Serial.print("joystickValue ");
  //  Serial.println(joystickValue);

  if (joystickMoved || buttonPressed) {
    lastInteractionTime = millis(); // Update last interaction time
    digitalWrite(EN_PIN, LOW); // Enable motor
    // Serial.println("Wake up...");
  }

  // Disable motor if no interaction for 10 seconds
  if (!fixedSpeedMoving && millis() - lastInteractionTime > inactivityTimeout) {
    digitalWrite(EN_PIN, HIGH); // Disable motor
    speed = 0; // Ensure motor stops
    // Serial.println("Sleep...");
    return; // Skip the rest of the loop
  }

  // Map joystick value to motor speed range for each direction (3000 to 150000)
  if (joystickValue > 650) {
    if (stepCount < 5500) {
      speed = map(joystickValue, 650, 1023, 3000, 150000);
      dir = true;
      setTozero = false;
      Serial.println("setTozero false");
    } else {
      speed = 0;
    }
  } else if (joystickValue < 510 && setTozero == false) {
    speed = map(joystickValue, 510, 0, 3000, 150000);
    dir = false;
  } else {
    speed = 0;
  }

  // Handle joystick button press for toggling motor running state
  if (buttonPressed) { // Button pressed
    Serial.println("Button pressed");
    delay(50); // Debounce delay
    if (digitalRead(JOYSTICK_BUTTON_PIN) == LOW) { // Confirm button still pressed
      fixedSpeedMoving = !fixedSpeedMoving; // Toggle motor running state
      while (digitalRead(JOYSTICK_BUTTON_PIN) == LOW) { // Wait for button release
        delay(10);
      }
    }
  }

  // Set motor speed and direction based on fixedSpeedMoving state
  if (fixedSpeedMoving) {
    speed = 20000;
    dir = false;
  }

  if (digitalRead(LIMIT_SWITCH_PIN) == LOW && dir == false && speed > 0) {
    if (setTozero == false) {
      if (limitSwitchEventStartTime == 0) {
        limitSwitchEventStartTime = millis(); // Start timing when switch is detected
      } else if (millis() - limitSwitchEventStartTime >= 400) { // Check if 0.1 seconds have passed
        Serial.println("Switch Pressed!!");
        speed = 0; // Stop motor if limit switch is triggered and direction is negative
        fixedSpeedMoving = false;
        limitSwitchEventStartTime = 0;
        setTozero = true;
        Serial.println("setTozero true");
      }
    }
  } else {
    limitSwitchEventStartTime = 0;
  }

  // Set motor direction
  TMCdriver.shaft(dir);

  // Set motor speed
  TMCdriver.VACTUAL(speed);

  // Increment or decrement step count based on direction and speed
  if (speed > 0) {
    long stepsToMove = speed / 5000; // Calculate steps based on speed (adjust divisor as needed)
    stepCount += dir ? stepsToMove : -stepsToMove;
  }

  // Debugging output
  // char debugMessage[128];
  // sprintf(debugMessage, "Joystick: %4d | Speed: %ld | Steps: %ld | Direction: %s", 
  //         joystickValue, speed, stepCount, dir ? "Positive" : "Negative");
  // Serial.println(debugMessage);

  delay(50); // Small delay for stability
}
