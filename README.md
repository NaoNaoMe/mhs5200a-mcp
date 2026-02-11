# MHS-5200A MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for controlling MHS-5200A series signal generators (and compatible models such as MHS-5200P / MHS-5225A) via a serial connection.

## Features

- **Full Channel Control**: Set frequency, amplitude, duty cycle, DC offset, phase, and waveform for both channels independently.
- **Waveform Selection**: Support for Sine, Square, Triangle, Sawtooth, and Arbitrary waveforms.
- **Frequency Sweep**: Configure and run linear or logarithmic frequency sweeps.
- **Arbitrary Waveforms**: Upload custom waveform data (2 048 points) to any of the 16 memory slots.
- **Advanced Features**: Control channel tracking, output inversion, and the internal power amplifier (if equipped).

## Requirements

- Python >= 3.11


## Installation

Using `uv` (recommended):

```bash
uv pip install mhs5200a-mcp
```

Or via `pip`:

```bash
pip install mhs5200a-mcp
```

Or from source:

```bash
git clone https://github.com/NaoNaoMe/mhs5200a-mcp.git
cd mhs5200a-mcp
uv sync
```

## Configuration

### Claude Desktop Config

Add the server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mhs5200-mcp": {
      "command": "uvx",
      "args": [
        "mhs5200a-mcp"
      ]
    }
  }
}
```

## Tools Overview

### Connection

- `mhs5200_connect`: Connect to the device via serial port (e.g., `COM3`, `/dev/ttyUSB0`).
- `mhs5200_disconnect`: Disconnect from the device.
- `mhs5200_get_status`: Get current settings for all channels.

### Channel Control

- `mhs5200_set_frequency`: Set frequency in Hz (0.01 Hz – 25 MHz).
- `mhs5200_set_amplitude`: Set amplitude in volts peak-to-peak (0–15 V).
- `mhs5200_set_waveform`: Select waveform (`SINE`, `SQUARE`, `TRIANGLE`, `SAWTOOTH_UP`, `SAWTOOTH_DOWN`, `ARB00`–`ARB15`).
- `mhs5200_set_duty_cycle`: Set duty cycle percentage (0–99.9 %).
- `mhs5200_set_offset`: Set DC offset percentage.
- `mhs5200_set_phase`: Set phase offset between channels.
- `mhs5200_set_invert`: Invert waveform output.

### Global Settings

- `mhs5200_set_output`: Enable or disable all outputs.
- `mhs5200_set_tracking`: Enable channel tracking (CH2 follows CH1).
- `mhs5200_set_power_amp`: Enable the internal power amplifier (if supported).

### Sweeps & Arbitrary Waveforms

- `mhs5200_configure_sweep`: Configure frequency sweep parameters (start/stop frequency, time, mode).
- `mhs5200_set_sweep`: Start or stop the configured sweep.
- `mhs5200_upload_arb_waveform`: Upload custom waveform data from a file.

## Example Workflow

1. **Connect**: Call `mhs5200_connect` with the serial port name (e.g., `COM3`).
2. **Check Status**: Call `mhs5200_get_status` to read the current device settings.
3. **Configure**: Use `mhs5200_set_frequency`, `mhs5200_set_amplitude`, etc. to set the desired output.
4. **Enable Output**: Call `mhs5200_set_output` to turn on the signal.
5. **Disconnect**: Call `mhs5200_disconnect` when finished.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
