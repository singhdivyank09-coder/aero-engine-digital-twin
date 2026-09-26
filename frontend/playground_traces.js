/**
 * Precomputed Scenario Trace Datasets for Public Fault Playground
 * Operates 100% client-side with zero backend calls or TwinSession side effects.
 */

window.PLAYGROUND_TRACES = {
    "CYLINDER_THERMAL": {
        id: "CYLINDER_THERMAL",
        title: "Cylinder Thermal Degradation",
        subsystem: "Thermal",
        component: "Cylinder 1 (CHT1)",
        description: "Gradual CHT1 thermal excursion exceeding reference model limit (145.0°C).",
        expected_fault_type: "Cylinder Head Overheating",
        frames: Array.from({ length: 601 }, (_, i) => {
            const t = i * 0.1;
            const progress = Math.min(1.0, t / 15.0);
            const cht1 = 120.0 + (progress * 32.0) + (Math.sin(t * 0.8) * 0.4);
            const egt1 = 748.0 + (progress * 55.0) + (Math.sin(t * 0.8) * 1.5);
            const oil_temp = 88.5 + (progress * 6.5);
            const status = cht1 >= 145.0 ? "CRITICAL" : (cht1 >= 135.0 ? "WARNING" : "NORMAL");
            const score = Math.min(0.95, progress * 0.85 + 0.02);
            return {
                t: Math.round(t * 10) / 10,
                progress_pct: Math.round(progress * 100),
                rpm: 5000 + Math.round(Math.sin(t * 0.1) * 15),
                cht1: Math.round(cht1 * 10) / 10,
                cht2: 120.8, cht3: 119.5, cht4: 120.2,
                egt1: Math.round(egt1 * 10) / 10,
                egt2: 750.0, egt3: 746.5, egt4: 749.0,
                oil_press: 4.20,
                oil_temp: Math.round(oil_temp * 10) / 10,
                vibration_rms: 1.12,
                battery_volt: 14.10,
                fuel_flow: 17.5,
                anomaly_score: Math.round(score * 1000) / 1000,
                status: status,
                classifier_label: progress > 0.3 ? "Cylinder Head Overheating" : "Nominal Operation",
                classifier_confidence: progress > 0.3 ? 0.94 : 0.99,
                advisory: progress > 0.5 ? "Reduce throttle and enrich mixture. CHT1 thermal limit exceeded." : "Nominal thermal state."
            };
        })
    },
    "OIL_PRESSURE": {
        id: "OIL_PRESSURE",
        title: "Lubrication Oil-Pressure Degradation",
        subsystem: "Lubrication",
        component: "Oil System (Pump / Filter)",
        description: "Exponential oil pressure drop below minimum operational threshold (2.0 bar).",
        expected_fault_type: "Lubrication System Pressure Loss",
        frames: Array.from({ length: 601 }, (_, i) => {
            const t = i * 0.1;
            const progress = Math.min(1.0, t / 15.0);
            const oil_p = Math.max(1.1, 4.20 - (progress * 2.5) + (Math.sin(t * 0.5) * 0.03));
            const oil_t = 88.5 + (progress * 18.0);
            const status = oil_p <= 2.0 ? "CRITICAL" : (oil_p <= 3.0 ? "WARNING" : "NORMAL");
            const score = Math.min(0.98, progress * 0.90 + 0.02);
            return {
                t: Math.round(t * 10) / 10,
                progress_pct: Math.round(progress * 100),
                rpm: 5000,
                cht1: 120.0, cht2: 120.8, cht3: 119.5, cht4: 120.2,
                egt1: 748.0, egt2: 750.0, egt3: 746.5, egt4: 749.0,
                oil_press: Math.round(oil_p * 100) / 100,
                oil_temp: Math.round(oil_t * 10) / 10,
                vibration_rms: Math.round((1.12 + (progress * 0.6)) * 100) / 100,
                battery_volt: 14.10,
                fuel_flow: 17.5,
                anomaly_score: Math.round(score * 1000) / 1000,
                status: status,
                classifier_label: progress > 0.3 ? "Lubrication System Pressure Loss" : "Nominal Operation",
                classifier_confidence: progress > 0.3 ? 0.96 : 0.99,
                advisory: progress > 0.5 ? "CRITICAL: Land immediately at nearest suitable airfield. Oil pressure critical." : "Nominal lubrication."
            };
        })
    },
    "INCREASING_VIBRATION": {
        id: "INCREASING_VIBRATION",
        title: "Increasing Mechanical Vibration",
        subsystem: "Mechanical",
        component: "Crankshaft / Bearing Assembly",
        description: "Ramping mechanical vibration RMS exceeding structural threshold (2.50 g).",
        expected_fault_type: "Abnormal Mechanical Vibration",
        frames: Array.from({ length: 601 }, (_, i) => {
            const t = i * 0.1;
            const progress = Math.min(1.0, t / 15.0);
            const vib = 1.12 + (progress * 1.8) + (Math.sin(t * 4.0) * 0.15);
            const status = vib >= 2.50 ? "WARNING" : (vib >= 1.80 ? "CAUTION" : "NORMAL");
            const score = Math.min(0.88, progress * 0.80 + 0.02);
            return {
                t: Math.round(t * 10) / 10,
                progress_pct: Math.round(progress * 100),
                rpm: 5000,
                cht1: 120.0, cht2: 120.8, cht3: 119.5, cht4: 120.2,
                egt1: 748.0, egt2: 750.0, egt3: 746.5, egt4: 749.0,
                oil_press: 4.20, oil_temp: 88.5,
                vibration_rms: Math.round(vib * 100) / 100,
                battery_volt: 14.10,
                fuel_flow: 17.5,
                anomaly_score: Math.round(score * 1000) / 1000,
                status: status,
                classifier_label: progress > 0.3 ? "Abnormal Mechanical Vibration" : "Nominal Operation",
                classifier_confidence: progress > 0.3 ? 0.91 : 0.99,
                advisory: progress > 0.4 ? "Monitor mechanical vibration RMS. Inspect bearing assembly post-flight." : "Nominal mechanical state."
            };
        })
    },
    "SENSOR_DRIFT": {
        id: "SENSOR_DRIFT",
        title: "Electrical Bus Sensor Drift",
        subsystem: "Electrical",
        component: "Electrical Bus / Voltage Sensor",
        description: "Linear sensor calibration drift on battery voltage signal down to 11.20 V.",
        expected_fault_type: "Electrical Bus Voltage Sensor Drift",
        frames: Array.from({ length: 601 }, (_, i) => {
            const t = i * 0.1;
            const progress = Math.min(1.0, t / 15.0);
            const volt = Math.max(11.20, 14.10 - (progress * 2.8));
            const status = volt <= 12.0 ? "WARNING" : (volt <= 13.0 ? "WATCH" : "NORMAL");
            const score = Math.min(0.75, progress * 0.70 + 0.02);
            return {
                t: Math.round(t * 10) / 10,
                progress_pct: Math.round(progress * 100),
                rpm: 5000,
                cht1: 120.0, cht2: 120.8, cht3: 119.5, cht4: 120.2,
                egt1: 748.0, egt2: 750.0, egt3: 746.5, egt4: 749.0,
                oil_press: 4.20, oil_temp: 88.5,
                vibration_rms: 1.12,
                battery_volt: Math.round(volt * 100) / 100,
                fuel_flow: 17.5,
                anomaly_score: Math.round(score * 1000) / 1000,
                status: status,
                classifier_label: progress > 0.3 ? "Electrical Bus Voltage Sensor Drift" : "Nominal Operation",
                classifier_confidence: progress > 0.3 ? 0.89 : 0.99,
                advisory: progress > 0.4 ? "Recalibrate voltage sensor and verify electrical bus connections." : "Nominal electrical bus."
            };
        })
    },
    "INTERMITTENT_COMBUSTION": {
        id: "INTERMITTENT_COMBUSTION",
        title: "Intermittent Combustion Misfire",
        subsystem: "Combustion",
        component: "Cylinder 3 (EGT3 / Ignition)",
        description: "Pulsed combustion misfires causing sharp EGT drops and vibration spikes.",
        expected_fault_type: "Intermittent Cylinder Misfire",
        frames: Array.from({ length: 601 }, (_, i) => {
            const t = i * 0.1;
            const is_misfire = Math.sin(t * 1.5) > 0.3;
            const egt3 = is_misfire ? 580.0 : 746.5;
            const vib = is_misfire ? 2.45 : 1.12;
            const status = is_misfire ? "WARNING" : "WATCH";
            const score = is_misfire ? 0.82 : 0.25;
            return {
                t: Math.round(t * 10) / 10,
                progress_pct: is_misfire ? 100 : 0,
                rpm: 5000 + (is_misfire ? -120 : 0),
                cht1: 120.0, cht2: 120.8, cht3: 118.0, cht4: 120.2,
                egt1: 748.0, egt2: 750.0, egt3: Math.round(egt3), egt4: 749.0,
                oil_press: 4.20, oil_temp: 88.5,
                vibration_rms: Math.round(vib * 100) / 100,
                battery_volt: 14.10,
                fuel_flow: 17.5,
                anomaly_score: score,
                status: status,
                classifier_label: is_misfire ? "Intermittent Cylinder Misfire" : "Nominal Operation",
                classifier_confidence: is_misfire ? 0.93 : 0.99,
                advisory: is_misfire ? "Inspect Cylinder 3 spark plugs and ignition leads." : "Nominal combustion."
            };
        })
    },
    "INJECTOR_DISTURBANCE": {
        id: "INJECTOR_DISTURBANCE",
        title: "Fuel Injector Abnormality",
        subsystem: "Combustion",
        component: "Fuel Injector Cylinder 2",
        description: "Fuel flow restriction causing lean mixture and elevated EGT2.",
        expected_fault_type: "Fuel Injector Restriction",
        frames: Array.from({ length: 601 }, (_, i) => {
            const t = i * 0.1;
            const progress = Math.min(1.0, t / 15.0);
            const ff = Math.max(11.5, 17.5 - (progress * 5.5));
            const egt2 = 750.0 + (progress * 85.0);
            const status = egt2 >= 820.0 ? "WARNING" : (egt2 >= 780.0 ? "CAUTION" : "NORMAL");
            const score = Math.min(0.85, progress * 0.82 + 0.02);
            return {
                t: Math.round(t * 10) / 10,
                progress_pct: Math.round(progress * 100),
                rpm: 5000,
                cht1: 120.0, cht2: Math.round((120.8 + progress * 22.0) * 10) / 10, cht3: 119.5, cht4: 120.2,
                egt1: 748.0, egt2: Math.round(egt2 * 10) / 10, egt3: 746.5, egt4: 749.0,
                oil_press: 4.20, oil_temp: 88.5,
                vibration_rms: 1.12,
                battery_volt: 14.10,
                fuel_flow: Math.round(ff * 10) / 10,
                anomaly_score: Math.round(score * 1000) / 1000,
                status: status,
                classifier_label: progress > 0.3 ? "Fuel Injector Restriction" : "Nominal Operation",
                classifier_confidence: progress > 0.3 ? 0.92 : 0.99,
                advisory: progress > 0.4 ? "Clean or replace Cylinder 2 fuel injector." : "Nominal fuel distribution."
            };
        })
    }
};
