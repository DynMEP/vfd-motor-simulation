# =============================================================================
# VFD-Motor-Simulation: 800HP Motor Startup with VFD Control
# =============================================================================
# Purpose: Python-based simulation of VFD-controlled startup for an 800HP motor,
#          optimized for high-power applications in research environments with
#          dynamic speed, torque, and current analysis.
# Version: 2.0.0 (Improved with corrected physics models)
# Author: Alfonso Davila - Electrical Engineer
# Repository: https://github.com/dynmep/vfd-motor-simulation
# License: MIT License (see LICENSE file in repository)
# Created: October 2025
# Compatibility: Python 3.x, NumPy, SciPy, Matplotlib
#
# Quick Start:
#   Simulation: python vfd_simulation.py
#   Customize:  Edit vfd_simulation.py for specific motor parameters
# =============================================================================

import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import odeint

# =============================================================================
# CONFIGURATION PARAMETERS
# =============================================================================

# Motor parameters (for an 800HP induction motor)
POWER_HP = 800  # HP
POWER_KW = POWER_HP * 0.7457  # Convert to kW
VOLTAGE = 460  # Volts (line-to-line)
BASE_FREQ = 60  # Hz
POLES = 4  # 4-pole motor
EFFICIENCY = 0.95  # Motor efficiency at rated load
POWER_FACTOR = 0.88  # Power factor at rated load

# Calculate motor characteristics
SYNC_SPEED_RPM = 120 * BASE_FREQ / POLES  # RPM
SYNC_SPEED_RAD = SYNC_SPEED_RPM * (2 * np.pi / 60)  # rad/s
RATED_TORQUE = (POWER_KW * 1000) / (SYNC_SPEED_RAD * (1 - 0.03))  # Nm (assume 3% slip)

# System dynamics parameters
INERTIA = 150  # kg*m^2 (system inertia - motor + load)
DAMPING = 2.0  # Damping coefficient (N*m*s/rad)
LOAD_TORQUE_FACTOR = 0.75  # Load torque as fraction of rated (75% load)

# VFD ramp parameters
RAMP_TIME = 30  # Seconds to reach full speed
V_BOOST = 0.15  # Low-frequency voltage boost (15%)
TIME_POINTS = 1000  # Number of simulation points

# =============================================================================
# DERIVED PARAMETERS
# =============================================================================

# Full load current calculation
FLA = (POWER_KW * 1000) / (np.sqrt(3) * VOLTAGE * POWER_FACTOR * EFFICIENCY)
LOAD_TORQUE = RATED_TORQUE * LOAD_TORQUE_FACTOR
time = np.linspace(0, RAMP_TIME, TIME_POINTS)

# =============================================================================
# VFD CONTROL FUNCTIONS
# =============================================================================

def freq_func(t):
    if t <= RAMP_TIME:
        return BASE_FREQ * (t / RAMP_TIME)
    return BASE_FREQ


def voltage_func(freq):
    base_voltage = VOLTAGE * (freq / BASE_FREQ)
    if freq < BASE_FREQ * 0.1:  # Below 10% of base frequency
        boost = VOLTAGE * V_BOOST * (1 - freq / (BASE_FREQ * 0.1))
        return base_voltage + boost
    return base_voltage


# =============================================================================
# MOTOR DYNAMICS MODEL
# =============================================================================

def motor_dynamics(state, t, freq_func, load_torque):
    omega_rad = state[0]
    freq = freq_func(t)
    
    # Handle very low frequency startup
    if freq < 1.0:  # Below 1 Hz
        # At very low frequencies, provide starting torque
        sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
        if sync_speed_rad < 0.1:
            return [0]
        slip = (sync_speed_rad - omega_rad) / sync_speed_rad
        slip = np.clip(slip, 0, 1.0)
        # Provide higher torque at startup with voltage boost
        torque_em = RATED_TORQUE * 2.5 * slip * (1 + V_BOOST * 5)
        d_omega_dt = (torque_em - load_torque * 0.3 - DAMPING * omega_rad) / INERTIA
        return [d_omega_dt]
    
    # Calculate slip for normal operation
    sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
    slip = (sync_speed_rad - omega_rad) / sync_speed_rad
    
    # Limit slip to reasonable range
    slip = np.clip(slip, 0, 1.0)
    
    # Electromagnetic torque using torque-slip characteristic
    # Using a more practical model that provides adequate starting torque
    # T/T_rated = a*s / (s^2 + b*s + c) where constants give realistic curve
    a = 2.5  # Peak torque multiplier
    b = 0.15  # Torque curve shape
    c = 0.08  # Starting torque adjustment
    
    torque_ratio = (a * slip) / (slip**2 + b * slip + c)
    torque_em = RATED_TORQUE * torque_ratio
    
    # Scale torque with frequency for V/f control
    freq_ratio = freq / BASE_FREQ
    torque_em *= freq_ratio
    
    # Add voltage boost effect at low frequencies (1-10 Hz)
    if freq < BASE_FREQ * 0.15:
        boost_factor = 1 + V_BOOST * (1 - freq / (BASE_FREQ * 0.15))
        torque_em *= boost_factor
    
    # Reduce load torque at low speeds (many loads are speed-dependent)
    speed_ratio = omega_rad / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
    effective_load = load_torque * (0.3 + 0.7 * speed_ratio)
    
    # Equation of motion
    d_omega_dt = (torque_em - effective_load - DAMPING * omega_rad) / INERTIA
    
    return [d_omega_dt]


# =============================================================================
# SIMULATION
# =============================================================================

# Initial conditions
omega0_rad = 0  # Start from standstill
initial_state = [omega0_rad]

