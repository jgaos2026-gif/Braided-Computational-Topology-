from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np


C_LIGHT = 299_792_458.0
SIGMA_SB = 5.670374e-8


class SystemState(Enum):
    IDLE = auto()
    CONTAINMENT_ACTIVE = auto()
    GRADIENT_SHAPED = auto()
    COUPLING_ENGAGED = auto()
    FIELD_CLOSURE = auto()
    ABORT = auto()


@dataclass(frozen=True)
class TelemetryRecord:
    timestamp_utc: str
    elapsed_s: float
    state: str
    energy_j: float
    momentum_kg_ms: Tuple[float, float, float]
    momentum_error_kg_ms: float
    position_m: Tuple[float, float, float]
    velocity_m_per_s: Tuple[float, float, float]
    temperature_k: float
    activation_A: float
    residual_coupling: float
    note: str = ""


@dataclass(frozen=True)
class StitchEvent:
    cycle_index: int
    entry_anchor_m: Tuple[float, float, float]
    exit_anchor_m: Tuple[float, float, float]
    displacement_m: float
    hidden_path_length_m: float
    unobserved_path_speed_m_per_s: float
    transition_time_s: float
    closure_duration_s: float
    energy_cost_j: float
    momentum_error_kg_ms: float


@dataclass
class ThermalProfile:
    temperature_k: float = 300.0
    max_safe_temp_k: float = 1200.0
    specific_heat_cp: float = 900.0
    surface_area_m2: float = 150.0
    emissivity: float = 0.85
    ambient_temp_k: float = 2.7


@dataclass
class CraftState:
    position: np.ndarray
    velocity: np.ndarray
    mass_eq: float
    length_m: float
    max_tidal_strain: float
    internal_energy: float
    thermal: ThermalProfile


class TelemetryJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, Enum):
            return obj.name
        return super().default(obj)


