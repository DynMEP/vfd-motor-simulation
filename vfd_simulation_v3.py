# =============================================================================
# VFD-Motor-Simulation: 800HP Motor Startup with VFD Control
# =============================================================================
# Purpose: Python-based simulation of VFD-controlled startup for an 800HP motor,
#          optimized for high-power applications in research environments with
#          dynamic speed, torque, and current analysis.
# Version: 3.0.0 (Enhanced with load types, DOL comparison, efficiency analysis)
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
import csv
from datetime import datetime

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

# Load type selection: 'constant_torque', 'fan_pump', 'constant_power'
LOAD_TYPE = 'constant_torque'  # Change this to simulate different loads

# Export settings
EXPORT_CSV = True  # Set to True to export data to CSV
CSV_FILENAME = f'vfd_simulation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

# =============================================================================
# DERIVED PARAMETERS
# =============================================================================

# Full load current calculation
FLA = (POWER_KW * 1000) / (np.sqrt(3) * VOLTAGE * POWER_FACTOR * EFFICIENCY)
LOAD_TORQUE = RATED_TORQUE * LOAD_TORQUE_FACTOR
time = np.linspace(0, RAMP_TIME, TIME_POINTS)

# =============================================================================
# LOAD TORQUE MODELS
# =============================================================================

def get_load_torque(speed_ratio, base_torque, load_type='constant_torque'):
    speed_ratio = max(0, min(speed_ratio, 1.0))
    
    if load_type == 'constant_torque':
        # Conveyors, hoists, positive displacement pumps
        return base_torque * (0.3 + 0.7 * speed_ratio)
    
    elif load_type == 'fan_pump':
        # Centrifugal fans and pumps (torque proportional to speed^2)
        return base_torque * speed_ratio**2
    
    elif load_type == 'constant_power':
        # Machine tools, winders
        if speed_ratio < 0.1:
            return base_torque * 0.1 / 0.1  # Avoid division by zero
        return base_torque * 1.0 / speed_ratio
    
    else:
        return base_torque * (0.3 + 0.7 * speed_ratio)

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

def motor_dynamics(state, t, freq_func, base_load_torque, load_type):
    omega_rad = state[0]
    freq = freq_func(t)
    
    # Handle very low frequency startup
    if freq < 1.0:
        sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
        if sync_speed_rad < 0.1:
            return [0]
        slip = (sync_speed_rad - omega_rad) / sync_speed_rad
        slip = np.clip(slip, 0, 1.0)
        torque_em = RATED_TORQUE * 2.5 * slip * (1 + V_BOOST * 5)
        speed_ratio = omega_rad / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
        effective_load = get_load_torque(speed_ratio, base_load_torque, load_type)
        d_omega_dt = (torque_em - effective_load - DAMPING * omega_rad) / INERTIA
        return [d_omega_dt]
    
    # Calculate slip for normal operation
    sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
    slip = (sync_speed_rad - omega_rad) / sync_speed_rad
    slip = np.clip(slip, 0, 1.0)
    
    # Electromagnetic torque using torque-slip characteristic
    a = 2.5  # Peak torque multiplier
    b = 0.15  # Torque curve shape
    c = 0.08  # Starting torque adjustment
    
    torque_ratio = (a * slip) / (slip**2 + b * slip + c)
    torque_em = RATED_TORQUE * torque_ratio
    
    # Scale torque with frequency for V/f control
    freq_ratio = freq / BASE_FREQ
    torque_em *= freq_ratio
    
    # Add voltage boost effect at low frequencies
    if freq < BASE_FREQ * 0.15:
        boost_factor = 1 + V_BOOST * (1 - freq / (BASE_FREQ * 0.15))
        torque_em *= boost_factor
    
    # Calculate effective load based on load type
    speed_ratio = omega_rad / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
    effective_load = get_load_torque(speed_ratio, base_load_torque, load_type)
    
    # Equation of motion
    d_omega_dt = (torque_em - effective_load - DAMPING * omega_rad) / INERTIA
    
    return [d_omega_dt]


# =============================================================================
# DOL (DIRECT-ON-LINE) STARTING SIMULATION
# =============================================================================

