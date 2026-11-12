"""Discrete PI DC-link voltage controller.

    e[k]   = Vref[k] - v_meas[k]
    u[k]   = Kp * e[k] + x_I[k]                       (parallel form)
    x_I[k+1] = x_I[k] + Ki * Ts * e[k]                (forward-Euler integrator)
    u_sat  = clip(u, -I_max, I_max)                   (grid current reference i_d*)

Anti-windup: conditional integration (clamping). The integrator is frozen
whenever the output is saturated AND the error would push it further into
saturation (Astrom & Hagglund, Advanced PID Control, 2006, ch. 3).

Bumpless transfer: when gains change, the integrator state is re-initialised
so that the controller output is continuous: x_I <- u_prev - Kp_new * e.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PIGains:
    Kp: float  # A / V
    Ki: float  # A / (V s)

    def __post_init__(self) -> None:
        if not (self.Kp > 0 and self.Ki > 0):
            raise ValueError(f"PI gains must be positive, got Kp={self.Kp}, Ki={self.Ki}")

    def as_tuple(self) -> tuple[float, float]:
        return (self.Kp, self.Ki)


class PIController:
    """Sampled PI with output saturation, clamping anti-windup and bumpless gain change."""

    def __init__(self, gains: PIGains, Ts: float, u_min: float, u_max: float) -> None:
        if Ts <= 0 or u_min >= u_max:
            raise ValueError("invalid sampling period or output limits")
        self.gains = gains
        self.Ts = Ts
        self.u_min, self.u_max = u_min, u_max
        self.x_i = 0.0
        self.u_prev = 0.0
        self.e_prev = 0.0
        self.saturated = False

    def reset(self, u0: float = 0.0, e0: float = 0.0) -> None:
        """Initialise for a steady state with output ``u0`` and error ``e0``."""
        self.x_i = u0 - self.gains.Kp * e0
        self.u_prev = u0
        self.e_prev = e0
        self.saturated = False

    def update(self, ref: float, meas: float) -> float:
        Kp, Ki = self.gains.Kp, self.gains.Ki
        e = ref - meas
        u_unsat = Kp * e + self.x_i
        u = min(max(u_unsat, self.u_min), self.u_max)
        self.saturated = u != u_unsat
        # clamping anti-windup: integrate unless saturated and error drives further in
        winding = (u_unsat > self.u_max and e > 0) or (u_unsat < self.u_min and e < 0)
        if not winding:
            self.x_i += Ki * self.Ts * e
        # keep integrator itself inside the actuator range
        self.x_i = min(max(self.x_i, self.u_min), self.u_max)
        self.u_prev, self.e_prev = u, e
        return u

    def set_gains(self, gains: PIGains, bumpless: bool = True) -> None:
        """Change gains; with ``bumpless`` the next output continues from u_prev."""
        if bumpless:
            self.x_i = self.u_prev - gains.Kp * self.e_prev
            self.x_i = min(max(self.x_i, self.u_min), self.u_max)
        self.gains = gains

    def state(self) -> dict[str, float | bool]:
        return {"Kp": self.gains.Kp, "Ki": self.gains.Ki, "x_i": self.x_i,
                "u": self.u_prev, "e": self.e_prev, "saturated": self.saturated}
