# =============================================================================
# VFD-Motor-Simulation: 800HP Motor Startup Comparison
# =============================================================================
# Purpose: Python-based simulation comparing VFD vs Soft Starter starting
#          methods for an 800HP motor, with dynamic analysis of speed, torque,
#          current, and energy consumption.
# Version: 4.0.0 (VFD vs Soft Starter Comparison)
# Author: Alfonso Davila - Electrical Engineer
# Repository: https://github.com/dynmep/vfd-motor-simulation
# License: MIT License (see LICENSE file in repository)
# Created: October 2025
# Compatibility: Python 3.x, NumPy, SciPy, Matplotlib
#
# Quick Start:
#   Simulation: python vfd_simulation_v4.py
#   Customize:  Edit vfd_simulation_v4.py for specific motor parameters
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

# Starting method parameters
VFD_RAMP_TIME = 30  # VFD ramp time (seconds)
SOFT_START_RAMP_TIME = 20  # Soft starter ramp time (seconds)
V_BOOST = 0.15  # Low-frequency voltage boost for VFD (15%)
SOFT_START_INITIAL_VOLTAGE = 0.3  # Soft starter initial voltage (30%)

# Load type selection: 'constant_torque', 'fan_pump', 'constant_power'
LOAD_TYPE = 'constant_torque'

# Export settings
EXPORT_CSV = True
CSV_FILENAME = f'vfd_vs_softstarter_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

# Simulation parameters
TIME_POINTS = 1000

# =============================================================================
# DERIVED PARAMETERS
# =============================================================================

FLA = (POWER_KW * 1000) / (np.sqrt(3) * VOLTAGE * POWER_FACTOR * EFFICIENCY)
LOAD_TORQUE = RATED_TORQUE * LOAD_TORQUE_FACTOR

# =============================================================================
# LOAD TORQUE MODELS
# =============================================================================

def get_load_torque(speed_ratio, base_torque, load_type='constant_torque'):
    speed_ratio = max(0, min(speed_ratio, 1.0))
    
    if load_type == 'constant_torque':
        return base_torque * (0.3 + 0.7 * speed_ratio)
    elif load_type == 'fan_pump':
        return base_torque * speed_ratio**2
    elif load_type == 'constant_power':
        if speed_ratio < 0.1:
            return base_torque * 0.1 / 0.1
        return base_torque * 1.0 / speed_ratio
    else:
        return base_torque * (0.3 + 0.7 * speed_ratio)

# =============================================================================
# VFD CONTROL FUNCTIONS
# =============================================================================

def vfd_freq_func(t, ramp_time):
    if t <= ramp_time:
        return BASE_FREQ * (t / ramp_time)
    return BASE_FREQ

def vfd_voltage_func(freq):
    base_voltage = VOLTAGE * (freq / BASE_FREQ)
    if freq < BASE_FREQ * 0.1:
        boost = VOLTAGE * V_BOOST * (1 - freq / (BASE_FREQ * 0.1))
        return base_voltage + boost
    return base_voltage

# =============================================================================
# SOFT STARTER CONTROL FUNCTIONS
# =============================================================================

def soft_start_voltage_func(t, ramp_time):
    if t <= ramp_time:
        # Voltage ramp from initial to full
        voltage_ratio = SOFT_START_INITIAL_VOLTAGE + (1 - SOFT_START_INITIAL_VOLTAGE) * (t / ramp_time)
        return VOLTAGE * voltage_ratio
    return VOLTAGE

# =============================================================================
# MOTOR DYNAMICS MODELS
# =============================================================================

def vfd_motor_dynamics(state, t, base_load_torque, load_type, ramp_time):
    omega_rad = state[0]
    freq = vfd_freq_func(t, ramp_time)
    
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
    
    sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
    slip = (sync_speed_rad - omega_rad) / sync_speed_rad
    slip = np.clip(slip, 0, 1.0)
    
    a = 2.5
    b = 0.15
    c = 0.08
    
    torque_ratio = (a * slip) / (slip**2 + b * slip + c)
    torque_em = RATED_TORQUE * torque_ratio
    freq_ratio = freq / BASE_FREQ
    torque_em *= freq_ratio
    
    if freq < BASE_FREQ * 0.15:
        boost_factor = 1 + V_BOOST * (1 - freq / (BASE_FREQ * 0.15))
        torque_em *= boost_factor
    
    speed_ratio = omega_rad / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
    effective_load = get_load_torque(speed_ratio, base_load_torque, load_type)
    
    d_omega_dt = (torque_em - effective_load - DAMPING * omega_rad) / INERTIA
    return [d_omega_dt]