def simulate_dol_start():
    dol_time = np.linspace(0, 5, 500)  # DOL typically takes 2-5 seconds
    dol_omega = np.zeros_like(dol_time)
    dol_current = np.zeros_like(dol_time)
    dol_torque = np.zeros_like(dol_time)
    
    for i, t in enumerate(dol_time):
        if t == 0:
            dol_omega[i] = 0
            dol_current[i] = FLA * 6.5  # Typical inrush current
            dol_torque[i] = RATED_TORQUE * 2.5  # Starting torque
        else:
            # Exponential approach to rated speed
            tau = 2.0  # Time constant
            speed_ratio = 1 - np.exp(-t / tau)
            dol_omega[i] = SYNC_SPEED_RPM * 0.97 * speed_ratio
            
            # Current decreases as motor accelerates
            slip_ratio = 1 - speed_ratio * 0.97
            dol_current[i] = FLA * (1 + 5.5 * slip_ratio)
            dol_torque[i] = RATED_TORQUE * (2.5 * slip_ratio + 1.0)
    
    return dol_time, dol_omega, dol_current, dol_torque


# =============================================================================
# VFD SIMULATION
# =============================================================================

# Initial conditions
omega0_rad = 0
initial_state = [omega0_rad]

# Solve ODE for angular velocity
solution = odeint(motor_dynamics, initial_state, time, 
                  args=(freq_func, LOAD_TORQUE, LOAD_TYPE))
omega_rad = solution[:, 0]
omega_rpm = omega_rad * (60 / (2 * np.pi))

# Calculate actual quantities for plotting
freq_array = np.array([freq_func(t) for t in time])
slip_array = np.zeros_like(time)
torque_array = np.zeros_like(time)
current_array = np.zeros_like(time)
load_torque_array = np.zeros_like(time)
power_output_array = np.zeros_like(time)
power_input_array = np.zeros_like(time)
efficiency_array = np.zeros_like(time)

for i, t in enumerate(time):
    freq = freq_array[i]
    
    if freq >= 0.5:
        sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
        slip = (sync_speed_rad - omega_rad[i]) / sync_speed_rad if sync_speed_rad > 0 else 1.0
        slip = np.clip(slip, 0, 1.0)
        slip_array[i] = slip * 100
        
        # Calculate electromagnetic torque
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
        
        # Calculate load torque based on type
        speed_ratio = omega_rad[i] / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
        load_torque_array[i] = get_load_torque(speed_ratio, LOAD_TORQUE, LOAD_TYPE)
        
        # Calculate current
        torque_component = FLA * (torque_em / RATED_TORQUE)
        magnetizing_component = FLA * 0.3
        current_array[i] = np.sqrt(torque_component**2 + magnetizing_component**2)
        
        # Calculate power and efficiency
        power_output_array[i] = (omega_rad[i] * load_torque_array[i]) / 1000  # kW
        power_input_array[i] = (np.sqrt(3) * VOLTAGE * current_array[i] * 
                                POWER_FACTOR) / 1000  # kW
        
        if power_input_array[i] > 0:
            efficiency_array[i] = (power_output_array[i] / power_input_array[i]) * 100
        else:
            efficiency_array[i] = 0
    else:
        slip_array[i] = 100
        torque_array[i] = 0
        current_array[i] = 0
        load_torque_array[i] = 0
        efficiency_array[i] = 0

# DOL simulation for comparison
dol_time, dol_omega, dol_current, dol_torque = simulate_dol_start()

# =============================================================================
# ENERGY AND EFFICIENCY CALCULATIONS
# =============================================================================

# VFD startup energy
vfd_energy_kj = np.trapz(power_input_array, time)
vfd_energy_kwh = vfd_energy_kj / 3600

# DOL startup energy (approximate)
dol_power = (np.sqrt(3) * VOLTAGE * dol_current * POWER_FACTOR) / 1000
dol_energy_kj = np.trapz(dol_power, dol_time)
dol_energy_kwh = dol_energy_kj / 3600

# Peak values
vfd_peak_current = np.max(current_array)
dol_peak_current = np.max(dol_current)

