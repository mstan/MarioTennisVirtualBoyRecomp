cmake_minimum_required(VERSION 3.20)
project(MarioTennisVirtualBoyRecomp C CXX)

# Top-level project file for the Mario's Tennis (Virtual Boy)
# static-recompiler build. The actual recompiler + runtime live in the
# vbrecomp/ submodule (a separate git repo at mstan/vbrecomp.git); this
# file is just the per-game integration point.
#
# What this file does:
#   1. Sets VBRECOMP_GAME=marios_tennis so the framework's runtime CMake
#      picks up generated/marios_tennis_{full,dispatch}.c and links them
#      into vb-runtime.exe.
#   2. Pulls in the framework via add_subdirectory(vbrecomp). The
#      framework CMake handles vb-runtime + vb-beetle wiring.
#
# What it does NOT do:
#   - Build a beetle-vb static archive. The mednafen-vb-libretro tree is
#     a separate clone under ./beetle-vb/ (gitignored — vendored at clean
#     upstream HEAD per the project-wide submodule rule); see
#     vbrecomp/docs/BRINGUP.md for the one-shot mingw32-make recipe.
#   - Build the Python recompiler. That's a dev-time step:
#       python -m recompiler.cli.vbrecomp_codegen --rom roms/marios_tennis.vb
#       --module marios_tennis --out generated/
#     The generated/ output then becomes a build input for vb-runtime.

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Force the game name so vb-runtime links the Mario's Tennis generated
# dispatch. The framework's CMake accepts other values for users who
# clone the framework separately and target a different cart.
set(VBRECOMP_GAME "marios_tennis" CACHE STRING
    "Module name of a vbrecomp codegen output to link into vb-runtime."
    FORCE)

if(NOT EXISTS "${CMAKE_SOURCE_DIR}/vbrecomp/CMakeLists.txt")
    message(FATAL_ERROR
        "vbrecomp/ subdirectory missing — the framework is a separate "
        "git repo. Clone it into this directory first:\n"
        "  git clone git@github.com:mstan/vbrecomp.git vbrecomp")
endif()

add_subdirectory(vbrecomp)