# Solve ODE for angular velocity
solution = odeint(motor_dynamics, initial_state, time, args=(freq_func, LOAD_TORQUE))
omega_rad = solution[:, 0]
omega_rpm = omega_rad * (60 / (2 * np.pi))

# Calculate actual quantities for plotting
freq_array = np.array([freq_func(t) for t in time])
slip_array = np.zeros_like(time)
torque_array = np.zeros_like(time)
current_array = np.zeros_like(time)

for i, t in enumerate(time):
    freq = freq_array[i]
    
    if freq >= 0.5:
        sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
        slip = (sync_speed_rad - omega_rad[i]) / sync_speed_rad if sync_speed_rad > 0 else 1.0
        slip = np.clip(slip, 0, 1.0)
        slip_array[i] = slip * 100  # Convert to percentage
        
        # Calculate electromagnetic torque using same model as dynamics
        if freq < 1.0:
            torque_em = RATED_TORQUE * 2.5 * slip * (1 + V_BOOST * 5)
        else:
            a = 2.5
            b = 0.15
            c = 0.08
            torque_ratio = (a * slip) / (slip**2 + b * slip + c)
            freq_ratio = freq / BASE_FREQ
            torque_em = RATED_TORQUE * torque_ratio * freq_ratio
            
            if freq < BASE_FREQ * 0.15:
                boost_factor = 1 + V_BOOST * (1 - freq / (BASE_FREQ * 0.15))
                torque_em *= boost_factor
        
        torque_array[i] = torque_em
        
        # Calculate current (simplified model)
        # Current increases with slip and torque
        torque_component = FLA * (torque_em / RATED_TORQUE)
        magnetizing_component = FLA * 0.3  # Magnetizing current ~30% of FLA
        current_array[i] = np.sqrt(torque_component**2 + magnetizing_component**2)
    else:
        slip_array[i] = 100
        torque_array[i] = 0
        current_array[i] = 0

# Calculate power
power_array = (torque_array * omega_rad) / 1000  # kW

# =============================================================================
# PLOTTING
# =============================================================================

fig, axs = plt.subplots(4, 1, figsize=(12, 14))
fig.suptitle(f'VFD-Controlled Motor Startup Simulation ({POWER_HP}HP Motor)\n', 
             fontsize=14, fontweight='bold')

# Plot 1: Speed
axs[0].plot(time, omega_rpm, 'b-', linewidth=2, label='Motor Speed')
axs[0].plot(time, (freq_array / BASE_FREQ) * SYNC_SPEED_RPM, 'r--', 
            linewidth=1.5, label='Synchronous Speed')
axs[0].set_ylabel('Speed (RPM)', fontsize=11)
axs[0].set_title('Motor Speed Response', fontsize=12)
axs[0].grid(True, alpha=0.3)
axs[0].legend(loc='lower right')
axs[0].set_xlim([0, RAMP_TIME])

# Plot 2: Torque
axs[1].plot(time, torque_array, 'g-', linewidth=2, label='Electromagnetic Torque')
axs[1].axhline(y=LOAD_TORQUE, color='r', linestyle='--', 
               linewidth=1.5, label=f'Load Torque ({LOAD_TORQUE:.0f} Nm)')
axs[1].axhline(y=RATED_TORQUE, color='orange', linestyle=':', 
               linewidth=1.5, label=f'Rated Torque ({RATED_TORQUE:.0f} Nm)')
axs[1].set_ylabel('Torque (Nm)', fontsize=11)
axs[1].set_title('Torque Profile', fontsize=12)
axs[1].grid(True, alpha=0.3)
axs[1].legend(loc='upper right')
axs[1].set_xlim([0, RAMP_TIME])

# Plot 3: Current
axs[2].plot(time, current_array, 'purple', linewidth=2, label='Motor Current')
axs[2].axhline(y=FLA, color='r', linestyle='--', 
               linewidth=1.5, label=f'Full Load Current ({FLA:.0f} A)')
axs[2].set_ylabel('Current (A)', fontsize=11)
axs[2].set_title('Current Draw', fontsize=12)
axs[2].grid(True, alpha=0.3)
axs[2].legend(loc='upper right')
axs[2].set_xlim([0, RAMP_TIME])

# Plot 4: Slip
axs[3].plot(time, slip_array, 'darkorange', linewidth=2)
axs[3].set_ylabel('Slip (%)', fontsize=11)
axs[3].set_xlabel('Time (s)', fontsize=11)
axs[3].set_title('Motor Slip', fontsize=12)
axs[3].grid(True, alpha=0.3)
axs[3].set_xlim([0, RAMP_TIME])

plt.tight_layout()

# =============================================================================
# SUMMARY STATISTICS
# =============================================================================

print("\n" + "="*60)
print("VFD MOTOR STARTUP SIMULATION SUMMARY")
print("="*60)
print(f"Motor Rating:          {POWER_HP} HP ({POWER_KW:.1f} kW)")
print(f"Rated Speed:           {SYNC_SPEED_RPM*(1-0.03):.0f} RPM")
print(f"Rated Torque:          {RATED_TORQUE:.0f} Nm")
print(f"Full Load Current:     {FLA:.1f} A")
print(f"Load Torque:           {LOAD_TORQUE:.0f} Nm ({LOAD_TORQUE_FACTOR*100:.0f}% of rated)")
print(f"Ramp Time:             {RAMP_TIME} seconds")
print("-"*60)
print(f"Peak Current:          {np.max(current_array):.1f} A ({np.max(current_array)/FLA:.2f} x FLA)")
print(f"Final Speed:           {omega_rpm[-1]:.0f} RPM")
print(f"Final Slip:            {slip_array[-1]:.2f}%")
print(f"Startup Energy:        {np.trapz(power_array, time):.1f} kJ")
print("="*60 + "\n")

plt.show()