def soft_start_motor_dynamics(state, t, base_load_torque, load_type, ramp_time):
    omega_rad = state[0]
    voltage = soft_start_voltage_func(t, ramp_time)
    voltage_ratio = voltage / VOLTAGE
    
    # Motor runs at full frequency, reduced voltage
    sync_speed_rad = SYNC_SPEED_RAD
    slip = (sync_speed_rad - omega_rad) / sync_speed_rad
    slip = np.clip(slip, 0, 1.0)
    
    # Torque proportional to voltage squared for reduced voltage operation
    a = 2.5
    b = 0.15
    c = 0.08
    
    torque_ratio = (a * slip) / (slip**2 + b * slip + c)
    # Key difference: torque scales with V^2 in soft starter
    torque_em = RATED_TORQUE * torque_ratio * (voltage_ratio ** 2)
    
    speed_ratio = omega_rad / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
    effective_load = get_load_torque(speed_ratio, base_load_torque, load_type)
    
    d_omega_dt = (torque_em - effective_load - DAMPING * omega_rad) / INERTIA
    return [d_omega_dt]

# =============================================================================
# RUN SIMULATIONS
# =============================================================================

# VFD Simulation
vfd_time = np.linspace(0, VFD_RAMP_TIME, TIME_POINTS)
vfd_solution = odeint(vfd_motor_dynamics, [0], vfd_time, 
                      args=(LOAD_TORQUE, LOAD_TYPE, VFD_RAMP_TIME))
vfd_omega_rad = vfd_solution[:, 0]
vfd_omega_rpm = vfd_omega_rad * (60 / (2 * np.pi))

# Soft Starter Simulation
ss_time = np.linspace(0, SOFT_START_RAMP_TIME, TIME_POINTS)
ss_solution = odeint(soft_start_motor_dynamics, [0], ss_time,
                     args=(LOAD_TORQUE, LOAD_TYPE, SOFT_START_RAMP_TIME))
ss_omega_rad = ss_solution[:, 0]
ss_omega_rpm = ss_omega_rad * (60 / (2 * np.pi))

# =============================================================================
# CALCULATE PERFORMANCE METRICS
# =============================================================================

def calculate_metrics(time, omega_rad, method='vfd', ramp_time=30):
    n_points = len(time)
    current = np.zeros(n_points)
    torque = np.zeros(n_points)
    slip = np.zeros(n_points)
    power_in = np.zeros(n_points)
    power_out = np.zeros(n_points)
    efficiency = np.zeros(n_points)
    load_torque_array = np.zeros(n_points)
    voltage_array = np.zeros(n_points)
    
    for i, t in enumerate(time):
        if method == 'vfd':
            freq = vfd_freq_func(t, ramp_time)
            if freq < 0.5:
                continue
            sync_speed_rad = (120 * freq / POLES) * (2 * np.pi / 60)
            voltage_array[i] = vfd_voltage_func(freq)
        else:  # soft starter
            sync_speed_rad = SYNC_SPEED_RAD
            freq = BASE_FREQ
            voltage_array[i] = soft_start_voltage_func(t, ramp_time)
        
        s = (sync_speed_rad - omega_rad[i]) / sync_speed_rad if sync_speed_rad > 0 else 1.0
        s = np.clip(s, 0, 1.0)
        slip[i] = s * 100
        
        # Calculate torque
        a, b, c = 2.5, 0.15, 0.08
        torque_ratio = (a * s) / (s**2 + b * s + c)
        
        if method == 'vfd':
            freq_ratio = freq / BASE_FREQ
            torque[i] = RATED_TORQUE * torque_ratio * freq_ratio
            if freq < BASE_FREQ * 0.15:
                boost = 1 + V_BOOST * (1 - freq / (BASE_FREQ * 0.15))
                torque[i] *= boost
        else:  # soft starter
            voltage_ratio = voltage_array[i] / VOLTAGE
            torque[i] = RATED_TORQUE * torque_ratio * (voltage_ratio ** 2)
        
        # Calculate load torque
        speed_ratio = omega_rad[i] / SYNC_SPEED_RAD if SYNC_SPEED_RAD > 0 else 0
        load_torque_array[i] = get_load_torque(speed_ratio, LOAD_TORQUE, LOAD_TYPE)
        
        # Calculate current (simplified model)
        torque_component = FLA * (torque[i] / RATED_TORQUE)
        magnetizing_component = FLA * 0.3
        current[i] = np.sqrt(torque_component**2 + magnetizing_component**2)
        
        # For soft starter, current is higher due to reduced voltage operation
        if method == 'soft_starter' and t < ramp_time:
            voltage_ratio = voltage_array[i] / VOLTAGE
            # Current increases as voltage decreases (maintaining power)
            if voltage_ratio > 0.3:
                current[i] *= (1.2 / voltage_ratio)
        
        # Calculate power
        power_out[i] = (omega_rad[i] * load_torque_array[i]) / 1000
        power_in[i] = (np.sqrt(3) * voltage_array[i] * current[i] * POWER_FACTOR) / 1000
        
        if power_in[i] > 0:
            efficiency[i] = (power_out[i] / power_in[i]) * 100
        
    return current, torque, slip, load_torque_array, power_in, power_out, efficiency, voltage_array

