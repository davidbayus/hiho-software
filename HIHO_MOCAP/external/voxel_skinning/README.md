# Vendored voxel heat diffuse skinning solver

Source: https://github.com/meshonline/Surface-Heat-Diffuse-Skinning
License: MIT (c) 2018 Mingfen Wang — see LICENSE. MIT is AGPL-3.0-compatible.
Despite the repo name, the solver is voxel-grid heat diffusion (robust on
multi-piece meshes). `vhd_mac_universal` compiled 2026-07-01 on macOS from
src/ with: clang++ *.cpp -std=c++11 -O2 -pthread -arch arm64 -arch x86_64
The Python glue in core/voxel_skinning.py is HIHO's own (the upstream
addon wrapper is GPL and was not used).
