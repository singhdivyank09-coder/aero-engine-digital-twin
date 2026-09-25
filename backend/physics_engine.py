import math

class AeroEnginePhysicsModel:
    def __init__(self):
        # Rotax 914 Turbocharged Aero Engine Specifications
        self.displacement_liters = 1.211 # 1211 cc
        self.max_rpm = 5800
        self.lhv_fuel = 43.5 # MJ/kg (AvGas 100LL / Mogas)
        self.cylinders = 4

    def compute_virtual_state(self, rpm: float, map_kpa: float, ambient_temp: float = 25.0, altitude_m: float = 0.0):
        """
        Computes baseline physics-expected values for key engine metrics
        given the operational point (RPM, MAP, Ambient Temp, Altitude).
        """
        # 1. Air density correction for altitude
        air_density_ratio = math.exp(-altitude_m / 8500.0)
        
        # 2. Brake Power Estimation (kW)
        volumetric_efficiency = 0.88 + 0.05 * (map_kpa / 100.0)
        brake_power_kw = (map_kpa * rpm * self.displacement_liters * volumetric_efficiency) / 1200.0
        brake_power_kw = max(5.0, min(85.0, brake_power_kw))

        # 3. Physics Expected CHT (°C)
        # Heat balance: CHT rises with power output and ambient temp, cooled by ram air
        cooling_factor = 1.0 + 0.2 * (altitude_m / 3000.0) # Less cooling air at high altitude
        expected_cht = ambient_temp + 110.0 * (brake_power_kw / 85.0)**0.7 * cooling_factor
        expected_cht = max(80.0, min(175.0, expected_cht))

        # 4. Physics Expected EGT (°C)
        # Exhaust temp scales with load & MAP
        expected_egt = 650.0 + 200.0 * (map_kpa / 135.0)**0.5
        expected_egt = max(600.0, min(880.0, expected_egt))

        # 5. Physics Expected Oil Pressure (bar)
        # Higher RPM raises pressure, but higher oil temp reduces viscosity
        expected_oil_press = 2.0 + 3.0 * (rpm / self.max_rpm)
        expected_oil_press = max(1.5, min(5.5, expected_oil_press))

        # 6. Physics Expected Oil Temp (°C)
        expected_oil_temp = ambient_temp + 65.0 * (brake_power_kw / 85.0)**0.6
        expected_oil_temp = max(60.0, min(130.0, expected_oil_temp))

        # 7. Physics Expected Fuel Flow (Liters/hour)
        # Specific Fuel Consumption (SFC) ~ 260 g/kWh
        sfc = 0.26 # kg/kWh
        fuel_density = 0.72 # kg/L
        expected_fuel_flow = (brake_power_kw * sfc) / fuel_density
        expected_fuel_flow = max(3.0, min(32.0, expected_fuel_flow))

        return {
            "expected_power_kw": round(brake_power_kw, 2),
            "expected_cht": round(expected_cht, 1),
            "expected_egt": round(expected_egt, 1),
            "expected_oil_press": round(expected_oil_press, 2),
            "expected_oil_temp": round(expected_oil_temp, 1),
            "expected_fuel_flow": round(expected_fuel_flow, 2)
        }

physics_model_instance = AeroEnginePhysicsModel()
