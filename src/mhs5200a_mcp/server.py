#!/usr/bin/env python3
"""
MCP Server for MHS-5200A Signal Generator.

This server provides tools to control MHS-5200A series signal generators
via serial communication, including waveform generation, frequency sweeps,
and arbitrary waveform uploads.
"""

import json
from typing import Optional, Literal, List, Dict, Any, TypeVar, Callable
from functools import wraps
from pathlib import Path
import serial
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP
from mhs5200 import MHS5200, Waveform, SweepMode


# ============================================================
# Constants
# ============================================================
CHANNEL_RANGE: tuple[int, int] = (1, 2)
FREQUENCY_MIN_HZ: float = 0.01
AMPLITUDE_MAX_VPP: float = 15.0
DUTY_CYCLE_MAX: float = 99.9
OFFSET_RANGE: tuple[int, int] = (-120, 120)
PHASE_RANGE: tuple[int, int] = (-180, 180)
SWEEP_TIME_RANGE: tuple[int, int] = (1, 600)
ARB_SLOT_RANGE: tuple[int, int] = (0, 15)
ARB_SAMPLE_COUNT: int = 2048
ARB_SAMPLE_MAX: int = 4095


# ============================================================
# Device State Management
# ============================================================
class DeviceState:
    """Manages MHS-5200A device connection state."""
    
    def __init__(self) -> None:
        self._device: Optional[MHS5200] = None
        self._port: Optional[str] = None
    
    @property
    def is_connected(self) -> bool:
        return self._device is not None
    
    @property
    def port(self) -> Optional[str]:
        return self._port
    
    def connect(self, port: str) -> Dict[str, Any]:
        """Connect to device and return device info."""
        if self._device is not None:
            self._device.close()
        
        self._device = MHS5200(port)
        self._port = port
        return self._device.get_device_info()
    
    def disconnect(self) -> None:
        """Disconnect from device."""
        if self._device is not None:
            self._device.close()
            self._device = None
            self._port = None
    
    def get_device(self) -> MHS5200:
        """Get device instance, raising if not connected."""
        if self._device is None:
            raise DeviceNotConnectedError(
                "Device not connected. Use mhs5200_connect first."
            )
        return self._device


class DeviceNotConnectedError(Exception):
    """Raised when attempting to use device before connecting."""
    pass


# Global device state
_state = DeviceState()


# ============================================================
# MCP Server Setup
# ============================================================
mcp = FastMCP(
    name="mhs5200_mcp",
    instructions="""
Control MHS-5200A signal generator via serial port. 
""",
)

# ============================================================
# Error Handling Utilities
# ============================================================
def format_success(data: Dict[str, Any]) -> str:
    """Format successful response as JSON."""
    return json.dumps({"status": "ok", **data}, indent=2)


def format_error(message: str) -> str:
    """Format error response as JSON."""
    return json.dumps({"status": "error", "message": message}, indent=2)


T = TypeVar('T', bound=Callable[..., str])


def handle_device_errors(func: T) -> T:
    """Decorator to handle common device errors consistently."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> str:
        try:
            return func(*args, **kwargs)
        except DeviceNotConnectedError as e:
            return format_error(str(e))
        except serial.SerialException as e:
            return format_error(f"Serial communication error: {e}")
        except KeyError as e:
            return format_error(f"Invalid value: {e}")
        except ValueError as e:
            return format_error(f"Validation error: {e}")
        except Exception as e:
            return format_error(f"Unexpected error: {type(e).__name__}: {e}")
    return wrapper  # type: ignore


# ============================================================
# Pydantic Base Models
# ============================================================
class MHS5200BaseModel(BaseModel):
    """Base model with common configuration for all inputs."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )


class ChannelParam(MHS5200BaseModel):
    """Base model for channel-specific operations."""
    channel: Literal[1, 2] = Field(
        default=1,
        description="Target channel (1 or 2)"
    )


# ============================================================
# Input Models - Connection
# ============================================================
class ConnectInput(MHS5200BaseModel):
    """Input for device connection."""
    port: str = Field(
        ...,
        description="Serial port name (e.g., 'COM3' on Windows, '/dev/ttyUSB0' on Linux)",
        min_length=1,
        max_length=64
    )


# ============================================================
# Input Models - Channel Parameters
# ============================================================
class FrequencyInput(ChannelParam):
    """Input for setting channel frequency."""
    frequency_hz: float = Field(
        ...,
        description="Frequency in Hz (0.01 to 25,000,000 depending on model)",
        ge=FREQUENCY_MIN_HZ
    )


