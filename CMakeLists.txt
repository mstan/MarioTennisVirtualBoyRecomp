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

set(VBRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/vbrecomp" CACHE PATH "vbrecomp checkout")
set(RECOMP_UI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/recomp-ui" CACHE PATH "Shared UI checkout")
option(MARIO_TENNIS_UI "Build the shared launcher and in-game settings" ON)
if(NOT EXISTS "${VBRECOMP_ROOT}/CMakeLists.txt")
    message(FATAL_ERROR
        "vbrecomp/ subdirectory missing — the framework is a separate "
        "git repo. Clone it into this directory first:\n"
        "  git clone git@github.com:mstan/vbrecomp.git vbrecomp")
endif()

if(MARIO_TENNIS_UI)
    set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "Mario Tennis mod catalog" FORCE)
    include("${RECOMP_UI_ROOT}/recomp_ui.cmake")
endif()
add_subdirectory("${VBRECOMP_ROOT}" vbrecomp)
target_compile_definitions(vb-runtime PRIVATE
    VB_GAME_ID="marios-tennis"
    VB_GAME_TITLE="Mario's Tennis Recompiled"
    VB_GAME_SHA256="5dc5e6b5d5f538f56b3b9727db1c7931d9dfe1bbd0743f698897e0fd90e70101"
    VB_GAME_CRC32=0x7CE7460Du)
set_target_properties(vb-runtime PROPERTIES OUTPUT_NAME MarioTennisVirtualBoyRecomp)
if(MARIO_TENNIS_UI)
    add_custom_target(mario-tennis-assets
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:vb-runtime>/assets/img"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/boxart.tga"
            "$<TARGET_FILE_DIR:vb-runtime>/assets/img/boxart.tga"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/NOTICE.md"
            "$<TARGET_FILE_DIR:vb-runtime>/assets/BOXART-NOTICE.md"
        VERBATIM)
    add_dependencies(vb-runtime mario-tennis-assets)
endif()
target_sources(vb-runtime PRIVATE src/tennis_color.cpp)
include(CTest)
if(BUILD_TESTING)
    add_executable(tennis-materials-test tests/materials_test.cpp)
    target_include_directories(tennis-materials-test PRIVATE src)
    if(MSVC)
        target_compile_options(tennis-materials-test PRIVATE /UNDEBUG)
    else()
        target_compile_options(tennis-materials-test PRIVATE -UNDEBUG)
    endif()
    add_test(NAME tennis-materials COMMAND tennis-materials-test
        "${CMAKE_CURRENT_SOURCE_DIR}/mods/full-color/materials.bin"
        "${CMAKE_CURRENT_BINARY_DIR}/invalid-materials-test.bin"
        "${CMAKE_CURRENT_SOURCE_DIR}/mods/full-color/hud-materials.bin")
endif()

find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
    set(_color_package "${CMAKE_CURRENT_BINARY_DIR}/mod-packages/marios-tennis-full-color-0.2.2.vbmod")
    add_custom_command(OUTPUT "${_color_package}"
        COMMAND "${Python3_EXECUTABLE}" "${VBRECOMP_ROOT}/tools/pack_mod.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/mods/full-color" "${_color_package}"
        DEPENDS mods/full-color/manifest.toml mods/full-color/palette.txt mods/full-color/materials.bin mods/full-color/hud-materials.bin
                "${VBRECOMP_ROOT}/tools/pack_mod.py"
        VERBATIM)
    add_custom_target(mario-tennis-mods DEPENDS "${_color_package}")
endif()
