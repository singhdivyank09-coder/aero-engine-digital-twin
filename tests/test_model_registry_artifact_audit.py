import sys
import os
import json
import asyncio

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath('.'))

from backend.model_registry import ModelRegistry

def run_model_registry_artifact_audit():
    print("=== STARTING AUTOMATED MODEL REGISTRY & ARTIFACT AUDIT SUITE ===")
    
    models = ModelRegistry.get_registered_models()
    datasets = ModelRegistry.get_dataset_provenance()
    
    print(f"Registered Models Count: {len(models)}")
    print(f"Dataset Provenance Entries Count: {len(datasets)}")
    
    # 1. Audit Autoencoder
    ae = models.get("autoencoder")
    assert ae is not None, "Autoencoder missing from ModelRegistry!"
    print(f"\n[AUTOENCODER AUDIT]")
    print(f"Artifact Path: {ae['artifact_path']} | Exists: {ae['artifact_exists']}")
    print(f"Status: {ae['status']} | Readiness: {ae['readiness_status']}")
    assert ae['artifact_exists'] == True, "Autoencoder model artifact does not exist!"
    assert ae['status'] == "TRAINED", "Autoencoder status must be TRAINED!"
    assert ae['metrics_exists'] == True, "Autoencoder metrics artifact does not exist!"
    assert "precision" in ae['evaluation_metrics'], "Precision metric missing from Autoencoder metrics!"
    print(f"Metrics Loaded: Precision={ae['evaluation_metrics']['precision']}, Recall={ae['evaluation_metrics']['recall']}, F1={ae['evaluation_metrics']['f1_score']}, ROC={ae['evaluation_metrics']['roc_auc']}")
    
    # 2. Audit GRU Forecaster
    gru = models.get("gru_forecaster")
    assert gru is not None, "GRU forecaster missing from ModelRegistry!"
    print(f"\n[GRU FORECASTER AUDIT]")
    print(f"Artifact Path: {gru['artifact_path']} | Exists: {gru['artifact_exists']}")
    print(f"Status: {gru['status']} | Readiness: {gru['readiness_status']}")
    assert gru['artifact_exists'] == True, "GRU forecaster weight file missing!"
    assert gru['training_dataset'] == "SIMULATED REFERENCE AERO-PISTON TRAJECTORY DATASET (125 Trajectories)", f"Unexpected GRU training source: {gru['training_dataset']}"
    assert "cht1" in gru['metrics_by_parameter_horizon'], "cht1 metrics missing from GRU metrics!"
    print(f"GRU 30s CHT1 MAE: {gru['metrics_by_parameter_horizon']['cht1']['30s']['mae']} °C")
    
    # 3. Audit LSTM RUL Model
    rul = models.get("lstm_rul")
    assert rul is not None, "LSTM RUL model missing from ModelRegistry!"
    print(f"\n[LSTM RUL PROGNOSTIC MODEL AUDIT]")
    print(f"Artifact Path: {rul['artifact_path']} | Exists: {rul['artifact_exists']}")
    print(f"Status: {rul['status']} | Readiness: {rul['readiness_status']}")
    assert rul['artifact_exists'] == True, "LSTM RUL weight file missing!"
    assert rul['unit'] == "cycles", f"RUL unit must be cycles, got {rul['unit']}"
    assert "mae_cycles" in rul['evaluation_metrics'], "mae_cycles missing from RUL evaluation metrics!"
    print(f"RUL MAE: {rul['evaluation_metrics']['mae_cycles']} cycles | RMSE: {rul['evaluation_metrics']['rmse_cycles']} cycles")
    
    # 4. Audit Fault Classifier
    xgb = models.get("xgboost_fault_classifier")
    assert xgb is not None, "XGBoost Fault Classifier missing from ModelRegistry!"
    print(f"\n[XGBOOST FAULT CLASSIFIER AUDIT]")
    print(f"Artifact Path: {xgb['artifact_path']} | Exists: {xgb['artifact_exists']}")
    print(f"Status: {xgb['status']} | Trained Classes Count: {len(xgb['trained_classes'])}")
    assert xgb['artifact_exists'] == True, "XGBoost model file missing!"
    assert len(xgb['trained_classes']) == 7, "Trained fault classes count must be 7!"
    assert len(xgb['simulated_prototype_scenarios']) == 6, "Simulated scenarios count must be 6!"
    print("Separated Trained Fault Classes vs Simulated Prototype Scenarios: VERIFIED YES")
    
    # 5. Audit Physics Model
    phys = models.get("physics_model")
    assert phys is not None, "Physics model missing from ModelRegistry!"
    print(f"\n[PHYSICS MODEL AUDIT]")
    print(f"Implementation Label: {phys['implementation_label']}")
    assert phys['status'] == "PHYSICS_MODEL", "Physics model status must be PHYSICS_MODEL!"
    assert phys['implementation_label'] == "0D/1D THERMODYNAMIC PHYSICS SURROGATE", "Physics model label must be 0D/1D THERMODYNAMIC PHYSICS SURROGATE!"
    
    # 6. Audit Dataset Provenance
    print(f"\n[DATASET PROVENANCE AUDIT]")
    cmapss_entry = next((d for d in datasets if d["dataset_name"] == "NASA C-MAPSS FD001"), None)
    assert cmapss_entry is not None, "NASA C-MAPSS entry missing from dataset provenance!"
    assert cmapss_entry["mapping_type"] == "ANALOGUE", f"NASA C-MAPSS mapping type must be ANALOGUE, got {cmapss_entry['mapping_type']}"
    
    alfa_entry = next((d for d in datasets if d["dataset_name"] == "ALFA UAV Dataset"), None)
    assert alfa_entry["active_status"] == "AVAILABLE / NOT CURRENTLY USED BY RUNTIME MODEL", "ALFA UAV status incorrect!"
    
    print("\n=== ALL ARTIFACT & MODEL REGISTRY AUDITS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_model_registry_artifact_audit()