class AmplitudeInput(ChannelParam):
    """Input for setting channel amplitude."""
    vpp: float = Field(
        ...,
        description="Peak-to-peak voltage in volts (0.0 to 15.0). Attenuation is adjusted automatically.",
        ge=0.0,
        le=AMPLITUDE_MAX_VPP
    )


class WaveformInput(ChannelParam):
    """Input for setting channel waveform type."""
    waveform: str = Field(
        ...,
        description="Waveform type: SINE, SQUARE, TRIANGLE, SAWTOOTH_UP, SAWTOOTH_DOWN, or ARB00-ARB15"
    )
    
    @field_validator('waveform')
    @classmethod
    def validate_waveform(cls, v: str) -> str:
        """Validate waveform name exists."""
        normalized = v.upper().strip()
        try:
            Waveform[normalized]
        except KeyError:
            valid_waveforms = [w.name for w in Waveform]
            raise ValueError(
                f"Invalid waveform '{v}'. Valid options: {', '.join(valid_waveforms)}"
            )
        return normalized


class DutyCycleInput(ChannelParam):
    """Input for setting duty cycle (primarily for square waves)."""
    duty_percent: float = Field(
        ...,
        description="Duty cycle percentage (0.0 to 99.9)",
        ge=0.0,
        le=DUTY_CYCLE_MAX
    )


class OffsetInput(ChannelParam):
    """Input for setting DC offset."""
    offset_percent: float = Field(
        ...,
        description="DC offset percentage (-120 to +120, where 0 is center)",
        ge=OFFSET_RANGE[0],
        le=OFFSET_RANGE[1]
    )


class PhaseInput(MHS5200BaseModel):
    """Input for setting phase relationship between channels."""
    phase_deg: int = Field(
        ...,
        description="Phase offset in degrees (-180 to +180). Positive: CH2 leads CH1, Negative: CH2 lags CH1",
        ge=PHASE_RANGE[0],
        le=PHASE_RANGE[1]
    )


class InvertInput(ChannelParam):
    """Input for inverting waveform output."""
    inverted: bool = Field(
        ...,
        description="True to invert (flip vertically) the waveform output"
    )


# ============================================================
# Input Models - Global Settings
# ============================================================
class OutputControlInput(MHS5200BaseModel):
    """Input for controlling all outputs."""
    enabled: bool = Field(
        ...,
        description="True to enable all outputs, False to disable"
    )


class TrackingInput(MHS5200BaseModel):
    """Input for frequency tracking mode."""
    enabled: bool = Field(
        ...,
        description="True to enable CH2 frequency tracking (follows CH1)"
    )


class PowerAmpInput(MHS5200BaseModel):
    """Input for internal power amplifier control."""
    enabled: bool = Field(
        ...,
        description="True to enable internal power amplifier (model-dependent)"
    )


# ============================================================
# Input Models - Sweep Configuration
# ============================================================
class SweepControlInput(MHS5200BaseModel):
    """Input for controlling sweep state."""
    enabled: bool = Field(
        description="True to start sweep, False to stop sweep"
    )


class SweepConfigInput(MHS5200BaseModel):
    """Input for frequency sweep configuration."""
    start_hz: float = Field(
        ...,
        description="Sweep start frequency in Hz",
        ge=FREQUENCY_MIN_HZ
    )
    stop_hz: float = Field(
        ...,
        description="Sweep stop frequency in Hz",
        ge=FREQUENCY_MIN_HZ
    )
    time_sec: int = Field(
        ...,
        description="Sweep duration in seconds (1 to 600)",
        ge=SWEEP_TIME_RANGE[0],
        le=SWEEP_TIME_RANGE[1]
    )
    mode: Literal["LINEAR", "LOG"] = Field(
        default="LINEAR",
        description="Sweep mode: LINEAR or LOG (logarithmic)"
    )
    channel: Literal[1, 2] = Field(
        default=1,
        description="Target channel for sweep (1 or 2)"
    )


# ============================================================
# Input Models - Arbitrary Waveform
# ============================================================
class ArbWaveformFileInput(MHS5200BaseModel):
    """Input for uploading arbitrary waveform data from file."""
    arb_index: int = Field(
        ...,
        description="Arbitrary waveform memory slot (0 to 15)",
        ge=ARB_SLOT_RANGE[0],
        le=ARB_SLOT_RANGE[1]
    )
    filepath: str = Field(
        ...,
        description="Path to file with 2048 samples. Formats: JSON array [0,100,...] or text (one integer 0-4095 per line)",
        min_length=1
    )


