Most AI-on-hardware work today still funnels data through files, HTTP endpoints, or remote SSH. We've been exploring the other direction.

**bus-mcp** is a small Model Context Protocol server that runs on a Raspberry Pi (or any Linux SBC) and exposes the platform's actual hardware buses — CAN, RS485, UART, I2C, SPI, GPIO — as tools an AI agent can call directly. The same protocol your coding assistant uses to read source files; pointed at silicon instead.

What that starts to unlock:

→ Motor drives you talk to in plain English. The agent inside the box reads error counters, retunes the bitrate, replays a move — no scope, no test fixture, no glue script.

→ PID loops tuned by describing the symptom. The agent reads encoders over RS485, walks Kp / Ki up and down, captures the response. Iteration time collapses from hours to minutes.

→ Drones, AGVs, and ROVs that report their own diagnostics in plain language, because the agent has live access to every protocol on board.

→ Working-companion robots where the LLM holding the conversation is the same one driving the limbs. No shim between intent and action.

Telemetry stays on the wire. Control stays in the loop. Data never has to leave the device.

We think this is the start of a much larger pattern — agents that live inside the machine they're helping with, where the tool surface is the hardware itself. Open-source, MIT-licensed, running on Pi 4 / 5 / CM5 today, Jetson next.

github.com/Pan-Robotics/bus-mcp

#Robotics #AIagents #ModelContextProtocol #EdgeAI #Embedded
