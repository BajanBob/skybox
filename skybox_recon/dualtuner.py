"""Dual-tuner control: two Linux DVB adapters driven independently.

Tuner A and Tuner B each get their own adapter, LNB, DiSEqC port, frequency,
polarization and symbol rate. The coordinator refuses to start unless the user
confirms the two adapters have separate RF inputs (two LNB cables or a
dual-output LNB); software cannot create a second tuner from one.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from .dvb import TuneParams, dvbv5_conf, dvbv5_zap_cmd, list_dvb_adapters
from .tuner_topology import DualTunerCoordinator, TunerCapabilities, TunerSession, TunerState


class DualTunerController:
    def __init__(self, adapter_a: int, adapter_b: int, separate_rf_inputs: bool) -> None:
        if adapter_a == adapter_b:
            raise ValueError("tuner A and tuner B must use different DVB adapters")
        present = list_dvb_adapters()
        missing = [a for a in (adapter_a, adapter_b) if a not in present]
        if missing:
            raise ValueError(f"DVB adapter(s) not found: {missing} (present: {present or 'none'})")
        caps = TunerCapabilities("linux-dvbv5", separate_rf_inputs, blind_scan=False, ts_output=True)
        self.adapters = {"A": adapter_a, "B": adapter_b}
        self.coord = DualTunerCoordinator(TunerSession("A", caps), TunerSession("B", caps))
        self.procs: dict[str, subprocess.Popen] = {}
        self.outputs: dict[str, str] = {}

    def tune(self, tuner: str, params: TuneParams, task: str, lnb: str = "UNIVERSAL",
             record_to: str | None = None) -> list[str]:
        self.stop(tuner)
        session = self.coord.tuners[tuner]
        session.frequency_khz, session.symbol_rate = params.freq_khz, params.sr
        session.polarization, session.modulation = params.pol, params.mod
        session.validate()
        self.coord.assign(tuner, task)
        conf = os.path.join(tempfile.gettempdir(), f"skybox-tuner-{tuner}.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write(dvbv5_conf(params))
        out = record_to or os.path.join(tempfile.gettempdir(), f"skybox-tuner-{tuner}.ts")
        cmd = dvbv5_zap_cmd(conf, params, adapter=self.adapters[tuner], lnb=lnb, out=out)
        cmd.insert(1, "-P")   # all PIDs, so Services/PIDs can read PAT/PMT/SDT/NIT
        self.procs[tuner] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True)
        self.outputs[tuner] = out
        session.state = TunerState.TUNING
        return cmd

    def poll(self) -> dict[str, dict[str, object]]:
        for tuner, proc in list(self.procs.items()):
            s = self.coord.tuners[tuner]
            if proc.poll() is not None:
                s.state = TunerState.ERROR if proc.returncode else TunerState.IDLE
                s.locked = False
            elif self.outputs.get(tuner) and os.path.exists(self.outputs[tuner]) and os.path.getsize(self.outputs[tuner]) > 0:
                s.state, s.locked = TunerState.LOCKED, True
        snap = self.coord.snapshot()
        for k, v in snap.items():
            v["adapter"] = self.adapters[k]
            v["output"] = self.outputs.get(k)
        return snap

    def stop(self, tuner: str) -> None:
        proc = self.procs.pop(tuner, None)
        if proc and proc.poll() is None:
            proc.terminate()
        s = self.coord.tuners[tuner]
        s.state, s.locked = TunerState.IDLE, False

    def stop_all(self) -> None:
        for t in ("A", "B"):
            self.stop(t)
