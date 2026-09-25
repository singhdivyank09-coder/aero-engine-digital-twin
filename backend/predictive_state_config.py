"""
Predictive State Machine Configuration — SIH 26054 Aero-Piston Digital Twin
Centralized Backend Configuration for Multi-Source Evidence Fusion & State Transitions

Defines:
- Configurable evidence fusion term weights
- Multi-subsystem state decision activation & recovery thresholds (Hysteresis)
- Temporal persistence Ring Buffer parameters (K-of-M logic)
- Safety Envelope Reference Thresholds
"""

# -------------------------------------------------------------------------
# 1. Multi-Source Evidence Fusion Weights (Sum = 1.00)
# -------------------------------------------------------------------------
EVIDENCE_WEIGHTS = {
    "forecast_risk": 0.30,           # GRU neural short-horizon forecast risk
    "time_to_risk": 0.20,            # Estimated time-to-risk urgency
    "degradation_score": 0.15,       # Subsystem trajectory degradation score
    "autoencoder_score": 0.10,       # Deep Autoencoder reconstruction anomaly
    "autoencoder_slope": 0.05,       # Anomaly score growth rate
    "cusum_detected": 0.05,          # Statistical CUSUM change-point detection
    "physics_residual": 0.10,        # PINN physical model residual magnitude
    "subsystem_health": 0.05         # Subsystem Health Index degradation
}

# -------------------------------------------------------------------------
# 2. State Transition Thresholds (Activation vs Recovery Hysteresis)
# -------------------------------------------------------------------------
# Hysteresis rule: activation_threshold > recovery_threshold
STATE_THRESHOLDS = {
    "WATCH": {
        "activation_score": 0.25,
        "recovery_score": 0.15,
        "health_activation": 84.0,
        "health_recovery": 88.0
    },
    "CAUTION": {
        "activation_score": 0.42,
        "recovery_score": 0.30,
        "health_activation": 72.0,
        "health_recovery": 76.0
    },
    "WARNING": {
        "activation_score": 0.68,
        "recovery_score": 0.52,
        "health_activation": 58.0,
        "health_recovery": 62.0
    },
    "CRITICAL": {
        # CRITICAL is strictly reserved for confirmed severe CURRENT condition
        # (e.g. physical limit breach or severe health collapse < 40.0%)
        "activation_score": 0.90,
        "recovery_score": 0.75,
        "health_activation": 40.0,
        "health_recovery": 45.0
    }
}

# -------------------------------------------------------------------------
# 3. Temporal Persistence Parameters (K-of-M Logic)
# -------------------------------------------------------------------------
# Step-up Activation Persistence
ACTIVATION_PERSISTENCE_DEPTH = 5   # M frames (0.5 seconds at 10 Hz)
ACTIVATION_K_OF_M = 3              # K required positive frames

# Step-down Recovery Persistence
RECOVERY_PERSISTENCE_DEPTH = 4     # M frames (0.4 seconds at 10 Hz)
RECOVERY_K_OF_M = 3                # K required recovery frames

# -------------------------------------------------------------------------
# 4. Safety Envelopes for Current Fault Confirmation
# -------------------------------------------------------------------------
SAFETY_ENVELOPES = {
    "cht": {"nominal_max": 135.0, "fault_limit": 145.0, "unit": "°C"},
    "oil_press": {"nominal_min": 3.50, "fault_limit": 2.50, "unit": "bar"},
    "vibration_rms": {"nominal_max": 1.50, "fault_limit": 2.50, "unit": "g"},
    "egt_spread": {"nominal_max": 45.0, "fault_limit": 90.0, "unit": "°C"},
    "battery_volt": {"fault_min": 11.50, "fault_max": 15.50, "unit": "V"}
}