# ============================================================
# Helper Functions
# ============================================================
def parse_waveform_samples(filepath: str) -> List[int]:
    """
    Parse waveform samples from file.
    
    Args:
        filepath: Path to file containing 2048 integer samples (0-4095).
                  Supports JSON array or one-value-per-line text format.
    
    Returns:
        List of 2048 integer samples.
    
    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If sample count or values are invalid.
        json.JSONDecodeError: If JSON format is invalid.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    content = path.read_text().strip()
    
    # Detect format and parse
    if content.startswith('['):
        samples = json.loads(content)
    else:
        samples = [int(line.strip()) for line in content.splitlines() if line.strip()]
    
    # Validate
    if len(samples) != ARB_SAMPLE_COUNT:
        raise ValueError(f"Expected {ARB_SAMPLE_COUNT} samples, got {len(samples)}")
    
    if not all(isinstance(s, int) and 0 <= s <= ARB_SAMPLE_MAX for s in samples):
        raise ValueError(f"All samples must be integers in range 0-{ARB_SAMPLE_MAX}")
    
    return samples


# ============================================================
# MCP Tools - Connection Management
# ============================================================
@mcp.tool(
    name="mhs5200_connect",
    annotations={
        "title": "Connect to MHS-5200A",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_connect(params: ConnectInput) -> str:
    """
    Connect to MHS-5200A signal generator via serial port.
    
    This must be called before using any other mhs5200_* tools.
    If already connected, the existing connection is closed first.
    
    Args:
        params: Connection parameters containing:
            - port (str): Serial port name (e.g., 'COM3', '/dev/ttyUSB0')
    
    Returns:
        JSON with connection status and device information:
        {
            "status": "ok",
            "model": "5225A",
            "serial": "1234567890"
        }
    """
    info = _state.connect(params.port)
    return json.dumps({"status": "connected", **info}, indent=2)


@mcp.tool(
    name="mhs5200_disconnect",
    annotations={
        "title": "Disconnect from MHS-5200A",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
def mhs5200_disconnect() -> str:
    """
    Disconnect from the MHS-5200A signal generator.
    
    Safe to call even if not connected.
    
    Returns:
        JSON with disconnection status:
        {"status": "disconnected"} or {"status": "not_connected"}
    """
    if not _state.is_connected:
        return json.dumps({"status": "not_connected"}, indent=2)
    
    _state.disconnect()
    return json.dumps({"status": "disconnected"}, indent=2)


@mcp.tool(
    name="mhs5200_get_status",
    annotations={
        "title": "Get Device Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_get_status() -> str:
    """
    Get complete status of all channels and device settings.
    
    Returns:
        JSON with full device status including:
        - Channel 1 & 2: frequency, amplitude, waveform, duty cycle, offset, phase
        - Global: output state, tracking mode, power amp state
    """
    dev = _state.get_device()
    return json.dumps(dev.get_all_status(), indent=2)


# ============================================================
# MCP Tools - Channel Configuration
# ============================================================
@mcp.tool(
    name="mhs5200_set_frequency",
    annotations={
        "title": "Set Channel Frequency",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_frequency(params: FrequencyInput) -> str:
    """
    Set the output frequency for a channel.
    
    Args:
        params: Frequency parameters containing:
            - channel (1 or 2): Target channel
            - frequency_hz (float): Frequency in Hz (0.01 to max supported by model)
    
    Returns:
        JSON confirming the new frequency setting.
    """
    dev = _state.get_device()
    dev.set_frequency(params.channel, params.frequency_hz)
    return format_success({
        "channel": params.channel,
        "frequency_hz": params.frequency_hz
    })


@mcp.tool(
    name="mhs5200_set_amplitude",
    annotations={
        "title": "Set Channel Amplitude",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_amplitude(params: AmplitudeInput) -> str:
    """
    Set the peak-to-peak voltage for a channel.
    
    Automatically adjusts attenuation setting for optimal output.
    
    Args:
        params: Amplitude parameters containing:
            - channel (1 or 2): Target channel
            - vpp (float): Peak-to-peak voltage (0.0 to 15.0 V)
    
    Returns:
        JSON confirming the new amplitude setting.
    """
    dev = _state.get_device()
    dev.set_amplitude_auto(params.channel, params.vpp)
    return format_success({
        "channel": params.channel,
        "vpp": params.vpp
    })


@mcp.tool(
    name="mhs5200_set_waveform",
    annotations={
        "title": "Set Channel Waveform",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_waveform(params: WaveformInput) -> str:
    """
    Set the waveform type for a channel.
    
    Args:
        params: Waveform parameters containing:
            - channel (1 or 2): Target channel
            - waveform (str): One of SINE, SQUARE, TRIANGLE, SAWTOOTH_UP,
                              SAWTOOTH_DOWN, or ARB00-ARB15 for arbitrary
    
    Returns:
        JSON confirming the new waveform setting.
    """
    dev = _state.get_device()
    wf = Waveform[params.waveform]
    dev.set_waveform(params.channel, wf)
    return format_success({
        "channel": params.channel,
        "waveform": wf.name
    })


@mcp.tool(
    name="mhs5200_set_duty_cycle",
    annotations={
        "title": "Set Duty Cycle",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_duty_cycle(params: DutyCycleInput) -> str:
    """
    Set the duty cycle for a channel (primarily affects square waves).
    
    Args:
        params: Duty cycle parameters containing:
            - channel (1 or 2): Target channel
            - duty_percent (float): Duty cycle (0.0 to 99.9 %)
    
    Returns:
        JSON confirming the new duty cycle setting.
    """
    dev = _state.get_device()
    dev.set_duty_cycle(params.channel, params.duty_percent)
    return format_success({
        "channel": params.channel,
        "duty_percent": params.duty_percent
    })


@mcp.tool(
    name="mhs5200_set_offset",
    annotations={
        "title": "Set DC Offset",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_offset(params: OffsetInput) -> str:
    """
    Set the DC offset for a channel.
    
    The offset is specified as a percentage of half the peak-to-peak amplitude (Vpp/2).
    For example, with a 5Vpp signal:
        - offset_percent = 100 shifts the signal by +2.5V
        - offset_percent = -120 shifts the signal by -3.0V
    
    Formula: DC offset voltage = (Vpp / 2) × (offset_percent / 100)
    
    Args:
        params: Offset parameters containing:
            - channel (1 or 2): Target channel
            - offset_percent (float): Offset as percentage of Vpp/2 (-120 to +120, 0 is center)
    
    Returns:
        JSON confirming the new offset setting.
    """
    dev = _state.get_device()
    dev.set_offset(params.channel, params.offset_percent)
    return format_success({
        "channel": params.channel,
        "offset_percent": params.offset_percent
    })


@mcp.tool(
    name="mhs5200_set_phase",
    annotations={
        "title": "Set Phase Offset",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_phase(params: PhaseInput) -> str:
    """
    Set the phase offset of CH2 relative to CH1.
    
    Args:
        params: Phase parameters containing:
            - phase_deg (int): Phase offset (-180° to +180°)
                               Positive = CH2 leads CH1
                               Negative = CH2 lags CH1
    
    Returns:
        JSON confirming the new phase setting.
    """
    dev = _state.get_device()
    dev.set_phase(params.phase_deg)
    return format_success({"phase_deg": params.phase_deg})


@mcp.tool(
    name="mhs5200_set_invert",
    annotations={
        "title": "Set Waveform Inversion",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_invert(params: InvertInput) -> str:
    """
    Invert (flip vertically) the waveform output for a channel.
    
    Args:
        params: Invert parameters containing:
            - channel (1 or 2): Target channel
            - inverted (bool): True to invert, False for normal
    
    Returns:
        JSON confirming the inversion setting.
    """
    dev = _state.get_device()
    dev.set_invert(params.channel, params.inverted)
    return format_success({
        "channel": params.channel,
        "inverted": params.inverted
    })


# ============================================================
# MCP Tools - Global Settings
# ============================================================
@mcp.tool(
    name="mhs5200_set_output",
    annotations={
        "title": "Enable/Disable Outputs",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_output(params: OutputControlInput) -> str:
    """
    Enable or disable all signal outputs.
    
    Args:
        params: Output control parameters containing:
            - enabled (bool): True to enable outputs, False to disable
    
    Returns:
        JSON confirming the output state.
    """
    dev = _state.get_device()
    dev.set_all_outputs(params.enabled)
    return format_success({"outputs_enabled": params.enabled})


@mcp.tool(
    name="mhs5200_set_tracking",
    annotations={
        "title": "Set Frequency Tracking",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_tracking(params: TrackingInput) -> str:
    """
    Enable or disable frequency tracking mode.
    
    When enabled, CH2 automatically follows CH1's frequency.
    
    Args:
        params: Tracking parameters containing:
            - enabled (bool): True to enable tracking
    
    Returns:
        JSON confirming the tracking mode.
    """
    dev = _state.get_device()
    dev.set_tracking(params.enabled)
    return format_success({"tracking_enabled": params.enabled})


@mcp.tool(
    name="mhs5200_set_power_amp",
    annotations={
        "title": "Set Power Amplifier",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_power_amp(params: PowerAmpInput) -> str:
    """
    Enable or disable the internal power amplifier.
    
    Note: Not all MHS-5200A models have this feature.
    
    Args:
        params: Power amp parameters containing:
            - enabled (bool): True to enable power amplifier
    
    Returns:
        JSON confirming the power amp state.
    """
    dev = _state.get_device()
    dev.set_power_amp(params.enabled)
    return format_success({"power_amp_enabled": params.enabled})


# ============================================================
# MCP Tools - Sweep
# ============================================================
@mcp.tool(
    name="mhs5200_set_sweep",
    annotations={
        "title": "Start/Stop Frequency Sweep",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_set_sweep(params: SweepControlInput) -> str:
    """
    Start or stop the frequency sweep.
    
    Use mhs5200_configure_sweep first to set sweep parameters,
    then use this tool to start/stop the sweep.
    
    Args:
        params: Sweep control parameters containing:
            - enabled (bool): True to start sweep, False to stop sweep
    
    Returns:
        JSON confirming the sweep state.
    """
    dev = _state.get_device()
    dev.set_sweep_enabled(params.enabled)
    return json.dumps({
        "status": "ok",
        "sweep_enabled": params.enabled
    }, indent=2)


@mcp.tool(
    name="mhs5200_configure_sweep",
    annotations={
        "title": "Configure Frequency Sweep",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_configure_sweep(params: SweepConfigInput) -> str:
    """
    Set sweep parameters for a channel. Use mhs5200_set_sweep to start/stop the configured sweep.
    
    Args:
        params: Sweep configuration containing:
            - start_hz (float): Start frequency in Hz
            - stop_hz (float): Stop frequency in Hz
            - time_sec (int): Sweep duration (1-600 seconds)
            - mode (str): "LINEAR" or "LOG"
            - channel (1 or 2): Target channel
    
    Returns:
        JSON confirming sweep configuration and start.
    """
    dev = _state.get_device()
    mode = SweepMode.LINEAR if params.mode == "LINEAR" else SweepMode.LOG
    dev.configure_sweep(
        params.start_hz,
        params.stop_hz,
        params.time_sec,
        mode,
        params.channel
    )
    return json.dumps({
        "status": "sweep_started",
        "config": {
            "start_hz": params.start_hz,
            "stop_hz": params.stop_hz,
            "time_sec": params.time_sec,
            "mode": params.mode,
            "channel": params.channel
        }
    }, indent=2)


# ============================================================
# MCP Tools - Arbitrary Waveform
# ============================================================
@mcp.tool(
    name="mhs5200_upload_arb_waveform",
    annotations={
        "title": "Upload Arbitrary Waveform",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@handle_device_errors
def mhs5200_upload_arb_waveform(params: ArbWaveformFileInput) -> str:
    """
    Upload custom arbitrary waveform data to device memory.
    
    The waveform data must contain exactly 2048 samples, each an integer
    from 0 to 4095 (12-bit resolution). 2048 is the midpoint (zero crossing).
    
    Args:
        params: Upload parameters containing:
            - arb_index (int): Memory slot (0-15, corresponds to ARB00-ARB15)
            - filepath (str): Path to data file
                              JSON format: [0, 100, 200, ...]
                              Text format: one integer per line
    
    Returns:
        JSON confirming upload success with slot number and sample count.
    """
    dev = _state.get_device()
    samples = parse_waveform_samples(params.filepath)
    dev.upload_arbitrary_waveform(params.arb_index, samples)
    return format_success({
        "slot": params.arb_index,
        "samples_uploaded": len(samples)
    })


# ============================================================
# Entry Point
# ============================================================
def main() -> None:
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()