# Average efficiency during ramp
avg_efficiency = np.mean(efficiency_array[efficiency_array > 0])

# =============================================================================
# EXPORT TO CSV
# =============================================================================

if EXPORT_CSV:
    with open(CSV_FILENAME, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['VFD Motor Startup Simulation Data'])
        writer.writerow(['Generated:', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(['Motor Rating:', f'{POWER_HP} HP'])
        writer.writerow(['Load Type:', LOAD_TYPE])
        writer.writerow([])
        writer.writerow(['Time (s)', 'Frequency (Hz)', 'Speed (RPM)', 'Slip (%)', 
                        'Torque (Nm)', 'Load Torque (Nm)', 'Current (A)', 
                        'Power Output (kW)', 'Power Input (kW)', 'Efficiency (%)'])
        
        for i in range(len(time)):
            writer.writerow([f'{time[i]:.3f}', f'{freq_array[i]:.2f}', 
                           f'{omega_rpm[i]:.1f}', f'{slip_array[i]:.2f}',
                           f'{torque_array[i]:.1f}', f'{load_torque_array[i]:.1f}',
                           f'{current_array[i]:.1f}', f'{power_output_array[i]:.2f}',
                           f'{power_input_array[i]:.2f}', f'{efficiency_array[i]:.1f}'])
    
    print(f"\n✓ Data exported to: {CSV_FILENAME}")

# =============================================================================
# PLOTTING
# =============================================================================

fig = plt.figure(figsize=(16, 12))
gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

fig.suptitle(f'VFD vs DOL Starting Comparison - {POWER_HP}HP Motor ({LOAD_TYPE.replace("_", " ").title()} Load)', 
             fontsize=14, fontweight='bold')

# Plot 1: Speed Comparison
ax1 = fig.add_subplot(gs[0, 0])
ax1.plot(time, omega_rpm, 'b-', linewidth=2, label='VFD Start')
ax1.plot(dol_time, dol_omega, 'r--', linewidth=2, label='DOL Start')
ax1.set_ylabel('Speed (RPM)', fontsize=11)
ax1.set_xlabel('Time (s)', fontsize=11)
ax1.set_title('Speed Response Comparison', fontsize=12)
ax1.grid(True, alpha=0.3)
ax1.legend(loc='lower right')
ax1.set_xlim([0, max(RAMP_TIME, 5)])

# Plot 2: Current Comparison
ax2 = fig.add_subplot(gs[0, 1])
ax2.plot(time, current_array, 'b-', linewidth=2, label='VFD Start')
ax2.plot(dol_time, dol_current, 'r--', linewidth=2, label='DOL Start')
ax2.axhline(y=FLA, color='green', linestyle=':', linewidth=1.5, label=f'FLA ({FLA:.0f} A)')
ax2.set_ylabel('Current (A)', fontsize=11)
ax2.set_xlabel('Time (s)', fontsize=11)
ax2.set_title('Current Draw Comparison', fontsize=12)
ax2.grid(True, alpha=0.3)
ax2.legend(loc='upper right')
ax2.set_xlim([0, max(RAMP_TIME, 5)])

# Plot 3: Torque Profile
ax3 = fig.add_subplot(gs[1, 0])
ax3.plot(time, torque_array, 'g-', linewidth=2, label='Motor Torque')
ax3.plot(time, load_torque_array, 'orange', linewidth=2, label='Load Torque')
ax3.axhline(y=RATED_TORQUE, color='red', linestyle='--', linewidth=1.5, 
           label=f'Rated Torque ({RATED_TORQUE:.0f} Nm)')
ax3.set_ylabel('Torque (Nm)', fontsize=11)
ax3.set_xlabel('Time (s)', fontsize=11)
ax3.set_title(f'Torque Profile - {LOAD_TYPE.replace("_", " ").title()} Load', fontsize=12)
ax3.grid(True, alpha=0.3)
ax3.legend(loc='upper right')
ax3.set_xlim([0, RAMP_TIME])

# Plot 4: Slip
ax4 = fig.add_subplot(gs[1, 1])
ax4.plot(time, slip_array, 'darkorange', linewidth=2)
ax4.set_ylabel('Slip (%)', fontsize=11)
ax4.set_xlabel('Time (s)', fontsize=11)
ax4.set_title('Motor Slip During Startup', fontsize=12)
ax4.grid(True, alpha=0.3)
ax4.set_xlim([0, RAMP_TIME])

# Plot 5: Power
ax5 = fig.add_subplot(gs[2, 0])
ax5.plot(time, power_input_array, 'b-', linewidth=2, label='Input Power')
ax5.plot(time, power_output_array, 'g-', linewidth=2, label='Output Power')
ax5.set_ylabel('Power (kW)', fontsize=11)
ax5.set_xlabel('Time (s)', fontsize=11)
ax5.set_title('Power During Startup', fontsize=12)
ax5.grid(True, alpha=0.3)
ax5.legend(loc='upper right')
ax5.set_xlim([0, RAMP_TIME])

# Plot 6: Efficiency
ax6 = fig.add_subplot(gs[2, 1])
ax6.plot(time, efficiency_array, 'purple', linewidth=2)
ax6.axhline(y=EFFICIENCY*100, color='green', linestyle='--', linewidth=1.5, 
           label=f'Rated Efficiency ({EFFICIENCY*100:.0f}%)')
ax6.set_ylabel('Efficiency (%)', fontsize=11)
ax6.set_xlabel('Time (s)', fontsize=11)
ax6.set_title('Motor Efficiency During Startup', fontsize=12)
ax6.grid(True, alpha=0.3)
ax6.legend(loc='lower right')
ax6.set_xlim([0, RAMP_TIME])
ax6.set_ylim([0, 100])

# =============================================================================
# SUMMARY STATISTICS
# =============================================================================

print("\n" + "="*70)
print("VFD MOTOR STARTUP SIMULATION SUMMARY")
print("="*70)
print(f"Motor Rating:          {POWER_HP} HP ({POWER_KW:.1f} kW)")
print(f"Load Type:             {LOAD_TYPE.replace('_', ' ').title()}")
print(f"Rated Speed:           {SYNC_SPEED_RPM*(1-0.03):.0f} RPM")
print(f"Rated Torque:          {RATED_TORQUE:.0f} Nm")
print(f"Full Load Current:     {FLA:.1f} A")
print(f"Base Load Torque:      {LOAD_TORQUE:.0f} Nm ({LOAD_TORQUE_FACTOR*100:.0f}% of rated)")
print(f"Ramp Time:             {RAMP_TIME} seconds")
print("-"*70)
print("VFD STARTING PERFORMANCE:")
print(f"  Peak Current:        {vfd_peak_current:.1f} A ({vfd_peak_current/FLA:.2f} × FLA)")
print(f"  Final Speed:         {omega_rpm[-1]:.0f} RPM")
print(f"  Final Slip:          {slip_array[-1]:.2f}%")
print(f"  Startup Energy:      {vfd_energy_kj:.1f} kJ ({vfd_energy_kwh:.3f} kWh)")
print(f"  Avg Efficiency:      {avg_efficiency:.1f}%")
print("-"*70)
print("DOL (DIRECT-ON-LINE) STARTING PERFORMANCE:")
print(f"  Peak Current:        {dol_peak_current:.1f} A ({dol_peak_current/FLA:.2f} × FLA)")
print(f"  Starting Time:       ~{dol_time[-1]:.1f} seconds")
print(f"  Startup Energy:      {dol_energy_kj:.1f} kJ ({dol_energy_kwh:.3f} kWh)")
print("-"*70)
print("VFD ADVANTAGES:")
print(f"  Current Reduction:   {(1 - vfd_peak_current/dol_peak_current)*100:.1f}% lower peak current")
print(f"  Energy Difference:   {abs(vfd_energy_kj - dol_energy_kj):.1f} kJ " + 
      f"({'more' if vfd_energy_kj > dol_energy_kj else 'less'} due to longer ramp)")
print(f"  Mechanical Stress:   Significantly reduced (controlled acceleration)")
print(f"  Grid Impact:         Minimal voltage sag vs severe for DOL")
print("="*70 + "\n")

plt.show()