# Calculate metrics for each method
vfd_current, vfd_torque, vfd_slip, vfd_load, vfd_pin, vfd_pout, vfd_eff, vfd_voltage = \
    calculate_metrics(vfd_time, vfd_omega_rad, 'vfd', VFD_RAMP_TIME)

ss_current, ss_torque, ss_slip, ss_load, ss_pin, ss_pout, ss_eff, ss_voltage = \
    calculate_metrics(ss_time, ss_omega_rad, 'soft_starter', SOFT_START_RAMP_TIME)

# =============================================================================
# ENERGY AND COST CALCULATIONS
# =============================================================================

vfd_energy_kj = np.trapz(vfd_pin, vfd_time)
ss_energy_kj = np.trapz(ss_pin, ss_time)

vfd_peak_current = np.max(vfd_current)
ss_peak_current = np.max(ss_current)

# Cost analysis
vfd_installed_cost = 70000  # Typical installed cost
ss_installed_cost = 15000   # Typical installed cost

# Annual operating costs (assuming 6000 hrs/year at rated load)
annual_hours = 6000
energy_cost_per_kwh = 0.10

# VFD continuous losses (3-5% when running)
vfd_continuous_loss_pct = 0.04
vfd_annual_loss_cost = vfd_continuous_loss_pct * POWER_KW * annual_hours * energy_cost_per_kwh

# Soft starter bypassed after startup (zero continuous losses)
ss_annual_loss_cost = 0

# Startup energy costs (assuming 2 starts per day)
starts_per_year = 2 * 365
vfd_startup_cost = (vfd_energy_kj / 3600) * energy_cost_per_kwh * starts_per_year
ss_startup_cost = (ss_energy_kj / 3600) * energy_cost_per_kwh * starts_per_year

# Total annual operating cost
vfd_total_annual_cost = vfd_annual_loss_cost + vfd_startup_cost
ss_total_annual_cost = ss_annual_loss_cost + ss_startup_cost

# Payback period for VFD premium (if used for constant speed only)
cost_difference = vfd_installed_cost - ss_installed_cost
annual_savings_ss = vfd_total_annual_cost - ss_total_annual_cost
payback_years = cost_difference / annual_savings_ss if annual_savings_ss > 0 else float('inf')

# =============================================================================
# CSV EXPORT
# =============================================================================

