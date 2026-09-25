# Automated Testing Guide — Aero Engine Digital Twin

## 1. Overview of Automated Test Suite

The repository contains a comprehensive suite of unit tests, integration tests, and acceptance test scripts located in the `tests/` and `scratch/` directories.

---

## 2. Running Automated Tests

### 2.1 Run Full Pytest Suite
To execute all automated unit and integration tests:

```bash
python -m pytest tests/
```

### 2.2 Run Specific Component Tests

```bash
# Test 5-State Predictive Health Engine & Hysteresis
python -m pytest tests/test_predictive_state_machine_suite.py

# Test PyTorch GRU 60s Forecaster Service
python -m pytest tests/test_gru_verification_suite.py

# Test Fault Analytics & Physical Input Perturbation
python -m pytest tests/test_fault_injection_analytics.py

# Test Data Integrity & Telemetry Counter Instrumentation
python -m pytest tests/test_data_integrity_instrumentation.py
```

### 2.3 Run Time-to-Risk Acceptance Test
To run the automated time-to-risk boundary verification script:

```bash
python scratch/test_time_to_risk_acceptance.py
```

Expected Output:
```
======================================================================
TIME-TO-RISK ACCEPTANCE TEST SUITE — COMPLETE SUCCESS
All risk calculations, threshold crossings, and boundary conditions verified!
======================================================================
```

---

## 3. Test Coverage Matrix

| Test Suite File | Coverage Area | Key Verification Items |
| :--- | :--- | :--- |
| `test_predictive_state_machine_suite.py` | State Machine | Evidence fusion weighting, K-of-M persistence (4/6 frames), stepwise hysteresis recovery. |
| `test_gru_verification_suite.py` | GRU Forecaster | 60-step input sequence sliding window, +10s/+30s/+60s projection accuracy. |
| `test_fault_injection_analytics.py` | Fault Injection | 60s thermal ramp timeline, physical input perturbation isolation. |
| `test_data_integrity_instrumentation.py` | Telemetry Pipeline | Schema validation, physical range checks, data integrity rate calculations. |
| `test_time_to_risk_acceptance.py` | Time-to-Risk Engine | Limit breach `0.0s LIMIT EXCEEDED`, nominal `999.0s`, slope projections. |
