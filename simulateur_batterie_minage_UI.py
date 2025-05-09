
import streamlit as st
import pandas as pd
import numpy as np

BATTERY_MAX = 30
SOC_MIN = 1.5
BATTERY_EFF = 0.95
BATTERY_POWER_LIMIT = 15
TARGET_MINER = 20
DEFAULT_PV_COST = 55  # €/MWh

st.title("Simulateur de gestion batterie - Minage optimisé")

st.sidebar.header("Entrées utilisateur")
prix_spot_input = st.sidebar.text_area("Prix SPOT (24 valeurs, séparées par des virgules)",
    "15,78,15,63,3,55,6,65,15,02,12,05,10,91,12,86,7,26,0,1,80,80,70,80,80,80,80,80,16,04,15,4,24,13,40,24,30,1")

pv_forecast_input = st.sidebar.file_uploader("Charger le fichier de prévision PV (96 valeurs, CSV avec 1 colonne)")
pv_cost = st.sidebar.number_input("Prix de revient du PV (€/MWh)", min_value=0.0, value=DEFAULT_PV_COST)

def simulate(prix_spot_hourly, pv_forecast_15min, pv_threshold):
    intervals_per_hour = 4
    total_steps = 96
    soc = [30]
    miner_power = []
    charge_grid = []
    charge_pv = []
    discharge = []
    grid_use = []

    prix_spot_15min = np.repeat(prix_spot_hourly, intervals_per_hour)

    daytime_indices = list(range(32, 80))
    pv_eligible_indices = [i for i in daytime_indices if prix_spot_15min[i] > pv_threshold]
    sorted_daytime_by_price = sorted(daytime_indices, key=lambda i: prix_spot_15min[i])
    night_indices = list(range(80, 96)) + list(range(0, 32))
    expensive_slots = [i for i in night_indices if prix_spot_15min[i] > THRESHOLD_SPOT]

    if expensive_slots:
        draw_per_interval = (soc[0] - SOC_MIN) / len(expensive_slots)
        planned_discharge = {i: draw_per_interval for i in expensive_slots}
    else:
        sorted_night = sorted(night_indices, key=lambda i: prix_spot_15min[i], reverse=True)
        top_slots = sorted_night[:8]
        draw_per_interval = (soc[0] - SOC_MIN) / len(top_slots)
        planned_discharge = {i: draw_per_interval for i in top_slots}

    sorted_grid_recharge = sorted(daytime_indices, key=lambda i: prix_spot_15min[i])

    for h in range(total_steps):
        current_soc = soc[-1]
        pv = pv_forecast_15min[h]
        price = prix_spot_15min[h]
        hour = h // intervals_per_hour
        is_daytime = 8 <= hour < 20
        is_night = not is_daytime

        batt_draw = 0
        batt_charge_grid = 0
        batt_charge_pv = 0
        grid_used = 0
        miner = 0

        if is_daytime and current_soc < BATTERY_MAX:
            if h in sorted_grid_recharge:
                charge = min(BATTERY_POWER_LIMIT, BATTERY_MAX - current_soc)
                batt_charge_grid = charge
                current_soc += (charge * BATTERY_EFF) / intervals_per_hour
                grid_used += charge
                sorted_grid_recharge.remove(h)
            elif h in pv_eligible_indices and pv > TARGET_MINER:
                surplus = pv - TARGET_MINER
                batt_charge_pv = min(surplus, BATTERY_POWER_LIMIT, BATTERY_MAX - current_soc)
                current_soc += (batt_charge_pv * BATTERY_EFF) / intervals_per_hour

        if h in planned_discharge and current_soc > SOC_MIN:
            draw = min(planned_discharge[h], BATTERY_POWER_LIMIT, current_soc - SOC_MIN)
            batt_draw = draw
            current_soc -= (draw / BATTERY_EFF) / intervals_per_hour
            miner = batt_draw
        elif is_night:
            miner = TARGET_MINER
            if batt_draw < TARGET_MINER:
                grid_used += TARGET_MINER - batt_draw
        else:
            miner = TARGET_MINER

        soc.append(min(current_soc, BATTERY_MAX))
        miner_power.append(miner)
        charge_grid.append(batt_charge_grid)
        charge_pv.append(batt_charge_pv)
        discharge.append(batt_draw)
        grid_use.append(grid_used)

    return pd.DataFrame({
        "Heure": pd.date_range("00:00", periods=96, freq="15min"),
        "Prix SPOT (€/MWh)": prix_spot_15min,
        "PV (kW)": pv_forecast_15min,
        "Minage (kW)": miner_power,
        "Recharge Réseau (kW)": charge_grid,
        "Recharge PV (kW)": charge_pv,
        "Décharge Batterie (kW)": discharge,
        "Réseau utilisé (kW)": grid_use,
        "SoC Batterie (kWh)": soc[:-1]
    })

if st.sidebar.button("Lancer la simulation"):
    try:
        prix_spot = [float(p.strip()) for p in prix_spot_input.split(",")]
        if len(prix_spot) != 24:
            st.error("Veuillez fournir exactement 24 valeurs horaires de prix SPOT.")
        else:
            if pv_forecast_input is not None:
                pv_df = pd.read_csv(pv_forecast_input, header=None)
                pv_forecast = pv_df.iloc[:, 0].values
                if len(pv_forecast) != 96:
                    st.error("Le fichier de production PV doit contenir exactement 96 valeurs.")
                else:
                    df_result = simulate(prix_spot, pv_forecast, pv_cost)
                    st.success("Simulation terminée.")
                    st.dataframe(df_result)
                    st.download_button("📥 Télécharger les résultats", df_result.to_csv(index=False), file_name="resultats_simulation.csv")
            else:
                st.warning("Veuillez importer un fichier de prévision PV.")
    except Exception as e:
        st.error(f"Erreur de traitement : {e}")
