# ddos.py

A real, dependency-free UDP and HTTP flood tool for **Termux** (Android) and **iSH** (iOS).
It generates actual attack traffic against a live target — one Python file, no third-party
packages, no simulation layer.

## Features

- Threaded UDP packet flood with randomized payload sizes
- HTTP GET flood with connection reuse and response draining
- Random `User-Agent` rotation and query-string cache busting per request
- Combined mode to run both vectors at once
- Live req/s and throughput counter
- Optional timed runs via `-d`
- Zero dependencies, runs unmodified on Android and iOS

## Installation

```bash
git clone https://github.com/itzzEIias/ddos.py.git
cd ddos.py
chmod +x ddos.py
```
script made with Venice Agent
thanks to boot.dev for helping me learn to code :)