class TransactionalFieldEngine:
    ALLOWED_TRANSITIONS: Dict[SystemState, Set[SystemState]] = {
        SystemState.IDLE: {SystemState.CONTAINMENT_ACTIVE, SystemState.ABORT},
        SystemState.CONTAINMENT_ACTIVE: {
            SystemState.GRADIENT_SHAPED,
            SystemState.ABORT,
        },
        SystemState.GRADIENT_SHAPED: {
            SystemState.COUPLING_ENGAGED,
            SystemState.ABORT,
        },
        SystemState.COUPLING_ENGAGED: {
            SystemState.FIELD_CLOSURE,
            SystemState.ABORT,
        },
        SystemState.FIELD_CLOSURE: {
            SystemState.IDLE,
            SystemState.ABORT,
        },
        SystemState.ABORT: {SystemState.IDLE},
    }

    def __init__(
        self,
        craft: CraftState,
        *,
        sigma: float = 5.0,
        containment_integrity: float = 0.98,
        energy_cost_base_j: float = 1.5e10,
        energy_cost_per_visible_meter_j: float = 1.0e6,
        momentum_tolerance_kg_ms: float = 1.0e-4,
        residual_tolerance: float = 1.0e-6,
        residual_decay_rate_per_s: float = 50.0,
        closure_steps: int = 10,
    ) -> None:
        self.craft = craft
        self.sigma = float(sigma)
        self.containment_integrity = float(containment_integrity)
        self.energy_cost_base_j = float(energy_cost_base_j)
        self.energy_cost_per_visible_meter_j = float(
            energy_cost_per_visible_meter_j
        )
        self.momentum_tolerance_kg_ms = float(momentum_tolerance_kg_ms)
        self.residual_tolerance = float(residual_tolerance)
        self.residual_decay_rate_per_s = float(residual_decay_rate_per_s)
        self.closure_steps = int(closure_steps)

        self.state = SystemState.IDLE
        self.activation_A = 0.0
        self.residual_coupling = 0.0
        self.last_momentum_error_kg_ms = 0.0

        self.run_start_monotonic = monotonic()
        self.run_start_utc = datetime.now(timezone.utc).isoformat()

        self.telemetry: List[TelemetryRecord] = []
        self.stitch_events: List[StitchEvent] = []
        self.last_cycle_parameters: Dict[str, Any] = {}

        self.validate_craft()
        self.validate_engine()
        self.log_telemetry(note="Simulation initialized")

    @staticmethod
    def _vector3(value: np.ndarray | Tuple[float, float, float]) -> np.ndarray:
        result = np.asarray(value, dtype=float)
        if result.shape != (3,) or not np.all(np.isfinite(result)):
            raise ValueError("Expected a vector containing three finite values.")
        return result

    @staticmethod
    def _tuple3(value: np.ndarray) -> Tuple[float, float, float]:
        vector = np.asarray(value, dtype=float).reshape(3)
        return (float(vector[0]), float(vector[1]), float(vector[2]))

    def validate_craft(self) -> None:
        c = self.craft
        c.position = self._vector3(c.position).copy()
        c.velocity = self._vector3(c.velocity).copy()

        positive_values = {
            "mass_eq": c.mass_eq,
            "length_m": c.length_m,
            "max_tidal_strain": c.max_tidal_strain,
        }
        for name, value in positive_values.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero.")

        if not math.isfinite(c.internal_energy) or c.internal_energy < 0:
            raise ValueError("internal_energy must be finite and non-negative.")

        th = c.thermal
        thermal_positive = {
            "temperature_k": th.temperature_k,
            "max_safe_temp_k": th.max_safe_temp_k,
            "specific_heat_cp": th.specific_heat_cp,
            "surface_area_m2": th.surface_area_m2,
        }
        for name, value in thermal_positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"thermal.{name} must be finite and positive.")

        if not math.isfinite(th.ambient_temp_k) or th.ambient_temp_k < 0:
            raise ValueError(
                "thermal.ambient_temp_k must be finite and non-negative."
            )
        if not math.isfinite(th.emissivity) or not 0.0 <= th.emissivity <= 1.0:
            raise ValueError("thermal.emissivity must be within [0, 1].")
        if th.temperature_k >= th.max_safe_temp_k:
            raise ValueError(
                "Initial temperature must be below max_safe_temp_k."
            )

    def validate_engine(self) -> None:
        positive = {
            "sigma": self.sigma,
            "energy_cost_base_j": self.energy_cost_base_j,
            "momentum_tolerance_kg_ms": self.momentum_tolerance_kg_ms,
            "residual_tolerance": self.residual_tolerance,
            "residual_decay_rate_per_s": self.residual_decay_rate_per_s,
        }
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero.")

        if (
            not math.isfinite(self.energy_cost_per_visible_meter_j)
            or self.energy_cost_per_visible_meter_j < 0
        ):
            raise ValueError(
                "energy_cost_per_visible_meter_j must be finite and non-negative."
            )
        if (
            not math.isfinite(self.containment_integrity)
            or not 0.0 <= self.containment_integrity <= 1.0
        ):
            raise ValueError("containment_integrity must be within [0, 1].")
        if self.closure_steps <= 0:
            raise ValueError("closure_steps must be greater than zero.")

    def _validate_parameters(
        self,
        target: np.ndarray,
        transition_time_s: float,
        hidden_path_length_m: Optional[float],
        gradient_per_m: float,
        cooling_dwell_s: float,
        closure_duration_s: float,
        impulse_applied_kg_ms: np.ndarray,
        exit_velocity_m_per_s: Optional[np.ndarray],
    ) -> Tuple[np.ndarray, float, float, float, float, np.ndarray, Optional[np.ndarray]]:
        target = self._vector3(target)

        scalar_checks = {
            "transition_time_s": transition_time_s,
            "gradient_per_m": gradient_per_m,
            "cooling_dwell_s": cooling_dwell_s,
            "closure_duration_s": closure_duration_s,
        }
        for name, value in scalar_checks.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite.")

        if transition_time_s <= 0:
            raise ValueError("Transition time must be > 0.")
        if cooling_dwell_s <= 0:
            raise ValueError("Cooling dwell must be > 0.")
        if closure_duration_s <= 0:
            raise ValueError("Closure duration must be > 0.")

        if hidden_path_length_m is not None:
            if not math.isfinite(hidden_path_length_m):
                raise ValueError("Hidden path length must be finite.")
            if hidden_path_length_m < 0:
                raise ValueError("Hidden path length cannot be negative.")

        impulse = self._vector3(impulse_applied_kg_ms)

        exit_velocity = None
        if exit_velocity_m_per_s is not None:
            exit_velocity = self._vector3(exit_velocity_m_per_s)

        if self.craft.internal_energy <= 0:
            raise ValueError("Internal energy nonpositive.")
        if self.state is not SystemState.IDLE:
            raise ValueError("Engine must begin cycle from IDLE state.")

        self.validate_craft()
        self.validate_engine()

        return (
            target,
            float(transition_time_s),
            float(hidden_path_length_m)
            if hidden_path_length_m is not None
            else math.nan,
            float(gradient_per_m),
            float(cooling_dwell_s),
            impulse,
            exit_velocity,
        )

    def _set_state_without_log(self, new_state: SystemState) -> None:
        allowed = self.ALLOWED_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise RuntimeError(
                f"Illegal state transition: "
                f"{self.state.name} -> {new_state.name}"
            )
        self.state = new_state

    def set_state(self, new_state: SystemState, *, note: str = "") -> None:
        self._set_state_without_log(new_state)
        self.log_telemetry(note=note)

    def log_telemetry(
        self,
        *,
        note: str = "",
        momentum_error_kg_ms: Optional[float] = None,
    ) -> None:
        momentum = self.craft.mass_eq * self.craft.velocity
        error = (
            self.last_momentum_error_kg_ms
            if momentum_error_kg_ms is None
            else float(momentum_error_kg_ms)
        )
        record = TelemetryRecord(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            elapsed_s=float(monotonic() - self.run_start_monotonic),
            state=self.state.name,
            energy_j=float(self.craft.internal_energy),
            momentum_kg_ms=self._tuple3(momentum),
            momentum_error_kg_ms=error,
            position_m=self._tuple3(self.craft.position),
            velocity_m_per_s=self._tuple3(self.craft.velocity),
            temperature_k=float(self.craft.thermal.temperature_k),
            activation_A=float(self.activation_A),
            residual_coupling=float(self.residual_coupling),
            note=note,
        )
        self.telemetry.append(record)

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "position": self.craft.position.copy(),
            "velocity": self.craft.velocity.copy(),
            "internal_energy": float(self.craft.internal_energy),
            "temperature_k": float(self.craft.thermal.temperature_k),
            "activation_A": float(self.activation_A),
            "residual_coupling": float(self.residual_coupling),
            "last_momentum_error_kg_ms": float(
                self.last_momentum_error_kg_ms
            ),
            "stitch_events": list(self.stitch_events),
            "telemetry": list(self.telemetry),
            "last_cycle_parameters": dict(self.last_cycle_parameters),
        }

    def _restore(self, snapshot: Dict[str, Any]) -> None:
        self.state = snapshot["state"]
        self.craft.position = snapshot["position"].copy()
        self.craft.velocity = snapshot["velocity"].copy()
        self.craft.internal_energy = snapshot["internal_energy"]
        self.craft.thermal.temperature_k = snapshot["temperature_k"]
        self.activation_A = snapshot["activation_A"]
        self.residual_coupling = snapshot["residual_coupling"]
        self.last_momentum_error_kg_ms = snapshot[
            "last_momentum_error_kg_ms"
        ]
        self.stitch_events = list(snapshot["stitch_events"])
        self.telemetry = list(snapshot["telemetry"])
        self.last_cycle_parameters = dict(
            snapshot["last_cycle_parameters"]
        )

    def abort(self, reason: str) -> bool:
        self.activation_A = 0.0
        self.residual_coupling = 0.0
        if self.state is SystemState.ABORT:
            self.log_telemetry(note=f"ABORT: {reason}")
            return False
        if SystemState.ABORT not in self.ALLOWED_TRANSITIONS[self.state]:
            self.state = SystemState.ABORT
            self.log_telemetry(note=f"ABORT: {reason}")
            return False
        self.set_state(SystemState.ABORT, note=f"ABORT: {reason}")
        return False

    def reset_from_abort(self) -> None:
        if self.state is not SystemState.ABORT:
            raise RuntimeError("Engine is not in ABORT state.")
        self.set_state(SystemState.IDLE, note="Abort cleared")

    def compute_chi(
        self,
        points: np.ndarray,
        *,
        amplitude: Optional[float] = None,
    ) -> np.ndarray:
        point_array = np.asarray(points, dtype=float)
        if point_array.shape[-1] != 3 or not np.all(np.isfinite(point_array)):
            raise ValueError(
                "points must end in a dimension of three finite coordinates."
            )
        A = self.activation_A if amplitude is None else float(amplitude)
        if not math.isfinite(A):
            raise ValueError("Amplitude must be finite.")
        distances_squared = np.sum(
            (point_array - self.craft.position) ** 2,
            axis=-1,
        )
        return A * np.exp(
            -distances_squared / (2.0 * self.sigma**2)
        )

    def _temperature_after_leakage(
        self,
        initial_temperature_k: float,
        source_energy_j: float,
    ) -> float:
        leakage_j = source_energy_j * (
            1.0 - self.containment_integrity
        )
        heat_capacity_j_per_k = (
            self.craft.mass_eq
            * self.craft.thermal.specific_heat_cp
        )
        return initial_temperature_k + leakage_j / heat_capacity_j_per_k

    def _predict_radiative_cooling(
        self,
        initial_temperature_k: float,
        duration_s: float,
    ) -> Tuple[float, float, float]:
        th = self.craft.thermal
        power_w = (
            th.emissivity
            * SIGMA_SB
            * th.surface_area_m2
            * (
                initial_temperature_k**4
                - th.ambient_temp_k**4
            )
        )
        heat_lost_j = max(0.0, power_w * duration_s)
        heat_capacity_j_per_k = (
            self.craft.mass_eq * th.specific_heat_cp
        )
        final_temperature_k = max(
            th.ambient_temp_k,
            initial_temperature_k
            - heat_lost_j / heat_capacity_j_per_k,
        )
        return final_temperature_k, power_w, heat_lost_j

    def execute_stitch_cycle(
        self,
        target_coords: np.ndarray,
        *,
        gradient_per_m: float = 2.5,
        transition_time_s: float = 0.01,
        hidden_path_length_m: Optional[float] = None,
        impulse_applied_kg_ms: Optional[np.ndarray] = None,
        exit_velocity_m_per_s: Optional[np.ndarray] = None,
        cooling_dwell_s: float = 10.0,
        closure_duration_s: float = 0.30,
    ) -> bool:
        snapshot = self._snapshot()
        try:
            impulse_input = (
                np.zeros(3, dtype=float)
                if impulse_applied_kg_ms is None
                else np.asarray(impulse_applied_kg_ms, dtype=float)
            )
            (
                target,
                transition_time_s,
                hidden_path_or_nan,
                gradient_per_m,
                cooling_dwell_s,
                impulse,
                exit_velocity,
            ) = self._validate_parameters(
                np.asarray(target_coords, dtype=float),
                transition_time_s,
                hidden_path_length_m,
                gradient_per_m,
                cooling_dwell_s,
                closure_duration_s,
                impulse_input,
                exit_velocity_m_per_s,
            )

            start_position = self.craft.position.copy()
            displacement = target - start_position
            visible_distance_m = float(np.linalg.norm(displacement))
            hidden_path_m = (
                visible_distance_m
                if math.isnan(hidden_path_or_nan)
                else hidden_path_or_nan
            )
            local_speed_m_per_s = (
                hidden_path_m / transition_time_s
            )
            if local_speed_m_per_s > C_LIGHT:
                raise ValueError(
                    f"Local manifold transit speed "
                    f"{local_speed_m_per_s:.6e} m/s exceeds c."
                )

            tidal_delta_a = (
                abs(gradient_per_m) * self.craft.length_m
            )
            if tidal_delta_a > self.craft.max_tidal_strain:
                raise ValueError(
                    f"Tidal differential {tidal_delta_a:.6f} m/s^2 "
                    f"exceeds hull limit."
                )

            energy_required_j = (
                self.energy_cost_base_j
                + visible_distance_m
                * self.energy_cost_per_visible_meter_j
            )
            predicted_energy_j = (
                self.craft.internal_energy - energy_required_j
            )
            if predicted_energy_j < 0:
                raise ValueError("Energy negative.")

            stage1_source_energy_j = (
                self.energy_cost_base_j * 0.1
            )
            stage3_source_energy_j = energy_required_j * 0.9

            predicted_stage1_temperature_k = (
                self._temperature_after_leakage(
                    self.craft.thermal.temperature_k,
                    stage1_source_energy_j,
                )
            )
            if (
                predicted_stage1_temperature_k
                >= self.craft.thermal.max_safe_temp_k
            ):
                raise ValueError(
                    "Stage 1 predicted temperature exceeds thermal limit."
                )

            predicted_stage3_temperature_k = (
                self._temperature_after_leakage(
                    predicted_stage1_temperature_k,
                    stage3_source_energy_j,
                )
            )
            if (
                predicted_stage3_temperature_k
                >= self.craft.thermal.max_safe_temp_k
            ):
                raise ValueError(
                    "Stage 3 predicted temperature exceeds thermal limit."
                )

            (
                predicted_final_temperature_k,
                predicted_radiative_power_w,
                predicted_heat_lost_j,
            ) = self._predict_radiative_cooling(
                predicted_stage3_temperature_k,
                cooling_dwell_s,
            )

            p_before = self.craft.mass_eq * self.craft.velocity
            p_expected = p_before + impulse
            predicted_velocity = (
                p_expected / self.craft.mass_eq
                if exit_velocity is None
                else exit_velocity.copy()
            )
            p_after = self.craft.mass_eq * predicted_velocity
            momentum_error = float(
                np.linalg.norm(p_after - p_expected)
            )
            if momentum_error > self.momentum_tolerance_kg_ms:
                raise ValueError(
                    f"Momentum error {momentum_error:.6e} > tolerance."
                )

            closure_dt_s = (
                closure_duration_s / self.closure_steps
            )
            predicted_residual_samples: List[float] = []
            predicted_residual = 1.0
            for _ in range(self.closure_steps):
                predicted_residual *= math.exp(
                    -self.residual_decay_rate_per_s
                    * closure_dt_s
                )
                predicted_residual_samples.append(
                    float(predicted_residual)
                )

            if predicted_residual > self.residual_tolerance:
                raise ValueError(
                    f"Residual {predicted_residual:.6e} "
                    f"> tolerance."
                )

            self.last_cycle_parameters = {
                "target_coords_m": self._tuple3(target),
                "transition_time_s": transition_time_s,
                "hidden_path_length_m": hidden_path_m,
                "gradient_per_m": gradient_per_m,
                "cooling_dwell_s": cooling_dwell_s,
                "closure_duration_s": closure_duration_s,
                "closure_steps": self.closure_steps,
                "impulse_applied_kg_ms": self._tuple3(impulse),
                "exit_velocity_m_per_s": self._tuple3(
                    predicted_velocity
                ),
            }

            self._set_state_without_log(
                SystemState.CONTAINMENT_ACTIVE
            )
            self.craft.thermal.temperature_k = (
                predicted_stage1_temperature_k
            )
            self.log_telemetry(
                note="Containment established; Stage 1 heat committed"
            )

            self._set_state_without_log(
                SystemState.GRADIENT_SHAPED
            )
            self.log_telemetry(
                note=(
                    f"Gradient shaped; tidal differential "
                    f"{tidal_delta_a:.6f} m/s^2"
                )
            )

            self.activation_A = 1.0
            self.residual_coupling = 1.0
            self.craft.internal_energy = predicted_energy_j
            self.craft.position = target.copy()
            self.craft.velocity = predicted_velocity.copy()
            self.craft.thermal.temperature_k = (
                predicted_stage3_temperature_k
            )
            self.last_momentum_error_kg_ms = momentum_error
            self._set_state_without_log(
                SystemState.COUPLING_ENGAGED
            )
            self.log_telemetry(
                note="Coupling engaged; transition committed",
                momentum_error_kg_ms=momentum_error,
            )

            self.activation_A = 0.0
            self._set_state_without_log(
                SystemState.FIELD_CLOSURE
            )
            self.log_telemetry(
                note="Field closure started",
                momentum_error_kg_ms=momentum_error,
            )

            for index, residual in enumerate(
                predicted_residual_samples,
                start=1,
            ):
                self.residual_coupling = residual
                self.log_telemetry(
                    note=(
                        f"Closure sample "
                        f"{index}/{self.closure_steps}"
                    ),
                    momentum_error_kg_ms=momentum_error,
                )

            self.craft.thermal.temperature_k = (
                predicted_final_temperature_k
            )
            self.log_telemetry(
                note=(
                    f"Radiative cooling committed; "
                    f"power={predicted_radiative_power_w:.6e} W; "
                    f"heat_lost={predicted_heat_lost_j:.6e} J"
                ),
                momentum_error_kg_ms=momentum_error,
            )

            event = StitchEvent(
                cycle_index=len(self.stitch_events) + 1,
                entry_anchor_m=self._tuple3(start_position),
                exit_anchor_m=self._tuple3(target),
                displacement_m=visible_distance_m,
                hidden_path_length_m=hidden_path_m,
                unobserved_path_speed_m_per_s=local_speed_m_per_s,
                transition_time_s=transition_time_s,
                closure_duration_s=closure_duration_s,
                energy_cost_j=energy_required_j,
                momentum_error_kg_ms=momentum_error,
            )
            self.stitch_events.append(event)

            self._set_state_without_log(SystemState.IDLE)
            self.log_telemetry(
                note="Cycle committed",
                momentum_error_kg_ms=momentum_error,
            )
            return True

        except Exception as exc:
            self._restore(snapshot)
            return self.abort(str(exc))

    def build_export_payload(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "engine_version": "4.0.0-transactional",
                "run_start_utc": self.run_start_utc,
                "exported_at_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "total_records_logged": len(self.telemetry),
                "completed_stitch_cycles": len(self.stitch_events),
            },
            "simulation_config": {
                "sigma_m": self.sigma,
                "containment_integrity": self.containment_integrity,
                "energy_cost_base_j": self.energy_cost_base_j,
                "energy_cost_per_visible_meter_j": (
                    self.energy_cost_per_visible_meter_j
                ),
                "residual_tolerance": self.residual_tolerance,
                "residual_decay_rate_per_s": (
                    self.residual_decay_rate_per_s
                ),
                "closure_steps": self.closure_steps,
                "speed_of_light_m_per_s": C_LIGHT,
                "momentum_tolerance_kg_ms": (
                    self.momentum_tolerance_kg_ms
                ),
                "thermal_profile": asdict(self.craft.thermal),
                "last_cycle_parameters": self.last_cycle_parameters,
            },
            "craft_final_state": {
                "position_m": self._tuple3(self.craft.position),
                "velocity_m_per_s": self._tuple3(
                    self.craft.velocity
                ),
                "remaining_energy_j": float(
                    self.craft.internal_energy
                ),
                "hull_temperature_k": float(
                    self.craft.thermal.temperature_k
                ),
                "system_status": self.state.name,
                "activation_A": float(self.activation_A),
                "residual_coupling": float(
                    self.residual_coupling
                ),
            },
            "stitch_events": [
                asdict(event) for event in self.stitch_events
            ],
            "telemetry_ledger": [
                asdict(record) for record in self.telemetry
            ],
        }

    def export_telemetry_to_json(
        self,
        filename: str | os.PathLike[str] = "flight_telemetry_ledger.json",
    ) -> str:
        destination = Path(filename).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.build_export_payload()

        temporary_path: Optional[str] = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                delete=False,
                prefix=f".{destination.name}.",
                suffix=".tmp",
            ) as temp:
                temporary_path = temp.name
                json.dump(
                    payload,
                    temp,
                    cls=TelemetryJSONEncoder,
                    indent=2,
                    allow_nan=False,
                )
                temp.flush()
                os.fsync(temp.fileno())

            os.replace(temporary_path, destination)
            temporary_path = None
            return str(destination)
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass


def build_demo_engine() -> TransactionalFieldEngine:
    craft = CraftState(
        position=np.array([0.0, 0.0, 0.0]),
        velocity=np.array([100.0, 0.0, 0.0]),
        mass_eq=15_000.0,
        length_m=12.0,
        max_tidal_strain=40.0,
        internal_energy=5.0e11,
        thermal=ThermalProfile(
            temperature_k=295.0,
            max_safe_temp_k=950.0,
        ),
    )
    return TransactionalFieldEngine(craft)


if __name__ == "__main__":
    engine = build_demo_engine()
    waypoints = [
        np.array([2000.0, 1000.0, 100.0]),
        np.array([5000.0, 4000.0, 300.0]),
        np.array([9000.0, 5000.0, 200.0]),
        np.array([12000.0, 8000.0, 500.0]),
    ]

    for target in waypoints:
        success = engine.execute_stitch_cycle(
            target,
            gradient_per_m=-2.5,
            transition_time_s=0.01,
            hidden_path_length_m=100.0,
            cooling_dwell_s=10.0,
            closure_duration_s=0.30,
        )
        if not success:
            break

    path = engine.export_telemetry_to_json(
        "flight_telemetry_ledger_v4.json"
    )
    print(path)