if EXPORT_CSV:
    with open(CSV_FILENAME, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['VFD vs Soft Starter Comparison - Motor Startup Simulation'])
        writer.writerow(['Generated:', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(['Motor Rating:', f'{POWER_HP} HP ({POWER_KW:.1f} kW)'])
        writer.writerow(['Load Type:', LOAD_TYPE])
        writer.writerow([])
        
        # VFD Data
        writer.writerow(['VFD DATA'])
        writer.writerow(['Time (s)', 'Speed (RPM)', 'Current (A)', 'Torque (Nm)', 
                        'Slip (%)', 'Power In (kW)', 'Power Out (kW)', 'Efficiency (%)'])
        for i in range(len(vfd_time)):
            writer.writerow([f'{vfd_time[i]:.3f}', f'{vfd_omega_rpm[i]:.1f}',
                           f'{vfd_current[i]:.1f}', f'{vfd_torque[i]:.1f}',
                           f'{vfd_slip[i]:.2f}', f'{vfd_pin[i]:.2f}',
                           f'{vfd_pout[i]:.2f}', f'{vfd_eff[i]:.1f}'])
        
        writer.writerow([])
        writer.writerow(['SOFT STARTER DATA'])
        writer.writerow(['Time (s)', 'Speed (RPM)', 'Current (A)', 'Torque (Nm)', 
                        'Slip (%)', 'Power In (kW)', 'Power Out (kW)', 'Efficiency (%)'])
        for i in range(len(ss_time)):
            writer.writerow([f'{ss_time[i]:.3f}', f'{ss_omega_rpm[i]:.1f}',
                           f'{ss_current[i]:.1f}', f'{ss_torque[i]:.1f}',
                           f'{ss_slip[i]:.2f}', f'{ss_pin[i]:.2f}',
                           f'{ss_pout[i]:.2f}', f'{ss_eff[i]:.1f}'])

# =============================================================================
# PLOTTING
# =============================================================================

fig = plt.figure(figsize=(18, 10))
gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

fig.suptitle(f'VFD vs Soft Starter Comparison - {POWER_HP}HP Motor ({LOAD_TYPE.replace("_", " ").title()} Load)', 
             fontsize=16, fontweight='bold')

# Plot 1: Speed Response
ax1 = fig.add_subplot(gs[0, 0])
ax1.plot(vfd_time, vfd_omega_rpm, 'b-', linewidth=2.5, label='VFD')
ax1.plot(ss_time, ss_omega_rpm, 'g-', linewidth=2.5, label='Soft Starter')
ax1.axhline(y=SYNC_SPEED_RPM, color='gray', linestyle=':', linewidth=1.5, label='Sync Speed')
ax1.set_ylabel('Speed (RPM)', fontsize=12, fontweight='bold')
ax1.set_xlabel('Time (s)', fontsize=12, fontweight='bold')
ax1.set_title('Speed Response\n', fontsize=13, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend(loc='lower right', fontsize=10)

# Plot 2: Current Draw
ax2 = fig.add_subplot(gs[0, 1])
ax2.plot(vfd_time, vfd_current, 'b-', linewidth=2.5, label='VFD')
ax2.plot(ss_time, ss_current, 'g-', linewidth=2.5, label='Soft Starter')
ax2.axhline(y=FLA, color='gray', linestyle='--', linewidth=2, label=f'FLA ({FLA:.0f}A)')
ax2.set_ylabel('Current (A)', fontsize=12, fontweight='bold')
ax2.set_xlabel('Time (s)', fontsize=12, fontweight='bold')
ax2.set_title('Current Draw\n', fontsize=13, fontweight='bold')
ax2.grid(True, alpha=0.3)
ax2.legend(loc='upper right', fontsize=10)

# Plot 3: Peak Current Comparison
ax3 = fig.add_subplot(gs[0, 2])
methods = ['VFD', 'Soft Starter']
peak_currents = [vfd_peak_current, ss_peak_current]
colors = ['blue', 'green']
bars = ax3.bar(methods, peak_currents, color=colors, alpha=0.7, edgecolor='black', linewidth=2, width=0.5)
ax3.axhline(y=FLA, color='gray', linestyle='--', linewidth=2, label='FLA')
ax3.set_ylabel('Peak Current (A)', fontsize=12, fontweight='bold')
ax3.set_title('Peak Current Comparison\n', fontsize=13, fontweight='bold')
ax3.grid(True, alpha=0.3, axis='y')
ax3.legend(fontsize=10)
for bar, current in zip(bars, peak_currents):
    height = bar.get_height()
    ax3.text(bar.get_x() + bar.get_width()/2., height,
            f'{current:.0f}A\n({current/FLA:.2f}×FLA)',
            ha='center', va='bottom', fontsize=10, fontweight='bold')

# Plot 4: Torque Profiles
ax4 = fig.add_subplot(gs[1, 0])
ax4.plot(vfd_time, vfd_torque, 'b-', linewidth=2, label='VFD Motor Torque')
ax4.plot(ss_time, ss_torque, 'g-', linewidth=2, label='Soft Starter Motor Torque')
ax4.plot(vfd_time, vfd_load, 'orange', linewidth=2, linestyle='--', label='Load Torque')
ax4.axhline(y=RATED_TORQUE, color='red', linestyle=':', linewidth=1.5, label='Rated Torque')
ax4.set_ylabel('Torque (Nm)', fontsize=12, fontweight='bold')
ax4.set_xlabel('Time (s)', fontsize=12, fontweight='bold')
ax4.set_title('Torque Profiles', fontsize=13, fontweight='bold')
ax4.grid(True, alpha=0.3)
ax4.legend(loc='upper right', fontsize=9)

# Plot 5: Motor Slip
ax5 = fig.add_subplot(gs[1, 1])
ax5.plot(vfd_time, vfd_slip, 'b-', linewidth=2.5, label='VFD')
ax5.plot(ss_time, ss_slip, 'g-', linewidth=2.5, label='Soft Starter')
ax5.set_ylabel('Slip (%)', fontsize=12, fontweight='bold')
ax5.set_xlabel('Time (s)', fontsize=12, fontweight='bold')
ax5.set_title('Motor Slip During Startup', fontsize=13, fontweight='bold')
ax5.grid(True, alpha=0.3)
ax5.legend(loc='upper right', fontsize=10)

# Plot 6: Cost Comparison
ax6 = fig.add_subplot(gs[1, 2])
ax6.axis('off')

# Create comparison table
comparison_data = [
    ['Parameter', 'VFD', 'Soft Starter', 'Advantage'],
    ['Peak Current', f'{vfd_peak_current:.0f}A', f'{ss_peak_current:.0f}A', 'VFD'],
    ['Current Ratio', f'{vfd_peak_current/FLA:.2f}×FLA', f'{ss_peak_current/FLA:.2f}×FLA', 'VFD'],
    ['Ramp Time', f'{VFD_RAMP_TIME}s', f'{SOFT_START_RAMP_TIME}s', 'Soft Starter'],
    ['Final Speed', f'{vfd_omega_rpm[-1]:.0f} RPM', f'{ss_omega_rpm[-1]:.0f} RPM', 'Tie'],
    ['Final Slip', f'{vfd_slip[-1]:.2f}%', f'{ss_slip[-1]:.2f}%', 'Tie'],
    ['Energy/Start', f'{vfd_energy_kj/3600:.2f} kWh', f'{ss_energy_kj/3600:.2f} kWh', 'VFD'],
    ['Installed Cost', f'${vfd_installed_cost:,}', f'${ss_installed_cost:,}', 'Soft Starter'],
    ['Annual Op. Cost', f'${vfd_total_annual_cost:,.0f}', f'${ss_total_annual_cost:,.0f}', 'Soft Starter'],
    ['Ongoing Losses', f'~{vfd_continuous_loss_pct*100:.0f}%', '0% (bypassed)', 'Soft Starter'],
]

table = ax6.table(cellText=comparison_data, cellLoc='left', loc='center',
                 bbox=[0, 0, 1, 1], colWidths=[0.3, 0.25, 0.25, 0.2])
table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1, 1.8)

# Style the header row
for i in range(4):
    cell = table[(0, i)]
    cell.set_facecolor('#4472C4')
    cell.set_text_props(weight='bold', color='white')

# Color code advantages
for i in range(1, len(comparison_data)):
    if comparison_data[i][3] == 'VFD':
        table[(i, 1)].set_facecolor('#D6E9F8')  # Light blue
    elif comparison_data[i][3] == 'Soft Starter':
        table[(i, 2)].set_facecolor('#E2EFD9')  # Light green

ax6.set_title('Performance Comparison', fontsize=13, fontweight='bold', pad=20)

plt.subplots_adjust(left=0.08, right=0.98, top=0.90, bottom=0.06, hspace=0.3, wspace=0.3)

# =============================================================================
# CONSOLE SUMMARY
# =============================================================================

print("\n" + "="*85)
print("VFD vs SOFT STARTER COMPARISON")
print("="*85)
print(f"Motor Rating:          {POWER_HP} HP ({POWER_KW:.1f} kW)")
print(f"Load Type:             {LOAD_TYPE.replace('_', ' ').title()}")
print(f"Synchronous Speed:     {SYNC_SPEED_RPM} RPM")
print(f"Rated Torque:          {RATED_TORQUE:.0f} Nm")
print(f"Full Load Current:     {FLA:.1f} A")
print(f"Load Torque:           {LOAD_TORQUE:.0f} Nm ({LOAD_TORQUE_FACTOR*100:.0f}% of rated)")
print("-"*85)
print("\n🔵 VFD PERFORMANCE:")
print(f"  Control Method:      Frequency + Voltage (Constant V/f)")
print(f"  Ramp Time:           {VFD_RAMP_TIME} seconds")
print(f"  Peak Current:        {vfd_peak_current:.1f} A ({vfd_peak_current/FLA:.2f} × FLA)")
print(f"  Final Speed:         {vfd_omega_rpm[-1]:.0f} RPM")
print(f"  Final Slip:          {vfd_slip[-1]:.2f}%")
print(f"  Energy per Start:    {vfd_energy_kj:.1f} kJ ({vfd_energy_kj/3600:.3f} kWh)")
print(f"  Installed Cost:      ${vfd_installed_cost:,}")
print(f"  Annual Startup Cost: ${vfd_startup_cost:,.0f}")
print(f"  Annual Running Loss: ${vfd_annual_loss_cost:,.0f} ({vfd_continuous_loss_pct*100:.0f}% continuous)")
print(f"  Total Annual Cost:   ${vfd_total_annual_cost:,.0f}")
print("-"*85)
print("\n🟢 SOFT STARTER PERFORMANCE:")
print(f"  Control Method:      Voltage Only (SCR Phase Angle Control)")
print(f"  Ramp Time:           {SOFT_START_RAMP_TIME} seconds")
print(f"  Peak Current:        {ss_peak_current:.1f} A ({ss_peak_current/FLA:.2f} × FLA)")
print(f"  Final Speed:         {ss_omega_rpm[-1]:.0f} RPM")
print(f"  Final Slip:          {ss_slip[-1]:.2f}%")
print(f"  Energy per Start:    {ss_energy_kj:.1f} kJ ({ss_energy_kj/3600:.3f} kWh)")
print(f"  Installed Cost:      ${ss_installed_cost:,}")
print(f"  Annual Startup Cost: ${ss_startup_cost:,.0f}")
print(f"  Annual Running Loss: $0 (bypassed after start)")
print(f"  Total Annual Cost:   ${ss_total_annual_cost:,.0f}")
print("-"*85)
print("\n📊 COMPARATIVE ANALYSIS:")
print(f"  Current Reduction:   VFD is {(1 - vfd_peak_current/ss_peak_current)*100:.1f}% lower than Soft Starter")
print(f"  Cost Savings:        Soft Starter saves ${cost_difference:,} upfront ({(1-ss_installed_cost/vfd_installed_cost)*100:.0f}%)")
print(f"  Operating Savings:   Soft Starter saves ${annual_savings_ss:,.0f}/year on operating costs")
print(f"  VFD Premium Payback: {payback_years:.1f} years (if used for constant speed only)")
print(f"  Speed Control:       VFD: Yes | Soft Starter: No")
print("-"*85)
print("\n💡 RECOMMENDATIONS:")
print("\n  FOR CONSTANT-SPEED APPLICATIONS:")
print("    ✓ Soft Starter is the CLEAR WINNER")
print(f"      - Saves ${cost_difference:,} upfront")
print(f"      - Saves ${annual_savings_ss:,.0f}/year in operating costs")
print(f"      - Peak current only {ss_peak_current/FLA:.2f}× FLA (vs VFD {vfd_peak_current/FLA:.2f}×)")
print("      - Zero continuous losses (bypassed after startup)")
print("      - Simpler maintenance, higher reliability")
print("\n  FOR VARIABLE-SPEED APPLICATIONS:")
print("    ✓ VFD is ESSENTIAL")
print("      - Energy savings from speed control justify premium")
print("      - Example: Running at 90% speed saves ~27% energy")
print("      - ROI typically 2-3 years for variable torque loads")
print("\n  THE DECIDING FACTOR:")
print("    → Will you EVER need to vary motor speed?")
print("      • YES: Choose VFD (energy savings >> initial cost)")
print("      • NO:  Choose Soft Starter (best value for constant speed)")
print("="*85 + "\n")

if EXPORT_CSV:
    print(f"✓ Simulation data exported to: {CSV_FILENAME}\n")

plt.show()